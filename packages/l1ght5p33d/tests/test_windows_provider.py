"""Contract tests exercise refusal before input and uncertain postconditions."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from l1ght5p33d.providers.base import ProviderRefused
from l1ght5p33d.providers.vision import (
    VisualSelectorError,
    match_template,
    match_text,
    template_path,
)
from l1ght5p33d.providers.windows import WindowIdentity, WindowsProvider


def png(array: np.ndarray) -> bytes:
    result = io.BytesIO()
    Image.fromarray(array).save(result, format="PNG")
    return result.getvalue()


def provider() -> WindowsProvider:
    return WindowsProvider({"executable": "fixture.exe", "title_re": "Fixture"})


def identity() -> WindowIdentity:
    return WindowIdentity(
        "fixture.exe",
        12,
        14,
        "Fixture",
        "Form",
        (10, 20, 310, 220),
        "display",
        (0, 0, 1000, 800),
        96,
        True,
    )


def test_template_matching_is_unique() -> None:
    pattern = np.random.default_rng(9).integers(0, 255, (20, 24), dtype=np.uint8)
    frame = np.zeros((120, 170), dtype=np.uint8)
    frame[20:40, 30:54] = pattern
    found = match_template(png(frame), png(pattern))
    assert found is not None and found.region == (30, 20, 24, 20)
    frame[80:100, 130:154] = pattern
    with pytest.raises(VisualSelectorError, match="multiple"):
        match_template(png(frame), png(pattern))


def test_flat_template_is_not_evidence() -> None:
    blank = png(np.zeros((20, 20), dtype=np.uint8))
    with pytest.raises(VisualSelectorError, match="structure"):
        match_template(blank, blank)


def test_template_root_cannot_be_escaped(tmp_path: Path) -> None:
    root = tmp_path / "calibration"
    root.mkdir()
    (tmp_path / "outside.png").write_bytes(b"x")
    with pytest.raises(VisualSelectorError, match="inside"):
        template_path(root, "../outside.png")


def test_visual_cannot_precede_semantic_selector() -> None:
    with pytest.raises(ProviderRefused, match="semantic"):
        provider()._resolve(Mock(), identity(), [{"method": "ocr", "text": "Save"}])


def test_semantic_ambiguity_halts_without_fallback() -> None:
    control = Mock()
    control.is_visible.return_value = True
    window = Mock()
    window.descendants.return_value = [control, control]
    with pytest.raises(ProviderRefused, match="ambiguous"):
        provider()._resolve(
            window,
            identity(),
            [{"method": "uia", "title": "Save"}, {"method": "ocr", "text": "Save"}],
        )


def test_relative_requires_explicit_policy() -> None:
    target = provider()
    window = Mock()
    window.descendants.return_value = []
    with pytest.raises(ProviderRefused, match="explicit policy"):
        target._resolve(
            window,
            identity(),
            [
                {"method": "uia", "title": "Missing"},
                {"method": "relative", "anchor": "window", "x": 0.5, "y": 0.5},
            ],
        )


def test_fill_postcondition_failure_is_uncertain_not_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = provider()
    control = Mock()
    control.element_info.control_type = "Edit"
    control.get_value.return_value = "wrong"
    monkeypatch.setattr(target, "_window", lambda **_: (Mock(), identity()))
    monkeypatch.setattr(
        target, "_resolve", lambda *args: (control, {"selector_method": "uia"}, [])
    )
    with pytest.raises(RuntimeError, match="delivered") as raised:
        target.execute("fill", {"selectors": [{}], "text": "expected"})
    assert not isinstance(raised.value, ProviderRefused)
    control.set_edit_text.assert_called_once_with("expected")


def test_window_movement_refuses_before_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    target = provider()
    control = Mock()
    old = identity()
    new = WindowIdentity(**{**old.__dict__, "bounds": (30, 20, 330, 220)})
    calls = iter([(Mock(), old), (Mock(), new)])
    monkeypatch.setattr(target, "_window", lambda **_: next(calls))
    monkeypatch.setattr(
        target, "_resolve", lambda *args: (control, {"selector_method": "uia"}, [])
    )
    with pytest.raises(ProviderRefused, match="moved"):
        target.execute("fill", {"selectors": [{}], "text": "test"})
    control.set_edit_text.assert_not_called()


def test_ocr_uses_recognition_confidence_and_rejects_duplicate_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    module = importlib.import_module("openadapt_flow.vision.ocr")
    low = module.OcrLine(text="Apply", region=(1, 2, 30, 15), confidence=0.7)
    high = module.OcrLine(text="Apply", region=(1, 2, 30, 15), confidence=0.99)
    monkeypatch.setattr(module, "ocr", lambda _: [low])
    assert match_text(b"local-pixels", "Apply") is None
    monkeypatch.setattr(module, "ocr", lambda _: [high])
    found = match_text(b"local-pixels", "Apply")
    assert found is not None and found.confidence == 0.99
    monkeypatch.setattr(module, "ocr", lambda _: [low, high])
    with pytest.raises(VisualSelectorError, match="ambiguous"):
        match_text(b"local-pixels", "Apply")


def test_missing_selector_stops_without_input() -> None:
    window = Mock()
    window.descendants.return_value = []
    with pytest.raises(ProviderRefused, match="No declared selector"):
        provider()._resolve(window, identity(), [{"method": "uia", "title": "Missing"}])


def test_disallowed_operation_cannot_launch_or_shell() -> None:
    for operation in ("launch", "shell", "run", "delete", "upload_screenshot"):
        with pytest.raises(ProviderRefused, match="Unsupported"):
            provider().execute(operation, {})


def test_generated_windows_workflow_validates() -> None:
    from l1ght5p33d.fixtures.windows_demo import fixture_workflow
    from l1ght5p33d.workflow import validate_document

    workflow = fixture_workflow(Path("fixture.exe"), 12, Path("calibration"))
    parsed = validate_document(workflow)
    assert len(parsed.workflow.steps) == 3
