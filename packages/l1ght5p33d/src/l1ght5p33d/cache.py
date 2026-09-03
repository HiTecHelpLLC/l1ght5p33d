"""Managed, inactive downloaded packs with conservative time-based eviction.

SQLite transactions serialize cooperating processes. Only exact tracked files
are eligible for deletion; user edits and unknown content always stop eviction.
Authored workflows and frozen run stores belong outside this directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psutil

from l1ght5p33d.registry import _SEMVER, MAX_WORKFLOW_BYTES, _json_object
from l1ght5p33d.workflow import validate_document

MAX_PACK_BYTES = 4_000_000
MAX_METADATA_BYTES = 1_000_000
_KEY = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_FILES = {
    "workflow.json",
    "provenance.json",
    "review.json",
    "evidence.json",
    "attestation.json",
}


class CacheError(ValueError):
    """A cache operation is unavailable or would affect unverified content."""


def _regular(path: Path) -> os.stat_result:
    if path.is_symlink() or path.is_junction():
        raise CacheError("Cache paths cannot be symlinks or junctions")
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CacheError("Cache files must be regular files with one hard link")
    return info


def _safe_directory(path: Path) -> None:
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise CacheError("Cache directories must be real directories")


def _key(value: str) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise CacheError("Expected an exact cache key")
    return value


class WorkflowCache:
    def __init__(
        self,
        root: Path,
        retention_days: int = 90,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise CacheError("Cache retention must be 1 to 3650 days")
        requested = Path(root).absolute()
        for ancestor in (requested, *requested.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                raise CacheError("Cache root cannot traverse symlinks or junctions")
        requested.mkdir(parents=True, exist_ok=True, mode=0o700)
        _safe_directory(requested)
        self.root = requested.resolve(strict=True)
        self.retention_days = retention_days
        self._clock = clock
        self._objects = self.root / "objects"
        self._database = self.root / "cache.sqlite3"
        if not self._database.exists() and any(self.root.iterdir()):
            raise CacheError("A new cache requires its own empty directory")
        if self._database.exists():
            _regular(self._database)
        self._objects.mkdir(exist_ok=True, mode=0o700)
        _safe_directory(self._objects)
        self._pid = os.getpid()
        self._process_started = psutil.Process(self._pid).create_time()
        with self._transaction() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS format (version INTEGER NOT NULL)"
            )
            versions = database.execute("SELECT version FROM format").fetchall()
            if not versions:
                database.execute("INSERT INTO format VALUES (1)")
            elif versions != [(1,)]:
                raise CacheError("Unsupported managed cache schema")
            database.execute(
                "CREATE TABLE IF NOT EXISTS packs ("
                "key TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, version TEXT NOT NULL, "
                "manifest TEXT NOT NULL, downloaded REAL NOT NULL, last_used REAL, "
                "pinned INTEGER NOT NULL DEFAULT 0)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS leases ("
                "id TEXT PRIMARY KEY, key TEXT NOT NULL, pid INTEGER NOT NULL, "
                "process_started REAL NOT NULL)"
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        _safe_directory(self.root)
        _safe_directory(self._objects)
        for name in ("cache.sqlite3", "cache.sqlite3-journal"):
            path = self.root / name
            if path.exists() or path.is_symlink() or path.is_junction():
                _regular(path)
        database = sqlite3.connect(self._database, timeout=10, isolation_level=None)
        try:
            database.execute("BEGIN IMMEDIATE")
            yield database
            database.commit()
        except BaseException:
            database.rollback()
            raise
        finally:
            database.close()

    def _row(self, database: sqlite3.Connection, key: str) -> tuple[Any, ...]:
        row = database.execute(
            "SELECT * FROM packs WHERE key = ?", (_key(key),)
        ).fetchone()
        if row is None:
            raise CacheError("Downloaded pack is not in the managed cache")
        return row

    def _inspect(self, row: tuple[Any, ...], *, verify: bool = True) -> dict[str, Any]:
        key, workflow_id, version, encoded, downloaded, last_used, pinned = row
        directory = self._objects / _key(key)
        manifest = json.loads(encoded)
        if not isinstance(manifest, dict) or not manifest or set(manifest) - _FILES:
            raise CacheError("Cache manifest contains unrecognized files")
        if verify:
            _safe_directory(directory)
            actual = {path.name for path in directory.iterdir()}
            if actual != set(manifest):
                raise CacheError(
                    "Pack has untracked, missing or authored files; retained"
                )
            for name, expected in manifest.items():
                if set(expected) != {"sha256", "size"} or not _KEY.fullmatch(
                    expected["sha256"]
                ):
                    raise CacheError("Invalid tracked file manifest")
                path = directory / name
                before = _regular(path)
                if (
                    before.st_size != expected["size"]
                    or before.st_size > MAX_PACK_BYTES
                ):
                    raise CacheError("Pack has locally modified files; retained")
                with path.open("rb") as stream:
                    data = stream.read(expected["size"] + 1)
                    opened = os.fstat(stream.fileno())
                after = _regular(path)
                if (
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or before.st_ino != opened.st_ino
                    or hashlib.sha256(data).hexdigest() != expected["sha256"]
                ):
                    raise CacheError("Pack has locally modified files; retained")
        return {
            "key": key,
            "workflow_id": workflow_id,
            "version": version,
            "directory": str(directory),
            "workflow_path": str(directory / "workflow.json"),
            "files": {
                name.removesuffix(".json"): str(directory / name) for name in manifest
            },
            "manifest": manifest,
            "downloaded_at": downloaded,
            "last_used_at": last_used,
            "expires_at": (downloaded if last_used is None else last_used)
            + self.retention_days * 86400,
            "pinned": bool(pinned),
            "bytes": sum(item["size"] for item in manifest.values()),
        }

    def store(
        self,
        workflow_id: str,
        version: str,
        workflow: bytes,
        expected_sha256: str,
        *,
        provenance: bytes,
        review: bytes | None = None,
        evidence: bytes | None = None,
        attestation: bytes | None = None,
    ) -> dict[str, Any]:
        if not isinstance(workflow_id, str) or not _ID.fullmatch(workflow_id):
            raise CacheError("Invalid workflow identity")
        if (
            not isinstance(version, str)
            or not _SEMVER.fullmatch(version)
            or len(version) > 80
        ):
            raise CacheError("An exact bounded workflow version is required")
        if (
            not isinstance(workflow, bytes)
            or not 1 <= len(workflow) <= MAX_WORKFLOW_BYTES
        ):
            raise CacheError("Workflow is outside cache byte limits")
        if (
            not isinstance(expected_sha256, str)
            or not _KEY.fullmatch(expected_sha256)
            or hashlib.sha256(workflow).hexdigest() != expected_sha256
        ):
            raise CacheError("Workflow hash does not match the reviewed download")
        raw = _json_object(workflow)
        if raw.get("includes"):
            raise CacheError(
                "Downloaded cache packs cannot reference external includes"
            )
        document = validate_document(raw)
        if document.id != workflow_id:
            raise CacheError("Workflow identity does not match cache identity")
        files = {"workflow.json": workflow, "provenance.json": provenance}
        for name, content in (
            ("review.json", review),
            ("evidence.json", evidence),
            ("attestation.json", attestation),
        ):
            if content is not None:
                files[name] = content
        for name, content in files.items():
            if (
                not isinstance(content, bytes)
                or not 1 <= len(content) <= MAX_METADATA_BYTES
            ):
                raise CacheError("Cache pack files must be bounded exact bytes")
            if name != "workflow.json":
                _json_object(content)
        if sum(map(len, files.values())) > MAX_PACK_BYTES:
            raise CacheError("Downloaded pack exceeds the cache size limit")
        manifest = {
            name: {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
            for name, content in files.items()
        }
        identity = json.dumps(
            {"id": workflow_id, "version": version, "files": manifest},
            sort_keys=True,
            separators=(",", ":"),
        )
        key = hashlib.sha256(identity.encode("ascii")).hexdigest()
        with self._transaction() as database:
            existing = database.execute(
                "SELECT * FROM packs WHERE key = ?", (key,)
            ).fetchone()
            if existing is not None:
                return self._inspect(existing)
            if database.execute("SELECT COUNT(*) FROM packs").fetchone()[0] >= 10000:
                raise CacheError("Cache entry limit reached; run cleanup first")
            directory = self._objects / key
            if directory.exists() or directory.is_symlink() or directory.is_junction():
                raise CacheError(
                    "Untracked cache destination already exists; refusing overwrite"
                )
            directory.mkdir(mode=0o700)
            try:
                for name, content in files.items():
                    path = directory / name
                    descriptor = os.open(
                        path,
                        os.O_CREAT
                        | os.O_EXCL
                        | os.O_WRONLY
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                database.execute(
                    "INSERT INTO packs VALUES (?, ?, ?, ?, ?, NULL, 0)",
                    (key, workflow_id, version, json.dumps(manifest), self._clock()),
                )
            except BaseException:
                # Preserve any interrupted/unknown content for manual inspection.
                # No broad rollback delete can erase edits or untracked files.
                raise
            return self._inspect(self._row(database, key))

    def get(self, key: str) -> dict[str, Any]:
        """Inspect exact content; lookup/search does not renew its retention clock."""
        with self._transaction() as database:
            return self._inspect(self._row(database, key))

    def touch(self, key: str) -> dict[str, Any]:
        """Call only after actual workflow use, not discovery or plan preparation."""
        with self._transaction() as database:
            self._inspect(self._row(database, key))
            database.execute(
                "UPDATE packs SET last_used = ? WHERE key = ?", (self._clock(), key)
            )
            return self._inspect(self._row(database, key), verify=False)

    def acquire(self, key: str) -> str:
        """Lease before copying/using a pack; the lease and eviction are serialized."""
        with self._transaction() as database:
            self._inspect(self._row(database, key))
            lease = uuid.uuid4().hex
            database.execute(
                "INSERT INTO leases VALUES (?, ?, ?, ?)",
                (lease, key, self._pid, self._process_started),
            )
            return lease

    def release(self, lease_id: str) -> bool:
        if not isinstance(lease_id, str) or not re.fullmatch(r"[0-9a-f]{32}", lease_id):
            raise CacheError("Invalid cache lease identity")
        with self._transaction() as database:
            cursor = database.execute(
                "DELETE FROM leases WHERE id = ? AND pid = ? AND process_started = ?",
                (lease_id, self._pid, self._process_started),
            )
            return cursor.rowcount == 1

    def _pin(self, key: str, pinned: bool) -> dict[str, Any]:
        with self._transaction() as database:
            self._row(database, key)
            database.execute(
                "UPDATE packs SET pinned = ? WHERE key = ?", (int(pinned), key)
            )
            return self._inspect(self._row(database, key), verify=False)

    def pin(self, key: str) -> dict[str, Any]:
        return self._pin(key, True)

    def unpin(self, key: str) -> dict[str, Any]:
        return self._pin(key, False)

    @staticmethod
    def _lease_alive(pid: int, started: float) -> bool:
        try:
            return psutil.Process(pid).create_time() == started
        except psutil.NoSuchProcess:
            return False
        except (psutil.AccessDenied, OSError):
            return True  # Unknown ownership is protected, never guessed stale.

    def status(self) -> dict[str, Any]:
        with self._transaction() as database:
            entries = []
            for row in database.execute("SELECT * FROM packs ORDER BY key"):
                item = self._inspect(row, verify=False)
                try:
                    self._inspect(row)
                    item["integrity"] = "verified"
                except (CacheError, OSError) as exc:
                    item["integrity"] = "protected_modified_or_unavailable"
                    item["reason"] = str(exc)
                entries.append(item)
            tracked = {item["key"] for item in entries}
            untracked = sorted(
                path.name
                for path in self._objects.iterdir()
                if path.name not in tracked
            )
            return {
                "root": str(self.root),
                "retention_days": self.retention_days,
                "entries": entries,
                "tracked_bytes": sum(item["bytes"] for item in entries),
                "untracked_objects_retained": untracked,
            }

    def find(self, workflow_id: str, version: str) -> list[dict[str, Any]]:
        """List exact-version variants; never silently choose a publisher/review."""
        if not isinstance(workflow_id, str) or not _ID.fullmatch(workflow_id):
            raise CacheError("Invalid workflow identity")
        if (
            not isinstance(version, str)
            or len(version) > 80
            or not _SEMVER.fullmatch(version)
        ):
            raise CacheError("Invalid exact workflow version")
        with self._transaction() as database:
            matches = []
            rows = database.execute(
                "SELECT * FROM packs WHERE workflow_id = ? AND version = ? "
                "ORDER BY downloaded DESC, key",
                (workflow_id, version),
            )
            for row in rows:
                item = self._inspect(row, verify=False)
                try:
                    self._inspect(row)
                    item["integrity"] = "verified"
                except (CacheError, OSError) as exc:
                    item["integrity"] = "protected_modified_or_unavailable"
                    item["reason"] = str(exc)
                matches.append(item)
            return matches

    def cleanup(self, protected_keys: Collection[str] = ()) -> dict[str, Any]:
        if len(protected_keys) > 10000:
            raise CacheError("Too many protected cache keys")
        protected = {_key(value) for value in protected_keys}
        removed = []
        retained = []
        with self._transaction() as database:
            for lease_id, key, pid, started in database.execute(
                "SELECT * FROM leases"
            ).fetchall():
                if self._lease_alive(pid, started):
                    protected.add(key)
                else:
                    database.execute("DELETE FROM leases WHERE id = ?", (lease_id,))
            now = self._clock()
            for row in database.execute("SELECT * FROM packs ORDER BY key").fetchall():
                item = self._inspect(row, verify=False)
                key = item["key"]
                reason = (
                    "pinned"
                    if item["pinned"]
                    else "active_or_protected"
                    if key in protected
                    else "recently_used_or_downloaded"
                    if item["expires_at"] > now
                    else None
                )
                if reason is not None:
                    retained.append({"key": key, "reason": reason})
                    continue
                try:
                    self._inspect(row)
                    directory = Path(item["directory"])
                    # Only these exact verified file names are removed. rmdir()
                    # refuses a concurrently added unknown file; never recurse.
                    for name in item["manifest"]:
                        path = directory / name
                        _regular(path)
                        if (
                            hashlib.sha256(path.read_bytes()).hexdigest()
                            != item["manifest"][name]["sha256"]
                        ):
                            raise CacheError("File changed before eviction; retained")
                        path.unlink()
                    directory.rmdir()
                    database.execute("DELETE FROM packs WHERE key = ?", (key,))
                    database.execute("DELETE FROM leases WHERE key = ?", (key,))
                    removed.append(key)
                except (CacheError, OSError) as exc:
                    retained.append(
                        {
                            "key": key,
                            "reason": "modified_or_untracked",
                            "detail": str(exc),
                        }
                    )
        return {
            "removed": removed,
            "retained": retained,
            "retention_days": self.retention_days,
        }
