import json

import pytest

from createrelay.workflow import load_workflow, validate_document


def document():
    return {
        "schema_version": "createrelay/v1",
        "id": "counter",
        "application": "counter",
        "workflow": {
            "schema_version": 2,
            "name": "counter",
            "steps": [
                {
                    "id": "increment",
                    "intent": "Increment local fixture",
                    "action": "wait",
                    "api_binding": {
                        "kind": "tool",
                        "method": "increment",
                        "url_template": "counter",
                        "on_unavailable": "halt",
                        "effects": [
                            {
                                "kind": "field_equals",
                                "match": {"provider": "counter"},
                                "field": "count",
                                "value": "1",
                            }
                        ],
                    },
                }
            ],
        },
    }


def test_ascii_workflow_uses_native_schema(tmp_path):
    file = tmp_path / "counter.json"
    file.write_text(json.dumps(document()), encoding="ascii")
    loaded = load_workflow(file)
    assert loaded.id == "counter"
    assert loaded.workflow.steps[0].api_binding.method == "increment"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(unrecognized=True),
        lambda d: d["workflow"]["steps"][0].update(unrecognized=True),
        lambda d: d["workflow"]["steps"][0]["api_binding"].update(kind="rest"),
        lambda d: d["workflow"]["steps"][0]["api_binding"].update(effects=[]),
        lambda d: d["workflow"]["steps"][0]["api_binding"].update(
            url_template="https://bad.invalid"
        ),
        lambda d: d["workflow"].update(schema_version=999),
    ],
)
def test_invalid_workflows_fail_before_execution(change):
    data = document()
    change(data)
    with pytest.raises(ValueError):
        validate_document(data)


def test_non_ascii_and_duplicate_keys_refused(tmp_path):
    file = tmp_path / "bad.json"
    file.write_bytes(b'{"description":"\xc3\xa9"}')
    with pytest.raises(ValueError, match="ASCII"):
        load_workflow(file)
    file.write_text('{"id":"one","id":"two"}', encoding="ascii")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_workflow(file)


def test_include_cannot_escape_folder(tmp_path):
    folder = tmp_path / "safe"
    folder.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(document()), encoding="ascii")
    data = document()
    data["includes"] = {"unsafe": "../outside.json"}
    file = folder / "workflow.json"
    file.write_text(json.dumps(data), encoding="ascii")
    with pytest.raises(ValueError, match="escapes"):
        load_workflow(file)


def test_digest_stable_without_timestamp():
    from createrelay.workflow import document_digest

    assert document_digest(validate_document(document())) == document_digest(
        validate_document(document())
    )


def test_include_imports_native_subflow(tmp_path):
    child = tmp_path / "child.json"
    child.write_text(json.dumps(document()), encoding="ascii")
    data = document()
    data["includes"] = {"child": "child.json"}
    data["workflow"]["steps"] = []
    data["workflow"]["program"] = {
        "entry": "call",
        "states": {
            "call": {
                "id": "call",
                "kind": "subflow_call",
                "subflow": "child",
                "transitions": [{"target": "done"}],
            },
            "done": {"id": "done", "kind": "terminal", "outcome": "success"},
        },
    }
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps(data), encoding="ascii")
    loaded = load_workflow(parent)
    assert loaded.workflow.subflows["child"].entry == "s::increment"


def test_invalid_graph_refuses_missing_target():
    from openadapt_flow.ir import lift_to_program

    data = document()
    native = validate_document(data).workflow
    graph = lift_to_program(native)
    native.steps = []
    native.program = graph
    graph.states[graph.entry].transitions[0].target = "missing"
    data["workflow"] = native.model_dump(mode="json")
    with pytest.raises(ValueError, match="Invalid Flow program"):
        validate_document(data)
