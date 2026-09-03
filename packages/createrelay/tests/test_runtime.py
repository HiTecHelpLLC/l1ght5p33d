from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from openadapt_flow.ir import ActionKind, ApiBinding, Step, Workflow
from openadapt_flow.runtime.actuators import ActuationStatus
from openadapt_flow.runtime.effects.effect import Effect, EffectKind

from createrelay.providers.base import ProviderRefused, ProviderVerifier, ToolActuator
from createrelay.runtime import ControlledReplayer, RunControl


class CounterProvider:
    name = "counter"
    operations = frozenset({"increment"})
    effect_tier = 1

    def __init__(self, path: Path):
        self.path = path
        path.write_text('{"count":0}', encoding="ascii")
        self.deliveries = 0
        self.fail_after_write = False
        self.refuse_at_delivery = 0

    def execute(self, operation, args):
        if args.get("refuse") or self.refuse_at_delivery == self.deliveries + 1:
            raise ProviderRefused("explicit pre-delivery refusal")
        count = self.inspect()["count"] + 1
        self.deliveries += 1
        self.path.write_text(json.dumps({"count": count}), encoding="ascii")
        if self.fail_after_write:
            raise RuntimeError("lost result after commit")
        return {"selector_method": "official_api", "count": count}

    def inspect(self):
        return json.loads(self.path.read_text(encoding="ascii"))

    def close(self):
        pass


def make_workflow(count=2, expected_offset=0):
    return Workflow(
        name="counter",
        steps=[
            Step(
                id=f"increment_{n}",
                intent="Increment the local fixture",
                action=ActionKind.WAIT,
                api_binding=ApiBinding(
                    kind="tool",
                    method="increment",
                    url_template="counter",
                    on_unavailable="halt",
                    effects=[
                        Effect(
                            kind=EffectKind.FIELD_EQUALS,
                            match={"provider": "counter"},
                            field="count",
                            value=str(n + expected_offset),
                            timeout_s=0.02,
                        )
                    ],
                ),
            )
            for n in range(1, count + 1)
        ],
    )


def runtime(tmp_path, *, control=None, sink=None):
    provider = CounterProvider(tmp_path / "store.json")
    registry = {"counter": provider}
    player = ControlledReplayer(
        control=control,
        receipt_sink=sink,
        api_actuator=ToolActuator(registry),
        effect_verifier=ProviderVerifier(registry, poll_interval_s=0.001),
        durable=True,
    )
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    return provider, player, dict(bundle_dir=bundle, run_dir=tmp_path / "run")


def until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for control state")
        time.sleep(0.01)


def run(player, workflow, kwargs, **extra):
    workflow.save(kwargs["bundle_dir"])
    return player.run(workflow, **kwargs, **extra)


def test_real_flow_runs_provider_and_checks_independent_file(tmp_path):
    receipts = []
    provider, player, kwargs = runtime(tmp_path, sink=receipts.append)
    report = run(player, make_workflow(), kwargs)
    assert report.success, report.model_dump()
    assert provider.deliveries == 2
    assert report.model_calls == 0
    assert all(result.effect_verified for result in report.results)
    assert len(receipts) == 2
    assert receipts[0]["provider_receipt"]["selector_method"] == "official_api"
    assert (tmp_path / "run" / "report.json").exists()


def test_step_pause_resume_and_abort_never_repeat(tmp_path):
    control = RunControl(initially_paused=True)
    provider, player, kwargs = runtime(tmp_path, control=control)
    result = []
    thread = threading.Thread(
        target=lambda: result.append(run(player, make_workflow(3), kwargs))
    )
    thread.start()
    until(lambda: control.status()["current_step"] == "increment_1")
    assert provider.deliveries == 0
    control.step()
    until(lambda: control.status()["current_step"] == "increment_2")
    assert control.status()["state"] == "paused"
    assert provider.deliveries == 1
    control.abort()
    thread.join(5)
    assert not thread.is_alive()
    assert provider.deliveries == 1
    assert result and not result[0].success
    assert result[0].results[-1].delivery_attempted is False
    with pytest.raises(RuntimeError):
        control.resume()


def test_resume_releases_waiting_run(tmp_path):
    control = RunControl(initially_paused=True)
    provider, player, kwargs = runtime(tmp_path, control=control)
    thread = threading.Thread(target=lambda: run(player, make_workflow(), kwargs))
    thread.start()
    until(lambda: control.status()["current_step"] == "increment_1")
    control.resume()
    thread.join(5)
    assert provider.deliveries == 2
    assert not thread.is_alive()


def test_failed_effect_halts_before_next_action(tmp_path):
    provider, player, kwargs = runtime(tmp_path)
    report = run(player, make_workflow(expected_offset=5), kwargs)
    assert not report.success
    assert provider.deliveries == 1
    assert report.results[0].effect_verified is False


def test_delivery_uncertainty_does_not_repeat(tmp_path):
    provider, player, kwargs = runtime(tmp_path)
    provider.fail_after_write = True
    report = run(player, make_workflow(), kwargs)
    assert not report.success
    assert provider.deliveries == 1


def test_registry_policy_and_template_fail_closed(tmp_path):
    provider = CounterProvider(tmp_path / "store.json")
    actuator = ToolActuator(
        {"counter": provider},
        policy_check=lambda *args: (_ for _ in ()).throw(PermissionError()),
    )
    binding = make_workflow().steps[0].api_binding
    result = actuator.actuate(binding, {})
    assert result.status is ActuationStatus.UNAVAILABLE
    assert provider.deliveries == 0
    actuator.policy_check = None
    binding.body_template = {"refuse": True}
    assert actuator.actuate(binding, {}).status is ActuationStatus.UNAVAILABLE
    binding.body_template = {"value": "{x.__class__}"}
    assert actuator.actuate(binding, {"x": 1}).status is ActuationStatus.UNAVAILABLE


def test_ui_provider_never_claims_independent_evidence(tmp_path):
    provider, player, kwargs = runtime(tmp_path)
    provider.effect_tier = 4
    report = run(player, make_workflow(), kwargs)
    assert report.success
    assert report.execution_outcome != "VERIFIED"
    assert int(player.effect_verifier.verification_tier) == 4


def test_credential_parameters_refused_before_durable_persistence(tmp_path):
    receipts = []
    _, player, kwargs = runtime(tmp_path, sink=receipts.append)
    workflow = make_workflow(1)
    with pytest.raises(ValueError, match="Credential parameters"):
        run(player, workflow, kwargs, params={"api_token": "sensitive-test-value"})
    assert "sensitive-test-value" not in json.dumps(receipts)
    assert not (tmp_path / "run").exists()


def test_finished_control_does_not_change_into_aborted():
    control = RunControl()
    control.finish()
    assert control.abort()["state"] == "finished"
    assert control.pause()["state"] == "finished"
    assert control.resume()["state"] == "finished"
    assert not control.aborted


def test_receipt_failure_halts_after_single_delivery(tmp_path):
    def fail(_receipt):
        raise OSError("disk full")

    provider, player, kwargs = runtime(tmp_path, sink=fail)
    report = run(player, make_workflow(), kwargs)
    assert not report.success
    assert provider.deliveries == 1


def test_native_graph_loops_conditions_and_parameter_effects(tmp_path):
    from openadapt_flow.ir import (
        LoopSpec,
        Predicate,
        ProgramGraph,
        Relation,
        State,
        Transition,
        lift_to_program,
    )

    provider, player, kwargs = runtime(tmp_path)
    workflow = make_workflow(1)
    workflow.steps[0].api_binding.effects[0].value = {"param": "expected_count"}
    # Normalize through Flow to preserve its typed ValueExpr contract.
    workflow = Workflow.model_validate(workflow.model_dump(mode="json"))
    body = lift_to_program(workflow)
    workflow.steps = []
    workflow.params = {"expected_count": "1", "enabled": "yes"}
    workflow.subflows = {"body": body}
    workflow.data_sources = {
        "counts": Relation(
            name="counts", rows=[{"expected_count": "1"}, {"expected_count": "2"}]
        )
    }
    workflow.program = ProgramGraph(
        entry="choose",
        states={
            "choose": State(
                id="choose",
                kind="branch",
                transitions=[
                    Transition(
                        target="loop",
                        guard=Predicate(
                            kind="param_equals", param="enabled", value="yes"
                        ),
                    ),
                    Transition(target="finish"),
                ],
            ),
            "loop": State(
                id="loop",
                kind="loop",
                loop=LoopSpec(relation="counts", body="body", max_iterations=2),
                transitions=[Transition(target="finish")],
            ),
            "finish": State(id="finish", kind="terminal", outcome="success"),
        },
    )
    report = run(player, workflow, kwargs)
    assert report.success, report.model_dump()
    assert provider.deliveries == 2
    assert all(r.effect_verified for r in report.results)


def test_native_durable_resume_requires_approval_and_revalidates(tmp_path):
    from openadapt_flow.runtime.durable.approval import (
        ApprovalRequired,
        issue_resume_approval,
    )
    from openadapt_flow.runtime.durable.checkpoint import CheckpointStore
    from openadapt_flow.runtime.durable.program_checkpoint import bundle_version
    from openadapt_flow.runtime.durable.resume import resume

    provider, player, kwargs = runtime(tmp_path)
    provider.refuse_at_delivery = 2
    first = run(player, make_workflow(2), kwargs)
    assert not first.success
    assert provider.deliveries == 1
    provider.refuse_at_delivery = 0
    registry = {provider.name: provider}
    recovered = ControlledReplayer(
        api_actuator=ToolActuator(registry), effect_verifier=ProviderVerifier(registry)
    )
    with pytest.raises(ApprovalRequired):
        resume(kwargs["run_dir"], recovered)
    store = CheckpointStore(kwargs["run_dir"])
    manifest = store.read_manifest()
    approval = issue_resume_approval(
        store.read_pending(),
        approver="test-operator",
        resolution="Inspected saved counter; continue once",
        bundle_version=bundle_version(kwargs["bundle_dir"]),
        run_id=manifest.run_id,
        workflow_name=manifest.workflow_name,
        run_dir=kwargs["run_dir"],
    )
    result = resume(kwargs["run_dir"], recovered, approval=approval)
    assert result.success, result.model_dump()
    assert provider.deliveries == 2  # first verified action was not repeated
