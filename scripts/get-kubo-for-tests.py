"""Fetch an exact, hash-verified Kubo executable for isolated peer tests only."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.43.0"
ASSETS = {
    "win32": (
        "windows-amd64.zip",
        "0486721fc406d36c9d70d16dc3984e70c50d5f1d1c890de3864a6904564080adb3f73546162ad30a8e1ee43024a18bf900fbda2b6c131197351ff2e8b9782178",
    ),
    "linux": (
        "linux-amd64.tar.gz",
        "6af21cd24a307d94326807b3d3827064c74fb7122f83b6940af250e6ae40da250e0ec0e1f3551256b78cd204623ed56c32ce735bbe28bdcc787b36943c52458a",
    ),
}


def download(destination: Path) -> Path:
    suffix, expected = ASSETS[sys.platform]
    filename = f"kubo_v{VERSION}_{suffix}"
    url = f"https://github.com/ipfs/kubo/releases/download/v{VERSION}/{filename}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(200_000_001)
    if len(data) > 200_000_000 or hashlib.sha512(data).hexdigest() != expected:
        raise ValueError("Kubo release archive digest differs from the reviewed pin")
    destination.mkdir(parents=True, exist_ok=True)
    executable = destination / ("ipfs.exe" if sys.platform == "win32" else "ipfs")
    if sys.platform == "win32":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            binary = archive.read("kubo/ipfs.exe")
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = archive.extractfile("kubo/ipfs")
            if member is None:
                raise ValueError("Missing Kubo executable")
            binary = member.read()
    with executable.open("xb") as output:
        output.write(binary)
    os.chmod(executable, 0o700)
    return executable.resolve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(download(args.out_dir))
