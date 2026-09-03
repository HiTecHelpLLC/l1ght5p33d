"""Local, capability-protected human review with details available on demand.

The service owns token expiry, immutable plan checks, and approval consumption.
These routes never infer authority from workflow descriptions or catalog labels.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

_ID = re.compile(r"[0-9a-f]{32}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,512}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_BODY_LIMIT = 100_000
_WORKFLOW_LIMIT = 2_000_000
_CSS = """
:root{color-scheme:light dark;font-family:system-ui,sans-serif;line-height:1.5}
body{max-width:860px;margin:36px auto;padding:0 20px;background:#111827;color:#edf2f7}
h1{font-size:1.8rem;margin-bottom:8px}h2{font-size:1.1rem;margin:22px 0 8px}
p{overflow-wrap:anywhere}a{color:#93c5fd}small,.muted{color:#b8c5d9}
.card,details{border:1px solid #43526a;border-radius:12px;padding:16px;margin:16px 0}
.badge{font-size:.85rem;color:#a7f3d0}.warning{border-color:#fbbf24;color:#fde68a}
dl{display:grid;grid-template-columns:minmax(110px,1fr) 3fr;gap:8px 16px}
dt{color:#b8c5d9}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}
summary{cursor:pointer;font-weight:600}button{padding:12px 20px;border:0;
border-radius:8px;background:#93c5fd;color:#111827;font-weight:700;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}label{display:block;margin:12px 0}
textarea{display:block;width:100%;box-sizing:border-box;min-height:180px;
padding:12px;background:#172238;color:#edf2f7;border:1px solid #64748b;border-radius:8px}
li{margin:8px 0}.actions{margin-top:24px}.secondary{background:#cbd5e1}
@media(max-width:540px){dl{display:block}dt{margin-top:12px}}
"""
_STYLE_HASH = base64.b64encode(hashlib.sha256(_CSS.encode()).digest()).decode()
_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; style-src 'sha256-" + _STYLE_HASH + "'"
    ),
}


class ReviewService(Protocol):
    def get_review_plan(self, plan_id: str, review_token: str) -> dict[str, Any]: ...

    def approve_review_plan(
        self, plan_id: str, review_token: str, expected_digest: str
    ) -> dict[str, Any]: ...

    def update_review_variables(
        self,
        plan_id: str,
        review_token: str,
        variables: dict[str, str],
        *,
        expected_digest: str | None = None,
    ) -> dict[str, Any]: ...

    def update_review_workflow(
        self, plan_id: str, review_token: str, content: str, expected_digest: str
    ) -> dict[str, Any]: ...


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False)


def _display(value: Any) -> str:
    return str(value) if isinstance(value, str) else _json(value)


def _operation_summary(step: dict[str, Any]) -> str:
    operation = str(step.get("operation") or step.get("action") or "Action")
    arguments = step.get("arguments") or {}
    target = arguments.get("file") or arguments.get("path") or arguments.get("url")
    for selector in arguments.get("selectors", []):
        if not target and isinstance(selector, dict):
            target = (
                selector.get("name") or selector.get("label") or selector.get("text")
            )
    label = operation.replace("_", " ").capitalize()
    return label + (": " + _display(target) if target else "")


def _effect_summary(effect: dict[str, Any]) -> str:
    value = effect.get("value", effect.get("expected", effect))
    if isinstance(value, dict) and "literal" in value:
        value = value["literal"]
    field = effect.get("field", effect.get("kind", "effect"))
    return str(field) + ": " + _display(value)


def _pairs(items: dict[str, Any]) -> str:
    return (
        "<dl>"
        + "".join(
            f"<dt>{_escape(key)}</dt><dd>{_escape(_display(value))}</dd>"
            for key, value in items.items()
        )
        + "</dl>"
    )


def _page(title: str, content: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(title)} | L1ght5p33d</title><style>{_CSS}</style>"
        '</head><body><p class="badge">L1ght5p33d / Local workflow review</p>'
        f"<main><h1>{_escape(title)}</h1>{content}</main></body></html>",
        status_code=status,
        headers=_HEADERS,
    )


def _hidden(token: str, digest: str) -> str:
    return (
        f'<input type="hidden" name="review_token" value="{_escape(token)}">'
        f'<input type="hidden" name="expected_digest" value="{_escape(digest)}">'
    )


def _review_location(plan_id: str, token: str) -> str:
    return "/review/" + plan_id + "?" + urlencode({"review_token": token})


def _execution_page(record: dict[str, Any], token: str) -> HTMLResponse:
    execution = record["execution"]
    status = execution.get("status", "unknown")
    done = execution.get("done") is True
    error = execution.get("error")
    verified = (
        done
        and not error
        and status in {"completed_ui_verified", "completed_fixture_verified"}
    )
    if verified:
        if status == "completed_fixture_verified":
            title = "Fixture run completed"
            message = "The synthetic fixture run finished and its expected results were verified. Live application qualification remains separate."
        else:
            title = "Workflow completed"
            message = "The workflow finished and its declared UI effects were verified."
    elif status == "aborted":
        title = "Run aborted"
        message = "The run was stopped. Inspect any completed actions before deciding what to do next."
    elif status == "halted":
        title = "Run halted"
        message = "The workflow could not finish. Review the error and any completed actions before recovery."
    elif done:
        title = "Run ended"
        message = "A fully verified result was not confirmed. Review the execution details before another run."
    else:
        title = "Workflow in progress"
        message = "The approved plan is running or settling its final state. A successful result has not yet been confirmed."
    content = "<p>" + _escape(message) + "</p>"
    content += (
        '<section class="card" aria-label="Execution status">'
        + _pairs(
            {
                "Workflow": record["plan"]["workflow_id"],
                "Application": record["plan"].get("application", "Unknown"),
                "Run": execution.get("run_id", "Unknown"),
                "Status": status,
                "Control": execution.get("control", {}).get("state", "Unknown"),
                "Verified steps": execution.get("completed_steps", 0),
                "Run settled": done,
            }
        )
        + "</section>"
    )
    if error:
        content += (
            '<section class="card warning"><h2>Error</h2><p>'
            + _escape(error)
            + "</p></section>"
        )
    manual_review = execution.get("manual_review", [])
    if manual_review:
        content += (
            "<h2>Manual review</h2><ul>"
            + "".join("<li>" + _escape(note) + "</li>" for note in manual_review)
            + "</ul>"
        )
    if execution.get("shutdown_warning"):
        content += (
            '<p class="warning">' + _escape(execution["shutdown_warning"]) + "</p>"
        )
    content += (
        '<p><a rel="noreferrer" href="'
        + _escape(_review_location(record["plan_id"], token))
        + '">Refresh status</a></p>'
    )
    content += (
        "<details><summary>Execution details</summary><pre>"
        + _escape(_json(execution))
        + "</pre></details>"
    )
    response = _page(title, content)
    if not done:
        # Refresh the same local URL. No script, third-party request or token in
        # the header is needed. A completed action status may still be settling
        # cleanup; only done=True ends polling and permits a success heading.
        response.headers["Refresh"] = "2"
    return response


def _review_page(record: dict[str, Any], token: str) -> HTMLResponse:
    if isinstance(record.get("execution"), dict):
        return _execution_page(record, token)
    plan = record["plan"]
    plan_id = record["plan_id"]
    digest = plan["plan_digest"]
    metadata = plan.get("author_metadata", {})
    steps = plan.get("steps", [])
    variables = plan.get("variables", {})
    operations = list(dict.fromkeys(_operation_summary(step) for step in steps))
    effects = [effect for step in steps for effect in step.get("effects", [])]
    effect_count = len(effects)
    effect_summary = list(dict.fromkeys(_effect_summary(effect) for effect in effects))
    blockers = plan.get("review_blockers", [])
    status = record.get("status", "awaiting_approval")
    can_approve = not blockers and status == "awaiting_approval"
    goal = plan.get("user_goal") or metadata.get("description") or plan["workflow_id"]
    goal_label = (
        "Your goal"
        if plan.get("user_goal")
        else "Workflow description (author supplied)"
    )
    summary = _pairs(
        {
            goal_label: goal,
            "Application": plan.get("application", "Unknown"),
            "Workflow": plan["workflow_id"],
            "Changes / actions": "; ".join(operations) or "No declared actions",
            "Expected results": "; ".join(effect_summary)
            or "No declared expected results",
            "Verification": f"{effect_count} declared expected effects across {len(steps)} actions",
            "Approval": "This exact plan, once. Approve and run starts it locally.",
        }
    )
    content = (
        "<p>Check the goal, inputs and changes. Expand the steps whenever you want "
        "the details; you do not need to read raw JSON to continue.</p>"
        f'<section class="card" aria-label="Run summary">{summary}</section>'
        "<h2>Inputs and target</h2>"
        + _pairs(variables or {"Variables": "No workflow variables"})
    )
    targets = plan.get("targets", {})
    target_fields = {
        key: value
        for key, value in targets.items()
        if key
        in {
            "url",
            "project",
            "project_id",
            "project_name",
            "executable",
            "title",
            "title_pattern",
            "mode",
            "channel",
        }
    }
    if target_fields:
        content += _pairs(target_fields)
    files = plan.get("input_files", [])
    if files:
        content += (
            "<p>Files read: "
            + "; ".join(_escape(item.get("path", "")) for item in files)
            + "</p>"
        )
    lifecycle = plan.get("provider_lifecycle", {})
    if lifecycle:
        content += "<h2>Application changes</h2>" + _pairs(
            {key: lifecycle[key] for key in ("startup", "cleanup") if key in lifecycle}
        )
    if blockers:
        content += '<section class="card warning"><h2>Clarification needed</h2><ul>'
        content += (
            "".join(f"<li>{_escape(item)}</li>" for item in blockers)
            + "</ul></section>"
        )
    provenance = plan.get("workflow_review")
    if provenance:
        content += (
            "<details><summary>Source, curator review and test scope</summary>"
            "<p>Source identity, curator review and fixture tests are separate from "
            "your permission to run this plan.</p><pre>"
            + _escape(_json(provenance))
            + "</pre></details>"
        )
    content += (
        f"<details><summary>All {len(steps)} steps and expected effects</summary>"
    )
    content += (
        "<p>" + _escape(plan.get("control_flow", {}).get("note", "")) + "</p><ol>"
    )
    for step in steps:
        content += (
            "<li><strong>"
            + _escape(step.get("operation", step.get("action", "Action")))
            + "</strong> "
            + _escape(step.get("provider", ""))
            + _pairs(
                {
                    "Arguments": step.get("arguments"),
                    "Expected effects": step.get("effects", []),
                }
            )
            + "</li>"
        )
    content += "</ol></details>"
    # Edits require a newly generated plan; neither edit form grants approval.
    if variables:
        content += (
            "<details><summary>Change inputs</summary><p>Edit declared values as "
            "JSON strings. Saving builds a fresh plan; it does not run anything.</p>"
            f'<form method="post" action="/review/{_escape(plan_id)}/variables">'
            + _hidden(token, digest)
            + '<label for="variables">Input values</label>'
            '<textarea id="variables" name="variables" spellcheck="false">'
            + _escape(
                _json(
                    {
                        key: value if isinstance(value, str) else json.dumps(value)
                        for key, value in variables.items()
                    }
                )
            )
            + '</textarea><button class="secondary" type="submit">Update preview</button></form></details>'
        )
    workflow_content = record.get("workflow_content")
    if isinstance(workflow_content, str):
        content += (
            "<details><summary>Edit workflow steps</summary>"
            "<p>Edit the complete ASCII workflow below. Saving creates a local "
            "copy and a fresh preview; it does not run anything. Any publisher "
            "signature remains attached to the original, not your edited copy. "
            "The edited copy requires fresh approval.</p>"
            f'<form method="post" action="/review/{_escape(plan_id)}/workflow">'
            + _hidden(token, digest)
            + '<label for="workflow-content">Workflow source</label>'
            '<textarea id="workflow-content" name="content" spellcheck="false">'
            + _escape(workflow_content)
            + '</textarea><button class="secondary" type="submit">'
            "Save local copy and update preview</button></form></details>"
        )
    content += (
        "<details><summary>Complete plan and settings</summary><pre>"
        + _escape(_json(plan))
        + "</pre></details>"
        '<p class="muted">Want different steps? Ask the AI to propose a workflow '
        "patch, then review the updated plan. Closing this page leaves an "
        "unapproved plan unapproved.</p>"
    )
    content += (
        f'<form class="actions" method="post" action="/review/{_escape(plan_id)}/approve">'
        + _hidden(token, digest)
        + '<button type="submit"'
        + ("" if can_approve else " disabled")
        + ">Approve and run</button></form>"
        '<p class="muted">Approval is single use and expires. Changed inputs or '
        "workflow steps need a new preview.</p>"
    )
    return _page("Ready to run?", content)


def create_review_app(service: ReviewService, *, port: int = 7331) -> Starlette:
    """Mount this app at /review outside MCP's separate bearer-token boundary."""
    if not 1 <= port <= 65535:
        raise ValueError("Invalid review port")
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def boundary(request: Request, *, write: bool = False) -> Response | None:
        host_values = request.headers.getlist("host")
        origin_values = request.headers.getlist("origin")
        host = host_values[0] if len(host_values) == 1 else ""
        origin = origin_values[0] if len(origin_values) == 1 else None
        if (
            host not in hosts
            or request.url.scheme != "http"
            or len(origin_values) > 1
            or (origin is not None and origin != "http://" + host)
            or (write and origin is None)
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return _page(
                "Review unavailable", "<p>Open the local review link directly.</p>", 403
            )
        return None

    def identity(request: Request, token: str) -> tuple[str, str]:
        plan_id = request.path_params["plan_id"]
        if not _ID.fullmatch(plan_id) or not _TOKEN.fullmatch(token):
            raise ValueError("Invalid review identity")
        return plan_id, token

    async def review(request: Request) -> Response:
        refusal = boundary(request)
        if refusal is not None:
            return refusal
        try:
            if (
                set(request.query_params) != {"review_token"}
                or len(request.query_params.getlist("review_token")) != 1
            ):
                raise ValueError("Missing review token")
            plan_id, token = identity(request, request.query_params["review_token"])
            record = service.get_review_plan(plan_id, token)
            return _review_page(record, token)
        except (ValueError, PermissionError, KeyError):
            return _page(
                "Review unavailable",
                "<p>This link is invalid or expired. Ask for a fresh preview.</p>",
                403,
            )

    async def form(request: Request, body_limit: int = _BODY_LIMIT) -> dict[str, str]:
        if (
            request.headers.get("content-type", "").split(";", 1)[0]
            != "application/x-www-form-urlencoded"
        ):
            raise ValueError("Expected form data")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > body_limit:
                raise ValueError("Review request is too large")
        pairs = parse_qsl(
            body.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=4,
        )
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("Duplicate form fields")
        return dict(pairs)

    async def submit(request: Request) -> Response:
        refusal = boundary(request, write=True)
        if refusal is not None:
            return refusal
        editing = request.url.path.endswith("/variables")
        editing_workflow = request.url.path.endswith("/workflow")
        try:
            # URL encoding can expand each ASCII character to three bytes.
            fields = await form(
                request,
                _WORKFLOW_LIMIT * 3 + _BODY_LIMIT if editing_workflow else _BODY_LIMIT,
            )
            expected = {"review_token", "expected_digest"} | (
                {"variables"} if editing else {"content"} if editing_workflow else set()
            )
            if set(fields) != expected or not _DIGEST.fullmatch(
                fields["expected_digest"]
            ):
                raise ValueError("Invalid form fields")
            if editing_workflow and (
                not fields["content"].isascii()
                or not 1 <= len(fields["content"]) <= _WORKFLOW_LIMIT
            ):
                raise ValueError("Workflow source must be bounded ASCII text")
            plan_id, token = identity(request, fields["review_token"])
        except (ValueError, UnicodeError):
            return _page(
                "Invalid request", "<p>Reload the preview and try again.</p>", 400
            )
        try:
            record = service.get_review_plan(plan_id, token)
        except (ValueError, PermissionError, KeyError):
            return _page(
                "Review unavailable",
                "<p>This link is invalid or expired. Ask for a fresh preview.</p>",
                403,
            )
        if record["plan"]["plan_digest"] != fields["expected_digest"]:
            return _page(
                "Preview changed",
                "<p>Review a fresh preview before continuing.</p>",
                409,
            )
        try:
            if editing or editing_workflow:
                if editing:
                    variables = json.loads(fields["variables"])
                    if not isinstance(variables, dict) or any(
                        not isinstance(key, str) or not isinstance(value, str)
                        for key, value in variables.items()
                    ):
                        raise ValueError("Input values must be JSON strings")
                    updated = service.update_review_variables(
                        plan_id,
                        token,
                        variables,
                        expected_digest=fields["expected_digest"],
                    )
                else:
                    updated = service.update_review_workflow(
                        plan_id, token, fields["content"], fields["expected_digest"]
                    )
                new_id, new_token = updated["plan_id"], updated["review_token"]
                if not _ID.fullmatch(new_id) or not _TOKEN.fullmatch(new_token):
                    raise ValueError("Invalid updated review")
                # Construct the local redirect; never follow a URL in metadata.
                location = _review_location(new_id, new_token)
                return RedirectResponse(location, status_code=303, headers=_HEADERS)
            service.approve_review_plan(plan_id, token, fields["expected_digest"])
            return RedirectResponse(
                _review_location(plan_id, token), status_code=303, headers=_HEADERS
            )
        except (ValueError, PermissionError, RuntimeError, KeyError):
            return _page(
                "Review needs updating",
                "<p>The plan could not proceed. Inputs, permissions or workflow "
                "content may have changed, or another run may be active. Ask for a fresh preview.</p>",
                409,
            )

    app = Starlette(
        routes=[
            Route("/{plan_id}", review, methods=["GET"]),
            Route("/{plan_id}/approve", submit, methods=["POST"]),
            Route("/{plan_id}/variables", submit, methods=["POST"]),
            Route("/{plan_id}/workflow", submit, methods=["POST"]),
        ]
    )

    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.update(_HEADERS)
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers)
    return app
