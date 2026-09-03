"""Pure, complete run review; planning never approves or executes a workflow."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from openadapt_flow.runtime.authorization import (
    effective_runtime_params,
    runtime_inputs_digest,
)

from l1ght5p33d.policy import Policy, digest
from l1ght5p33d.providers.base import ProviderRefused, substitute
from l1ght5p33d.workflow import (
    WorkflowDocument,
    reject_credential_parameters,
    validate_document,
)

_CREDENTIAL = re.compile(
    r"password|passwd|secret|token|cookie|credential|authorization", re.I
)


def _reject_configuration_credentials(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if item and _CREDENTIAL.search(str(key)):
                raise ValueError("Credential configuration cannot appear in a run plan")
            _reject_configuration_credentials(item)
    elif isinstance(value, list):
        for item in value:
            _reject_configuration_credentials(item)


def _effect_params(value: Any) -> set[str]:
    if isinstance(value, dict):
        names = (
            {value["param"]}
            if set(value) <= {"literal", "param"}
            and isinstance(value.get("param"), str)
            else set()
        )
        for child in value.values():
            names.update(_effect_params(child))
        return names
    if isinstance(value, list):
        return set().union(*(_effect_params(item) for item in value))
    return set()


def build_run_plan(
    document: WorkflowDocument, policy: Policy, variables: dict[str, str]
) -> dict[str, Any]:
    """Describe actual executable declarations without opening files or providers.

    Existing workflow approval is deliberately not required. The service owns
    policy admission and the separate, exact-plan human approval transaction.
    A program's action inventory is NOT a prediction of the path it will take.
    Its complete native graph, relations and contracts remain in the plan.
    """
    document = validate_document(document.model_dump(mode="json"))
    if not isinstance(variables, dict) or any(
        not isinstance(name, str) or not isinstance(value, str) or len(value) > 10000
        for name, value in variables.items()
    ):
        raise ValueError("Variables must be declared names with bounded string values")
    workflow = document.workflow
    reject_credential_parameters(workflow, variables)
    _reject_configuration_credentials(document.configuration)
    known = set(workflow.params) | set(workflow.param_specs)
    unknown = set(variables) - known
    if unknown:
        raise ValueError("Unknown workflow variables: " + ", ".join(sorted(unknown)))
    params = effective_runtime_params(workflow, variables)
    for name, spec in workflow.param_specs.items():
        value = params.get(name)
        if spec.required and (value is None or value == ""):
            raise ValueError("Required workflow variable has no value: " + name)
        if value is None:
            continue
        if spec.type.value == "enum" and spec.choices and value not in spec.choices:
            raise ValueError("Variable is outside its declared choices: " + name)
        if spec.type.value == "number":
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(value))
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                raise ValueError("Variable must be a finite number: " + name)
        if spec.type.value == "boolean" and not (
            isinstance(value, bool)
            or (isinstance(value, str) and value in {"true", "false"})
        ):
            raise ValueError("Variable must be a Boolean or true/false text: " + name)

    native = workflow.model_dump(mode="json")
    graphs = dict(workflow.subflows)
    if workflow.program is not None:
        graphs = {"$program": workflow.program, **graphs}

    # Loop rows and human decision outputs can replace base parameters at run
    # time. Never pretend a base default is the value used in every such scope.
    dynamic: set[str] = set()
    for graph in graphs.values():
        for state in graph.states.values():
            if state.loop is not None:
                relation = workflow.data_sources.get(state.loop.relation)
                if relation is not None:
                    for row in relation.rows:
                        dynamic.update(row)
            decision = state.model_dump(mode="json").get("decision")
            if decision and isinstance(decision.get("output_param"), str):
                dynamic.add(decision["output_param"])
    resolved_scope = {
        name: value for name, value in params.items() if name not in dynamic
    }
    unresolved: list[dict[str, Any]] = []

    def unresolved_value(path: str, names: set[str], template: Any) -> dict[str, Any]:
        item = {
            "path": path,
            "parameters": sorted(names),
            "reason": (
                "Value depends on a loop row or a later human decision"
                if names & dynamic
                else "Value is unavailable in the supplied runtime parameters"
            ),
        }
        unresolved.append(item)
        return {"status": "unresolved", **item, "template": template}

    def arguments(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            return {
                key: arguments(item, f"{path}.{key}") for key, item in value.items()
            }
        if isinstance(value, list):
            return [arguments(item, f"{path}[{i}]") for i, item in enumerate(value)]
        try:
            return substitute(value, resolved_scope)
        except KeyError as exc:
            return unresolved_value(path, {str(exc.args[0])}, value)
        except (ProviderRefused, ValueError) as exc:
            raise ValueError("Invalid parameter template at " + path) from exc

    inventory: list[dict[str, Any]] = []

    def add_step(step: Any, location: str) -> None:
        definition = step.model_dump(mode="json")
        binding = step.api_binding
        effects = []
        for index, effect in enumerate(
            [*step.effects, *(binding.effects if binding is not None else [])]
        ):
            raw = effect.model_dump(mode="json")
            missing = _effect_params(raw) - set(resolved_scope)
            effects.append(
                unresolved_value(f"{location}.effects[{index}]", missing, raw)
                if missing
                else effect.resolve(resolved_scope).model_dump(mode="json")
            )
        inventory.append(
            {
                "id": step.id,
                "location": location,
                "author_intent_untrusted": step.intent,
                "action": step.action.value,
                "provider": binding.url_template if binding is not None else None,
                "operation": binding.method if binding is not None else None,
                "arguments": (
                    arguments(binding.body_template, f"{location}.arguments")
                    if binding is not None
                    else None
                ),
                "effects": effects,
                "risk": definition["risk"],
                "definition": definition,
            }
        )

    for index, step in enumerate(workflow.steps):
        add_step(step, f"workflow.steps[{index}]")
    for graph_name, graph in sorted(graphs.items()):
        for state_name, state in sorted(graph.states.items()):
            if state.step is not None:
                add_step(state.step, f"graphs.{graph_name}.states.{state_name}.step")

    configuration = document.configuration
    selected = configuration.get(document.application, configuration)
    plan: dict[str, Any] = {
        "schema_version": "l1ght5p33d-run-plan/v1",
        "workflow_id": document.id,
        "workflow_digest": digest(document),
        "policy_digest": digest(policy),
        "runtime_version": "1.34.0",
        "runtime_inputs_digest": runtime_inputs_digest(workflow, params, None),
        "application": document.application,
        "configuration": configuration,
        "targets": selected,
        "author_metadata": {
            "trusted": False,
            "description": document.description,
            "workflow_name": workflow.name,
            "note": "Author descriptions are claims; review actual actions and effects below",
        },
        "variables": params,
        "variable_sources": {
            name: (
                "supplied"
                if name in variables
                else "recorded_default"
                if name in workflow.params
                else "typed_example_default"
            )
            for name in sorted(params)
        },
        "steps": inventory,
        "control_flow": {
            "inventory_is_execution_order": (
                workflow.program is None and not workflow.subflows
            ),
            "note": (
                "Declared linear order; guards may skip actions or halt"
                if workflow.program is None
                else "All action declarations, not a predicted path. Review every branch, loop, "
                "subflow, exception edge and terminal in the complete native workflow"
            ),
            "linear_order": [step.id for step in workflow.steps],
            "program": native.get("program"),
            "subflows": native.get("subflows", {}),
            "data_sources": native.get("data_sources", {}),
            "scope_dependent_parameters": sorted(dynamic),
        },
        "unresolved_values": unresolved,
        "includes": document.includes,
        "policy": policy.model_dump(mode="json"),
        "native_workflow": native,
        "review_boundary": {
            "actions_delivered": 0,
            "approved": False,
            "external_files_read": False,
            "file_contents_verified": False,
            "note": "Referenced file paths are declarations; planning does not inspect file contents",
        },
    }
    plan["plan_digest"] = digest(plan)
    # Return detached JSON data, with nonfinite numbers rejected before review.
    return json.loads(json.dumps(plan, ensure_ascii=True, allow_nan=False))


def render_run_plan(plan: dict[str, Any]) -> str:
    """Render every field without truncation or active terminal control text."""
    lines = [
        "RUN PLAN - review the entire plan before approving any execution.",
        "Application: " + json.dumps(plan.get("application"), ensure_ascii=True),
        "Inputs (including defaults): "
        + json.dumps(plan.get("variables", {}), ensure_ascii=True),
        "Startup and cleanup: "
        + json.dumps(plan.get("provider_lifecycle", {}), ensure_ascii=True),
        "Declared steps (conditional paths are detailed below):",
    ]
    for number, step in enumerate(plan.get("steps", []), start=1):
        lines.append(
            f"{number}. "
            + json.dumps(
                {
                    "operation": f"{step.get('provider')}.{step.get('operation')}",
                    "target_and_values": step.get("arguments"),
                    "verify": step.get("effects"),
                },
                ensure_ascii=True,
            )
        )
    return (
        "\n".join(lines) + "\n\nCOMPLETE REVIEW DETAILS\n"
        "Author labels are untrusted. Actual operations, arguments, effects and all\n"
        "control paths are included. Unresolved values are not guessed.\n\nCOMPLETE PLAN JSON\n"
        + json.dumps(plan, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    )
