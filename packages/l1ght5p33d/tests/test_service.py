from __future__ import annotations

import io
import json
import time

import httpx
import pytest
from starlette.testclient import TestClient

from l1ght5p33d.examples import browser_workflow
from l1ght5p33d.fixtures.creative import serve_creative_fixture
from l1ght5p33d.mcp_server import create_app, run_json_rpc
from l1ght5p33d.policy import PermissionDenied, Policy, digest, redact
from l1ght5p33d.service import WorkflowService, write_json
from l1ght5p33d.workflow import load_workflow, validate_document


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail("Timed out waiting for execution boundary")


def approved_policy(data):
    return Policy(approved_workflow_digests=[digest(validate_document(data))])


def test_policy_paths_and_origins(tmp_path):
    allowed = tmp_path / "assets"
    allowed.mkdir()
    media = allowed / "a.mid"
    media.write_bytes(b"synthetic")
    policy = Policy(read_roots=[str(allowed)])
    assert policy.path(media) == media
    with pytest.raises(PermissionDenied):
        policy.path(__file__)
    with pytest.raises(PermissionDenied):
        policy.url("https://example.com")
    with pytest.raises(PermissionDenied):
        policy.url("http://user:pass@localhost")
    with pytest.raises(PermissionDenied):
        policy.action("browser", "evaluate", {})


def test_nested_configuration_cannot_evade_live_approval():
    data = browser_workflow("https://example.com")
    data["configuration"] = {"browser": data["configuration"]}
    policy = Policy(allowed_origins=["https://example.com"])
    doc = validate_document(data)
    with pytest.raises(PermissionDenied, match="exact digest"):
        policy.check_workflow(doc)
    policy.approved_workflow_digests.append(digest(doc))
    policy.check_workflow(doc)


def test_patch_is_validated_diffed_and_preserves_original(tmp_path):
    path = tmp_path / "poster.json"
    write_json(path, browser_workflow("http://127.0.0.1:9999"))
    before = path.read_bytes()
    service = WorkflowService(
        tmp_path, approved_policy(json.loads(before)), state_root=tmp_path / "state"
    )
    data = json.loads(before)
    data["description"] = "Edited description"
    patch = service.propose_workflow_patch("poster-demo", json.dumps(data))
    assert "Edited description" in patch["diff"]
    assert path.read_bytes() == before
    assert service.approve_workflow_patch(patch["patch_id"])["original_preserved"]
    service.validate_workflow("poster-demo")  # metadata-only approval carries forward
    assert (
        tmp_path / "state" / "originals" / f"{patch['patch_id']}.json"
    ).read_bytes() == before
    data["workflow"]["steps"][0]["api_binding"]["effects"] = []
    with pytest.raises(ValueError):
        service.propose_workflow_patch("poster-demo", json.dumps(data))


def test_config_patch_needs_local_operator(tmp_path):
    data = browser_workflow("http://127.0.0.1:9999")
    write_json(tmp_path / "poster.json", data)
    service = WorkflowService(tmp_path, Policy(), state_root=tmp_path / "state")
    data["configuration"]["url"] = "http://127.0.0.1:9998"
    patch = service.propose_workflow_patch("poster-demo", json.dumps(data))
    with pytest.raises(PermissionDenied):
        service.approve_workflow_patch(patch["patch_id"])


def test_executable_patch_needs_local_operator_and_persists(tmp_path):
    data = browser_workflow("http://127.0.0.1:9999")
    path = tmp_path / "poster.json"
    write_json(path, data)
    before = path.read_bytes()
    policy = approved_policy(data)
    service = WorkflowService(tmp_path, policy, state_root=tmp_path / "state")
    data["workflow"]["steps"][-1]["api_binding"]["body_template"]["selectors"] = [
        {"kind": "role", "role": "button", "name": "A different action"}
    ]
    patch = service.propose_workflow_patch("poster-demo", json.dumps(data))
    assert patch["requires_local_approval"]
    with pytest.raises(PermissionDenied):
        service.approve_workflow_patch(patch["patch_id"])
    assert path.read_bytes() == before
    restarted = WorkflowService(tmp_path, policy, state_root=tmp_path / "state")
    assert restarted.approve_workflow_patch(patch["patch_id"], local_operator=True)[
        "approved"
    ]
    restarted.validate_workflow("poster-demo")


def test_metadata_patch_cannot_approve_previously_unapproved_actions(tmp_path):
    data = browser_workflow("http://127.0.0.1:9999")
    path = tmp_path / "poster.json"
    write_json(path, data)
    before = path.read_bytes()
    service = WorkflowService(tmp_path, Policy(), state_root=tmp_path / "state")
    data["description"] = "Changed description"
    patch = service.propose_workflow_patch("poster-demo", json.dumps(data))
    assert not patch["requires_local_approval"]
    with pytest.raises(PermissionDenied, match="exact digest"):
        service.approve_workflow_patch(patch["patch_id"])
    assert path.read_bytes() == before


def test_redaction():
    assert redact({"token": "abc", "message": "secret abc"}, ("abc",)) == {
        "token": "[REDACTED]",
        "message": "secret [REDACTED]",
    }


def test_mcp_requires_token_and_defends_origin(tmp_path):
    write_json(tmp_path / "poster.json", browser_workflow("http://127.0.0.1:9999"))
    service = WorkflowService(tmp_path, Policy(), state_root=tmp_path / "state")
    token = "x" * 40
    app = create_app(service, token)
    with TestClient(app, base_url="http://127.0.0.1:7331") as client:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert client.post("/mcp", json=body).status_code == 401
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }
        assert (
            client.post(
                "/mcp", json=body, headers={**headers, "Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/mcp", json=body, headers={**headers, "Host": "evil.example"}
            ).status_code
            == 403
        )
        response = client.post("/mcp", json=body, headers=headers)
        assert response.status_code == 200, response.text
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        assert len(names) == 16
        assert {"run_workflow", "run_step", "approve_workflow_patch"} <= names
        result = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_workflows", "arguments": {}},
            },
            headers=headers,
        )
        assert "poster-demo" in result.text
    assert service._shutting_down


@pytest.mark.browser
def test_browser_service_step_resume_and_verified_fallback(tmp_path):
    with serve_creative_fixture() as url:
        path = tmp_path / "poster.json"
        data = browser_workflow(url)
        write_json(path, data)
        service = WorkflowService(
            tmp_path, approved_policy(data), state_root=tmp_path / "state"
        )
        run = service.run_workflow("poster-demo", step_mode=True)
        run_id = run["run_id"]
        wait_until(
            lambda: (
                service.get_execution_status(run_id)["control"]["current_step"]
                == "name_poster"
            )
        )
        assert service.get_execution_log(run_id) == []
        service.run_step(run_id)
        wait_until(lambda: len(service.get_execution_log(run_id)) == 1)
        assert service.get_execution_status(run_id)["control"]["pause_requested"]
        service.resume_workflow(run_id)
        wait_until(lambda: service.get_execution_status(run_id)["done"])
        status = service.get_execution_status(run_id)
        assert status["status"] == "completed_ui_verified", status
        receipts = service.get_execution_log(run_id)
        assert [r["step_id"] for r in receipts] == [
            "name_poster",
            "choose_palette",
            "save_poster",
        ]
        assert receipts[-1]["fallback_used"]
        assert all(receipt["checkpoint_created"] for receipt in receipts)
        assert service.abort_workflow(run_id)["state"] == "finished"
        assert service.get_execution_status(run_id)["status"] == "completed_ui_verified"
        assert service.inspect_ui_state(run_id)["screenshots"] == []
        saved = httpx.get(url + "/state", trust_env=False).json()
        assert saved == {
            "poster_title": "Make something wonderful",
            "palette": "Sunset",
        }
        assert (
            len(
                (tmp_path / "state" / "runs" / run_id / "receipts.jsonl")
                .read_text()
                .splitlines()
            )
            == 3
        )


def test_dry_run_has_no_provider_side_effects(tmp_path):
    data = browser_workflow("http://127.0.0.1:1")
    write_json(tmp_path / "poster.json", data)
    service = WorkflowService(
        tmp_path, approved_policy(data), state_root=tmp_path / "state"
    )
    result = service.run_workflow("poster-demo", dry_run=True)
    assert result["actions_delivered"] == 0
    assert service.runs == {}
    assert digest(load_workflow(tmp_path / "poster.json")) == digest(
        load_workflow(tmp_path / "poster.json")
    )


def test_credentials_cannot_enter_managed_variables_or_native_bundle(tmp_path):
    data = browser_workflow("http://127.0.0.1:1")
    path = tmp_path / "poster.json"
    write_json(path, data)
    service = WorkflowService(
        tmp_path, approved_policy(data), state_root=tmp_path / "state"
    )
    with pytest.raises(ValueError, match="Credential parameters"):
        service.set_workflow_variables(
            "poster-demo", {"api_token": "private-credential"}
        )
    assert service.variables == {}
    data["workflow"]["params"]["api_token"] = "private-credential"
    with pytest.raises(ValueError, match="Credential parameters"):
        service.propose_workflow_patch("poster-demo", json.dumps(data))
    assert "private-credential" not in path.read_text("ascii")
    # Even an in-process caller bypassing set_workflow_variables is refused
    # before the native engine writes plaintext params or a workflow bundle.
    service.variables["poster-demo"] = {"api_token": "private-credential"}
    run_id = service.run_workflow("poster-demo")["run_id"]
    wait_until(lambda: service.get_execution_status(run_id)["done"])
    assert service.get_execution_status(run_id)["status"] == "halted"
    assert not (tmp_path / "state" / "runs" / run_id / "bundle").exists()
    assert not (tmp_path / "state" / "runs" / run_id / "flow").exists()
    for artifact in (tmp_path / "state").rglob("*.json"):
        assert "private-credential" not in artifact.read_text("ascii")


def test_secondary_snapshot_failure_keeps_verified_action_and_stale_state(
    tmp_path, monkeypatch
):
    class Provider:
        name = "browser"
        operations = frozenset({"fill"})
        effect_tier = 4

        def __init__(self):
            self.inspections = 0
            self.deliveries = 0
            self.state = {"poster_title": ""}

        def inspect(self):
            self.inspections += 1
            if self.inspections == 4:
                raise RuntimeError("Snapshot unavailable after effect verification")
            return dict(self.state)

        def execute(self, operation, args):
            self.deliveries += 1
            self.state["poster_title"] = args["text"]
            return {"selector_method": "label"}

        def close(self):
            pass

    data = browser_workflow("http://127.0.0.1:1")
    data["workflow"]["steps"] = data["workflow"]["steps"][:1]
    data["configuration"]["manual_review"] = ["Instrument classification is heuristic"]
    write_json(tmp_path / "poster.json", data)
    service = WorkflowService(
        tmp_path, approved_policy(data), state_root=tmp_path / "state"
    )
    provider = Provider()
    monkeypatch.setattr(service, "_provider", lambda _doc: provider)
    run_id = service.run_workflow("poster-demo")["run_id"]
    wait_until(lambda: service.get_execution_status(run_id)["done"])
    status = service.get_execution_status(run_id)
    assert status["status"] == "completed_ui_verified", status
    assert status["manual_review"] == ["Instrument classification is heuristic"]
    assert provider.deliveries == 1
    assert service.inspect_ui_state(run_id)["stale"]
    assert service.get_execution_log(run_id)[0]["checkpoint_created"]


def test_rpc_eof_cancels_paused_run_and_closes_provider(tmp_path, monkeypatch):
    from types import SimpleNamespace

    delivered = []
    closed = []
    provider = SimpleNamespace(
        name="browser",
        effect_tier=4,
        operations=frozenset({"fill", "select", "click"}),
        inspect=lambda: {"poster_title": ""},
        execute=lambda *args: delivered.append(args),
        close=lambda: closed.append(True),
    )
    data = browser_workflow("http://127.0.0.1:1")
    write_json(tmp_path / "poster.json", data)
    service = WorkflowService(
        tmp_path, approved_policy(data), state_root=tmp_path / "state"
    )
    monkeypatch.setattr(service, "_provider", lambda _doc: provider)
    run_id = service.run_workflow("poster-demo", step_mode=True)["run_id"]
    wait_until(lambda: service.get_execution_status(run_id)["control"]["current_step"])
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    run_json_rpc(service)
    status = service.get_execution_status(run_id)
    assert status["status"] == "aborted", status
    assert status["done"]
    assert delivered == []
    assert closed == [True]
    with pytest.raises(RuntimeError, match="shutting down"):
        service.run_workflow("poster-demo")
