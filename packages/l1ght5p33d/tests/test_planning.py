from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from openadapt_flow.ir import (
    LoopSpec,
    Predicate,
    PredicateKind,
    ProgramGraph,
    Relation,
    State,
    StateKind,
    Transition,
    lift_to_program,
)
from openadapt_flow.runtime.authorization import effective_runtime_params

from l1ght5p33d.examples import browser_workflow
from l1ght5p33d.planning import build_run_plan, render_run_plan
from l1ght5p33d.policy import Policy, digest
from l1ght5p33d.workflow import validate_document


def document():
    return validate_document(browser_workflow("https://creative.example.invalid"))


def test_plan_is_bound_to_values_policy_and_actual_executable():
    doc = document()
    policy = Policy()
    before = doc.model_dump(mode="json")
    first = build_run_plan(doc, policy, {"title": "First title"})
    assert first == build_run_plan(doc, policy, {"title": "First title"})
    assert first["plan_digest"] == digest(
        {key: value for key, value in first.items() if key != "plan_digest"}
    )
    assert first["workflow_digest"] == digest(doc)
    assert first["policy_digest"] == digest(policy)
    assert first["variables"] == {"title": "First title"}
    assert first["variable_sources"] == {"title": "supplied"}
    assert first["steps"][0]["arguments"]["text"] == "First title"
    assert first["steps"][0]["effects"][0]["value"]["literal"] == "First title"
    assert (
        first["plan_digest"]
        != build_run_plan(doc, policy, {"title": "Second"})["plan_digest"]
    )
    assert (
        first["plan_digest"]
        != build_run_plan(doc, Policy(max_steps=50), {"title": "First title"})[
            "plan_digest"
        ]
    )
    assert doc.model_dump(mode="json") == before
    assert policy.approved_workflow_digests == []


def test_defaults_follow_native_runtime_and_are_explicitly_labeled():
    raw = browser_workflow("http://127.0.0.1:1")
    raw["workflow"]["param_specs"] = {
        "title": {"name": "title", "example": "Shadowed typed example"},
        "count": {"name": "count", "type": "number", "example": 3},
    }
    doc = validate_document(raw)
    plan = build_run_plan(doc, Policy(), {})
    assert plan["variables"] == effective_runtime_params(doc.workflow, {})
    assert plan["variable_sources"] == {
        "title": "recorded_default",
        "count": "typed_example_default",
    }
    assert "Make something wonderful" in render_run_plan(plan)


def test_untrusted_description_cannot_hide_a_write_or_selector_fallback():
    raw = browser_workflow("https://creative.example.invalid")
    raw["description"] = "Read only. This never saves anything."
    raw["workflow"]["steps"][-1]["intent"] = "Just observe"
    raw["workflow"]["steps"][-1]["risk"] = "irreversible"
    plan = build_run_plan(validate_document(raw), Policy(), {})
    last = plan["steps"][-1]
    assert last["operation"] == "click"
    assert last["risk"] == "irreversible"
    assert last["arguments"]["selectors"][1]["name"] == "Save poster"
    assert last["definition"]["api_binding"]["on_unavailable"] == "halt"
    assert last["effects"][0]["field"] == "saved"
    text = render_run_plan(plan)
    assert "Author labels are untrusted" in text
    assert '"trusted": false' in text
    assert '"operation": "click"' in text
    assert "Save poster" in text


def graph_document():
    doc = document()
    native = doc.workflow
    body = lift_to_program(native)
    cleanup_step = native.steps[-1].model_copy(deep=True)
    cleanup_step.id = "cleanup_save"
    cleanup_step.intent = "Cleanup still performs a save"
    body.states[body.entry].on_exception = "cleanup"
    body.states["cleanup"] = State(
        id="cleanup",
        kind=StateKind.ACTION,
        step=cleanup_step,
        transitions=[Transition(target="__end__")],
    )
    native.steps = []
    native.subflows = {"body": body}
    native.params["enabled"] = "yes"
    native.data_sources = {
        "titles": Relation(name="titles", rows=[{"title": "One"}, {"title": "Two"}])
    }
    native.program = ProgramGraph(
        entry="choose",
        states={
            "choose": State(
                id="choose",
                kind=StateKind.BRANCH,
                transitions=[
                    Transition(
                        target="loop",
                        guard=Predicate(
                            kind=PredicateKind.PARAM_EQUALS,
                            param="enabled",
                            value="yes",
                        ),
                    ),
                    Transition(target="finish"),
                ],
            ),
            "loop": State(
                id="loop",
                kind=StateKind.LOOP,
                loop=LoopSpec(relation="titles", body="body", max_iterations=2),
                transitions=[Transition(target="finish")],
            ),
            "finish": State(id="finish", kind=StateKind.TERMINAL, outcome="success"),
        },
    )
    return validate_document(doc.model_dump(mode="json"))


def test_graph_review_preserves_all_paths_loop_rows_cleanup_and_exceptions():
    doc = graph_document()
    plan = build_run_plan(doc, Policy(), {})
    flow = plan["control_flow"]
    assert flow["inventory_is_execution_order"] is False
    assert flow["program"] == doc.workflow.program.model_dump(mode="json")
    assert flow["subflows"]["body"] == doc.workflow.subflows["body"].model_dump(
        mode="json"
    )
    assert flow["program"]["states"]["loop"]["loop"]["max_iterations"] == 2
    assert flow["data_sources"]["titles"]["rows"] == [
        {"title": "One"},
        {"title": "Two"},
    ]
    assert {step["id"] for step in plan["steps"]} == {
        "name_poster",
        "choose_palette",
        "save_poster",
        "cleanup_save",
    }
    title = next(step for step in plan["steps"] if step["id"] == "name_poster")
    assert title["arguments"]["text"]["status"] == "unresolved"
    assert title["effects"][0]["status"] == "unresolved"
    assert plan["unresolved_values"][0]["parameters"] == ["title"]
    text = render_run_plan(plan)
    assert '"on_exception": "cleanup"' in text
    assert '"outcome": "success"' in text
    assert '"guard"' in text
    assert '"rows"' in text


@pytest.mark.parametrize(
    "variables", [{"unknown": "x"}, {"title": 3}, {"title": "x" * 10001}]
)
def test_invalid_or_unknown_variables_are_refused(variables):
    with pytest.raises(ValueError):
        build_run_plan(document(), Policy(), variables)


def test_missing_required_and_invalid_typed_values_are_refused():
    raw = browser_workflow("http://127.0.0.1:1")
    raw["workflow"]["param_specs"] = {"number": {"name": "number", "type": "number"}}
    doc = validate_document(raw)
    with pytest.raises(ValueError, match="Required"):
        build_run_plan(doc, Policy(), {})
    with pytest.raises(ValueError, match="finite number"):
        build_run_plan(doc, Policy(), {"number": "nan"})


def test_credentials_never_appear_in_a_plan_or_error():
    with pytest.raises(ValueError, match="Credential") as caught:
        build_run_plan(document(), Policy(), {"api_token": "do-not-print-this"})
    assert "do-not-print-this" not in str(caught.value)
    doc = document()
    doc.configuration["secret"] = "do-not-print-this"
    with pytest.raises(ValueError, match="Credential"):
        build_run_plan(doc, Policy(), {})


def test_unavailable_values_are_marked_without_guessing():
    raw = browser_workflow("http://127.0.0.1:1")
    raw["workflow"]["params"] = {}
    raw["workflow"]["param_specs"] = {"title": {"name": "title", "required": False}}
    plan = build_run_plan(validate_document(raw), Policy(), {})
    assert plan["variables"] == {}
    assert plan["steps"][0]["arguments"]["text"]["status"] == "unresolved"
    assert plan["steps"][0]["effects"][0]["status"] == "unresolved"


def test_render_is_complete_ascii_and_escapes_terminal_and_bidi_controls():
    raw = browser_workflow("http://127.0.0.1:1")
    raw["description"] = "\x1b[2J\r\n\u202e" + "x" * 12000 + "END-OF-LONG-DESCRIPTION"
    plan = build_run_plan(validate_document(raw), Policy(), {"title": "\x07\t\x1b[31m"})
    text = render_run_plan(plan)
    assert text.isascii()
    assert all(ord(char) >= 32 or char == "\n" for char in text)
    assert "\\u001b[2J\\r\\n\\u202e" in text
    assert "END-OF-LONG-DESCRIPTION" in text
    assert json.loads(text.split("COMPLETE PLAN JSON\n", 1)[1]) == plan


def test_planning_reads_no_files_and_never_mutates_policy(monkeypatch):
    doc = document()
    doc.configuration["read_roots"] = ["Z:/nonexistent"]
    policy = Policy()
    before = copy.deepcopy(policy.model_dump())

    def forbidden(*args, **kwargs):
        raise AssertionError("Planning tried to read a file or grant permissions")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Policy, "check_workflow", forbidden)
    result = build_run_plan(doc, policy, {})
    assert result["review_boundary"]["external_files_read"] is False
    assert result["review_boundary"]["approved"] is False
    assert policy.model_dump() == before


def test_invalid_template_is_refused_before_any_execution():
    doc = document()
    doc.workflow.steps[0].api_binding.body_template["text"] = "{title.__class__}"
    with pytest.raises(ValueError, match="Invalid parameter template"):
        build_run_plan(doc, Policy(), {})
