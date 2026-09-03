"""Cooperative controls and receipts around Flow's unchanged interpreter."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openadapt_flow.ir import Step, StepResult, Workflow
from openadapt_flow.runtime.authorization import runtime_params_for_gui
from openadapt_flow.runtime.program_predicates import evaluate_program_predicate
from openadapt_flow.runtime.replayer import Replayer

ReceiptSink = Callable[[dict[str, Any]], None]


def resume_from_checkpoint(
    run_dir: Path, replayer: "ControlledReplayer", *, approval: Any
) -> Any:
    """Resume through Flow's exact-bundle, approval and effect revalidation gate.

    The caller must rebuild the same authorized providers and obtain an explicit
    operator ApprovalRecord. No approval is issued here. A rejected/aborted run,
    changed bundle, changed parameters or divergent retained effects is refused.
    """
    from openadapt_flow.runtime.durable.resume import resume

    return resume(run_dir, replayer, approval=approval)


class RunControl:
    """Pause only between actions; finish current delivery verification first.

    An abort is irreversible for this run instance. No thread is killed, no key is
    left intentionally held, and no already-delivered operation is blindly retried.
    """

    def __init__(self, *, initially_paused: bool = False) -> None:
        self._condition = threading.Condition()
        self._paused = initially_paused
        self._aborted = False
        self._permits = 0
        self._active = False
        self._finished = False
        self._step_id: str | None = None
        self._completed = 0

    def pause(self) -> dict[str, Any]:
        with self._condition:
            if self._finished:
                return self.status()
            self._paused = True
            self._permits = 0
            return self.status()

    def resume(self) -> dict[str, Any]:
        with self._condition:
            if self._aborted:
                raise RuntimeError("An aborted run cannot be resumed")
            if self._finished:
                return self.status()
            self._paused = False
            self._permits = 0
            self._condition.notify_all()
            return self.status()

    def step(self) -> dict[str, Any]:
        with self._condition:
            if self._aborted or self._finished:
                raise RuntimeError("A terminal run cannot be stepped")
            if self._active:
                raise RuntimeError("Wait for the active step to finish before stepping")
            self._paused = True
            self._permits = 1
            self._condition.notify_all()
            return self.status()

    def abort(self) -> dict[str, Any]:
        with self._condition:
            if self._finished:
                return self.status()
            self._aborted = True
            self._condition.notify_all()
            return self.status()

    def before_step(self, step_id: str) -> bool:
        with self._condition:
            self._step_id = step_id
            while self._paused and self._permits == 0 and not self._aborted:
                self._condition.wait(0.1)
            if self._aborted:
                return False
            self._permits = max(0, self._permits - 1)
            self._active = True
            return True

    def after_step(self, verified: bool) -> None:
        with self._condition:
            self._active = False
            if verified:
                self._completed += 1
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self._active = False
            self._finished = True
            self._condition.notify_all()

    @property
    def aborted(self) -> bool:
        with self._condition:
            return self._aborted

    def status(self) -> dict[str, Any]:
        with self._condition:
            state = (
                "aborting"
                if self._aborted and self._active
                else "aborted"
                if self._aborted
                else "finished"
                if self._finished
                else "pausing"
                if self._paused and self._active
                else "running"
                if self._active or not self._paused
                else "paused"
            )
            return {
                "state": state,
                "current_step": self._step_id,
                "completed_steps": self._completed,
                "active_action": self._active,
                "pause_requested": self._paused,
                "abort_requested": self._aborted,
            }


def redact(value: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(
                word in str(key).lower()
                for word in ("secret", "password", "token", "cookie", "credential")
            )
            else redact(item, secrets=secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


class NoGuiBackend:
    """Provider-only boundary: never fabricate screenshot evidence."""

    viewport = (1, 1)

    def screenshot(self) -> bytes:
        raise RuntimeError("This tool-only workflow has no pixel observation backend")

    def click(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Direct GUI operations require an explicit backend")

    type_text = click
    press = click
    scroll = click


class _ParameterOnlyObservation:
    """No image exists for a decision whose guards only read parameters.

    Flow 1.34 requests a settled frame even for this case, then explicitly excludes
    it from evidence. Delegate every other method and never service visual guards.
    """

    def __init__(self, vision: Any) -> None:
        self._vision = vision

    def wait_settled(self, backend: Any) -> bytes:
        return b""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._vision, name)


class ControlledReplayer(Replayer):
    """Extend the existing action boundary without replacing Flow semantics."""

    def __init__(
        self,
        backend: Any = None,
        *,
        control: RunControl | None = None,
        receipt_sink: ReceiptSink | None = None,
        **kwargs: Any,
    ) -> None:
        self.control = control or RunControl()
        self.receipt_sink = receipt_sink
        # Tool-only execution never needs OCR. An explicit backend retains the
        # upstream default local vision module unless the caller supplies one.
        if backend is None:
            backend = NoGuiBackend()
        super().__init__(backend, **kwargs)

    def run(self, workflow: Workflow, **kwargs: Any) -> Any:
        from l1ght5p33d.workflow import reject_credential_parameters

        try:
            reject_credential_parameters(workflow, kwargs.get("params"))
            return super().run(workflow, **kwargs)
        finally:
            self.control.finish()

    def _select_transition(self, state: Any, **kwargs: Any) -> Any:
        if any(self._program_guard_uses_frame(t.guard) for t in state.transitions):
            return super()._select_transition(state, **kwargs)
        original = self.vision
        self.vision = _ParameterOnlyObservation(original)
        try:
            return super()._select_transition(state, **kwargs)
        finally:
            self.vision = original

    def _predicate_holds(
        self,
        pred: Any,
        frame_png: bytes,
        bundle_dir: Path,
        params: Mapping[str, Any],
        *,
        workflow: Workflow | None = None,
    ) -> bool:
        if isinstance(
            self.vision, _ParameterOnlyObservation
        ) and not self._program_guard_uses_frame(pred):
            return evaluate_program_predicate(
                pred,
                b"",
                runtime_params_for_gui(params),
                vision=self.vision,
                viewport=(0, 0),
                asset_loader=lambda rel: b"",
            )
        return super()._predicate_holds(
            pred, frame_png, bundle_dir, params, workflow=workflow
        )

    def _run_step(
        self,
        step: Step,
        *,
        workflow: Workflow,
        step_index: int,
        params: Mapping[str, Any],
        bundle_dir: Path,
        run_dir: Path,
        new_crops: dict[str, bytes],
        graph_ctx: Any = None,
    ) -> StepResult:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        permitted = self.control.before_step(step.id)
        if self.api_actuator is not None and hasattr(self.api_actuator, "last_receipt"):
            self.api_actuator.last_receipt = {}
        if not permitted:
            result = StepResult(
                step_id=step.id,
                intent=step.intent,
                ok=False,
                delivery_attempted=False,
                safety_halt=True,
                failure_category="continuation_preempted",
                error="Run aborted before this step; no input delivered",
            )
        else:
            result = super()._run_step(
                step,
                workflow=workflow,
                step_index=step_index,
                params=params,
                bundle_dir=bundle_dir,
                run_dir=run_dir,
                new_crops=new_crops,
                graph_ctx=graph_ctx,
            )
            if self.control.aborted and result.ok:
                result.ok = False
                result.safety_halt = True
                result.failure_category = "continuation_preempted"
                result.error = (
                    "Abort requested during delivery; this step's verification finished. "
                    "Inspect the receipt before continuing; do not repeat the action."
                )
        self.control.after_step(result.ok)
        binding = step.api_binding
        provider_receipt = (
            getattr(self.api_actuator, "last_receipt", {}) if permitted else {}
        )
        receipt = {
            "timestamp": started,
            "duration_ms": round((time.monotonic() - t0) * 1000, 3),
            "workflow_id": workflow.name,
            "step_id": step.id,
            "step_index": step_index,
            "application": binding.url_template if binding else workflow.surface,
            "requested_action": binding.method if binding else step.action.value,
            "variables": dict(params),
            "selector_chain": provider_receipt.get("selector_chain", []),
            "selector_method": provider_receipt.get(
                "selector_method", result.actuation
            ),
            "confidence": provider_receipt.get("confidence"),
            "window": provider_receipt.get(
                "window", provider_receipt.get("application")
            ),
            "retry_count": provider_receipt.get("retry_count", 0),
            "fallback_used": provider_receipt.get("fallback_used", False),
            "input_delivered": result.delivery_attempted,
            "result": "verified" if result.ok else "halted",
            "verification": {
                "effect_verified": result.effect_verified,
                "postconditions_ok": result.postconditions_ok,
                "evidence": [e.model_dump(mode="json") for e in result.effect_evidence],
                "details": result.effect_results,
            },
            "checkpoint_created": False,
            "checkpoint_policy": "Flow durable layer records after this result",
            "recovery_decision": "continue" if result.ok else "inspect_before_resume",
            "error_classification": result.failure_category,
            "error": result.error,
            "provider_receipt": provider_receipt,
        }
        secret_values = tuple(
            str(value)
            for name, value in params.items()
            if name in workflow.secret_params
            or any(
                word in name.lower()
                for word in ("secret", "password", "token", "credential")
            )
        )
        if self.receipt_sink:
            try:
                self.receipt_sink(redact(receipt, secrets=secret_values))
            except Exception:
                result.ok = False
                result.safety_halt = True
                result.failure_category = "runtime_failure"
                result.error = "Execution receipt could not be persisted; inspect state before resuming"
        return result
