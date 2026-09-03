"""Opt-in real WinForms/UIA test. Set CREATERELAY_WINDOWS_LIVE=1 on Windows.

All generated binaries, images and calibration data live under pytest tmp_path.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from createrelay.providers.base import ProviderRefused
from createrelay.providers.windows import WindowsProvider


@pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("CREATERELAY_WINDOWS_LIVE") != "1",
    reason="Requires explicit interactive Windows fixture test",
)
def test_real_uia_and_local_template_fallback(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "build_fixture", root / "fixtures" / "windows" / "build_fixture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    executable = module.build(tmp_path / "binary")
    process = subprocess.Popen([str(executable)])
    config = {
        "executable": str(executable),
        "title_re": "CreateRelay Creative Fixture",
        "process_id": process.pid,
        "template_root": str(tmp_path / "calibration"),
        "observables": {"status": {"method": "uia", "auto_id": "statusText"}},
    }
    target = WindowsProvider(config)
    try:
        import win32gui

        deadline = time.monotonic() + 15
        while True:
            try:
                window, _ = target._window(require_foreground=False)
                # Test setup explicitly focuses only the synthetic fixture.
                # Production providers never steal focus from another app.
                try:
                    win32gui.ShowWindow(window.handle, 9)
                    win32gui.SetForegroundWindow(window.handle)
                except Exception:
                    if os.environ.get("CREATERELAY_ALLOW_NO_FOREGROUND") == "1":
                        pytest.skip(
                            "Host denied foreground activation; run manual qualification on an unlocked interactive desktop"
                        )
                    raise
                initial = target.inspect()
                break
            except ProviderRefused:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        assert initial["status"] == "Ready"
        filled = target.execute(
            "fill",
            {
                "selectors": [
                    {"method": "uia", "auto_id": "titleEditor", "control_type": "Edit"}
                ],
                "text": "Synthetic artwork",
            },
        )
        assert filled["result"] == "verified"
        receipt = target.execute(
            "click",
            {
                "selectors": [
                    {"method": "uia", "auto_id": "applyTitle", "control_type": "Button"}
                ],
                "verify": {
                    "selector": {"method": "uia", "auto_id": "statusText"},
                    "text": "Applied: Synthetic artwork",
                },
            },
        )
        assert receipt["verification"]["passed"]
        assert receipt["window"]["process_id"] == process.pid
        assert receipt["window"]["foreground"]
        assert receipt["window"]["dpi"] > 0
        calibration = tmp_path / "calibration"
        calibration.mkdir()
        window, _ = target._window()
        panel = target._semantic(window, {"method": "uia", "auto_id": "stampCanvas"})
        assert panel is not None
        panel.capture_as_image().save(calibration / "stamp.png")
        visual = target.execute(
            "click",
            {
                "selectors": [
                    {
                        "method": "uia",
                        "auto_id": "nonexistentStampButton",
                        "control_type": "Button",
                    },
                    {"method": "template", "template": "stamp.png", "confidence": 0.98},
                ],
                "verify": {
                    "selector": {"method": "uia", "auto_id": "statusText"},
                    "text": "Stamped",
                },
            },
        )
        assert visual["selector_method"] == "template"
        assert visual["selector_chain"][0]["result"] == "not_found"
        assert visual["verification"]["passed"]
        assert target.inspect()["status"] == "Stamped"
        target.calibrate(calibration / "window.json", theme="fixture-light")
    finally:
        target.close()
        process.terminate()
        process.wait(timeout=10)
