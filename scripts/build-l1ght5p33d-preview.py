"""Build a source-only Windows preview from an explicit distribution allowlist."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "l1ght5p33d"
VERSION = "0.2.0"


def build(destination: Path) -> Path:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files: set[Path] = set()
    for name in (
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "scripts/install-l1ght5p33d.ps1",
        "scripts/l1ght5p33d_package_check.py",
        "scripts/l1ght5p33d_license_check.py",
        "scripts/build-l1ght5p33d-preview.py",
        "scripts/workflow-catalog.py",
        "scripts/qualify-p2p.py",
    ):
        files.add(ROOT / name)
    for name in ("README.md", "LICENSE", "pyproject.toml", "uv.lock"):
        files.add(PACKAGE / name)
    for path in (PACKAGE / "src").rglob("*"):
        if path.is_file() and (
            path.suffix in {".py", ".cs", ".html"} or path.name == "py.typed"
        ):
            files.add(path)
    files.update((PACKAGE / "tests").glob("*.py"))
    files.update((ROOT / "fixtures" / "windows").glob("*.py"))
    files.update((ROOT / "examples" / "l1ght5p33d").glob("*.json"))
    for name in (
        "prior-art.md",
        "acceptance.md",
        "adapter-development.md",
        "bandlab.md",
        "windows.md",
        "mcp.md",
        "ROADMAP.md",
        "recorder-calibration.md",
        "troubleshooting.md",
        "trademark-disclaimer.md",
        "workflow-library.md",
        "workflow-review.md",
        "companion.md",
        "third-party-inventory.json",
        "registry-operations.md",
    ):
        files.add(ROOT / "docs" / name)
    for subdir in ("research", "l1ght5p33d", "adr"):
        files.update((ROOT / "docs" / subdir).glob("*.md"))
    files.update((ROOT / "integrations" / "thebest").rglob("*.php"))
    files.add(ROOT / "integrations" / "thebest" / "README.md")
    archive = destination / f"l1ght5p33d-{VERSION}-windows-developer-preview.zip"
    prefix = f"l1ght5p33d-{VERSION}"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(files):
            relative = path.relative_to(ROOT)
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError(f"Distribution link refused: {relative}")
            if not path.is_file():
                raise ValueError(f"Required distribution file missing: {relative}")
            output.write(path, f"{prefix}/{relative.as_posix()}")
        output.writestr(
            f"{prefix}/PREVIEW.txt",
            f"L1ght5p33d {VERSION} Windows developer preview\n\n"
            "Install Python 3.12. Extract this ZIP, open PowerShell in its folder,\n"
            "and run .\\scripts\\install-l1ght5p33d.ps1. An internet connection is\n"
            "required for the locked dependencies and Chromium download.\n\n"
            "This source-only kit contains the downstream extension and fixtures.\n"
            "It does not contain Python, browser binaries, credentials, music, or\n"
            "the inherited repository-only benchmarks. OpenAdapt Flow 1.34.0 is\n"
            "installed from its published package. Full Git history and original\n"
            "upstream source are at https://github.com/HiTecHelpLLC/l1ght5p33d .\n"
            "Read docs/acceptance.md for tested and pending environments.\n",
        )
    with ZipFile(archive) as built:
        assert built.testzip() is None
        for name in built.namelist():
            if any(
                part in {"benchmark", ".venv", ".git", "profiles", "__pycache__"}
                for part in Path(name).parts
            ):
                raise ValueError(f"Forbidden archive entry: {name}")
    print(f"Built {archive.name}: {len(files)} source files")
    return archive


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "l1ght5p33d"
    result = build(target)
    print(f"SHA256 {hashlib.sha256(result.read_bytes()).hexdigest()}")
