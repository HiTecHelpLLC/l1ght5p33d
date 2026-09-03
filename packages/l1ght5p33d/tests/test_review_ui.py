from __future__ import annotations

import copy
import json

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from l1ght5p33d.policy import PermissionDenied
from l1ght5p33d.review_ui import create_review_app

PLAN_ID = "a" * 32
TOKEN = "b" * 43
DIGEST = "c" * 64
BASE = "http://127.0.0.1:7331"
PATH = f"/review/{PLAN_ID}"


class FakeService:
    def __init__(self):
        self.approvals = []
        self.edits = []
        self.workflow_edits = []
        self.expired = False
        self.changed = False
        self.used = False
        self.record = {
            "plan_id": PLAN_ID,
            "status": "awaiting_approval",
            "expires_at": "2026-09-03T23:59:00Z",
            "workflow_content": '{"description": "</textarea><script>alert(1)</script>"}',
            "plan": {
                "plan_digest": DIGEST,
                "workflow_id": "poster",
                "application": "browser",
                "author_metadata": {
                    "description": '<img src=x onerror="alert(1)">Read only',
                },
                "variables": {"title": "My poster"},
                "targets": {"url": "http://127.0.0.1:1234"},
                "steps": [
                    {
                        "provider": "browser",
                        "operation": "click",
                        "arguments": {"selectors": [{"name": "Save poster"}]},
                        "effects": [{"field": "saved", "value": {"literal": True}}],
                    }
                ],
                "input_files": [{"path": "C:/art/input.png", "sha256": "d" * 64}],
                "provider_lifecycle": {
                    "startup": "Open browser",
                    "cleanup": "Close browser",
                },
                "control_flow": {"note": "Guards may skip actions or halt"},
                "review_blockers": [],
                "workflow_review": {
                    "source": "community",
                    "qualification": "fixture only",
                },
            },
        }

    def get_review_plan(self, plan_id, review_token):
        if (
            plan_id != PLAN_ID
            or review_token != TOKEN
            or self.expired
            or (self.used and "execution" not in self.record)
        ):
            raise PermissionDenied("Invalid or expired capability")
        return copy.deepcopy(self.record)

    def approve_review_plan(self, plan_id, review_token, expected_digest):
        self.get_review_plan(plan_id, review_token)
        if self.changed or expected_digest != DIGEST or self.used:
            raise PermissionDenied("Workflow changed since preview")
        if self.record["plan"]["review_blockers"]:
            raise PermissionDenied("Unresolved values")
        self.approvals.append((plan_id, expected_digest))
        self.used = True
        self.record["execution"] = {
            "run_id": "e" * 32,
            "status": "starting",
            "done": False,
            "completed_steps": 0,
            "error": None,
            "manual_review": [],
        }
        return {"run_id": "e" * 32, "status": "starting"}

    def update_review_variables(
        self, plan_id, review_token, variables, *, expected_digest=None
    ):
        self.get_review_plan(plan_id, review_token)
        if self.changed or expected_digest != DIGEST:
            raise PermissionDenied("Workflow changed since preview")
        self.edits.append(variables)
        self.used = True
        return {
            "plan_id": "f" * 32,
            "review_token": "g" * 43,
            "review_url": "https://evil.example/ignored",
        }

    def update_review_workflow(self, plan_id, review_token, content, expected_digest):
        self.get_review_plan(plan_id, review_token)
        if self.changed or expected_digest != DIGEST:
            raise PermissionDenied("Workflow changed since preview")
        self.workflow_edits.append(content)
        self.used = True
        return {"plan_id": "f" * 32, "review_token": "g" * 43}


@pytest.fixture
def review():
    service = FakeService()
    app = Starlette(routes=[Mount("/review", create_review_app(service))])
    with TestClient(app, base_url=BASE) as client:
        yield service, client


def fields(**extra):
    return {"review_token": TOKEN, "expected_digest": DIGEST, **extra}


def test_get_is_read_only_escaped_and_complete_details_optional(review):
    service, client = review
    response = client.get(PATH, params={"review_token": TOKEN})
    assert response.status_code == 200
    assert service.approvals == []
    assert "<img src=x" not in response.text
    assert "&lt;img src=x" in response.text
    assert "All 1 steps and expected effects" in response.text
    assert "<details open" not in response.text
    assert "Save poster" in response.text
    assert "Expected results" in response.text
    assert "saved" in response.text
    assert "C:/art/input.png" in response.text
    assert "fixture only" in response.text
    assert "Source, curator review and test scope" in response.text
    assert "Approve and run" in response.text
    assert "read raw JSON to continue" in response.text
    assert "Edit workflow steps" in response.text
    assert "Save local copy and update preview" in response.text
    assert "signature remains attached to the original" in response.text
    assert "</textarea><script>" not in response.text
    assert "&lt;/textarea&gt;&lt;script&gt;" in response.text
    assert "script-src" not in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "form-action 'self'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("suffix", ["/approve", "/variables", "/workflow"])
def test_get_cannot_approve_or_edit(review, suffix):
    service, client = review
    response = client.get(PATH + suffix, params={"review_token": TOKEN})
    assert response.status_code == 405
    assert response.headers["cache-control"].startswith("no-store")
    assert not service.approvals and not service.edits
    assert not service.workflow_edits


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": "http://localhost:7331"},
        {"Origin": BASE, "Host": "evil.example:7331"},
        {"Origin": BASE, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_site_or_missing_origin_cannot_approve(review, headers):
    service, client = review
    response = client.post(PATH + "/approve", data=fields(), headers=headers)
    assert response.status_code == 403
    assert not service.approvals


@pytest.mark.parametrize("token", ["", "bad", "z" * 43])
def test_wrong_capability_get_cannot_reveal_plan(review, token):
    service, client = review
    response = client.get(PATH, params={"review_token": token})
    assert response.status_code == 403
    assert "My poster" not in response.text
    assert not service.approvals


def test_duplicate_query_token_is_rejected(review):
    _, client = review
    response = client.get(
        PATH, params=[("review_token", TOKEN), ("review_token", TOKEN)]
    )
    assert response.status_code == 403


def test_post_token_is_required_even_with_mcp_bearer(review):
    service, client = review
    response = client.post(
        PATH + "/approve",
        data={"expected_digest": DIGEST},
        headers={"Origin": BASE, "Authorization": "Bearer " + "x" * 50},
    )
    assert response.status_code == 400
    assert not service.approvals


def test_wrong_validly_shaped_post_capability_is_rejected(review):
    service, client = review
    response = client.post(
        PATH + "/approve", data=fields(review_token="z" * 43), headers={"Origin": BASE}
    )
    assert response.status_code == 403
    assert not service.approvals


def test_expired_capability_cannot_approve(review):
    service, client = review
    service.expired = True
    response = client.post(PATH + "/approve", data=fields(), headers={"Origin": BASE})
    assert response.status_code == 403
    assert not service.approvals


@pytest.mark.parametrize("changed_in_service", [False, True])
def test_stale_plan_cannot_approve(review, changed_in_service):
    service, client = review
    service.changed = changed_in_service
    data = fields(expected_digest=DIGEST if changed_in_service else "d" * 64)
    response = client.post(PATH + "/approve", data=data, headers={"Origin": BASE})
    assert response.status_code == 409
    assert not service.approvals


def test_explicit_click_approves_exact_plan_and_cannot_replay(review):
    service, client = review
    response = client.post(
        PATH + "/approve",
        data=fields(),
        headers={"Origin": BASE},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert service.approvals == [(PLAN_ID, DIGEST)]
    assert response.headers["location"] == PATH + "?review_token=" + TOKEN
    response = client.get(response.headers["location"])
    assert response.status_code == 200
    assert "starting" in response.text
    assert "Workflow in progress" in response.text
    assert "Approve and run" not in response.text
    assert "successfully completed" not in response.text
    repeated = client.post(PATH + "/approve", data=fields(), headers={"Origin": BASE})
    assert repeated.status_code == 409
    assert len(service.approvals) == 1


@pytest.mark.parametrize(
    "status,done,heading,refresh",
    [
        ("running", False, "Workflow in progress", True),
        ("paused", False, "Workflow in progress", True),
        ("completed_ui_verified", True, "Workflow completed", False),
        ("completed_fixture_verified", True, "Fixture run completed", False),
        ("completed_ui_verified", False, "Workflow in progress", True),
        ("aborted", True, "Run aborted", False),
        ("aborted", False, "Run aborted", True),
        ("halted", True, "Run halted", False),
        ("halted", False, "Run halted", True),
        ("unknown", True, "Run ended", False),
    ],
)
def test_results_truthfully_show_status_and_only_active_runs_refresh(
    review, status, done, heading, refresh
):
    service, client = review
    service.record["execution"] = {
        "run_id": "e" * 32,
        "status": status,
        "done": done,
        "completed_steps": 3,
        "error": None,
        "manual_review": ["Confirm instrument choice"],
        "control": {"state": "finished" if done else "running"},
    }
    response = client.get(PATH, params={"review_token": TOKEN})
    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert "Verified steps</dt><dd>3" in response.text
    assert "Confirm instrument choice" in response.text
    assert "Refresh status" in response.text
    assert ("refresh" in response.headers) is refresh
    if refresh:
        assert response.headers["refresh"] == "2"
        assert TOKEN not in response.headers["refresh"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"].startswith("no-store")
    assert "<form" not in response.text
    assert "<textarea" not in response.text
    assert "Approve and run" not in response.text
    assert "<script" not in response.text
    assert not service.approvals and not service.edits and not service.workflow_edits


def test_error_blocks_success_label_and_is_escaped_in_results(review):
    service, client = review
    service.record["execution"] = {
        "run_id": "e" * 32,
        "status": "completed_ui_verified",
        "done": True,
        "completed_steps": 2,
        "error": "<script>alert(1)</script>",
        "manual_review": ["<img src=x>"],
    }
    response = client.get(PATH, params={"review_token": TOKEN})
    assert "<h1>Run ended</h1>" in response.text
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text
    assert "<img src=x>" not in response.text and "&lt;img src=x&gt;" in response.text
    assert "refresh" not in response.headers
    assert not service.approvals


def test_blockers_disable_button_and_service_refuses_post(review):
    service, client = review
    service.record["plan"]["review_blockers"] = ["Choose a target project"]
    response = client.get(PATH, params={"review_token": TOKEN})
    assert "Choose a target project" in response.text
    assert 'type="submit" disabled>Approve and run' in response.text
    response = client.post(PATH + "/approve", data=fields(), headers={"Origin": BASE})
    assert response.status_code == 409
    assert not service.approvals


def test_input_edit_builds_fresh_preview_and_never_approves(review):
    service, client = review
    response = client.post(
        PATH + "/variables",
        data=fields(variables=json.dumps({"title": "Changed title"})),
        headers={"Origin": BASE},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/review/" + "f" * 32 + "?review_token=" + "g" * 43
    )
    assert service.edits == [{"title": "Changed title"}]
    assert not service.approvals


@pytest.mark.parametrize("variables", ["[]", '{"title":false}', "not JSON"])
def test_invalid_input_values_cannot_update(review, variables):
    service, client = review
    response = client.post(
        PATH + "/variables", data=fields(variables=variables), headers={"Origin": BASE}
    )
    assert response.status_code == 409
    assert not service.edits and not service.approvals


def test_duplicate_fields_and_oversize_body_rejected(review):
    service, client = review
    response = client.post(
        PATH + "/approve",
        content=f"review_token={TOKEN}&review_token={TOKEN}&expected_digest={DIGEST}",
        headers={"Origin": BASE, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    response = client.post(
        PATH + "/variables",
        data=fields(variables="x" * 100_001),
        headers={"Origin": BASE},
    )
    assert response.status_code == 400
    assert not service.edits and not service.approvals


def test_workflow_editor_only_shown_when_source_available(review):
    service, client = review
    service.record.pop("workflow_content")
    response = client.get(PATH, params={"review_token": TOKEN})
    assert "Edit workflow steps" not in response.text


def test_workflow_edit_creates_fresh_local_preview_without_running(review):
    service, client = review
    content = '{"description":"Local changed copy"}'
    response = client.post(
        PATH + "/workflow",
        data=fields(content=content),
        headers={"Origin": BASE},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert service.workflow_edits == [content]
    assert not service.approvals
    assert response.headers["location"].startswith("/review/" + "f" * 32)


@pytest.mark.parametrize(
    "content",
    ["", "non-ASCII: \u00e9", "x" * 2_000_001],
    ids=["empty", "non-ascii", "oversized"],
)
def test_workflow_editor_rejects_unbounded_or_nonascii_source(review, content):
    service, client = review
    response = client.post(
        PATH + "/workflow", data=fields(content=content), headers={"Origin": BASE}
    )
    assert response.status_code == 400
    assert not service.workflow_edits and not service.approvals


@pytest.mark.parametrize(
    "path,data",
    [
        ("/variables", {"variables": '{"title":"new"}'}),
        ("/workflow", {"content": "{}"}),
    ],
)
def test_editor_checks_digest_atomically_at_service(review, path, data):
    service, client = review
    service.changed = True
    response = client.post(PATH + path, data=fields(**data), headers={"Origin": BASE})
    assert response.status_code == 409
    assert not service.edits and not service.workflow_edits and not service.approvals


def test_workflow_editor_requires_same_origin_and_token(review):
    service, client = review
    response = client.post(
        PATH + "/workflow",
        data=fields(content="{}"),
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    response = client.post(
        PATH + "/workflow",
        data=fields(content="{}", review_token="z" * 43),
        headers={"Origin": BASE},
    )
    assert response.status_code == 403
    assert not service.workflow_edits and not service.approvals
