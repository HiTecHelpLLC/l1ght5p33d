"""Packaged, harmless Windows demonstration using the real workflow service."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

from createrelay.policy import Policy, digest
from createrelay.providers.base import ProviderRefused
from createrelay.providers.windows import WindowsProvider
from createrelay.service import WorkflowService
from createrelay.workflow import validate_document


def build_fixture(output: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError(
            "Windows demo requires Windows 11 and an unlocked interactive desktop"
        )
    compiler = (
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
        / "csc.exe"
    )
    if not compiler.is_file():
        raise RuntimeError("Windows .NET Framework C# compiler was not found")
    source = Path(str(files("createrelay.fixtures").joinpath("CreatorFixture.cs")))
    output.mkdir(parents=True, exist_ok=True)
    executable = output / "CreateRelayFixture.exe"
    if executable.exists():
        raise FileExistsError("Fixture output must be an empty directory")
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:winexe",
            f"/out:{executable}",
            "/reference:System.Windows.Forms.dll",
            "/reference:System.Drawing.dll",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return executable


def fixture_workflow(
    executable: Path, process_id: int, calibration: Path
) -> dict[str, Any]:
    """Return an ASCII-serializable native Flow envelope; no Python workflow."""

    def step(
        step_id: str, operation: str, arguments: dict[str, Any], field: str, value: str
    ) -> dict[str, Any]:
        return {
            "id": step_id,
            "intent": step_id.replace("-", " "),
            "action": "wait",
            "api_binding": {
                "kind": "tool",
                "on_unavailable": "halt",
                "url_template": "windows",
                "method": operation,
                "body_template": arguments,
                "effects": [
                    {
                        "kind": "field_equals",
                        "match": {"provider": "windows"},
                        "field": field,
                        "value": value,
                    }
                ],
            },
        }

    return {
        "schema_version": "createrelay/v1",
        "id": "windows-creative",
        "description": "Title and stamp synthetic artwork through Windows UIA and local visual fallback",
        "application": "windows",
        "configuration": {
            "executable": str(executable),
            "process_id": process_id,
            "title_re": "CreateRelay Creative Fixture",
            "template_root": str(calibration),
            "observables": {
                "title_text": {
                    "method": "uia",
                    "auto_id": "titleEditor",
                    "control_type": "Edit",
                },
                "status": {"method": "uia", "auto_id": "statusText"},
            },
        },
        "workflow": {
            "schema_version": 2,
            "name": "windows-creative",
            "steps": [
                step(
                    "set-artwork-title",
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
                    "title_text",
                    "Synthetic artwork",
                ),
                step(
                    "apply-artwork-title",
                    "click",
                    {
                        "selectors": [
                            {
                                "method": "uia",
                                "auto_id": "applyTitle",
                                "control_type": "Button",
                            }
                        ]
                    },
                    "status",
                    "Applied: Synthetic artwork",
                ),
                step(
                    "stamp-using-local-template",
                    "click",
                    {
                        "selectors": [
                            {
                                "method": "uia",
                                "auto_id": "missingStampButton",
                                "control_type": "Button",
                            },
                            {
                                "method": "template",
                                "template": "stamp.png",
                                "confidence": 0.98,
                            },
                        ]
                    },
                    "status",
                    "Stamped",
                ),
            ],
        },
    }


def run_demo() -> int:
    if sys.platform != "win32":
        print("Windows demo requires Windows 11 and an unlocked interactive desktop.")
        return 2
    output = Path(tempfile.mkdtemp(prefix="createrelay-windows-"))
    executable = build_fixture(output / "binary")
    calibration = output / "calibration"
    calibration.mkdir()
    process = subprocess.Popen([str(executable)])
    data = fixture_workflow(executable, process.pid, calibration)
    target = WindowsProvider(data["configuration"])
    try:
        print(
            "Click the CreateRelay Creative Fixture window once to begin (60 seconds).",
            flush=True,
        )
        print(f"Local artifacts: {output}", flush=True)
        deadline = time.monotonic() + 60
        while True:
            try:
                window, _ = target._window()
                break
            except ProviderRefused:
                if time.monotonic() >= deadline:
                    print(
                        "No input delivered: fixture could not acquire foreground. Retry on an unlocked interactive desktop and click the fixture."
                    )
                    return 2
                time.sleep(0.1)
        panel = target._semantic(window, {"method": "uia", "auto_id": "stampCanvas"})
        if panel is None:
            raise RuntimeError("Synthetic calibration anchor was not found")
        panel.capture_as_image().save(calibration / "stamp.png")
        target.calibrate(calibration / "window.json", theme="fixture-light")
        target.close()
        document = validate_document(data)
        registry = output / "workflows"
        registry.mkdir()
        (registry / "windows-creative.json").write_text(
            json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=True),
            "ascii",
        )
        # This command explicitly authorizes only the generated synthetic
        # fixture document, exact executable, PID, selectors and operations.
        policy = Policy(
            applications=["windows"],
            read_roots=[str(output)],
            allowed_operations={"windows": ["fill", "click", "read", "assert_text"]},
            approved_workflow_digests=[digest(document)],
        )
        service = WorkflowService(registry, policy, state_root=output / "state")
        run = service.run_workflow("windows-creative")
        deadline = time.monotonic() + 60
        while not service.get_execution_status(run["run_id"])["done"]:
            if time.monotonic() >= deadline:
                service.abort_workflow(run["run_id"])
                print("Demo timed out; execution was aborted. Inspect local receipts.")
                return 2
            time.sleep(0.05)
        status = service.get_execution_status(run["run_id"])
        print(json.dumps(status, indent=2, ensure_ascii=True))
        return 0 if status["status"] == "completed_ui_verified" else 2
    finally:
        target.close()
        process.terminate()
        process.wait(timeout=10)
