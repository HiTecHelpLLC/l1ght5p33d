"""Local, expiring, single-use run approvals. No remote approval endpoint."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from l1ght5p33d.policy import PermissionDenied, digest


class RunPlanStore:
    """The operator's OS account owns this directory, like the policy file.

    This separates MCP capability from approval. It cannot defend against a
    process with unrestricted access to the same user's files or terminal.
    """

    def __init__(self, state_root: Path) -> None:
        self.root = (state_root / "run-plans").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, plan_id: str, suffix: str = ".json") -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", plan_id):
            raise ValueError("Invalid run plan id")
        path = self.root / f"{plan_id}{suffix}"
        if path.is_symlink() or path.resolve().parent != self.root:
            raise PermissionDenied("Run plan storage must remain local")
        return path

    @staticmethod
    def _write_new(path: Path, value: dict[str, Any]) -> None:
        content = json.dumps(value, ensure_ascii=True, indent=2)
        if len(content) > 8_000_000:
            raise PermissionDenied("Run plan record exceeds the 8 MB review limit")
        with path.open("x", encoding="ascii") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file() or path.stat().st_size > 8_000_000:
            raise PermissionDenied("Run plan record is missing or exceeds limits")
        value = json.loads(path.read_text("ascii"))
        if not isinstance(value, dict):
            raise PermissionDenied("Invalid run plan record")
        return value

    def prepare(
        self, plan: dict[str, Any], workflow_root: Path, variables: dict[str, str]
    ) -> dict[str, Any]:
        plan_id = uuid.uuid4().hex
        record = {
            "plan_id": plan_id,
            "workflow_root": str(workflow_root),
            "supplied_variables": variables,
            "created_at": time.time(),
            "expires_at": time.time() + 900,
            "plan": plan,
        }
        self._write_new(self._path(plan_id), record)
        return record

    def read(self, plan_id: str) -> dict[str, Any]:
        record = self._read(self._path(plan_id))
        if record.get("plan_id") != plan_id:
            raise PermissionDenied("Run plan identity changed")
        plan = dict(record["plan"])
        expected = plan.pop("plan_digest", None)
        if expected != digest(plan):
            raise PermissionDenied(
                "Stored review content changed; prepare a fresh plan"
            )
        return record

    def status(self, plan_id: str) -> str:
        record = self.read(plan_id)
        if self._path(plan_id, ".claimed").exists():
            return "consumed"
        if time.time() >= record["expires_at"]:
            return "expired"
        if self._path(plan_id, ".approval").exists():
            approval = self._read(self._path(plan_id, ".approval"))
            if approval.get("plan_digest") != record["plan"]["plan_digest"]:
                return "invalid"
            return "approved"
        return "awaiting_approval"

    def approve(self, plan_id: str, expected_digest: str) -> None:
        record = self.read(plan_id)
        if record["plan"]["plan_digest"] != expected_digest:
            raise PermissionDenied("Displayed plan changed; review a fresh plan")
        if self.status(plan_id) != "awaiting_approval":
            raise PermissionDenied("Only an unexpired, unused plan can be approved")
        self._write_new(
            self._path(plan_id, ".approval"),
            {
                "plan_id": plan_id,
                "plan_digest": expected_digest,
                "approved_at": time.time(),
                "authority": "local_operator_confirmation",
            },
        )

    def consume(self, plan_id: str, expected_digest: str) -> None:
        record = self.read(plan_id)
        if record["plan"]["plan_digest"] != expected_digest:
            raise PermissionDenied("Approved plan no longer matches this run")
        if self.status(plan_id) != "approved":
            raise PermissionDenied("Run requires an unexpired, unused human approval")
        try:
            self._write_new(
                self._path(plan_id, ".claimed"),
                {"plan_id": plan_id, "plan_digest": expected_digest},
            )
        except FileExistsError as exc:
            raise PermissionDenied("Run approval was already used") from exc
