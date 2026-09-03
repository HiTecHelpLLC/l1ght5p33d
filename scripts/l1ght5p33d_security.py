"""Pinned Gitleaks download and downstream-history scan; no credentials printed."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "8.30.1"
UPSTREAM = "0b1e6b2a8b7cc1641a8fad4a46e71860d051760a"
ARTIFACTS = {
    "win32": (
        "windows_x64.zip",
        "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
    ),
    "linux": (
        "linux_x64.tar.gz",
        "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    ),
}


def downstream_files(root: Path) -> list[Path]:
    """Include staged/unstaged changes and untracked, nonignored source files."""
    names = set()
    for arguments in (
        ["diff", "--name-only", "--diff-filter=ACMR", "-z", UPSTREAM, "--"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ):
        result = subprocess.run(
            ["git", *arguments], cwd=root, check=True, capture_output=True
        )
        names.update(
            part.decode("utf-8") for part in result.stdout.split(b"\0") if part
        )
    files = []
    for name in sorted(names):
        target = root / name
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError("Downstream source snapshot cannot include external links")
        if target.is_file():
            if target.stat().st_size > 20_000_000:
                raise ValueError(
                    f"Oversized downstream source needs explicit review: {name}"
                )
            files.append(target)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist", type=Path, help="Also scan the actual wheel/sdist contents"
    )
    arguments = parser.parse_args()
    suffix, expected = ARTIFACTS[sys.platform]
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{suffix}"
    data = urllib.request.urlopen(url, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Gitleaks archive checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="l1ght5p33d-gitleaks-") as directory:
        executable = Path(directory) / (
            "gitleaks.exe" if sys.platform == "win32" else "gitleaks"
        )
        if sys.platform == "win32":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                executable.write_bytes(archive.read("gitleaks.exe"))
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                entry = archive.extractfile("gitleaks")
                assert entry is not None
                executable.write_bytes(entry.read())
            os.chmod(executable, 0o700)
        root = Path(__file__).resolve().parents[1]
        history = subprocess.call(
            [
                str(executable),
                "git",
                "--redact",
                "--no-banner",
                f"--log-opts={UPSTREAM}..HEAD",
            ],
            cwd=root,
        )
        if history:
            return history
        snapshot = Path(directory) / "source"
        snapshot.mkdir()
        files = downstream_files(root)
        for source in files:
            target = snapshot / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if arguments.dist is not None:
            from l1ght5p33d_package_check import checked_members

            artifacts = sorted(arguments.dist.glob("l1ght5p33d-*"))
            if len(artifacts) != 2:
                raise ValueError("Expected built wheel and sdist for secret scanning")
            for artifact in artifacts:
                for name, content in checked_members(artifact).items():
                    target = snapshot / "built-artifacts" / artifact.name / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
        print(
            f"Scanning {len(files)} current downstream source files, including uncommitted changes",
            flush=True,
        )
        return subprocess.call(
            [
                str(executable),
                "dir",
                str(snapshot),
                "--redact",
                "--no-banner",
            ],
            cwd=root,
        )


if __name__ == "__main__":
    raise SystemExit(main())
