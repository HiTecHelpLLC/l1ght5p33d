"""Exercise the downloaded-pack -> human review -> real browser boundary."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from starlette.testclient import TestClient
from test_packs import SyntheticLibrary

from l1ght5p33d import packs
from l1ght5p33d.examples import browser_workflow
from l1ght5p33d.fixtures.creative import serve_creative_fixture
from l1ght5p33d.mcp_server import create_app
from l1ght5p33d.policy import PermissionDenied, Policy
from l1ght5p33d.service import WorkflowService, write_json


@pytest.fixture
def setup_service(tmp_path, monkeypatch):
    library = SyntheticLibrary()
    now = datetime.now(UTC)
    library.claims["issued_at"] = (now - timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    library.claims["expires_at"] = (now + timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    library.publish()
    monkeypatch.setattr(
        packs,
        "THEBEST_PUBLIC_KEY_HEX",
        library.key.public_key().public_bytes_raw().hex(),
    )
    root = tmp_path / "authored"
    root.mkdir()
    service = WorkflowService(root, Policy(), state_root=tmp_path / "state")
    service.companion.source = packs.CuratedPackSource(fetcher=library.get)
    yield service, library
    service.shutdown()


def test_download_reuses_exact_pack_offline_without_refreshing_inactivity(
    setup_service,
):
    service, library = setup_service
    first = service.prepare_task("poster-demo", "0.1.0")
    assert first["status"] == "awaiting_approval"
    assert not first["download"]["cache_hit"]
    calls = list(library.calls)
    second = service.prepare_task("poster-demo", "0.1.0")
    assert second["download"]["cache_hit"]
    assert library.calls == calls
    assert not service.runs
    entry = service.get_cache_status()["entries"][0]
    assert entry["last_used_at"] is None
    assert entry["expires_at"] - entry["downloaded_at"] == 90 * 86400
    assert first["plan"]["workflow_review"]["execution_approved"] is False
    assert second["review_token"] != first["review_token"]


def test_review_token_and_digest_bind_edits_to_fresh_approval(setup_service):
    service, _ = setup_service
    plan = service.prepare_task("poster-demo", "0.1.0")
    with pytest.raises(PermissionDenied):
        service.get_review_plan(plan["plan_id"], "x" * 40)
    with pytest.raises(ValueError, match="changed"):
        service.update_review_variables(
            plan["plan_id"],
            plan["review_token"],
            {"title": "New"},
            expected_digest="f" * 64,
        )
    fresh = service.update_review_variables(
        plan["plan_id"],
        plan["review_token"],
        {"title": "New"},
        expected_digest=plan["plan"]["plan_digest"],
    )
    assert fresh["plan"]["variables"]["title"] == "New"
    with pytest.raises(PermissionDenied):
        service.get_review_plan(plan["plan_id"], plan["review_token"])
    assert service.get_task_status(fresh["plan_id"])["execution"] is None
    assert not service.runs


def test_edit_preserves_signed_pack_and_removes_qualification_from_local_copy(
    setup_service,
):
    service, _ = setup_service
    plan = service.prepare_task("poster-demo", "0.1.0")
    original = service._path("poster-demo")
    before = original.read_bytes()
    modified = json.loads(before)
    modified["workflow"]["params"]["title"] = "My local design"
    fresh = service.update_review_workflow(
        plan["plan_id"],
        plan["review_token"],
        json.dumps(modified),
        plan["plan"]["plan_digest"],
    )
    assert original.read_bytes() == before
    assert service._path("poster-demo").parent == service.root
    assert "workflow_review" not in fresh["plan"]
    assert fresh["status"] == "awaiting_approval"
    assert not service.runs
    service.companion.cache._clock = lambda: time.time() + 200 * 86400
    service.companion.cleanup()
    assert service._path("poster-demo").exists()
    assert list((service.state_root / "originals").glob("*.json"))


def test_authored_id_collision_and_expired_attestation_fail_closed(setup_service):
    service, library = setup_service
    write_json(service.root / "mine.json", library.workflow)
    with pytest.raises(ValueError, match="local workflow"):
        service.prepare_task("poster-demo", "0.1.0")
    (service.root / "mine.json").unlink()
    plan = service.prepare_task("poster-demo", "0.1.0")
    original_verify = packs.verify_pack

    def expired(*args, **kwargs):
        return original_verify(
            *args, **kwargs, now=datetime.now(UTC) + timedelta(days=100)
        )

    from unittest.mock import patch

    with patch("l1ght5p33d.companion.verify_pack", expired):
        with pytest.raises(ValueError, match="expired"):
            service.approve_review_plan(
                plan["plan_id"], plan["review_token"], plan["plan"]["plan_digest"]
            )
    assert not service.runs


def test_stale_editor_cannot_overwrite_a_newer_local_change(setup_service):
    service, library = setup_service
    local = service.root / "mine.json"
    write_json(local, library.workflow)
    plan = service.companion.issue_review(service.prepare_workflow_run("poster-demo"))
    stale_content = local.read_text("ascii")
    newer = json.loads(stale_content)
    newer["description"] = "A newer local edit"
    write_json(local, newer)
    with pytest.raises(PermissionDenied, match="changed"):
        service.get_review_plan(plan["plan_id"], plan["review_token"])
    with pytest.raises(PermissionDenied, match="changed"):
        service.update_review_workflow(
            plan["plan_id"],
            plan["review_token"],
            stale_content,
            plan["plan"]["plan_digest"],
        )
    assert json.loads(local.read_text("ascii"))["description"] == newer["description"]


def test_failed_cache_use_record_never_launches_a_provider(setup_service, monkeypatch):
    service, _ = setup_service
    plan = service.prepare_task("poster-demo", "0.1.0")
    calls = []
    monkeypatch.setattr(service, "_provider", lambda doc: calls.append(doc))

    def fail(key):
        raise OSError("Synthetic unavailable cache")

    monkeypatch.setattr(service.companion.cache, "touch", fail)
    with pytest.raises(OSError):
        service.approve_review_plan(
            plan["plan_id"], plan["review_token"], plan["plan"]["plan_digest"]
        )
    assert not calls and not service.runs


def test_real_browser_download_review_approval_and_independent_saved_state(
    setup_service,
):
    service, library = setup_service
    with serve_creative_fixture(port=7332) as url:
        library.workflow = browser_workflow(url)
        library.metadata["summary"] = library.workflow["description"]
        library.metadata["application"]["configuration"] = library.workflow[
            "configuration"
        ]
        library.metadata["defaults"] = library.workflow["workflow"]["params"]
        library.metadata["reviewed_steps"] = [
            {
                "id": step["id"],
                "intent": step["intent"],
                "provider": "browser",
                "operation": step["api_binding"]["method"],
                "arguments": step["api_binding"]["body_template"],
                "effects": step["api_binding"]["effects"],
            }
            for step in library.workflow["workflow"]["steps"]
        ]
        library.evidence["steps_verified"] = 3
        library.publish()
        app = create_app(service, "s" * 40)
        with TestClient(app, base_url="http://127.0.0.1:7331") as client:
            plan = service.prepare_task(
                "poster-demo", "0.1.0", {"title": "Download, review, create"}
            )
            link = urlsplit(plan["review_url"])
            page = client.get(link.path + "?" + link.query)
            assert page.status_code == 200, page.text
            assert "Approve and run" in page.text
            assert "Edit workflow steps" in page.text
            assert not service.runs
            data = {
                "review_token": plan["review_token"],
                "expected_digest": plan["plan"]["plan_digest"],
            }
            # MCP bearer and GET cannot substitute for the local form capability.
            assert client.post(link.path + "/approve", data=data).status_code == 403
            response = client.post(
                link.path + "/approve",
                data=data,
                headers={"Origin": "http://127.0.0.1:7331"},
            )
            assert response.status_code == 200, response.text
            assert len(service.runs) == 1
            run = next(iter(service.runs.values()))
            entry = service.get_cache_status()["entries"][0]
            assert entry["last_used_at"] is not None
            # An active run holds a lease even after the review lease is released.
            service.companion.cache._clock = lambda: time.time() + 200 * 86400
            if not run["done"]:
                service.companion.cleanup()
                assert Path(entry["workflow_path"]).exists()
            run["thread"].join(30)
            assert run["done"]
            assert run["status"] == "completed_ui_verified", run.get("diagnostic")
            assert httpx.get(url + "/state").json() == {
                "poster_title": "Download, review, create",
                "palette": "Sunset",
            }
            receipts = service.get_execution_log(run["run_id"])
            assert len(receipts) == 3
            assert all(r["result"] == "verified" for r in receipts)
            assert receipts[-1]["fallback_used"]
            assert service.get_task_status(plan["plan_id"])["execution"]["done"]
            again = client.post(
                link.path + "/approve",
                data=data,
                headers={"Origin": "http://127.0.0.1:7331"},
            )
            assert again.status_code in {403, 409}
            assert len(service.runs) == 1
            service.companion.cleanup()
            assert not Path(entry["workflow_path"]).exists()
            assert (run["directory"] / "approved-plan.json").is_file()
            assert (run["directory"] / "receipts.jsonl").is_file()
