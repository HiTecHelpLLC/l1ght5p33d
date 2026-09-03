"""Inspect actual creator wheel/sdist boundaries before distributing them."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import sys
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

MAX_FILE = 20_000_000
MAX_TOTAL = 100_000_000
REQUIRED_SOURCE = (
    "l1ght5p33d/cli.py",
    "l1ght5p33d/runtime.py",
    "l1ght5p33d/policy.py",
    "l1ght5p33d/py.typed",
    "l1ght5p33d/fixtures/bandlab.html",
    "l1ght5p33d/fixtures/CreatorFixture.cs",
)


def checked_members(file: Path) -> dict[str, bytes]:
    """Read bounded ordinary files, without extracting archive paths."""
    entries: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0

    def admit(name: str, size: int, regular: bool, directory: bool) -> bool:
        nonlocal total
        path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or ":" in name
            or path.is_absolute()
            or ".." in path.parts
        ):
            raise ValueError(f"Unsafe archive path: {name}")
        normalized = name.rstrip("/").casefold()
        if normalized in seen:
            raise ValueError(f"Duplicate/case-colliding archive path: {name}")
        seen.add(normalized)
        if directory:
            return False
        if not regular or size < 0 or size > MAX_FILE:
            raise ValueError(f"Nonregular or oversized archive member: {name}")
        total += size
        if total > MAX_TOTAL:
            raise ValueError("Uncompressed archive exceeds the distribution limit")
        return True

    if file.suffix == ".whl":
        with zipfile.ZipFile(file) as archive:
            for member in archive.infolist():
                mode = member.external_attr >> 16
                regular = not stat.S_ISLNK(mode) and not (
                    mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                )
                if admit(member.filename, member.file_size, regular, member.is_dir()):
                    entries[member.filename] = archive.read(member)
    else:
        with tarfile.open(file) as archive:
            for member in archive:
                if admit(member.name, member.size, member.isfile(), member.isdir()):
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError("Missing regular archive member")
                    entries[member.name] = stream.read(MAX_FILE + 1)
    return entries


def inspect_archive(file: Path) -> None:
    entries = checked_members(file)
    forbidden_parts = {
        "openimis",
        "benchmark",
        ".env",
        "session.token",
        "profiles",
        "cookies",
        ".venv",
        ".git",
        "calibration",
        "recordings",
    }
    forbidden_extensions = {
        ".mid",
        ".midi",
        ".wav",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".flac",
        ".mp3",
        ".mp4",
        ".sqlite",
        ".db",
        ".exe",
        ".dll",
        ".pyd",
    }
    for name in entries:
        path = PurePosixPath(name.lower())
        if (
            any(
                part in forbidden_parts or part.startswith(".env.")
                for part in path.parts
            )
            or path.suffix in forbidden_extensions
        ):
            raise ValueError(f"Forbidden private/binary/benchmark artifact: {name}")
    for required in REQUIRED_SOURCE:
        if not any(name.endswith(required) for name in entries):
            raise ValueError(f"Missing required package content: {required}")
    licenses = [
        data
        for name, data in entries.items()
        if name.endswith("/LICENSE") or name == "LICENSE"
    ]
    if not any(
        b"Permission is hereby granted, free of charge" in data and b"MIT" in data
        for data in licenses
    ):
        raise ValueError(f"Missing actual MIT license text in {file.name}")
    if file.suffix != ".whl":
        if not any(name.endswith("/uv.lock") for name in entries):
            raise ValueError(
                "Source distribution must contain the frozen dependency lock"
            )
        return
    metadata_paths = [name for name in entries if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise ValueError("Wheel must have exactly one metadata directory")
    info = metadata_paths[0].rsplit("/", 1)[0]
    if any(not name.startswith(("l1ght5p33d/", info + "/")) for name in entries):
        raise ValueError("Wheel contains another package or installation payload")
    metadata = BytesParser().parsebytes(entries[metadata_paths[0]])
    if metadata["Name"] != "l1ght5p33d" or metadata["License-Expression"] != "MIT":
        raise ValueError("Wheel name/license metadata differs from the release")
    if metadata["Version"] != file.name.split("-")[1]:
        raise ValueError("Wheel version differs from its filename")
    dependencies = metadata.get_all("Requires-Dist", [])
    if not any(
        item.startswith("openadapt-flow==1.34.0") for item in dependencies
    ) or any("==" not in item.split(";", 1)[0] for item in dependencies):
        raise ValueError(
            "Direct runtime and development dependencies must remain exactly pinned"
        )
    record_name = info + "/RECORD"
    if record_name not in entries:
        raise ValueError("Missing wheel RECORD")
    recorded = set()
    for name, checksum, size in csv.reader(
        io.StringIO(entries[record_name].decode("utf-8"))
    ):
        if name in recorded or name not in entries:
            raise ValueError("Duplicate/missing wheel RECORD entry")
        recorded.add(name)
        if name == record_name:
            if checksum or size:
                raise ValueError("RECORD must not hash itself")
            continue
        expected = (
            "sha256="
            + base64.urlsafe_b64encode(hashlib.sha256(entries[name]).digest())
            .rstrip(b"=")
            .decode()
        )
        if checksum != expected or size != str(len(entries[name])):
            raise ValueError(f"Wheel RECORD integrity failure: {name}")
    if recorded != set(entries):
        raise ValueError("Wheel has unrecorded content")


def main() -> None:
    dist = Path(sys.argv[1])
    files = sorted(path for path in dist.iterdir() if path.is_file())
    if (
        len(files) != 2
        or len(list(dist.glob("l1ght5p33d-*.whl"))) != 1
        or len(list(dist.glob("l1ght5p33d-*.tar.gz"))) != 1
    ):
        raise ValueError("Expected one creator wheel and one sdist")
    for file in files:
        inspect_archive(file)
        print(f"Archive boundary, metadata and integrity passed: {file.name}")


if __name__ == "__main__":
    main()
