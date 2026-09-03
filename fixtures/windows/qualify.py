"""Run a reviewable native UIA and template qualification on the local fixture.

The operator may need to click the fixture once to give it foreground focus.
No focus, identity, or verification checks are disabled for qualification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from build_fixture import build
from createrelay.providers.base import ProviderRefused
from createrelay.providers.windows import WindowsProvider


def qualify(output: Path, wait_for_focus: float) -> None:
    output = output.resolve()
    executable = build(output / "binary")
    process = subprocess.Popen([str(executable)])
    calibration = output / "calibration"
    calibration.mkdir()
    target = WindowsProvider(
        {
            "executable": str(executable),
            "process_id": process.pid,
            "title_re": "CreateRelay Creative Fixture",
            "template_root": str(calibration),
            "observables": {"status": {"method": "uia", "auto_id": "statusText"}},
        }
    )
    print(
        "Click the CreateRelay Creative Fixture window to begin the native test.",
        flush=True,
    )
    receipts: list[dict] = []
    try:
        deadline = time.monotonic() + wait_for_focus
        while True:
            try:
                target.inspect()
                break
            except ProviderRefused:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        receipts.append(
            target.execute(
                "fill",
                {
                    "selectors": [
                        {
                            "method": "uia",
                            "auto_id": "titleEditor",
                            "control_type": "Edit",
                        }
                    ],
                    "text": "Synthetic artwork",
                },
            )
        )
        receipts.append(
            target.execute(
                "click",
                {
                    "selectors": [
                        {
                            "method": "uia",
                            "auto_id": "applyTitle",
                            "control_type": "Button",
                        }
                    ],
                    "verify": {
                        "selector": {"method": "uia", "auto_id": "statusText"},
                        "text": "Applied: Synthetic artwork",
                    },
                },
            )
        )
        window, _ = target._window()
        panel = target._semantic(window, {"method": "uia", "auto_id": "stampCanvas"})
        if panel is None:
            raise RuntimeError("Synthetic calibration panel was not found")
        panel.capture_as_image().save(calibration / "stamp.png")
        receipts.append(
            target.execute(
                "click",
                {
                    "selectors": [
                        {"method": "uia", "auto_id": "missingStampButton"},
                        {
                            "method": "template",
                            "template": "stamp.png",
                            "confidence": 0.98,
                        },
                    ],
                    "verify": {
                        "selector": {"method": "uia", "auto_id": "statusText"},
                        "text": "Stamped",
                    },
                },
            )
        )
        target.calibrate(calibration / "window.json", theme="fixture-light")
        print(
            "Native fixture passed: UIA fill, Invoke, local template fallback, and fresh effect readback.",
            flush=True,
        )
    finally:
        with (output / "receipts.jsonl").open("w", encoding="ascii") as stream:
            for receipt in receipts:
                stream.write(json.dumps(receipt, ensure_ascii=True) + "\n")
        target.close()
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-for-focus", type=float, default=60)
    args = parser.parse_args()
    qualify(args.output, min(max(args.wait_for_focus, 1), 120))
