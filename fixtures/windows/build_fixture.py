"""Compile the repository's fixed harmless WinForms fixture using Windows .NET.

This developer helper is not exposed as a workflow operation or MCP tool.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def build(output_dir: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("The fixture requires Windows")
    framework = (
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
    )
    compiler = framework / "csc.exe"
    if not compiler.is_file():
        raise RuntimeError("Windows .NET Framework C# compiler was not found")
    from importlib.resources import files

    source = Path(
        str(files("createrelay.fixtures").joinpath("CreatorFixture.cs"))
    ).resolve(strict=True)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    executable = output_dir / "CreateRelayFixture.exe"
    if executable.exists():
        raise FileExistsError("Choose an empty fixture output directory")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--launch", action="store_true")
    arguments = parser.parse_args()
    executable = build(arguments.output)
    print(executable)
    if arguments.launch:
        # The user requested a visible interactive test application.
        subprocess.Popen([str(executable)])
