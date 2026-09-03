"""Registry and run lifecycle shared by the local CLI and MCP interface."""

from __future__ import annotations

import difflib
import hashlib
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

from l1ght5p33d.approvals import RunPlanStore
from l1ght5p33d.discovery import DiscoveryConfig, WorkflowDiscovery
from l1ght5p33d.planning import build_run_plan
from l1ght5p33d.policy import PermissionDenied, Policy, digest, redact
from l1ght5p33d.providers.base import ProviderVerifier, ToolActuator, substitute
from l1ght5p33d.runtime import ControlledReplayer, RunControl
from l1ght5p33d.workflow import (
    WorkflowDocument,
    all_steps,
    load_workflow,
    reject_credential_parameters,
    validate_document,
)


def local_home() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "L1ght5p33d"
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=True), "ascii")
    temp.replace(path)


class WorkflowService:
    def __init__(
        self,
        workflow_root: Path,
        policy: Policy,
        *,
        state_root: Path | None = None,
        discovery: DiscoveryConfig | None = None,
        cache_retention_days: int = 90,
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
        self.plans = RunPlanStore(self.state_root)
        self.discovery = WorkflowDiscovery(discovery or DiscoveryConfig(), self.root)
        from l1ght5p33d.companion import Companion

        self.review_base_url = "http://127.0.0.1:7331"
        self.companion = Companion(self, cache_retention_days)

    def search_curated_workflows(
        self, query: str, application: str | None = None
    ) -> list[dict[str, Any]]:
        return self.companion.source.search(query, application)

    def prepare_task(
        self,
        workflow_id: str,
        version: str,
        variables: dict[str, str] | None = None,
        source: str = "thebest",
    ) -> dict[str, Any]:
        """Resolve and fetch a reviewed pack, then hand the exact plan to its user."""
        with self._lock:
            if source != "thebest":
                raise ValueError("Use a configured catalog import for other sources")
            downloaded = self.download_workflow(source, workflow_id, version)
            self.set_workflow_variables(workflow_id, variables or {})
            record = self.companion.issue_review(self.prepare_workflow_run(workflow_id))
            return {**record, "download": downloaded, "approval_required": True}

    def get_cache_status(self) -> dict[str, Any]:
        return self.companion.cache.status()

    def get_task_status(self, plan_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get_run_plan(plan_id)
            run = next((r for r in self.runs.values() if r["plan_id"] == plan_id), None)
            return {
                "plan_id": plan_id,
                "status": record["status"],
                "execution": self.get_execution_status(run["run_id"]) if run else None,
            }

    def get_review_plan(self, plan_id: str, review_token: str) -> dict[str, Any]:
        with self._lock:
            record = self.companion.authorize(plan_id, review_token)
            result = dict(record)
            run_id = self.companion.reviews[plan_id]["run_id"]
            if run_id:
                result.update(
                    status=self.runs[run_id]["status"],
                    execution=self.get_execution_status(run_id),
                )
            else:
                self.companion.check_current(record)
                result["workflow_content"] = self._path(
                    record["plan"]["workflow_id"]
                ).read_text("ascii")
            return result

    def approve_review_plan(
        self, plan_id: str, review_token: str, expected_digest: str
    ) -> dict[str, Any]:
        with self._lock:
            record = self.companion.authorize(plan_id, review_token, expected_digest)
            self.approve_run_plan(plan_id, expected_digest, local_operator=True)
            run = self.run_workflow(record["plan"]["workflow_id"], plan_id=plan_id)
            self.companion.reviews[plan_id]["run_id"] = run["run_id"]
            self.companion.release_review_lease(plan_id)
            return run

    def update_review_variables(
        self,
        plan_id: str,
        review_token: str,
        variables: dict[str, str],
        expected_digest: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self.companion.authorize(plan_id, review_token, expected_digest)
            workflow_id = record["plan"]["workflow_id"]
            self.set_workflow_variables(workflow_id, variables)
            fresh = self.companion.issue_review(self.prepare_workflow_run(workflow_id))
            self.companion.revoke(plan_id)
            return fresh

    def update_review_workflow(
        self, plan_id: str, review_token: str, content: str, expected_digest: str
    ) -> dict[str, Any]:
        with self._lock:
            record = self.companion.authorize(plan_id, review_token, expected_digest)
            workflow_id = record["plan"]["workflow_id"]
            patch = self.propose_workflow_patch(workflow_id, content)
            self.approve_workflow_patch(
                patch["patch_id"],
                local_operator=True,
                expected_digest=patch["new_digest"],
            )
            fresh = self.companion.issue_review(self.prepare_workflow_run(workflow_id))
            self.companion.revoke(plan_id)
            return fresh

    def search_workflow_catalog(
        self, query: str, application: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        return self.discovery.search(query, application, limit)

    def download_workflow(
        self, registry_name: str, workflow_id: str, version: str
    ) -> dict[str, Any]:
        with self._lock:
            if any(not run["done"] for run in self.runs.values()):
                raise RuntimeError("Finish or abort the active run before downloading")
            if registry_name == "thebest":
                return self.companion.download(workflow_id, version)
            return self.discovery.stage(registry_name, workflow_id, version)

    def _input_files(
        self,
        doc: WorkflowDocument,
        params: dict[str, Any],
        *,
        arguments: dict[str, Any] | None = None,
        policy: Policy | None = None,
    ) -> list[dict[str, Any]]:
        paths: set[Path] = set()
        file_policy = policy or self.policy

        def resolved(value: Any) -> Any:
            return value if arguments is not None else substitute(value, params)

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("method") == "template":
                    from l1ght5p33d.providers.vision import template_path

                    config = doc.configuration.get(doc.application, doc.configuration)
                    if not config.get("template_root"):
                        raise PermissionDenied(
                            "Template review needs a configured local root"
                        )
                    path = template_path(
                        Path(config["template_root"]),
                        str(resolved(value.get("template", ""))),
                    )
                    paths.add(file_policy.path(path))
                for key, item in value.items():
                    if key in {"file", "path", "filename", "reference_wav"} and item:
                        paths.add(file_policy.path(str(resolved(item))))
                    elif key in {"files", "paths"} and item:
                        for entry in resolved(item):
                            paths.add(file_policy.path(str(entry)))
                    else:
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        if arguments is not None:
            visit(arguments)
        else:
            for step in all_steps(doc.workflow):
                visit(step.api_binding.body_template)
        results = []
        for path in sorted(paths):
            before = path.stat()
            if before.st_size > 4_000_000_000:
                raise PermissionDenied("Input exceeds the 4 GB review limit")
            file_hash = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    file_hash.update(chunk)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise PermissionDenied("Input changed during review; prepare again")
            results.append(
                {
                    "path": str(path),
                    "size": after.st_size,
                    "sha256": file_hash.hexdigest(),
                }
            )
        return results

    def _build_plan(
        self, doc: WorkflowDocument, variables: dict[str, str]
    ) -> dict[str, Any]:
        plan = build_run_plan(doc, self.policy, variables)
        plan["input_files"] = self._input_files(doc, plan["variables"])
        plan["review_boundary"].update(
            external_files_read=bool(plan["input_files"]),
            file_contents_verified=True,
            note="Declared file inputs are hashed locally; content hashes are rechecked before file actions",
        )
        plan["workflow_root"] = str(self.root)
        settings = self._provider_configuration(doc)
        lifecycle = {
            "browser": {
                "startup": "Launch a dedicated browser context, navigate to the configured URL, inspect its identity",
                "cleanup": "Close the owned browser context and stop the browser connection",
            },
            "bandlab": {
                "startup": "When Studio opens, attach or launch the dedicated browser, create a page and navigate to the configured URL",
                "cleanup": "Disconnect and preserve live Studio pages; close the owned browser for fixture runs",
            },
            "windows": {
                "startup": "Attach to the already-open executable and inspect window identity; require foreground before input",
                "cleanup": "Release automation resources; leave the application open",
            },
        }
        plan["provider_lifecycle"] = {
            **lifecycle.get(doc.application, {"startup": "Provider is not installed"}),
            "effective_settings": settings,
        }
        plan["review_blockers"] = (
            [
                "Resolve unavailable or dynamic values before execution; this preview does not "
                "expand every loop/decision scope into a reviewable run"
            ]
            if plan["unresolved_values"]
            else []
        )
        review = self.companion.provenance(doc.id)
        if review:
            plan["workflow_review"] = review
        plan.pop("plan_digest", None)
        plan["plan_digest"] = digest(plan)
        return plan

    def prepare_workflow_run(self, workflow_id: str) -> dict[str, Any]:
        with self._lock:
            doc = load_workflow(self._path(workflow_id))
            self.policy.check_workflow(doc, require_approval=False)
            variables = dict(self.variables.get(workflow_id, {}))
            plan = self._build_plan(doc, variables)
            record = self.plans.prepare(plan, self.root, variables)
            return {
                **record,
                "status": "blocked" if plan["review_blockers"] else "awaiting_approval",
                "actions_delivered": 0,
            }

    def get_run_plan(self, plan_id: str) -> dict[str, Any]:
        record = self.plans.read(plan_id)
        if record["workflow_root"] != str(self.root):
            raise PermissionDenied("Plan belongs to a different workflow library")
        return {
            **record,
            "status": "blocked"
            if record["plan"].get("review_blockers")
            else self.plans.status(plan_id),
        }

    def approve_run_plan(
        self, plan_id: str, expected_digest: str, *, local_operator: bool = False
    ) -> dict[str, Any]:
        if not local_operator:
            raise PermissionDenied(
                "Only the local human review command can approve a run"
            )
        with self._lock:
            record = self.get_run_plan(plan_id)
            doc = load_workflow(self._path(record["plan"]["workflow_id"]))
            self.policy.check_workflow(doc, require_approval=False)
            current = self._build_plan(doc, record["supplied_variables"])
            if current["review_blockers"]:
                raise PermissionDenied(
                    "Unresolved plan values require clarification before approval"
                )
            if current["plan_digest"] != expected_digest:
                raise PermissionDenied(
                    "Inputs, workflow or policy changed; prepare a new plan"
                )
            self.plans.approve(plan_id, expected_digest)
            return {"plan_id": plan_id, "status": "approved", "single_use": True}

    def _local_registry(self) -> dict[str, Path]:
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

    def _registry(self) -> dict[str, Path]:
        entries = self._local_registry()
        for workflow_id in self.companion.selected:
            if workflow_id not in entries:
                try:
                    entries[workflow_id] = self.companion.path(workflow_id)
                except (ValueError, OSError):
                    continue
        return entries

    def _path(self, workflow_id: str) -> Path:
        local = self._local_registry().get(workflow_id)
        if local:
            return local
        if workflow_id in self.companion.selected:
            return self.companion.path(workflow_id)
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
        self.policy.check_workflow(doc, require_approval=False)
        return {"valid": True, "digest": digest(doc), "id": doc.id}

    def inspect_environment(self) -> dict[str, Any]:
        return {
            "os": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "applications": self.policy.applications,
            "screenshots_leave_machine": False,
            "ai_required": False,
            "workflow_schema": "l1ght5p33d/v1",
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

    def _provider_configuration(self, doc: WorkflowDocument) -> dict[str, Any]:
        config = dict(doc.configuration)
        config = dict(config.get(doc.application, config))
        if doc.application == "browser":
            config.setdefault("channel", None)
            config.setdefault("headless", not bool(config.get("profile")))
            config.setdefault("timeout_s", 5)
        if doc.application == "bandlab":
            config.setdefault("mode", "fixture")
            config.setdefault("timeout_ms", 5000)
            if config["mode"] == "live":
                config.setdefault("channel", "msedge")
                config.setdefault("profile", "bandlab")
            else:
                config.setdefault("headless", True)
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
        return config

    def _provider(self, doc: WorkflowDocument) -> Any:
        config = self._provider_configuration(doc)
        if doc.application == "browser":
            from l1ght5p33d.providers.browser import BrowserProvider

            return BrowserProvider(config)
        if doc.application == "bandlab":
            from l1ght5p33d.providers.bandlab import BandLabProvider

            return BandLabProvider(config)
        if doc.application == "windows":
            from l1ght5p33d.providers.windows import WindowsProvider

            return WindowsProvider(config)
        raise ValueError("Provider is not installed")

    def run_workflow(
        self,
        workflow_id: str,
        *,
        step_mode: bool = False,
        dry_run: bool = False,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            key = self.companion.key_for(workflow_id)
            lease = self.companion.cache.acquire(key) if key else None
            try:
                result = self._run_workflow(
                    workflow_id,
                    step_mode=step_mode,
                    dry_run=dry_run,
                    plan_id=plan_id,
                    cache_lease=lease,
                    cache_key=key,
                )
                if "run_id" in result:
                    lease = None  # The execution's finally block now owns the lease.
                return result
            finally:
                if lease:
                    self.companion.cache.release(lease)

    def _run_workflow(
        self,
        workflow_id: str,
        *,
        step_mode: bool = False,
        dry_run: bool = False,
        plan_id: str | None = None,
        cache_lease: str | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        path = self._path(workflow_id)
        doc = load_workflow(path)
        self.policy.check_workflow(doc, require_approval=False)
        if dry_run:
            return {
                "status": "dry_run",
                "actions_delivered": 0,
                **self.describe_workflow(workflow_id),
                "plan": self._build_plan(doc, self.variables.get(workflow_id, {})),
            }
        with self._lock:
            if self._shutting_down:
                raise RuntimeError("Service is shutting down; no new run can start")
            if any(not run["done"] for run in self.runs.values()):
                raise RuntimeError(
                    "Only one active automation run is allowed per service"
                )
            if plan_id is None:
                return self.prepare_workflow_run(workflow_id)
            record = self.get_run_plan(plan_id)
            current_variables = dict(self.variables.get(workflow_id, {}))
            if (
                record["plan"]["workflow_id"] != workflow_id
                or current_variables != record["supplied_variables"]
            ):
                raise PermissionDenied(
                    "Plan identity or variables changed; prepare a new plan"
                )
            current_plan = self._build_plan(doc, current_variables)
            if current_plan["review_blockers"]:
                raise PermissionDenied(
                    "Unresolved plan values require clarification before execution"
                )
            self.plans.consume(plan_id, current_plan["plan_digest"])
            if cache_key:
                # Record the approved execution attempt before any provider can act.
                # A cache failure must not report rejection after launching a run.
                self.companion.cache.touch(cache_key)
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
                "plan_id": plan_id,
                "plan_digest": current_plan["plan_digest"],
                "approved_input_files": current_plan["input_files"],
                "control": control,
                "directory": run_dir,
                "done": False,
                "status": "starting",
                "receipts": [],
                "ui_state": {},
                "error": None,
                "manual_review": [str(note) for note in manual_review],
                "cache_lease": cache_lease,
            }
            self.runs[run_id] = run
            write_json(run_dir / "approved-plan.json", current_plan)
            params = {**doc.workflow.params, **self.variables.get(workflow_id, {})}
            thread = threading.Thread(
                target=self._execute,
                args=(run, doc, path.parent, params, self.policy.model_copy(deep=True)),
                daemon=True,
            )
            run["thread"] = thread
            thread.start()
        return {"run_id": run_id, "status": "starting", "step_mode": step_mode}

    def shutdown(self, timeout_s: float = 60) -> dict[str, Any]:
        """Cancel at the next verified boundary and wait for provider cleanup."""
        deadline = time.monotonic() + min(max(timeout_s, 0), 60)
        with self._lock:
            self._shutting_down = True
            self.companion.close()
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
        policy_snapshot: Policy,
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

            def check_action(name: str, operation: str, args: dict[str, Any]) -> None:
                policy_snapshot.action(name, operation, args)
                expected_files = {
                    entry["path"]: entry for entry in run["approved_input_files"]
                }
                for entry in self._input_files(
                    doc, {}, arguments=args, policy=policy_snapshot
                ):
                    if expected_files.get(entry["path"]) != entry:
                        raise PermissionDenied(
                            "Input file changed or was absent from the approved plan"
                        )

            replayer = ControlledReplayer(
                control=run["control"],
                receipt_sink=receipt_sink,
                api_actuator=ToolActuator(providers, policy_check=check_action),
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
            if run.get("cache_lease"):
                try:
                    self.companion.cache.release(run.pop("cache_lease"))
                except Exception:
                    run["cache_warning"] = (
                        "Cache lease cleanup deferred; execution has stopped"
                    )
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
            "durable_recovery": "Use l1ght5p33d.runtime.resume_from_checkpoint with a fresh provider registry and an operator-reviewed ApprovalRecord; see docs/l1ght5p33d/recovery.md.",
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
        self,
        patch_id: str,
        *,
        local_operator: bool = False,
        expected_digest: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", patch_id):
            raise ValueError("Invalid patch id")
        patch = self._patches.get(patch_id)
        if patch is None and local_operator:
            path = self.state_root / "patches" / f"{patch_id}.json"
            patch = json.loads(path.read_text("ascii")) if path.is_file() else None
        if not patch:
            raise ValueError("Unknown proposed patch")
        if expected_digest is not None and patch["new_digest"] != expected_digest:
            raise PermissionDenied("Patch changed after display; review a fresh diff")
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
            if self.companion.key_for(patch["workflow_id"]):
                # A derivative belongs to the user's library, outside cache expiry.
                # Never transfer the original pack's curator signature to edited bytes.
                path = self.root / f"local-{patch['workflow_id']}.json"
                if path.exists() or path.is_symlink():
                    raise PermissionDenied(
                        "Local derivative destination already exists"
                    )
            write_json(path, json.loads(patch["content"]))
            if patch["new_digest"] not in self.policy.approved_workflow_digests:
                self.policy.approved_workflow_digests.append(patch["new_digest"])
            self._patches.pop(patch_id, None)
        return {
            "approved": True,
            "digest": patch["new_digest"],
            "original_preserved": True,
        }
