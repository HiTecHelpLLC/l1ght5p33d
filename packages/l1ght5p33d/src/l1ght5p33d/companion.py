"""On-demand reviewed packs and the local human handoff, without model calls."""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from l1ght5p33d.cache import CacheError, WorkflowCache
from l1ght5p33d.packs import CuratedPackSource, ReviewedPack, verify_pack
from l1ght5p33d.policy import PermissionDenied

if TYPE_CHECKING:
    from l1ght5p33d.service import WorkflowService


class Companion:
    def __init__(self, service: WorkflowService, retention_days: int) -> None:
        self.service = service
        self.cache = WorkflowCache(
            service.state_root / "workflow-cache", retention_days
        )
        self.source = CuratedPackSource()
        self.selection_path = service.state_root / "selected-packs.json"
        self.selected: dict[str, str] = {}
        if self.selection_path.exists():
            if self.selection_path.stat().st_size > 100_000:
                raise ValueError("Managed workflow selection exceeds limits")
            value = json.loads(self.selection_path.read_text("ascii"))
            if not isinstance(value, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in value.items()
            ):
                raise ValueError("Invalid managed workflow selection")
            self.selected = value
        self.reviews: dict[str, dict[str, Any]] = {}
        self.stop_event = threading.Event()
        self.maintenance: threading.Thread | None = None

    def _save_selection(self) -> None:
        from l1ght5p33d.service import write_json

        write_json(self.selection_path, self.selected)

    def key_for(self, workflow_id: str) -> str | None:
        # A human-edited local derivative intentionally takes precedence.
        if workflow_id in self.service._local_registry():
            return None
        return self.selected.get(workflow_id)

    def verify(self, key: str) -> tuple[dict[str, Any], ReviewedPack]:
        lease = self.cache.acquire(key)
        try:
            record = self.cache.get(key)
            files = record["files"]
            pack = verify_pack(
                Path(files["workflow"]).read_bytes(),
                Path(files["review"]).read_bytes(),
                Path(files["evidence"]).read_bytes(),
                Path(files["attestation"]).read_bytes(),
            )
            if (pack.workflow_id, pack.version) != (
                record["workflow_id"],
                record["version"],
            ):
                raise PermissionDenied("Cached review identity changed")
            return record, pack
        finally:
            self.cache.release(lease)

    def path(self, workflow_id: str) -> Path:
        key = self.key_for(workflow_id)
        if key is None:
            raise ValueError("Unknown managed workflow")
        record, pack = self.verify(key)
        if pack.workflow_id != workflow_id:
            raise PermissionDenied("Selected workflow identity changed")
        return Path(record["workflow_path"])

    def provenance(self, workflow_id: str) -> dict[str, Any] | None:
        key = self.key_for(workflow_id)
        if key is None:
            return None
        _, pack = self.verify(key)
        return {
            "cache_key": key,
            "workflow_sha256": pack.workflow_sha256,
            "pack_digest": pack.pack_digest,
            "curator_review": pack.claims,
            "metadata": pack.metadata,
            "execution_approved": False,
            "qualification_is_environment_specific": True,
        }

    def download(self, workflow_id: str, version: str) -> dict[str, Any]:
        self.cleanup()
        if workflow_id in self.service._local_registry():
            raise ValueError(
                "A local workflow already uses this ID; use that local copy or rename it first"
            )
        record = None
        for candidate in self.cache.find(workflow_id, version):
            try:
                record, _ = self.verify(candidate["key"])
                break
            except (ValueError, OSError, KeyError):
                continue
        hit = record is not None
        if record is None:
            pack = self.source.fetch(workflow_id, version)
            record = self.cache.store(
                workflow_id,
                version,
                pack.workflow_bytes,
                pack.workflow_sha256,
                provenance=json.dumps(
                    pack.provenance, sort_keys=True, ensure_ascii=True
                ).encode("ascii"),
                review=pack.metadata_bytes,
                evidence=pack.evidence_bytes,
                attestation=pack.attestation_bytes,
            )
        self.selected[workflow_id] = record["key"]
        self._save_selection()
        return {
            "workflow_id": workflow_id,
            "version": version,
            "cache_hit": hit,
            "cache_key": record["key"],
            "retention_days": self.cache.retention_days,
            "executed": False,
            "execution_approved": False,
        }

    def issue_review(self, record: dict[str, Any]) -> dict[str, Any]:
        workflow_id = record["plan"]["workflow_id"]
        key = self.key_for(workflow_id)
        lease = self.cache.acquire(key) if key else None
        token = secrets.token_urlsafe(32)
        self.reviews[record["plan_id"]] = {
            "token": token,
            "expires_at": record["expires_at"],
            "lease": lease,
            "run_id": None,
        }
        return {
            **record,
            "review_token": token,
            "review_url": f"{self.service.review_base_url}/review/{record['plan_id']}?"
            + urlencode({"review_token": token}),
        }

    def authorize(
        self, plan_id: str, token: str, expected_digest: str | None = None
    ) -> dict[str, Any]:
        review = self.reviews.get(plan_id)
        if not review or not hmac.compare_digest(review["token"], token):
            raise PermissionDenied("Invalid local review capability")
        if time.time() >= review["expires_at"]:
            self.revoke(plan_id)
            raise PermissionDenied("Review expired; prepare a fresh plan")
        record = self.service.get_run_plan(plan_id)
        if expected_digest is not None:
            if record["plan"]["plan_digest"] != expected_digest:
                raise ValueError("Displayed plan changed; review a fresh plan")
            if review["run_id"] or record["status"] != "awaiting_approval":
                raise PermissionDenied("Review already used or unavailable")
            self.check_current(record)
        return record

    def check_current(self, record: dict[str, Any]) -> None:
        from l1ght5p33d.workflow import load_workflow

        workflow_id = record["plan"]["workflow_id"]
        if self.service.variables.get(workflow_id, {}) != record["supplied_variables"]:
            raise PermissionDenied("Variables changed; prepare a fresh preview")
        document = load_workflow(self.service._path(workflow_id))
        current = self.service._build_plan(document, record["supplied_variables"])
        if current["plan_digest"] != record["plan"]["plan_digest"]:
            raise PermissionDenied(
                "Workflow, inputs or policy changed; prepare a fresh preview"
            )

    def revoke(self, plan_id: str) -> None:
        review = self.reviews.pop(plan_id, None)
        if review and review["lease"]:
            self._release_review(review)

    def _release_review(self, review: dict[str, Any]) -> None:
        try:
            self.cache.release(review["lease"])
        except (ValueError, OSError, sqlite3.Error):
            logging.warning("Review lease cleanup deferred; pack remains protected")
        review["lease"] = None

    def release_review_lease(self, plan_id: str) -> None:
        review = self.reviews.get(plan_id)
        if review and review["lease"]:
            self._release_review(review)

    def cleanup(self) -> dict[str, Any]:
        with self.service._lock:
            for plan_id, review in list(self.reviews.items()):
                if time.time() >= review["expires_at"]:
                    self.revoke(plan_id)
            result = self.cache.cleanup()
            for workflow_id, key in list(self.selected.items()):
                try:
                    self.cache.get(key)
                except CacheError:
                    # Preserve modified packs in storage, but don't offer them as runnable.
                    self.selected.pop(workflow_id)
            self._save_selection()
            return result

    def start(self) -> None:
        if self.maintenance is not None:
            return
        self.cleanup()

        def maintain() -> None:
            while not self.stop_event.wait(3600):
                try:
                    self.cleanup()
                except (ValueError, OSError, sqlite3.Error):
                    logging.warning(
                        "Cache cleanup deferred; local storage needs inspection"
                    )

        self.maintenance = threading.Thread(target=maintain, daemon=True)
        self.maintenance.start()

    def close(self) -> None:
        self.stop_event.set()
        for plan_id in list(self.reviews):
            self.revoke(plan_id)
