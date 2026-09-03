"""Explicit local capabilities; workflows cannot grant themselves permission."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


class PermissionDenied(ValueError):
    """A requested action exceeds the local operator's capability grant."""


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "createrelay-policy/v1"
    applications: list[str] = Field(default_factory=lambda: ["browser"])
    read_roots: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)
    allow_loopback: bool = True
    allowed_operations: dict[str, list[str]] = Field(default_factory=dict)
    approved_workflow_digests: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=1000, ge=1, le=10000)
    max_timeout_s: float = Field(default=60, ge=1, le=300)

    def path(self, value: str | Path) -> Path:
        target = Path(value).expanduser().resolve(strict=True)
        if not target.is_file():
            raise PermissionDenied("Expected an existing regular file")
        if not any(target.is_relative_to(Path(r).resolve()) for r in self.read_roots):
            raise PermissionDenied("File is outside operator-approved read roots")
        return target

    def url(self, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.scheme not in {"http", "https"}:
            raise PermissionDenied(
                "Only credential-free HTTP(S) application URLs are allowed"
            )
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if self.allow_loopback and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            return value
        if origin not in self.allowed_origins:
            raise PermissionDenied("Application origin needs a local operator grant")
        return value

    def action(self, provider: str, operation: str, args: dict[str, Any]) -> None:
        if provider not in self.applications:
            raise PermissionDenied(f"Application provider is not allowed: {provider}")
        if operation in {"shell", "execute", "evaluate", "script", "exec", "launch"}:
            raise PermissionDenied("Arbitrary code or process execution is unavailable")
        allowed = self.allowed_operations.get(provider)
        if allowed is not None and operation not in allowed:
            raise PermissionDenied(f"Operation is not granted: {provider}.{operation}")
        if re.search(
            r"publish|purchase|delete|distribute|follow|message|comment|login",
            operation,
            re.I,
        ):
            raise PermissionDenied(
                "Consequential and account/social operations are not exposed"
            )
        for key, value in args.items():
            if key in {"file", "path", "filename", "reference_wav"} and value:
                self.path(str(value))
            if key in {"files", "paths"}:
                for item in value:
                    self.path(str(item))
            if key in {"url", "target_url"} and value:
                self.url(str(value))

    def check_workflow(self, document: Any, *, require_approval: bool = True) -> None:
        data = (
            document.model_dump(mode="json")
            if hasattr(document, "model_dump")
            else document
        )
        app = data["application"]
        if app not in self.applications:
            raise PermissionDenied(f"Application provider is not allowed: {app}")
        config = data.get("configuration", {})
        config = config.get(app, config)
        if config.get("profile_dir"):
            raise PermissionDenied(
                "Workflow may name a dedicated profile, not supply a profile directory"
            )
        needs_approval = require_approval
        for name in ("url", "fixture_url", "project_url"):
            if config.get(name):
                self.url(config[name])
                if urlsplit(config[name]).hostname not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    needs_approval = True
        if app == "bandlab" and config.get("mode") != "fixture":
            needs_approval = True
        if (
            require_approval
            and needs_approval
            and digest(data) not in self.approved_workflow_digests
        ):
            raise PermissionDenied("Workflow needs local approval of its exact digest")
        # Recursively inspect graph actions as well as the linear step list.
        count = 0

        def visit(node: Any) -> None:
            nonlocal count
            if isinstance(node, dict):
                if "action" in node and "id" in node and not node.get("api_binding"):
                    raise PermissionDenied(
                        "This interface exposes registered providers only; use upstream CLI for native bundles"
                    )
                if node.get("api_binding"):
                    count += 1
                    binding = node["api_binding"]
                    if (
                        binding.get("kind") != "tool"
                        or binding.get("on_unavailable") != "halt"
                    ):
                        raise PermissionDenied(
                            "CreateRelay requires bounded tool bindings with halt fallback"
                        )
                    provider = binding["url_template"]
                    if provider not in self.applications or "{" in provider:
                        raise PermissionDenied(
                            "Provider names must be literal operator-approved applications"
                        )
                    if (binding.get("timeout_s") or 5) > self.max_timeout_s:
                        raise PermissionDenied("Step timeout exceeds policy")
                    if not binding.get("effects"):
                        raise PermissionDenied(
                            "Every action requires a declared verification contract"
                        )
                    if (
                        require_approval
                        and node.get("risk") == "irreversible"
                        and digest(data) not in self.approved_workflow_digests
                    ):
                        raise PermissionDenied(
                            "Irreversible workflow requires local approval of its exact digest"
                        )
                    self.action(provider, binding["method"], {})
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(data["workflow"])
        if count > self.max_steps:
            raise PermissionDenied("Workflow exceeds the maximum declared action count")


def digest(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


def load_policy(path: Path | None) -> Policy:
    return Policy.model_validate_json(path.read_text("ascii")) if path else Policy()


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Redact by field name and known secret value, recursively, before persistence."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"password|secret|token|cookie|authorization", str(k), re.I)
            else redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value
