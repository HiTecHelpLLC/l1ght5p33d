"""Verified catalog discovery and inactive installation through a local Kubo node.

The operator supplies the Ed25519 trust root. Downloading a signed workflow is
not an execution grant: this module never imports providers or modifies policy.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from l1ght5p33d.workflow import validate_document

MAX_CATALOG_BYTES = 2_000_000
MAX_WORKFLOW_BYTES = 1_000_000
_IDENTIFIER = r"^[a-z][a-z0-9_-]{0,63}$"
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)"
)


class RegistryError(ValueError):
    """The catalog or artifact failed its trust, transport or content contract."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Verification(_StrictModel):
    level: Literal["fixture", "local", "live"]
    description: str = Field(min_length=1, max_length=4000)


class WorkflowEntry(_StrictModel):
    id: str = Field(pattern=_IDENTIFIER)
    version: str = Field(min_length=5, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=4000)
    application: str = Field(pattern=_IDENTIFIER)
    workflow_schema: Literal["l1ght5p33d/v1"]
    runtime_version: Literal["1.34.0"]
    license: str = Field(min_length=1, max_length=100)
    cid: str = Field(pattern=r"^b[a-z2-7]{58}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1, le=MAX_WORKFLOW_BYTES)
    compatibility: dict[
        Annotated[str, StringConstraints(min_length=1, max_length=64)],
        Annotated[str, StringConstraints(max_length=200)],
    ] = Field(max_length=32)
    verification: Verification

    @field_validator("version")
    @classmethod
    def semver(cls, value: str) -> str:
        if not _SEMVER.fullmatch(value):
            raise ValueError("Workflow version must be SemVer")
        return value

    @model_validator(mode="after")
    def cid_matches_hash(self) -> WorkflowEntry:
        if self.cid != _cid_for_digest(bytes.fromhex(self.sha256)):
            raise ValueError("CID must identify the raw SHA-256 workflow block")
        return self


class Catalog(_StrictModel):
    schema_version: Literal["l1ght5p33d-catalog/v1"]
    revision: int = Field(ge=1)
    generated_at: datetime
    expires_at: datetime
    workflows: list[WorkflowEntry] = Field(max_length=500)

    @field_validator("generated_at", "expires_at", mode="before")
    @classmethod
    def utc_timestamp(cls, value: Any) -> datetime:
        if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
            raise ValueError("Catalog timestamps must be ISO UTC strings")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @model_validator(mode="after")
    def freshness_and_identity(self) -> Catalog:
        now = datetime.now(UTC)
        if self.expires_at <= now:
            raise ValueError("Catalog has expired")
        if self.generated_at > now + timedelta(minutes=5):
            raise ValueError("Catalog generation time is in the future")
        if self.expires_at <= self.generated_at:
            raise ValueError("Catalog expiry must follow generation")
        identities = [(entry.id, entry.version) for entry in self.workflows]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate workflow ID and version in catalog")
        return self


class _Envelope(_StrictModel):
    payload_b64: str = Field(min_length=4, max_length=MAX_CATALOG_BYTES)
    signature_b64: str = Field(min_length=88, max_length=88)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError("Duplicate JSON key is not allowed")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise RegistryError("Non-finite JSON numbers are not allowed")


def _json_object(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RegistryError("Expected a bounded ASCII JSON object") from exc
    if not isinstance(value, dict):
        raise RegistryError("Expected a JSON object")
    return value


def _decode_base64(value: str) -> bytes:
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RegistryError("Invalid catalog base64 encoding") from exc
    if base64.b64encode(result).decode("ascii") != value:
        raise RegistryError("Catalog base64 encoding must be canonical")
    return result


def _cid_for_digest(digest: bytes) -> str:
    # CIDv1 (01), raw codec (55), sha2-256 (12), digest length (20).
    block = b"\x01\x55\x12\x20" + digest
    return "b" + base64.b32encode(block).decode("ascii").lower().rstrip("=")


def raw_cid(data: bytes) -> str:
    """Return the CIDv1/raw/sha2-256 address of exact artifact bytes."""
    return _cid_for_digest(hashlib.sha256(data).digest())


def load_catalog(data: bytes, public_key_hex: str) -> Catalog:
    """Verify the operator-pinned signature before parsing any payload fields."""
    if not data or len(data) > MAX_CATALOG_BYTES:
        raise RegistryError("Signed catalog exceeds the 2 MB size limit")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", public_key_hex):
        raise RegistryError("The pinned Ed25519 public key must be 32-byte hex")
    envelope = _Envelope.model_validate(_json_object(data))
    payload = _decode_base64(envelope.payload_b64)
    signature = _decode_base64(envelope.signature_b64)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
            signature, payload
        )
    except InvalidSignature as exc:
        raise RegistryError("Catalog signature does not match the pinned key") from exc
    return Catalog.model_validate(_json_object(payload))


def _checked_url(url: str, *, kubo: bool) -> str:
    if not url or any(ord(char) <= 32 or ord(char) >= 127 for char in url):
        raise RegistryError("Use a credential-free ASCII HTTP(S) URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise RegistryError("Invalid registry URL") from exc
    local = parts.hostname in {"127.0.0.1", "::1"}
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise RegistryError("Use a credential-free HTTP(S) URL without a fragment")
    if parts.scheme == "http" and not local:
        raise RegistryError("Catalog HTTP is limited to literal loopback addresses")
    if kubo and (not local or parts.path not in {"", "/"} or parts.query):
        raise RegistryError("Kubo must use a literal loopback origin without a path")
    return url.rstrip("/") if kubo else url


def _download(
    method: str, url: str, *, limit: int, params: dict[str, str] | None = None
) -> bytes:
    deadline = time.monotonic() + 30
    try:
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(10, connect=5),
            headers={"Accept-Encoding": "identity"},
        ) as client:
            with client.stream(method, url, params=params) as response:
                if response.status_code != 200:
                    raise RegistryError(
                        f"Registry download refused HTTP status {response.status_code}"
                    )
                if response.headers.get("content-encoding", "identity").lower() not in {
                    "identity",
                    "",
                }:
                    raise RegistryError("Compressed registry responses are unavailable")
                length = response.headers.get("content-length")
                if length is not None and (
                    not re.fullmatch(r"[0-9]+", length) or int(length) > limit
                ):
                    raise RegistryError("Registry download exceeds its byte limit")
                data = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise RegistryError("Registry download exceeded its time limit")
                    if len(chunk) > limit - len(data):
                        raise RegistryError("Registry download exceeds its byte limit")
                    data.extend(chunk)
                if length is not None and int(length) != len(data):
                    raise RegistryError(
                        "Registry response length does not match its body"
                    )
                return bytes(data)
    except httpx.HTTPError as exc:
        raise RegistryError("Registry network request did not complete") from exc


def fetch_catalog(url: str, public_key_hex: str) -> Catalog:
    """Fetch a signed HTTPS catalog; literal loopback HTTP supports local testing."""
    return load_catalog(
        _download("GET", _checked_url(url, kubo=False), limit=MAX_CATALOG_BYTES),
        public_key_hex,
    )


def install_workflow(
    entry: WorkflowEntry,
    workflow_root: Path,
    kubo_url: str = "http://127.0.0.1:5001",
) -> Path:
    """Retrieve one verified raw block and exclusively install its inactive JSON.

    Kubo handles peer discovery/transfer. Its API is local and this client uses
    only block/get. Includes are refused before validation, so downloaded data
    cannot cause reads of other local files during installation.
    """
    entry = WorkflowEntry.model_validate(entry.model_dump(mode="json"))
    root = Path(workflow_root)
    if root.is_symlink() or root.is_junction():
        raise RegistryError("Workflow folder cannot be a symlink or junction")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise RegistryError("Workflow folder must be an existing directory")
    destination = root / f"workflow-{entry.id}.json"
    if destination.exists() or destination.is_symlink() or destination.is_junction():
        raise RegistryError("Workflow destination already exists; refusing overwrite")
    endpoint = _checked_url(kubo_url, kubo=True) + "/api/v0/block/get"
    data = _download(
        "POST", endpoint, limit=entry.size_bytes, params={"arg": entry.cid}
    )
    if len(data) != entry.size_bytes:
        raise RegistryError("Workflow byte size does not match catalog")
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise RegistryError("Workflow SHA-256 does not match catalog")
    if raw_cid(data) != entry.cid:
        raise RegistryError("Workflow CID does not match catalog")
    raw = _json_object(data)
    if raw.get("includes"):
        raise RegistryError("Catalog v1 supports a single workflow without includes")
    document = validate_document(raw)
    if document.id != entry.id or document.application != entry.application:
        raise RegistryError("Workflow identity does not match catalog")
    if document.schema_version != entry.workflow_schema:
        raise RegistryError("Workflow schema does not match catalog")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise RegistryError(
            "Workflow destination already exists; refusing overwrite"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # The exclusive create above established this file; no existing file
        # was opened. Do not leave a partial artifact discoverable as installed.
        destination.unlink(missing_ok=True)
        raise
    return destination
