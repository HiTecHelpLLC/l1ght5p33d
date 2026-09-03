#!/usr/bin/env python3
"""Operator tools for reviewed, signed, standalone workflow catalogs.

Run with the L1ght5p33d development environment. Entry/sign are local; only the
explicit seed command sends workflow bytes to a local, operator-managed Kubo.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from l1ght5p33d.registry import WorkflowEntry, load_catalog, raw_cid
from l1ght5p33d.workflow import validate_document


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Input exceeds the 2 MB limit")
    return json.loads(path.read_bytes().decode("ascii"), object_pairs_hook=unique_pairs)


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("ascii")


def write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)


def outside_repository(path: Path) -> Path:
    """Reject private material anywhere in this or another Git checkout."""
    resolved = path.expanduser().resolve()
    checkout = Path(__file__).resolve().parents[1]
    if resolved.is_relative_to(checkout) or any(
        (parent / ".git").exists() for parent in resolved.parents
    ):
        raise ValueError("Private keys must be stored outside every Git checkout")
    if resolved.suffix != ".key":
        raise ValueError("Use a .key filename for private key material")
    return resolved


def keygen(path: Path) -> dict[str, str]:
    path = outside_repository(path)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw().hex()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        # Windows ignores POSIX permission bits: restrict the empty file before
        # placing private material in it. icacls is invoked directly, never shell.
        if os.name == "nt":
            sid_result = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            import csv

            sid = next(csv.reader([sid_result.stdout.strip()]))[1]
            if not sid.startswith("S-1-"):
                raise ValueError("Unable to identify the current Windows account")
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"],
                capture_output=True,
                check=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        raw = json_bytes(
            {
                "algorithm": "Ed25519",
                "private_key_hex": key.private_bytes_raw().hex(),
                "public_key_hex": public,
            }
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(raw)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    return {"private_key_file": str(path), "public_key_hex": public}


def reviewed_workflow(path: Path) -> tuple[bytes, Any]:
    with path.open("rb") as stream:
        raw = stream.read(1_000_001)
    if not 0 < len(raw) <= 1_000_000:
        raise ValueError("A catalog workflow must be between 1 and 1,000,000 bytes")
    data = json.loads(raw.decode("ascii"), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict) or data.get("includes"):
        raise ValueError("Catalog v1 requires one standalone workflow without includes")
    return raw, validate_document(data)


def entry(args: argparse.Namespace) -> dict[str, Any]:
    import hashlib

    raw, doc = reviewed_workflow(args.workflow)
    compatibility = {}
    for item in args.compatibility:
        name, separator, value = item.partition("=")
        if not separator or not name or not value or name in compatibility:
            raise ValueError("Compatibility must use unique NAME=VALUE items")
        compatibility[name] = value
    result = WorkflowEntry.model_validate(
        {
            "id": doc.id,
            "version": args.version,
            "title": args.title or doc.workflow.name,
            "description": doc.description,
            "application": doc.application,
            "workflow_schema": doc.schema_version,
            "runtime_version": "1.34.0",
            "license": args.license,
            "cid": raw_cid(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "compatibility": compatibility,
            "verification": {
                "level": args.verification_level,
                "description": args.verification_description,
            },
        }
    )
    return result.model_dump(mode="json")


def sign(args: argparse.Namespace) -> dict[str, str]:
    key_data = read_json(outside_repository(args.key))
    if key_data.get("algorithm") != "Ed25519":
        raise ValueError("Expected an Ed25519 private key file")
    key = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(key_data["private_key_hex"])
    )
    public = key.public_key().public_bytes_raw().hex()
    if public != key_data["public_key_hex"]:
        raise ValueError("Private and public keys do not match")
    entries = read_json(args.entries)
    if not isinstance(entries, list):
        raise ValueError("Entries input must be a JSON array of workflow entries")
    now = datetime.now(UTC)
    payload = json_bytes(
        {
            "schema_version": "l1ght5p33d-catalog/v1",
            "revision": args.revision,
            "generated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=args.expires_days)).isoformat(),
            "workflows": entries,
        }
    )
    envelope = {
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "signature_b64": base64.b64encode(key.sign(payload)).decode("ascii"),
    }
    # Validate the exact signed payload through the same consumer contract.
    load_catalog(json_bytes(envelope), public)
    return envelope


def seed(path: Path, url: str) -> dict[str, Any]:
    raw, _ = reviewed_workflow(path)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Kubo must be an HTTP literal-loopback root URL")
    expected = raw_cid(raw)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.post(
            url.rstrip("/") + "/api/v0/block/put",
            params={"cid-codec": "raw", "mhtype": "sha2-256", "pin": "true"},
            files={"file": ("workflow.json", raw, "application/json")},
        )
        response.raise_for_status()
        result = response.json()
    if result.get("Key") != expected or result.get("Size") != len(raw):
        raise ValueError("Kubo returned a different CID or byte length")
    return {
        "cid": expected,
        "size_bytes": len(raw),
        "pinned": True,
        "notice": "The selected node can share these public bytes with its peers",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    key_parser = commands.add_parser("keygen", help="Create a private .key outside Git")
    key_parser.add_argument("--private-out", type=Path, required=True)
    entry_parser = commands.add_parser(
        "entry", help="Describe reviewed bytes; no upload"
    )
    entry_parser.add_argument("--workflow", type=Path, required=True)
    entry_parser.add_argument("--version", required=True)
    entry_parser.add_argument("--license", required=True)
    entry_parser.add_argument("--title")
    entry_parser.add_argument("--compatibility", action="append", default=[])
    entry_parser.add_argument(
        "--verification-level", choices=["fixture", "local", "live"], required=True
    )
    entry_parser.add_argument("--verification-description", required=True)
    entry_parser.add_argument("--reviewed", action="store_true", required=True)
    entry_parser.add_argument("--out", type=Path, required=True)
    sign_parser = commands.add_parser("sign", help="Sign exact ASCII catalog bytes")
    sign_parser.add_argument("--entries", type=Path, required=True)
    sign_parser.add_argument("--key", type=Path, required=True)
    sign_parser.add_argument("--revision", type=int, required=True)
    sign_parser.add_argument("--expires-days", type=int, default=30)
    sign_parser.add_argument("--out", type=Path, required=True)
    seed_parser = commands.add_parser(
        "seed", help="Publish reviewed bytes to local Kubo"
    )
    seed_parser.add_argument("--workflow", type=Path, required=True)
    seed_parser.add_argument("--kubo-url", default="http://127.0.0.1:5001")
    seed_parser.add_argument("--reviewed", action="store_true", required=True)
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            result = keygen(args.private_out)
        elif args.command == "entry":
            result = entry(args)
            write_new(args.out, json_bytes(result))
        elif args.command == "sign":
            if not 1 <= args.expires_days <= 365:
                raise ValueError("Expiry must be between 1 and 365 days")
            result = sign(args)
            write_new(args.out, json_bytes(result))
            result = {"catalog_file": str(args.out), "revision": args.revision}
        else:
            result = seed(args.workflow, args.kubo_url)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        httpx.HTTPError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Catalog operation refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
