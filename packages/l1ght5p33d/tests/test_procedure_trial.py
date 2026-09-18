"""Synthetic operator approval is confined to this local fixture test harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest

from l1ght5p33d.examples import browser_workflow
from l1ght5p33d.fixtures.creative import serve_creative_fixture
from l1ght5p33d.policy import Policy
from l1ght5p33d.service import WorkflowService, write_json


@pytest.mark.browser
@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_saved_poster_procedure(tmp_path: Path, attempt: int) -> None:
    expected = {"poster_title": f"Create at lightspeed {attempt}", "palette": "Sunset"}
    output = tmp_path / "saved"
    started = time.perf_counter()
    with serve_creative_fixture(output_dir=output) as url:
        document = browser_workflow(url)
        document["workflow"]["params"]["title"] = expected["poster_title"]
        workflows = tmp_path / "workflows"
        workflows.mkdir()
        path = workflows / "poster.json"
        write_json(path, document)
        path.read_bytes().decode("ascii")
        service = WorkflowService(workflows, Policy(), state_root=tmp_path / "state")
        try:
            plan = service.prepare_workflow_run("poster-demo")
            # Test-only synthetic consent, not evidence of human approval.
            service.approve_run_plan(
                plan["plan_id"], plan["plan"]["plan_digest"], local_operator=True
            )
            run_started = time.perf_counter()
            run = service.run_workflow("poster-demo", plan_id=plan["plan_id"])
            run_id = run["run_id"]
            deadline = time.monotonic() + 30
            while not service.get_execution_status(run_id)["done"]:
                if time.monotonic() >= deadline:
                    service.abort_workflow(run_id)
                    pytest.fail("Procedure exceeded its 30-second execution bound")
                time.sleep(0.02)
            elapsed = time.perf_counter() - run_started
            status = service.get_execution_status(run_id)
            receipts = service.get_execution_log(run_id)
            assert status["status"] == "completed_ui_verified", status
            assert len(receipts) == 3
            assert all(row["result"] == "verified" for row in receipts)
            assert receipts[-1]["fallback_used"]
            assert httpx.get(url + "/state", trust_env=False).json() == expected
        finally:
            service.shutdown()
    # Independent file verification AFTER the browser and fixture have stopped.
    assert json.loads((output / "poster.json").read_text()) == expected
    svg = ElementTree.parse(output / "poster.svg")
    assert svg.find("{http://www.w3.org/2000/svg}text").text == expected["poster_title"]
    report = {
        "scope": "synthetic local fixture; not a live application qualification",
        "approval": "test harness synthetic consent",
        "attempt": attempt,
        "execution_seconds": round(elapsed, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "verified_steps": len(receipts),
        "declared_fallback_used": receipts[-1]["fallback_used"],
        "independent_disk_verification": True,
        "run_id": run_id,
    }
    write_json(tmp_path / "measurement.json", report)
    print(json.dumps(report))


def test_fixture_rejects_invalid_save(tmp_path: Path) -> None:
    with serve_creative_fixture(output_dir=tmp_path) as url:
        result = httpx.post(
            url + "/save",
            json={"poster_title": "Test", "palette": "Invalid"},
            trust_env=False,
        )
        assert result.status_code == 400
        assert httpx.get(url + "/state", trust_env=False).json() == {}
    assert not (tmp_path / "poster.json").exists()
