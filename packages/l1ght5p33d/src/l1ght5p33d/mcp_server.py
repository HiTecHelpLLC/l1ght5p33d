"""Official MCP transport with mandatory loopback session authentication."""

from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from l1ght5p33d.service import WorkflowService


class SessionBoundary:
    """Apply authorization before MCP dispatch, including notifications/GET/DELETE."""

    def __init__(self, app: Any, token: str, port: int) -> None:
        if len(token) < 32:
            raise ValueError("Session token must contain at least 32 characters")
        self.app, self.token, self.port = app, token, port

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        origin = headers.get("origin")
        if headers.get("host") not in hosts or (
            origin and origin not in {f"http://{h}" for h in hosts}
        ):
            await JSONResponse({"error": "Untrusted host or origin"}, 403)(
                scope, receive, send
            )
            return
        if not hmac.compare_digest(
            headers.get("authorization", ""), f"Bearer {self.token}"
        ):
            await JSONResponse({"error": "Session token required"}, 401)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


def create_app(service: WorkflowService, token: str, *, port: int = 7331) -> Any:
    server = MCPServer(
        "L1ght5p33d",
        version="0.1.0",
        instructions=(
            "Operate registered local workflows. Inspect failure receipts before proposing repairs. "
            "Screenshots and secrets are never exposed. Approval cannot expand local policy."
        ),
    )

    @server.tool()
    def list_workflows() -> list[dict[str, Any]]:
        return service.list_workflows()

    @server.tool()
    def describe_workflow(workflow_id: str) -> dict[str, Any]:
        return service.describe_workflow(workflow_id)

    @server.tool()
    def validate_workflow(workflow_id: str) -> dict[str, Any]:
        return service.validate_workflow(workflow_id)

    @server.tool()
    def inspect_environment() -> dict[str, Any]:
        return service.inspect_environment()

    @server.tool()
    def inspect_ui_state(run_id: str) -> dict[str, Any]:
        return service.inspect_ui_state(run_id)

    @server.tool()
    def set_workflow_variables(
        workflow_id: str, variables: dict[str, str]
    ) -> dict[str, Any]:
        return service.set_workflow_variables(workflow_id, variables)

    @server.tool()
    def run_workflow(
        workflow_id: str, step_mode: bool = False, dry_run: bool = False
    ) -> dict[str, Any]:
        return service.run_workflow(workflow_id, step_mode=step_mode, dry_run=dry_run)

    @server.tool()
    def run_step(run_id: str) -> dict[str, Any]:
        return service.run_step(run_id)

    @server.tool()
    def pause_workflow(run_id: str) -> dict[str, Any]:
        return service.pause_workflow(run_id)

    @server.tool()
    def resume_workflow(run_id: str) -> dict[str, Any]:
        return service.resume_workflow(run_id)

    @server.tool()
    def abort_workflow(run_id: str) -> dict[str, Any]:
        return service.abort_workflow(run_id)

    @server.tool()
    def get_execution_status(run_id: str) -> dict[str, Any]:
        return service.get_execution_status(run_id)

    @server.tool()
    def get_execution_log(
        run_id: str, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return service.get_execution_log(run_id, offset, limit)

    @server.tool()
    def explain_failure(run_id: str) -> dict[str, Any]:
        return service.explain_failure(run_id)

    @server.tool()
    def propose_workflow_patch(workflow_id: str, content: str) -> dict[str, Any]:
        return service.propose_workflow_patch(workflow_id, content)

    @server.tool()
    def approve_workflow_patch(patch_id: str) -> dict[str, Any]:
        return service.approve_workflow_patch(patch_id)

    app = server.streamable_http_app(
        host="127.0.0.1",
        stateless_http=True,
        json_response=True,
        max_request_body_size=2_100_000,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}"],
            allowed_origins=[f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
        ),
    )
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: Any):
        async with original_lifespan(application):
            try:
                yield
            finally:
                await asyncio.to_thread(service.shutdown)

    app.router.lifespan_context = lifespan
    return SessionBoundary(app, token, port)


def run_json_rpc(service: WorkflowService) -> None:
    """Line-delimited local JSON-RPC; process access is the local capability."""
    import sys

    allowed = {
        "list_workflows",
        "describe_workflow",
        "validate_workflow",
        "inspect_environment",
        "inspect_ui_state",
        "set_workflow_variables",
        "run_workflow",
        "run_step",
        "pause_workflow",
        "resume_workflow",
        "abort_workflow",
        "get_execution_status",
        "get_execution_log",
        "explain_failure",
        "propose_workflow_patch",
        "approve_workflow_patch",
    }
    try:
        for line in sys.stdin:
            request: dict[str, Any] = {}
            try:
                if len(line) > 2_100_000:
                    raise ValueError("Request exceeds size limit")
                parsed = json.loads(line)
                if not isinstance(parsed, dict):
                    raise ValueError("JSON-RPC requests must be objects")
                request = parsed
                if (
                    request.get("jsonrpc") != "2.0"
                    or request.get("method") not in allowed
                ):
                    raise ValueError("Unknown JSON-RPC method")
                params = request.get("params", {})
                if not isinstance(params, dict) or "local_operator" in params:
                    raise ValueError("Invalid method parameters")
                result = getattr(service, request["method"])(**params)
                response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            except Exception as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32602, "message": str(exc)},
                }
            if "id" in request:
                print(json.dumps(response, ensure_ascii=True), flush=True)
    finally:
        service.shutdown()
