"""Synthetic signed packs: no network, real private keys, providers or approval."""

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from l1ght5p33d import packs, registry
from l1ght5p33d.packs import CuratedPackSource, PackError, verify_pack

NOW = datetime(2026, 9, 3, 23, tzinfo=UTC)
COMMIT = "e51098ffa1e7ca42b96d6372578876d1c32e632b"
WORKFLOW_PATH = "workflows/browser-poster.json"
METADATA_PATH = "entries/browser-poster.json"
EVIDENCE_PATH = "evidence/browser-poster-windows.json"
ATTESTATION_PATH = "attestations/browser-poster-0.1.0.json"


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


class SyntheticLibrary:
    def __init__(self):
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.calls = []
        effect = {
            "kind": "field_equals",
            "match": {"provider": "browser"},
            "field": "poster_title",
            "value": {"param": "title"},
            "timeout_s": 3,
        }
        arguments = {
            "selectors": [{"kind": "label", "name": "Poster title"}],
            "text": "{title}",
        }
        self.workflow = {
            "schema_version": "l1ght5p33d/v1",
            "id": "poster-demo",
            "description": "Create a synthetic poster",
            "application": "browser",
            "configuration": {
                "url": "http://127.0.0.1:7332",
                "title_pattern": "L1ght5p33d Poster Studio",
                "headless": True,
            },
            "workflow": {
                "schema_version": 2,
                "name": "Synthetic poster",
                "params": {"title": "Example"},
                "steps": [
                    {
                        "id": "set-title",
                        "intent": "Set fixture title",
                        "action": "wait",
                        "api_binding": {
                            "kind": "tool",
                            "url_template": "browser",
                            "method": "fill",
                            "on_unavailable": "halt",
                            "body_template": arguments,
                            "effects": [effect],
                        },
                    }
                ],
            },
        }
        self.metadata = {
            "schema_version": "l1ght5p33d-curated-entry/v1",
            "id": "poster-demo",
            "version": "0.1.0",
            "title": "Synthetic browser poster",
            "summary": self.workflow["description"],
            "status": "fixture-qualified",
            "workflow": WORKFLOW_PATH,
            "sha256": "0" * 64,
            "license": "MIT",
            "runtime": {
                "project": "l1ght5p33d",
                "version": "0.1.0",
                "commit": COMMIT,
                "flow_version": "1.34.0",
            },
            "provenance": {
                "source_repository": "https://github.com/HiTecHelpLLC/l1ght5p33d",
                "source_commit": COMMIT,
                "source_path": "examples/l1ght5p33d/browser-poster.json",
                "copyright": ["Copyright synthetic test"],
                "modifications": "None",
            },
            "application": {
                "provider": "browser",
                "fixture": "l1ght5p33d.fixtures.creative",
                "configuration": copy.deepcopy(self.workflow["configuration"]),
            },
            "defaults": {"title": "Example"},
            "test_scope": {
                "kind": "local-browser-fixture",
                "command": "python scripts/qualify_browser.py --synthetic-fixture-only",
                "runtime_commit": COMMIT,
                "environment_substitutions": ["Synthetic loopback port"],
                "checks": ["Readback"],
                "limitations": ["Synthetic browser only; no live desktop"],
            },
            "explicit_local_approval_required": True,
            "reviewed_steps": [
                {
                    "id": "set-title",
                    "intent": "Set fixture title",
                    "provider": "browser",
                    "operation": "fill",
                    "arguments": copy.deepcopy(arguments),
                    "effects": copy.deepcopy([effect]),
                }
            ],
        }
        self.evidence = {
            "status": "fixture_qualified",
            "purpose": "Synthetic qualification test",
            "source_sha256": "0" * 64,
            "runtime": copy.deepcopy(self.metadata["runtime"]),
            "environment": {"platform": "Windows-11", "python": "3.12.6"},
            "steps_verified": 1,
            "semantic_fallback_verified": True,
            "independent_saved_state_verified": True,
            "model_calls": 0,
            "user_workflow_approval_granted": False,
        }
        self.claims = {
            "schema_version": "l1ght5p33d-attestation-claims/v1",
            "identity": "thebest",
            "role": "curator",
            "issued_at": "2026-09-03T22:00:00Z",
            "expires_at": "2026-12-02T22:00:00Z",
            "workflow": {"path": WORKFLOW_PATH, "sha256": "0" * 64},
            "metadata": {"path": METADATA_PATH, "sha256": "0" * 64},
            "evidence": {"path": EVIDENCE_PATH, "sha256": "0" * 64},
            "qualification": {
                "scope": "Synthetic Windows 11 browser fixture only",
                "environment": copy.deepcopy(self.evidence["environment"]),
                "source_commit": COMMIT,
            },
        }
        self.index = {
            "schema_version": "l1ght5p33d-curated-index/v1",
            "description": "Untrusted candidate paths",
            "entries": [METADATA_PATH],
            "source_files": [
                "index.json",
                WORKFLOW_PATH,
                METADATA_PATH,
                EVIDENCE_PATH,
                ATTESTATION_PATH,
            ],
        }
        self.files = {}
        self.publish()

    def sign(self, payload=None):
        payload = encoded(self.claims) if payload is None else payload
        self.files[ATTESTATION_PATH] = encoded(
            {
                "schema_version": "l1ght5p33d-attestation/v1",
                "algorithm": "Ed25519",
                "payload_b64": base64.b64encode(payload).decode("ascii"),
                "signature_b64": base64.b64encode(self.key.sign(payload)).decode(
                    "ascii"
                ),
            }
        )

    def publish(self):
        self.files[WORKFLOW_PATH] = encoded(self.workflow)
        digest = hashlib.sha256(self.files[WORKFLOW_PATH]).hexdigest()
        self.metadata["sha256"] = digest
        self.evidence["source_sha256"] = digest
        self.files[METADATA_PATH] = encoded(self.metadata)
        self.files[EVIDENCE_PATH] = encoded(self.evidence)
        for kind, path in (
            ("workflow", WORKFLOW_PATH),
            ("metadata", METADATA_PATH),
            ("evidence", EVIDENCE_PATH),
        ):
            self.claims[kind]["sha256"] = hashlib.sha256(self.files[path]).hexdigest()
        self.files["index.json"] = encoded(self.index)
        self.sign()

    def get(self, url, limit):
        assert url.startswith(packs.LIBRARY_BASE_URL)
        path = url.removeprefix(packs.LIBRARY_BASE_URL)
        self.calls.append(path)
        if path not in self.files:
            raise registry.RegistryError("Missing synthetic artifact")
        return self.files[path]

    def cached(self, now=NOW, **kwargs):
        return verify_pack(
            self.files[WORKFLOW_PATH],
            self.files[METADATA_PATH],
            self.files[EVIDENCE_PATH],
            self.files[ATTESTATION_PATH],
            now=now,
            **kwargs,
        )


@pytest.fixture
def library(monkeypatch):
    library = SyntheticLibrary()
    monkeypatch.setattr(
        packs,
        "THEBEST_PUBLIC_KEY_HEX",
        library.key.public_key().public_bytes_raw().hex(),
    )
    return library


def source(library):
    return CuratedPackSource(fetcher=library.get, clock=lambda: NOW)


def test_search_verifies_claims_without_downloading_or_executing_workflow(library):
    results = source(library).search("poster", application="browser")
    assert len(results) == 1
    assert results[0]["id"] == "poster-demo"
    assert results[0]["workflow_bytes_verified"] is False
    assert results[0]["execution_approved"] is False
    assert results[0]["provenance"]["role"] == "curator"
    assert results[0]["provenance"]["repository_head_authenticated"] is False
    assert "shipped" in results[0]["provenance"]["trust_source"]
    assert WORKFLOW_PATH not in library.calls
    assert len(library.calls) == 4
    assert source(library).search("BandLab") == []
    assert source(library).search("poster", application="windows") == []


def test_fetch_returns_exact_complete_bytes_and_honest_qualification(library):
    pack = source(library).fetch("poster-demo", "0.1.0")
    assert pack.workflow_bytes == library.files[WORKFLOW_PATH]
    assert pack.metadata_bytes == library.files[METADATA_PATH]
    assert pack.evidence_bytes == library.files[EVIDENCE_PATH]
    assert pack.attestation_bytes == library.files[ATTESTATION_PATH]
    assert pack.metadata_path == METADATA_PATH
    assert pack.workflow_sha256 == library.metadata["sha256"]
    assert pack.provenance["qualification"]["environment"]["platform"] == "Windows-11"
    assert pack.metadata["runtime"]["version"] == "0.1.0"
    assert pack.provenance["execution_approved"] is False
    assert pack.provenance["tests_executed_by_verifier"] is False
    assert pack.pack_digest == library.cached().pack_digest
    with pytest.raises(PackError, match="exact workflow ID and version"):
        source(library).fetch("poster-demo", "0.2.0")


@pytest.mark.parametrize("path", [WORKFLOW_PATH, METADATA_PATH, EVIDENCE_PATH])
def test_tampered_artifact_is_rejected(library, path):
    library.files[path] += b" "
    with pytest.raises(PackError, match="SHA-256"):
        source(library).fetch("poster-demo", "0.1.0")


def test_wrong_key_and_signature_tamper_are_rejected_before_metadata(library):
    library.key = Ed25519PrivateKey.from_private_bytes(b"x" * 32)
    library.sign()
    with pytest.raises(PackError, match="signature"):
        source(library).search("")
    assert METADATA_PATH not in library.calls
    envelope = json.loads(library.files[ATTESTATION_PATH])
    envelope["signature_b64"] = base64.b64encode(b"\0" * 64).decode("ascii")
    library.files[ATTESTATION_PATH] = encoded(envelope)
    with pytest.raises(PackError, match="signature"):
        library.cached()


@pytest.mark.parametrize(
    "field,value", [("role", "author"), ("identity", "another-curator")]
)
def test_author_role_or_other_identity_never_substitutes_for_curator(
    library, field, value
):
    library.claims[field] = value
    library.sign()
    with pytest.raises(PackError, match="curator role and identity"):
        source(library).search("")


@pytest.mark.parametrize(
    "change",
    [
        {"expires_at": "2026-09-03T22:30:00Z"},
        {"issued_at": "2026-09-04T00:00:00Z"},
        {"issued_at": "2026-02-30T22:00:00Z"},
        {"expires_at": "2026-12-02T22:00:00+00:00"},
    ],
)
def test_expired_future_or_invalid_timestamps_fail(library, change):
    library.claims.update(change)
    library.sign()
    with pytest.raises(PackError, match="expired|calendar|UTC timestamp"):
        source(library).search("")


def test_cached_use_rechecks_expiry_and_optional_metadata_path(library):
    assert library.cached().workflow_id == "poster-demo"
    with pytest.raises(PackError, match="expired"):
        library.cached(NOW + timedelta(days=91))
    with pytest.raises(PackError, match="metadata path"):
        library.cached(metadata_path="entries/different.json")


@pytest.mark.parametrize(
    "path",
    [
        "../escape.json",
        "entries/../escape.json",
        "https://evil.example/x",
        "entries/%2e%2e/x",
        "C:/data.json",
        "entries\\x.json",
        "/etc/passwd",
        "entries/CON.json",
        "entries//x.json",
        "entries/x.json?redirect=1",
    ],
)
def test_index_cannot_trigger_escaping_or_arbitrary_urls(library, path):
    library.index["entries"] = [path]
    library.index["source_files"].append(path)
    library.files["index.json"] = encoded(library.index)
    with pytest.raises(PackError, match="repository"):
        source(library).search("")
    assert library.calls == ["index.json"]


def test_signed_claim_paths_are_checked_before_following(library):
    library.claims["evidence"]["path"] = "https://evil.example/evidence.json"
    library.sign()
    with pytest.raises(PackError, match="repository"):
        source(library).search("")
    assert len(library.calls) == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lib: lib.metadata["runtime"].update(commit="f" * 40),
        lambda lib: lib.metadata["test_scope"].update(runtime_commit="f" * 40),
        lambda lib: lib.metadata["provenance"].update(source_commit="f" * 40),
        lambda lib: lib.claims["qualification"].update(source_commit="f" * 40),
    ],
)
def test_signed_but_incoherent_runtime_source_claims_fail(library, mutate):
    mutate(library)
    library.publish()
    with pytest.raises(PackError, match="commits disagree"):
        source(library).search("")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lib: lib.evidence["environment"].update(platform="unqualified"),
        lambda lib: lib.evidence.update(steps_verified=2),
        lambda lib: lib.evidence.update(model_calls=False),
        lambda lib: lib.evidence.update(user_workflow_approval_granted=True),
        lambda lib: lib.evidence.update(extra="hidden"),
    ],
)
def test_signed_but_incoherent_evidence_fails(library, mutate):
    mutate(library)
    library.publish()
    with pytest.raises(PackError, match="evidence"):
        source(library).search("")


def test_actual_action_is_checked_against_review_even_when_hash_signed(library):
    library.workflow["workflow"]["steps"][0]["api_binding"]["body_template"]["text"] = (
        "Unreviewed content"
    )
    library.publish()
    with pytest.raises(PackError, match="Actual actions"):
        source(library).fetch("poster-demo", "0.1.0")


def test_hidden_graph_or_include_cannot_expand_reviewed_steps(library):
    library.workflow["includes"] = {"surprise": "file.json"}
    library.publish()
    with pytest.raises(PackError, match="unknown or missing fields"):
        source(library).fetch("poster-demo", "0.1.0")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lib: lib.metadata.update(unknown="hidden"),
        lambda lib: lib.metadata["application"]["configuration"].update(
            url="https://evil.example"
        ),
        lambda lib: lib.metadata.update(explicit_local_approval_required=False),
        lambda lib: lib.metadata["runtime"].update(flow_version="1.35.0"),
    ],
)
def test_exact_closed_published_schema_is_enforced(library, mutate):
    mutate(library)
    library.publish()
    with pytest.raises(PackError, match="closed entry schema"):
        source(library).search("")


def test_noncanonical_payload_and_unknown_envelope_key_fail(library):
    library.sign(json.dumps(library.claims, indent=2).encode("ascii"))
    with pytest.raises(PackError, match="canonical"):
        library.cached()
    library.sign()
    envelope = json.loads(library.files[ATTESTATION_PATH])
    envelope["public_key_hex"] = "0" * 64
    library.files[ATTESTATION_PATH] = encoded(envelope)
    with pytest.raises(PackError, match="unknown or missing"):
        library.cached()


def test_duplicate_json_and_oversized_responses_fail(library):
    library.files["index.json"] = b'{"schema_version":"a","schema_version":"b"}'
    with pytest.raises(PackError, match="ASCII JSON"):
        source(library).search("")
    library.files["index.json"] = b" " * (packs.MAX_INDEX_BYTES + 1)
    with pytest.raises(PackError, match="byte limit"):
        source(library).search("")


def test_http_transport_is_readonly_fixed_origin_and_refuses_redirects(
    library, monkeypatch
):
    original = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/"})

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return original(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(registry.httpx, "Client", client)
    with pytest.raises(PackError, match="302"):
        CuratedPackSource(clock=lambda: NOW).search("")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == packs.LIBRARY_BASE_URL + "index.json"


def test_missing_signed_artifact_fails_closed(library):
    del library.files[EVIDENCE_PATH]
    with pytest.raises(PackError, match="Missing synthetic artifact"):
        source(library).search("")


def test_pack_digest_changes_when_signed_metadata_changes(library):
    first = library.cached().pack_digest
    library.metadata["title"] = "Updated reviewed title"
    library.publish()
    assert library.cached().pack_digest != first
