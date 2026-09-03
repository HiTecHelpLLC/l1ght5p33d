"""Approval is checked before any provider is created, even with old grants."""

from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

from l1ght5p33d.approvals import RunPlanStore
from l1ght5p33d.cli import main
from l1ght5p33d.examples import browser_workflow
from l1ght5p33d.mcp_server import create_app, run_json_rpc
from l1ght5p33d.policy import PermissionDenied, Policy, digest
from l1ght5p33d.service import WorkflowService, write_json
from l1ght5p33d.workflow import validate_document


def service_at(tmp_path, monkeypatch):
    data = browser_workflow("http://127.0.0.1:9999")
    write_json(tmp_path / "poster.json", data)
    policy = Policy(approved_workflow_digests=[digest(validate_document(data))])
    service = WorkflowService(tmp_path, policy, state_root=tmp_path / "state")
    calls = []

    def provider(doc):
        calls.append(doc.id)
        raise AssertionError("A rejected plan must not construct a provider")

    monkeypatch.setattr(service, "_provider", provider)
    return service, calls


def approve(service):
    plan = service.prepare_workflow_run("poster-demo")
    service.approve_run_plan(
        plan["plan_id"], plan["plan"]["plan_digest"], local_operator=True
    )
    return plan


def test_old_workflow_grant_cannot_start_unreviewed_run(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    plan = service.run_workflow("poster-demo", step_mode=True)
    assert plan["status"] == "awaiting_approval"
    assert plan["actions_delivered"] == 0
    assert not calls and not service.runs
    with pytest.raises(PermissionDenied, match="human approval"):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    with pytest.raises(PermissionDenied, match="local human"):
        service.approve_run_plan(plan["plan_id"], plan["plan"]["plan_digest"])


def test_validation_without_execution_grant_sends_no_input(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    service.policy.approved_workflow_digests.clear()
    assert service.validate_workflow("poster-demo")["valid"]
    assert service.run_workflow("poster-demo")["status"] == "awaiting_approval"
    assert not calls and not service.runs


@pytest.mark.parametrize("changed", ["variables", "workflow", "policy"])
def test_changes_invalidate_approval_before_provider(tmp_path, monkeypatch, changed):
    service, calls = service_at(tmp_path, monkeypatch)
    plan = approve(service)
    if changed == "variables":
        service.set_workflow_variables("poster-demo", {"title": "A different request"})
    elif changed == "policy":
        service.policy.max_steps -= 1
    else:
        path = tmp_path / "poster.json"
        data = json.loads(path.read_text("ascii"))
        data["description"] = "A changed description also needs review"
        write_json(path, data)
    with pytest.raises(PermissionDenied):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    assert not calls and not service.runs


def test_file_content_change_invalidates_plan(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    media = tmp_path / "input.mid"
    media.write_bytes(b"original")
    path = tmp_path / "poster.json"
    data = json.loads(path.read_text("ascii"))
    data["workflow"]["steps"][0]["api_binding"]["body_template"]["file"] = str(media)
    write_json(path, data)
    service.policy.read_roots = [str(tmp_path)]
    plan = approve(service)
    media.write_bytes(b"replaced")
    with pytest.raises(PermissionDenied):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    assert not calls


def test_unresolved_values_cannot_be_approved_or_open_a_provider(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    path = tmp_path / "poster.json"
    data = json.loads(path.read_text("ascii"))
    data["workflow"]["params"] = {}
    data["workflow"]["param_specs"] = {"title": {"name": "title", "required": False}}
    write_json(path, data)
    plan = service.prepare_workflow_run("poster-demo")
    assert plan["status"] == "blocked"
    with pytest.raises(PermissionDenied, match="Unresolved"):
        service.approve_run_plan(
            plan["plan_id"], plan["plan"]["plan_digest"], local_operator=True
        )
    with pytest.raises(PermissionDenied, match="Unresolved"):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    assert not calls


def test_visual_template_change_invalidates_review(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    template = tmp_path / "anchor.png"
    template.write_bytes(b"original synthetic template bytes")
    path = tmp_path / "poster.json"
    data = json.loads(path.read_text("ascii"))
    data["configuration"]["template_root"] = str(tmp_path)
    data["workflow"]["steps"][0]["api_binding"]["body_template"]["selectors"] = [
        {"method": "template", "template": "anchor.png"}
    ]
    write_json(path, data)
    service.policy.read_roots = [str(tmp_path)]
    plan = approve(service)
    assert plan["plan"]["input_files"][0]["path"] == str(template)
    template.write_bytes(b"different template changes which target matches")
    with pytest.raises(PermissionDenied):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    assert not calls


def test_resolved_file_braces_are_not_interpreted_again(tmp_path, monkeypatch):
    service, _ = service_at(tmp_path, monkeypatch)
    media = tmp_path / "{take}.mid"
    media.write_bytes(b"synthetic")
    service.policy.read_roots = [str(tmp_path)]
    doc = validate_document(browser_workflow("http://127.0.0.1:9999"))
    assert service._input_files(doc, {}, arguments={"file": str(media)})[0][
        "path"
    ] == str(media)


def test_corrupt_displayed_plan_is_detected(tmp_path, monkeypatch):
    service, _ = service_at(tmp_path, monkeypatch)
    plan = service.prepare_workflow_run("poster-demo")
    record = service.plans.read(plan["plan_id"])
    record["plan"]["steps"] = []
    write_json(service.plans._path(plan["plan_id"]), record)
    with pytest.raises(PermissionDenied, match="review content changed"):
        service.get_run_plan(plan["plan_id"])


def test_local_review_cannot_approve_changed_display(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    plan = service.prepare_workflow_run("poster-demo")
    service.policy.allowed_origins.append("https://another.example")
    with pytest.raises(PermissionDenied, match="changed"):
        service.approve_run_plan(
            plan["plan_id"], plan["plan"]["plan_digest"], local_operator=True
        )
    assert service.get_run_plan(plan["plan_id"])["status"] == "awaiting_approval"
    assert not calls


def test_expired_approval_refuses_before_provider(tmp_path, monkeypatch):
    service, calls = service_at(tmp_path, monkeypatch)
    plan = approve(service)
    record = service.plans.read(plan["plan_id"])
    record["expires_at"] = 0
    write_json(service.plans._path(plan["plan_id"]), record)
    with pytest.raises(PermissionDenied, match="unexpired"):
        service.run_workflow("poster-demo", plan_id=plan["plan_id"])
    assert not calls


def test_single_use_claim_is_atomic_across_services(tmp_path):
    first, second = RunPlanStore(tmp_path), RunPlanStore(tmp_path)
    plan_hash = digest({"workflow_id": "test"})
    plan = first.prepare(
        {"workflow_id": "test", "plan_digest": plan_hash}, tmp_path, {}
    )
    first.approve(plan["plan_id"], plan_hash)

    def claim(store):
        try:
            store.consume(plan["plan_id"], plan_hash)
            return True
        except PermissionDenied:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(claim, [first, second])) == [False, True]


@pytest.mark.parametrize("interactive,answer", [(False, "APPROVE"), (True, "no")])
def test_cli_never_grants_before_confirmation(
    tmp_path, monkeypatch, capsys, interactive, answer
):
    path = tmp_path / "workflow.json"
    policy_path = tmp_path / "policy.json"
    write_json(path, browser_workflow("https://example.com"))
    write_json(policy_path, Policy().model_dump(mode="json"))
    before = policy_path.read_bytes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: interactive)
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    assert main(["approve-workflow", str(path), "--policy", str(policy_path)]) == 2
    assert policy_path.read_bytes() == before
    assert "example.com" in capsys.readouterr().out


def test_rpc_cannot_approve_or_change_catalog_trust(tmp_path, monkeypatch, capsys):
    service, calls = service_at(tmp_path, monkeypatch)
    methods = ["approve_run_plan", "configure_registry"]
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            "\n".join(
                json.dumps({"jsonrpc": "2.0", "id": i, "method": name})
                for i, name in enumerate(methods)
            )
        ),
    )
    run_json_rpc(service)
    responses = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert all("error" in row for row in responses)
    assert not calls


def test_mcp_exposes_discovery_and_plan_but_no_self_approval(tmp_path, monkeypatch):
    service, _ = service_at(tmp_path, monkeypatch)
    token = "p" * 32
    with TestClient(
        create_app(service, token), base_url="http://127.0.0.1:7331"
    ) as client:
        result = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        names = {tool["name"] for tool in result.json()["result"]["tools"]}
    assert {
        "search_workflow_catalog",
        "download_workflow",
        "prepare_workflow_run",
        "get_run_plan",
    } <= names
    assert "approve_run_plan" not in names
