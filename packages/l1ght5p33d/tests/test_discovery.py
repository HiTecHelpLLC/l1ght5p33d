import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from l1ght5p33d import discovery, registry
from l1ght5p33d.discovery import (
    MAX_CONFIG_BYTES,
    DiscoveryConfig,
    DiscoveryError,
    TrustedRegistry,
    WorkflowDiscovery,
    load_discovery,
)
from l1ght5p33d.registry import Catalog, RegistryError, WorkflowEntry, raw_cid


def source(name="primary", **changes):
    value = {
        "name": name,
        "url": f"https://{name}.example/catalog.json",
        "public_key_hex": "ab" * 32,
    }
    value.update(changes)
    return TrustedRegistry.model_validate(value)


def entry(workflow_id="poster", version="0.1.0", data=b"fixture", **changes):
    value = {
        "id": workflow_id,
        "version": version,
        "title": "Creative poster workflow",
        "description": "Set a poster title in a local fixture",
        "application": "browser",
        "workflow_schema": "l1ght5p33d/v1",
        "runtime_version": "1.34.0",
        "license": "MIT",
        "cid": raw_cid(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "compatibility": {},
        "verification": {"level": "fixture", "description": "Author's fixture claim"},
    }
    value.update(changes)
    return WorkflowEntry.model_validate(value)


def catalog(*entries, revision=1):
    now = datetime.now(UTC)
    return Catalog.model_validate(
        {
            "schema_version": "l1ght5p33d-catalog/v1",
            "revision": revision,
            "generated_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "workflows": [item.model_dump(mode="json") for item in entries],
        }
    )


def service(tmp_path, *sources):
    return WorkflowDiscovery(DiscoveryConfig(registries=sources), tmp_path)


def test_empty_default_never_contacts_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery, "fetch_catalog", lambda *args: pytest.fail("Unexpected network call")
    )
    config = load_discovery()
    result = WorkflowDiscovery(config, tmp_path).search("anything")
    assert result["candidates"] == []
    assert result["registries_configured"] == 0
    assert result["selected"] is None
    assert result["executed"] is False


def test_local_config_is_strict_and_deeply_immutable(tmp_path):
    path = tmp_path / "discovery.json"
    path.write_text(
        json.dumps({"registries": [source().model_dump()]}), encoding="ascii"
    )
    config = load_discovery(path)
    assert isinstance(config.registries, tuple)
    with pytest.raises(ValidationError):
        config.registries[0].url = "https://untrusted.example"
    with pytest.raises(ValidationError):
        config.kubo_url = "http://127.0.0.1:9999"
    with pytest.raises(AttributeError):
        WorkflowDiscovery(config, tmp_path).config = DiscoveryConfig()


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "other/v1"},
        {"extra": True},
        {"registries": [source().model_dump()] * 2},
        {"registries": [source(f"source{i}").model_dump() for i in range(17)]},
        {"kubo_url": "http://localhost:5001"},
        {"kubo_url": "https://external.example"},
        {"kubo_url": "http://127.0.0.1:5001/path"},
    ],
)
def test_invalid_local_config_is_refused(change):
    with pytest.raises(ValueError):
        DiscoveryConfig.model_validate(change)


@pytest.mark.parametrize(
    "change",
    [
        {"name": "../bad"},
        {"url": "http://external.example/catalog"},
        {"url": "https://user:password@example.com/catalog"},
        {"url": "file:///catalog.json"},
        {"public_key_hex": "not-a-key"},
        {"auto_approve": True},
    ],
)
def test_invalid_registry_is_refused(change):
    with pytest.raises(ValueError):
        source(**change)


@pytest.mark.parametrize(
    "data",
    [b"{}" * MAX_CONFIG_BYTES, b'{"registries":[],"registries":[]}'],
    ids=["oversized", "duplicate-keys"],
)
def test_config_size_and_duplicate_keys_refused(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        load_discovery(path)


def test_search_matches_literal_terms_and_exposes_provenance(tmp_path, monkeypatch):
    calls = []

    def fetch(url, key):
        calls.append((url, key))
        return catalog(entry(), entry("music", title="Arrange music", description=""))

    monkeypatch.setattr(discovery, "fetch_catalog", fetch)
    result = service(tmp_path, source()).search(
        "POSTER creative", application="browser"
    )
    assert calls == [(source().url, source().public_key_hex)]
    assert [item["id"] for item in result["candidates"]] == ["poster"]
    candidate = result["candidates"][0]
    assert candidate["registry"]["name"] == "primary"
    assert candidate["registry"]["key_fingerprint"].startswith("sha256:")
    assert candidate["runtime_version"] == "1.34.0"
    assert candidate["license"] == "MIT"
    assert candidate["verification"]["level"] == "fixture"
    assert candidate["verification_independently_confirmed"] is False
    assert candidate["author_metadata_trusted"] is False
    assert result["semantic_match_guaranteed"] is False
    assert result["selected"] is None


def test_search_stable_order_limits_and_application_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery,
        "fetch_catalog",
        lambda *args: catalog(
            entry("z-last"), entry("a-first", "0.2.0"), entry("a-first", "0.1.0")
        ),
    )
    runner = service(tmp_path, source("z-source"), source("a-source"))
    result = runner.search("", limit=2)
    assert result["total_matches"] == 6
    assert result["truncated"] is True
    assert [item["version"] for item in result["candidates"]] == ["0.1.0", "0.2.0"]
    assert all(item["registry"]["name"] == "a-source" for item in result["candidates"])
    assert runner.search("", application="windows")["candidates"] == []


def test_search_reports_each_failed_source_without_discarding_results(
    tmp_path, monkeypatch
):
    def fetch(url, key):
        if "bad.example" in url:
            raise RegistryError("Catalog signature does not match the pinned key")
        return catalog(entry())

    monkeypatch.setattr(discovery, "fetch_catalog", fetch)
    runner = service(tmp_path, source("bad"), source("good"))
    result = runner.search("poster")
    assert result["status"] == "partial"
    assert len(result["candidates"]) == 1
    assert result["errors"][0]["registry"]["name"] == "bad"
    assert "signature" in result["errors"][0]["error"]
    assert service(tmp_path, source("bad")).search("")["status"] == "failed"
    unmatched = runner.search("no-workflow-has-this-term")
    assert unmatched["candidates"] == []
    assert unmatched["status"] == "partial"
    assert unmatched["registries_succeeded"] == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "x" * 513},
        {"query": "line\nnext"},
        {"query": "x", "application": "../browser"},
        {"query": "x", "limit": 0},
        {"query": "x", "limit": 101},
        {"query": "x", "limit": True},
    ],
)
def test_invalid_search_cannot_contact_a_registry(tmp_path, monkeypatch, kwargs):
    monkeypatch.setattr(
        discovery, "fetch_catalog", lambda *args: pytest.fail("Unexpected fetch")
    )
    with pytest.raises(DiscoveryError):
        service(tmp_path, source()).search(**kwargs)


def test_stage_refetches_exact_version_and_records_provenance(tmp_path, monkeypatch):
    selected = entry(version="0.1.0")
    calls = []
    installs = []

    def fetch(url, key):
        calls.append((url, key))
        return catalog(selected, entry(version="9.0.0"), revision=12)

    def install(item, root, kubo):
        installs.append((item, root, kubo))
        path = root / f"workflow-{item.id}.json"
        path.write_bytes(b"fixture")
        return path

    monkeypatch.setattr(discovery, "fetch_catalog", fetch)
    monkeypatch.setattr(discovery, "install_workflow", install)
    runner = service(tmp_path, source())
    runner.search("poster")
    result = runner.stage("primary", "poster", "0.1.0")
    assert len(calls) == 2
    assert installs == [(selected, tmp_path.resolve(), "http://127.0.0.1:5001")]
    assert result["status"] == "staged_not_approved"
    assert result["approved"] is result["executed"] is False
    provenance = json.loads(Path(result["provenance"]).read_text())
    assert provenance["catalog_revision"] == 12
    assert provenance["workflow"]["sha256"] == selected.sha256
    assert provenance["workflow"]["version"] == "0.1.0"
    assert provenance["approved"] is provenance["executed"] is False
    assert [path.name for path in tmp_path.glob("*.json")] == ["workflow-poster.json"]
    assert not list(tmp_path.rglob("*policy*"))
    assert not list((tmp_path / ".provenance").glob(".receipt-*"))


def test_stage_rejects_nonallowlisted_sources_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery, "fetch_catalog", lambda *args: pytest.fail("Unexpected fetch")
    )
    runner = service(tmp_path, source())
    with pytest.raises(DiscoveryError, match="startup trust"):
        runner.stage("unknown", "poster", "0.1.0")
    with pytest.raises(TypeError):
        runner.stage("primary", "poster", "0.1.0", url="https://untrusted.example")


def test_missing_exact_version_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "fetch_catalog", lambda *args: catalog(entry()))
    monkeypatch.setattr(
        discovery, "install_workflow", lambda *args: pytest.fail("Unexpected install")
    )
    with pytest.raises(DiscoveryError, match="Exact workflow"):
        service(tmp_path, source()).stage("primary", "poster", "9.9.9")


def test_changed_catalog_does_not_use_a_stale_search_result(tmp_path, monkeypatch):
    answers = iter([catalog(entry()), catalog()])
    monkeypatch.setattr(discovery, "fetch_catalog", lambda *args: next(answers))
    runner = service(tmp_path, source())
    assert runner.search("poster")["candidates"]
    with pytest.raises(DiscoveryError, match="absent"):
        runner.stage("primary", "poster", "0.1.0")
    assert not list(tmp_path.glob("*.json"))


def test_stage_does_not_overwrite_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "fetch_catalog", lambda *args: catalog(entry()))
    monkeypatch.setattr(
        discovery, "install_workflow", lambda *args: pytest.fail("Unexpected install")
    )
    provenance = tmp_path / ".provenance"
    provenance.mkdir()
    path = provenance / "workflow-poster.json"
    path.write_text("original")
    with pytest.raises(DiscoveryError, match="refusing overwrite"):
        service(tmp_path, source()).stage("primary", "poster", "0.1.0")
    assert path.read_text() == "original"


def test_invalid_artifact_stops_before_provenance(tmp_path, monkeypatch):
    data = b'{"schema_version":"other/v1"}'
    monkeypatch.setattr(
        discovery, "fetch_catalog", lambda *args: catalog(entry(data=data))
    )
    monkeypatch.setattr(registry, "_download", lambda *args, **kwargs: data)
    with pytest.raises(ValueError):
        service(tmp_path, source()).stage("primary", "poster", "0.1.0")
    assert not list(tmp_path.rglob("*.json"))


def test_failed_provenance_is_not_reported_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "fetch_catalog", lambda *args: catalog(entry()))

    def install(item, root, kubo):
        path = root / "workflow-poster.json"
        path.write_bytes(b"fixture")
        return path

    def fail(*args):
        raise OSError("Disk full")

    monkeypatch.setattr(discovery, "install_workflow", install)
    monkeypatch.setattr(discovery, "_atomic_provenance", fail)
    with pytest.raises(DiscoveryError, match="remains inactive"):
        service(tmp_path, source()).stage("primary", "poster", "0.1.0")
    assert (tmp_path / "workflow-poster.json").read_bytes() == b"fixture"


def test_atomic_provenance_refuses_existing_file(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("original")
    with pytest.raises(OSError):
        discovery._atomic_provenance(path, {"new": True})
    assert path.read_text() == "original"
    assert not list(tmp_path.glob(".receipt-*"))
