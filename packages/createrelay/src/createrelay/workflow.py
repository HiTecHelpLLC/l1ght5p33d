"""Strict ASCII envelope around the native OpenAdapt Flow workflow schema."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from openadapt_flow.bundle_validation import validate_workflow as validate_native
from openadapt_flow.ir import Workflow, lift_to_program
from pydantic import BaseModel, ConfigDict, Field


class WorkflowDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["createrelay/v1"] = "createrelay/v1"
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    description: str = ""
    application: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    includes: dict[str, str] = Field(default_factory=dict)
    workflow: Workflow


def reject_credential_parameters(
    workflow: Workflow, values: dict[str, Any] | None = None
) -> None:
    """The preview uses manual authentication and never persists credentials.

    Flow's ordinary durable parameter map is plaintext. Until a creator secret
    reference adapter exists, refuse declared credentials before bundle/run writes.
    """
    sensitive = re.compile(
        r"password|passwd|secret|token|cookie|credential|authorization", re.I
    )

    def contains_credentials(node: Any) -> bool:
        if isinstance(node, dict):
            return any(
                (bool(value) and sensitive.search(str(key)))
                or contains_credentials(value)
                for key, value in node.items()
            )
        if isinstance(node, list):
            return any(contains_credentials(item) for item in node)
        return False

    names = set(workflow.params) | set(workflow.param_specs) | set(values or {})
    if (
        workflow.secret_params
        or any(
            bool(getattr(spec, "secret", False))
            for spec in workflow.param_specs.values()
        )
        or any(sensitive.search(name) for name in names)
        or contains_credentials(workflow.model_dump(mode="json"))
    ):
        raise ValueError(
            "Credential parameters are unavailable; authenticate manually in the dedicated application"
        )


def all_steps(workflow: Workflow) -> list[Any]:
    if workflow.program is None:
        return list(workflow.steps)
    return [
        state.step
        for graph in [workflow.program, *workflow.subflows.values()]
        for state in graph.states.values()
        if state.step is not None
    ]


def _strict_schema(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node.setdefault("additionalProperties", False)
        for child in node.values():
            _strict_schema(child)
    elif isinstance(node, list):
        for child in node:
            _strict_schema(child)


_SCHEMA = WorkflowDocument.model_json_schema()
_strict_schema(_SCHEMA)
# Flow intentionally accepts bare strings for effect ValueExpr values in
# hand-authored workflows. Its generated schema describes only the normalized
# object representation, so document that existing input compatibility here.
_SCHEMA["$defs"]["ValueExpr"] = {
    "anyOf": [_SCHEMA["$defs"]["ValueExpr"], {"type": "string"}]
}
_VALIDATOR = Draft202012Validator(_SCHEMA)


def workflow_schema() -> dict[str, Any]:
    return json.loads(json.dumps(_SCHEMA))


def validate_document(
    data: dict[str, Any], *, _allow_unresolved_includes: bool = False
) -> WorkflowDocument:
    if not isinstance(data, dict):
        raise ValueError("Workflow document must be a JSON object")
    data = copy.deepcopy(data)
    if isinstance(data.get("workflow"), dict):
        data["workflow"].setdefault("created_at", "1970-01-01T00:00:00+00:00")
    errors = sorted(_VALIDATOR.iter_errors(data), key=lambda error: str(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "document"
        raise ValueError(f"Invalid workflow at {location}: {first.message}")
    doc = WorkflowDocument.model_validate(data)
    reject_credential_parameters(doc.workflow)
    if doc.workflow.schema_version != 2:
        raise ValueError("CreateRelay v1 requires native Flow schema_version 2")
    if doc.workflow.program is not None and doc.workflow.steps:
        raise ValueError("Use either a program graph or linear steps, not both")
    steps = all_steps(doc.workflow)
    if not steps and not (_allow_unresolved_includes and doc.includes):
        raise ValueError("Workflow must contain an executable action")
    if not (_allow_unresolved_includes and doc.includes):
        report = validate_native(doc.workflow)
        structural_errors = report.by_category("structure")
        if structural_errors:
            raise ValueError("Invalid Flow program: " + structural_errors[0].render())
    ids = [step.id for step in steps]
    if len(ids) != len(set(ids)):
        raise ValueError(
            "Step identifiers must be unique across the workflow and subflows"
        )
    for step in steps:
        binding = step.api_binding
        if binding is None:
            if step.action.value not in {"wait"} and step.anchor is None:
                raise ValueError(
                    f"Step {step.id} must have an anchored selector or tool binding"
                )
            if not step.expect and not step.effects:
                raise ValueError(
                    f"Step {step.id} requires an explicit verification contract"
                )
            continue
        if (
            binding.kind != "tool"
            or binding.on_unavailable != "halt"
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", binding.url_template)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", binding.method)
            or binding.headers
            or binding.query
        ):
            raise ValueError(
                f"Step {step.id} must use a named fail-closed provider tool"
            )
        if not binding.effects:
            raise ValueError(f"Step {step.id} requires api_binding.effects")
        if any(
            effect.match.get("provider") != binding.url_template
            for effect in binding.effects
        ):
            raise ValueError(
                f"Step {step.id} effects must identify the invoked provider"
            )
    return doc


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_workflow(
    path: Path | str, *, _seen: frozenset[Path] = frozenset()
) -> WorkflowDocument:
    path = Path(path).resolve(strict=True)
    if path in _seen or len(_seen) >= 8:
        raise ValueError("Workflow include cycle or nesting limit reached")
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("Workflow exceeds the 2 MB size limit")
    try:
        data = json.loads(raw.decode("ascii"), object_pairs_hook=_unique_pairs)
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Workflow must be ASCII text; use JSON Unicode escapes"
        ) from exc
    doc = validate_document(data, _allow_unresolved_includes=True)
    for name, relative in doc.includes.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
            raise ValueError("Include names must be simple identifiers")
        if Path(relative).is_absolute():
            raise ValueError("Includes must be relative to the workflow folder")
        target = (path.parent / relative).resolve(strict=True)
        if not target.is_relative_to(path.parent):
            raise ValueError("Include escapes the workflow folder")
        imported = load_workflow(target, _seen=_seen | {path})
        if (
            imported.application != doc.application
            or imported.configuration != doc.configuration
        ):
            raise ValueError("Includes cannot change application or configuration")
        if imported.workflow.subflows:
            raise ValueError(
                "An included workflow must be self-contained without nested subflows"
            )
        if name in doc.workflow.subflows:
            raise ValueError(f"Include name already exists: {name}")
        doc.workflow.subflows[name] = imported.workflow.program or lift_to_program(
            imported.workflow
        )
    return validate_document(doc.model_dump(mode="json"))


def document_digest(document: WorkflowDocument) -> str:
    raw = json.dumps(
        document.model_dump(mode="json"), sort_keys=True, ensure_ascii=True
    )
    return hashlib.sha256(raw.encode("ascii")).hexdigest()
