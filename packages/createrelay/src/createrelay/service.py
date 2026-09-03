"""Registry and run lifecycle shared by the local CLI and MCP interface."""

from __future__ import annotations

import difflib
import json
import os
import platform
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from createrelay.policy import PermissionDenied, Policy, digest, redact
from createrelay.providers.base import ProviderVerifier, ToolActuator
from createrelay.runtime import ControlledReplayer, RunControl
from createrelay.workflow import (
    WorkflowDocument,
    all_steps,
    load_workflow,
    reject_credential_parameters,
    validate_document,
)


def local_home() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local")))
        / "CreateRelay"
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=True), "ascii")
    temp.replace(path)


class WorkflowService:
    def __init__(
        self, workflow_root: Path, policy: Policy, *, state_root: Path | None = None
    ) -> None:
        self.root = workflow_root.resolve(strict=True)
        self.policy = policy
        self.state_root = (state_root or local_home()).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.runs: dict[str, dict[str, Any]] = {}
        self.variables: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self._patches: dict[str, dict[str, Any]] = {}
        self._shutting_down = False

    def _registry(self) -> dict[str, Path]:
        entries = {}
        for path in sorted(self.root.glob("*.json"))[:500]:
            resolved = path.resolve()
            if not resolved.is_relative_to(self.root):
                continue
            try:
                doc = load_workflow(resolved)
            except (ValueError, OSError):
                continue
            if doc.id in entries:
                raise ValueError(f"Duplicate workflow id in registry: {doc.id}")
            entries[doc.id] = resolved
        return entries

    def _path(self, workflow_id: str) -> Path:
        try:
            return self._registry()[workflow_id]
        except KeyError as exc:
            raise ValueError("Unknown registered workflow id") from exc

    def list_workflows(self) -> list[dict[str, Any]]:
        return [self.describe_workflow(name) for name in self._registry()]

    def describe_workflow(self, workflow_id: str) -> dict[str, Any]:
        doc = load_workflow(self._path(workflow_id))
        return {
            "id": doc.id,
            "description": doc.description,
            "application": doc.application,
            "digest": digest(doc),
            "steps": [
                {"id": s.id, "intent": s.intent} for s in all_steps(doc.workflow)
            ],
            "parameters": list(doc.workflow.params),
            "schema_version": doc.schema_version,
        }

    def validate_workflow(self, workflow_id: str) -> dict[str, Any]:
        doc = load_workflow(self._path(workflow_id))
        self.policy.check_workflow(doc)
        return {"valid": True, "digest": digest(doc), "id": doc.id}

    def inspect_environment(self) -> dict[str, Any]:
        return {
            "os": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "applications": self.policy.applications,
            "screenshots_leave_machine": False,
            "ai_required": False,
            "workflow_schema": "createrelay/v1",
        }

    def set_workflow_variables(
        self, workflow_id: str, variables: dict[str, str]
    ) -> dict[str, Any]:
        doc = load_workflow(self._path(workflow_id))
        reject_credential_parameters(doc.workflow, variables)
        known = set(doc.workflow.params) | set(doc.workflow.param_specs)
        if set(variables) - known:
            raise ValueError("Variables must be declared by the registered workflow")
        if any(not isinstance(v, str) or len(v) > 10000 for v in variables.values()):
            raise ValueError("Variables must be bounded strings")
        with self._lock:
            self.variables[workflow_id] = dict(variables)
        return {"id": workflow_id, "variables": redact(variables)}

    def _provider(self, doc: WorkflowDocument) -> Any:
        config = dict(doc.configuration)
        config = dict(config.get(doc.application, config))
        profile = config.get("profile")
        if profile:
            # Profile names, never arbitrary browser-profile paths over MCP.
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", profile):
                raise PermissionDenied(
                    "Use a dedicated profile name, not a filesystem path"
                )
            config["profile"] = str(self.state_root / "profiles" / profile)
            if doc.application == "bandlab":
                config["profile_dir"] = config["profile"]
        if doc.application == "browser":
            from createrelay.providers.browser import BrowserProvider

            return BrowserProvider(config)
        if doc.application == "bandlab":
            from createrelay.providers.bandlab import BandLabProvider

            return BandLabProvider(config)
        if doc.application == "windows":
            from createrelay.providers.windows import WindowsProvider

            return WindowsProvider(config)
        raise ValueError("Provider is not installed")

    def run_workflow(
        self, workflow_id: str, *, step_mode: bool = False, dry_run: bool = False
    ) -> dict[str, Any]:
        path = self._path(workflow_id)
        doc = load_workflow(path)
        self.policy.check_workflow(doc)
        if dry_run:
            return {
                "status": "dry_run",
                "actions_delivered": 0,
                **self.describe_workflow(workflow_id),
            }
        with self._lock:
            if self._shutting_down:
                raise RuntimeError("Service is shutting down; no new run can start")
            if any(not run["done"] for run in self.runs.values()):
                raise RuntimeError(
                    "Only one active automation run is allowed per service"
                )
            run_id = uuid.uuid4().hex
            run_dir = self.state_root / "runs" / run_id
            run_dir.mkdir(parents=True)
            control = RunControl(initially_paused=step_mode)
            config = doc.configuration.get(doc.application, doc.configuration)
            manual_review = config.get("manual_review", [])
            if not isinstance(manual_review, list):
                raise ValueError("manual_review must be a list of review notes")
            run: dict[str, Any] = {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "digest": digest(doc),
                "control": control,
                "directory": run_dir,
                "done": False,
                "status": "starting",
                "receipts": [],
                "ui_state": {},
                "error": None,
                "manual_review": [str(note) for note in manual_review],
            }
            self.runs[run_id] = run
            params = {**doc.workflow.params, **self.variables.get(workflow_id, {})}
            thread = threading.Thread(
                target=self._execute, args=(run, doc, path.parent, params), daemon=True
            )
            run["thread"] = thread
            thread.start()
        return {"run_id": run_id, "status": "starting", "step_mode": step_mode}

    def shutdown(self, timeout_s: float = 60) -> dict[str, Any]:
        """Cancel at the next verified boundary and wait for provider cleanup."""
        deadline = time.monotonic() + min(max(timeout_s, 0), 60)
        with self._lock:
            self._shutting_down = True
            active = [run for run in self.runs.values() if not run["done"]]
            for run in active:
                run["control"].abort()
        for run in active:
            thread = run["thread"]
            if thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
        with self._lock:
            pending = [run for run in active if not run["done"]]
            for run in pending:
                run["shutdown_warning"] = (
                    "Active action did not settle before shutdown timeout; "
                    "inspect application and reconcile delivery before another run"
                )
                self._persist(run)
        return {
            "stopped": not pending,
            "pending_runs": [run["run_id"] for run in pending],
        }

    def _execute(
        self,
        run: dict[str, Any],
        doc: WorkflowDocument,
        bundle_dir: Path,
        params: dict[str, str],
    ) -> None:
        provider = None
        run_dir = run["directory"]
        try:
            reject_credential_parameters(doc.workflow, params)
            provider = self._provider(doc)
            providers = {provider.name: provider}
            run["ui_state"] = redact(provider.inspect())
            run["state_timestamp"] = datetime.now(timezone.utc).isoformat()
            run["status"] = "running"

            def receipt_sink(receipt: dict[str, Any]) -> None:
                with self._lock:
                    receipt = redact(receipt)
                    with (run_dir / "receipts.jsonl").open(
                        "a", encoding="ascii"
                    ) as handle:
                        handle.write(json.dumps(receipt, ensure_ascii=True) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    with (run_dir / "execution.log").open(
                        "a", encoding="utf-8"
                    ) as handle:
                        handle.write(
                            f"{receipt['timestamp']} {receipt['step_id']} {receipt['result']} "
                            f"{receipt['duration_ms']}ms {receipt.get('selector_method')}\n"
                        )
                    run["receipts"].append(receipt)
                    try:
                        run["ui_state"] = redact(provider.inspect())
                        run["state_timestamp"] = datetime.now(timezone.utc).isoformat()
                        run["state_stale"] = False
                    except Exception:
                        # This is a cache refresh after independent effect
                        # verification, not permission to revoke or retry input.
                        run["state_stale"] = True
                        run["state_warning"] = (
                            "Post-action snapshot unavailable; inspect live state before another run"
                        )
                    self._persist(run)

            replayer = ControlledReplayer(
                control=run["control"],
                receipt_sink=receipt_sink,
                api_actuator=ToolActuator(providers, policy_check=self.policy.action),
                effect_verifier=ProviderVerifier(providers),
                durable=True,
            )
            native = doc.workflow.model_copy(deep=True)
            sealed_bundle = run_dir / "bundle"
            native.save(sealed_bundle)
            report = replayer.run(
                native,
                params=params,
                bundle_dir=sealed_bundle,
                run_dir=run_dir / "flow",
            )
            run["report"] = report.model_dump(mode="json")
            self._finalize_receipts(run)
            completed = bool(report.success) and not run["control"].aborted
            run["status"] = (
                (
                    "completed_ui_verified"
                    if provider.effect_tier == 4
                    else "completed_fixture_verified"
                )
                if completed
                else "halted"
            )
            if run["control"].aborted:
                run["status"] = "aborted"
            if not completed:
                run["error"] = next(
                    (
                        r.get("error")
                        for r in reversed(run["receipts"])
                        if r.get("error")
                    ),
                    "Run halted; inspect the Flow report",
                )
        except Exception as exc:
            run["status"] = "halted"
            # Avoid third-party exception text containing file contents or authentication state.
            run["error"] = (
                f"{type(exc).__name__}: initialization or execution failed; inspect local diagnostics"
            )
            run["diagnostic"] = (
                str(exc)[:2000]
                if isinstance(exc, (ValueError, PermissionDenied))
                else type(exc).__name__
            )
        finally:
            if provider:
                try:
                    provider.close()
                except Exception:
                    run["cleanup_warning"] = "Provider cleanup needs manual review"
            run["control"].finish()
            run["done"] = True
            self._persist(run)

    def _finalize_receipts(self, run: dict[str, Any]) -> None:
        """Confirm checkpoint creation only after Flow persisted its results."""
        from openadapt_flow.runtime.durable.checkpoint import CheckpointStore

        store = CheckpointStore(run["directory"] / "flow")
        checkpoints = list(store.checkpoints()) + list(store.program_checkpoints())
        available: dict[str, list[Any]] = {}
        for checkpoint in checkpoints:
            available.setdefault(checkpoint.step_id, []).append(checkpoint)
        for receipt in run["receipts"]:
            candidates = available.get(receipt["step_id"], [])
            matched_checkpoint = candidates.pop(0) if candidates else None
            receipt["checkpoint_created"] = matched_checkpoint is not None
            receipt["checkpoint_policy"] = (
                "Confirmed in native Flow checkpoint store"
                if matched_checkpoint is not None
                else "No verified native checkpoint for this action"
            )
        run["checkpoint_count"] = len(checkpoints)
        path = run["directory"] / "receipts.jsonl"
        temporary = path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="ascii") as handle:
            for receipt in run["receipts"]:
                handle.write(json.dumps(receipt, ensure_ascii=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def _persist(self, run: dict[str, Any]) -> None:
        value = {
            k: v
            for k, v in run.items()
            if k not in {"control", "directory", "thread", "report", "receipts"}
        }
        value["control"] = run["control"].status()
        write_json(run["directory"] / "status.json", redact(value))

    def _run(self, run_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id) or run_id not in self.runs:
            raise ValueError("Unknown active-service run id")
        return self.runs[run_id]

    def get_execution_status(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        return {
            "run_id": run_id,
            "status": run["status"],
            "done": run["done"],
            "error": run["error"],
            "diagnostic": run.get("diagnostic"),
            "manual_review": redact(run.get("manual_review", [])),
            "shutdown_warning": run.get("shutdown_warning"),
            "control": run["control"].status(),
            "completed_steps": len(
                [r for r in run["receipts"] if r["result"] == "verified"]
            ),
        }

    def inspect_ui_state(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        return {
            "state": run["ui_state"],
            "observed_at": run.get("state_timestamp"),
            "freshness": "last completed action boundary; no cross-thread GUI access",
            "stale": run.get("state_stale", False),
            "screenshots": [],
        }

    def run_step(self, run_id: str) -> dict[str, Any]:
        return self._run(run_id)["control"].step()

    def pause_workflow(self, run_id: str) -> dict[str, Any]:
        return self._run(run_id)["control"].pause()

    def resume_workflow(self, run_id: str) -> dict[str, Any]:
        if self._run(run_id)["done"]:
            raise RuntimeError(
                "A halted/terminal run needs inspected durable recovery; it cannot be restarted through MCP"
            )
        return self._run(run_id)["control"].resume()

    def abort_workflow(self, run_id: str) -> dict[str, Any]:
        return self._run(run_id)["control"].abort()

    def get_execution_log(
        self, run_id: str, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid log page")
        return self._run(run_id)["receipts"][offset : offset + limit]

    def explain_failure(self, run_id: str) -> dict[str, Any]:
        status = self.get_execution_status(run_id)
        return {
            **status,
            "last_receipt": self.get_execution_log(run_id)[-1:],
            "next_action": "Inspect current state and fix selectors/configuration. Never blindly replay an uncertain import.",
            "durable_recovery": "Use createrelay.runtime.resume_from_checkpoint with a fresh provider registry and an operator-reviewed ApprovalRecord; see docs/createrelay/recovery.md.",
        }

    def propose_workflow_patch(self, workflow_id: str, content: str) -> dict[str, Any]:
        if len(content) > 2_000_000 or not content.isascii():
            raise ValueError("Patch must be bounded ASCII JSON")
        path = self._path(workflow_id)
        old = load_workflow(path)
        proposed = validate_document(json.loads(content))
        if proposed.id != workflow_id or proposed.includes != old.includes:
            raise ValueError("Patches cannot change registry identity or includes")
        self.policy.check_workflow(proposed, require_approval=False)
        requires_local = (
            proposed.application != old.application
            or proposed.configuration != old.configuration
            or proposed.workflow.model_dump(mode="json")
            != old.workflow.model_dump(mode="json")
        )
        patch_id = uuid.uuid4().hex
        patch = {
            "patch_id": patch_id,
            "workflow_id": workflow_id,
            "old_digest": digest(old),
            "new_digest": digest(proposed),
            "content": content,
            "requires_local_approval": requires_local,
            "diff": "".join(
                difflib.unified_diff(
                    path.read_text("ascii").splitlines(True),
                    content.splitlines(True),
                    fromfile="original",
                    tofile="proposed",
                )
            ),
        }
        self._patches[patch_id] = patch
        write_json(self.state_root / "patches" / f"{patch_id}.json", patch)
        return {k: v for k, v in patch.items() if k != "content"}

    def approve_workflow_patch(
        self, patch_id: str, *, local_operator: bool = False
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", patch_id):
            raise ValueError("Invalid patch id")
        patch = self._patches.get(patch_id)
        if patch is None and local_operator:
            path = self.state_root / "patches" / f"{patch_id}.json"
            patch = json.loads(path.read_text("ascii")) if path.is_file() else None
        if not patch:
            raise ValueError("Unknown proposed patch")
        if patch["requires_local_approval"] and not local_operator:
            raise PermissionDenied(
                "Executable/application/configuration changes need local operator approval"
            )
        with self._lock:
            if any(not r["done"] for r in self.runs.values()):
                raise RuntimeError("Finish or abort the active run before patching")
            path = self._path(patch["workflow_id"])
            original = load_workflow(path)
            if digest(original) != patch["old_digest"]:
                raise ValueError("Original workflow changed; propose a fresh diff")
            proposed = validate_document(json.loads(patch["content"]))
            if digest(proposed) != patch["new_digest"]:
                raise ValueError(
                    "Persisted patch content changed; propose a fresh diff"
                )
            if not local_operator:
                self.policy.check_workflow(original)
                if (
                    proposed.application != original.application
                    or proposed.configuration != original.configuration
                    or proposed.workflow.model_dump(mode="json")
                    != original.workflow.model_dump(mode="json")
                ):
                    raise PermissionDenied(
                        "Executable changes need local operator approval"
                    )
            self.policy.check_workflow(proposed, require_approval=False)
            backup = self.state_root / "originals" / f"{patch_id}.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(path.read_bytes())
            write_json(path, json.loads(patch["content"]))
            if patch["new_digest"] not in self.policy.approved_workflow_digests:
                self.policy.approved_workflow_digests.append(patch["new_digest"])
            self._patches.pop(patch_id, None)
        return {
            "approved": True,
            "digest": patch["new_digest"],
            "original_preserved": True,
        }
