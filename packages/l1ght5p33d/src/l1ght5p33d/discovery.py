"""Bounded discovery from operator-pinned catalogs, with inactive staging only.

Author-provided descriptions are search data, never instructions or evidence of
semantic suitability. Trust roots are read once from local startup configuration;
the callable search/stage surface accepts no URLs, keys or destination paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from l1ght5p33d.registry import (
    RegistryError,
    WorkflowEntry,
    _checked_url,
    _json_object,
    fetch_catalog,
    install_workflow,
)

MAX_CONFIG_BYTES = 64_000
MAX_RESULTS = 100
_IDENTIFIER = r"^[a-z][a-z0-9_-]{0,63}$"


class DiscoveryError(RegistryError):
    """Discovery configuration, exact selection or provenance was refused."""


class TrustedRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(pattern=_IDENTIFIER)
    url: str = Field(min_length=1, max_length=2048)
    public_key_hex: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("url")
    @classmethod
    def checked_catalog_url(cls, value: str) -> str:
        return _checked_url(value, kubo=False)

    @field_validator("public_key_hex")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.lower()


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["l1ght5p33d-discovery/v1"] = "l1ght5p33d-discovery/v1"
    registries: tuple[TrustedRegistry, ...] = Field(default=(), max_length=16)
    kubo_url: str = Field(default="http://127.0.0.1:5001", max_length=2048)

    @field_validator("registries", mode="before")
    @classmethod
    def immutable_registries(cls, value: Any) -> Any:
        # JSON arrays become tuples so frozen configuration has no mutable list.
        return tuple(value) if isinstance(value, list) else value

    @field_validator("kubo_url")
    @classmethod
    def checked_kubo_url(cls, value: str) -> str:
        return _checked_url(value, kubo=True)

    @model_validator(mode="after")
    def unique_registries(self) -> DiscoveryConfig:
        names = [registry.name for registry in self.registries]
        if len(names) != len(set(names)):
            raise DiscoveryError("Trusted registry names must be unique")
        return self


def load_discovery(path: Path | None = None) -> DiscoveryConfig:
    """Load bounded local ASCII configuration; no path means no remote registries."""
    if path is None:
        return DiscoveryConfig()
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_CONFIG_BYTES + 1)
    if not data or len(data) > MAX_CONFIG_BYTES:
        raise DiscoveryError("Discovery configuration exceeds its 64 KB limit")
    return DiscoveryConfig.model_validate(_json_object(data))


def _identity(source: TrustedRegistry) -> dict[str, str]:
    return {
        "name": source.name,
        "url": source.url,
        "key_fingerprint": "sha256:"
        + hashlib.sha256(bytes.fromhex(source.public_key_hex)).hexdigest(),
    }


def _candidate(source: TrustedRegistry, entry: WorkflowEntry) -> dict[str, Any]:
    return {
        "registry": _identity(source),
        **entry.model_dump(mode="json"),
        "author_metadata_trusted": False,
        "verification_independently_confirmed": False,
        "semantic_match_guaranteed": False,
        "approved": False,
    }


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(_IDENTIFIER, value):
        raise DiscoveryError(f"{label} must be a bounded workflow identifier")


def _atomic_provenance(destination: Path, data: dict[str, Any]) -> None:
    """Publish a complete receipt with an exclusive atomic hard link."""
    descriptor, name = tempfile.mkstemp(prefix=".receipt-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(data, ensure_ascii=True, indent=2).encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        # Unlike replace(), link() cannot silently replace a prior receipt.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


class WorkflowDiscovery:
    def __init__(self, config: DiscoveryConfig, workflow_root: Path):
        # Validate again to reject model_construct bypasses and detach references.
        self._config = DiscoveryConfig.model_validate(config.model_dump(mode="json"))
        root = Path(workflow_root)
        if root.is_symlink() or root.is_junction():
            raise DiscoveryError("Workflow folder cannot be a symlink or junction")
        self._workflow_root = root.resolve(strict=True)
        if not self._workflow_root.is_dir():
            raise DiscoveryError("Workflow folder must be an existing directory")

    @property
    def config(self) -> DiscoveryConfig:
        return self._config

    def search(
        self, query: str, application: str | None = None, limit: int = MAX_RESULTS
    ) -> dict[str, Any]:
        """Return literal term matches without automatic selection or execution."""
        if not isinstance(query, str) or len(query) > 512:
            raise DiscoveryError(
                "Search query must be a string of at most 512 characters"
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in query):
            raise DiscoveryError("Search query cannot contain control characters")
        if application is not None:
            _identifier(application, "Application")
        if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
            raise DiscoveryError("Search limit must be an integer from 1 to 100")
        terms = query.casefold().split()
        candidates: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        succeeded = 0
        sources = sorted(self._config.registries, key=lambda source: source.name)
        # Each registry fetch has its own transport time/byte bound. At most four
        # run together; no request can introduce another registry or trust root.
        with ThreadPoolExecutor(max_workers=4) as executor:
            requests = [
                (
                    source,
                    executor.submit(fetch_catalog, source.url, source.public_key_hex),
                )
                for source in sources
            ]
            for source, request in requests:
                try:
                    catalog = request.result()
                except (ValueError, OSError) as exc:
                    errors.append(
                        {
                            "registry": _identity(source),
                            "error": str(exc)[:1000],
                            "error_details_trusted": False,
                            "classification": "catalog_unavailable_or_invalid",
                        }
                    )
                    continue
                succeeded += 1
                for entry in catalog.workflows:
                    if application is not None and entry.application != application:
                        continue
                    text = " ".join(
                        [entry.id, entry.title, entry.description, entry.application]
                    ).casefold()
                    if all(term in text for term in terms):
                        candidates.append(_candidate(source, entry))
        candidates.sort(
            key=lambda item: (item["registry"]["name"], item["id"], item["version"])
        )
        return {
            "status": "partial"
            if errors and succeeded
            else "failed"
            if errors
            else "ok",
            "query": query,
            "application": application,
            "candidates": candidates[:limit],
            "total_matches": len(candidates),
            "truncated": len(candidates) > limit,
            "errors": errors,
            "registries_configured": len(sources),
            "registries_succeeded": succeeded,
            "matching": "all_literal_terms_case_insensitive",
            "semantic_match_guaranteed": False,
            "author_metadata_trusted": False,
            "selected": None,
            "executed": False,
        }

    def stage(
        self, registry_name: str, workflow_id: str, version: str
    ) -> dict[str, Any]:
        """Re-fetch an exact signed version and save it without granting execution."""
        _identifier(registry_name, "Registry name")
        _identifier(workflow_id, "Workflow ID")
        if not isinstance(version, str) or not 5 <= len(version) <= 80:
            raise DiscoveryError("Workflow version must be an exact bounded version")
        source = next(
            (item for item in self._config.registries if item.name == registry_name),
            None,
        )
        if source is None:
            raise DiscoveryError(
                "Registry is not in the local startup trust configuration"
            )
        catalog = fetch_catalog(source.url, source.public_key_hex)
        entry = next(
            (
                item
                for item in catalog.workflows
                if item.id == workflow_id and item.version == version
            ),
            None,
        )
        if entry is None:
            raise DiscoveryError(
                "Exact workflow ID and version are absent from catalog"
            )
        provenance_root = self._workflow_root / ".provenance"
        if provenance_root.is_symlink() or provenance_root.is_junction():
            raise DiscoveryError("Provenance folder cannot be a symlink or junction")
        provenance_root.mkdir(exist_ok=True, mode=0o700)
        destination = provenance_root / f"workflow-{entry.id}.json"
        if (
            destination.exists()
            or destination.is_symlink()
            or destination.is_junction()
        ):
            raise DiscoveryError(
                "Workflow provenance already exists; refusing overwrite"
            )
        path = install_workflow(entry, self._workflow_root, self._config.kubo_url)
        provenance = {
            "schema_version": "l1ght5p33d-provenance/v1",
            "staged_at": datetime.now(UTC).isoformat(),
            "registry": _identity(source),
            "catalog_revision": catalog.revision,
            "catalog_expires_at": catalog.expires_at.isoformat(),
            "workflow": entry.model_dump(mode="json"),
            "path": str(path),
            "approved": False,
            "executed": False,
            "author_metadata_trusted": False,
        }
        try:
            _atomic_provenance(destination, provenance)
        except OSError as exc:
            raise DiscoveryError(
                "Workflow downloaded but provenance could not be recorded; "
                "the downloaded file remains inactive and requires manual review"
            ) from exc
        return {
            "status": "staged_not_approved",
            "workflow_id": entry.id,
            "version": entry.version,
            "path": str(path),
            "sha256": entry.sha256,
            "provenance": str(destination),
            "registry": _identity(source),
            "approved": False,
            "executed": False,
            "requires_local_approval": True,
        }
