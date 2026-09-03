import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from l1ght5p33d import registry
from l1ght5p33d.registry import (
    MAX_CATALOG_BYTES,
    RegistryError,
    WorkflowEntry,
    fetch_catalog,
    install_workflow,
    load_catalog,
    raw_cid,
)


def workflow_bytes(**changes):
    data = {
        "schema_version": "l1ght5p33d/v1",
        "id": "poster",
        "application": "browser",
        "configuration": {"url": "http://127.0.0.1:7332"},
        "workflow": {
            "schema_version": 2,
            "name": "Shared harmless poster workflow",
            "params": {"title": "A synthetic poster"},
            "steps": [
                {
                    "id": "set-title",
                    "intent": "Set and read back a fixture title",
                    "action": "wait",
                    "api_binding": {
                        "kind": "tool",
                        "method": "fill",
                        "url_template": "browser",
                        "on_unavailable": "halt",
                        "body_template": {
                            "selectors": [{"kind": "label", "name": "Poster title"}],
                            "text": "{title}",
                        },
                        "effects": [
                            {
                                "kind": "field_equals",
                                "match": {"provider": "browser"},
                                "field": "poster_title",
                                "value": {"param": "title"},
                            }
                        ],
                    },
                }
            ],
        },
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=True).encode("ascii")


def entry_data(data=None, **changes):
    data = workflow_bytes() if data is None else data
    entry = {
        "id": "poster",
        "version": "0.1.0",
        "title": "Local poster editor",
        "description": "Synthetic example; no live application claim",
        "application": "browser",
        "workflow_schema": "l1ght5p33d/v1",
        "runtime_version": "1.34.0",
        "license": "MIT",
        "cid": raw_cid(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "compatibility": {"browser": "Chromium fixture"},
        "verification": {"level": "fixture", "description": "Synthetic readback"},
    }
    entry.update(changes)
    return entry


def catalog_data(**changes):
    now = datetime.now(UTC)
    data = {
        "schema_version": "l1ght5p33d-catalog/v1",
        "revision": 1,
        "generated_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "workflows": [entry_data()],
    }
    data.update(changes)
    return data


@pytest.fixture
def key():
    return Ed25519PrivateKey.generate()


def signed(key, payload=None):
    if payload is None:
        payload = catalog_data()
    if not isinstance(payload, bytes):
        payload = json.dumps(payload, ensure_ascii=True).encode("ascii")
    return json.dumps(
        {
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "signature_b64": base64.b64encode(key.sign(payload)).decode("ascii"),
        }
    ).encode("ascii")


def public_hex(key):
    return key.public_key().public_bytes_raw().hex()


@pytest.fixture
def transport(monkeypatch):
    original_client = httpx.Client
    requests = []

    def set_response(response):
        def handle(request):
            requests.append(request)
            return response(request) if callable(response) else response

        def client(**kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
            assert kwargs["headers"]["Accept-Encoding"] == "identity"
            return original_client(transport=httpx.MockTransport(handle), **kwargs)

        monkeypatch.setattr(registry.httpx, "Client", client)
        return requests

    return set_response


def test_signed_catalog_verifies_exact_bytes_and_metadata(key):
    catalog = load_catalog(signed(key), public_hex(key))
    assert catalog.revision == 1
    assert catalog.workflows[0].runtime_version == "1.34.0"
    assert catalog.workflows[0].verification.level == "fixture"


def test_signature_is_checked_before_parsing_payload(key):
    envelope = json.loads(signed(key, b"not JSON: \xff"))
    envelope["signature_b64"] = base64.b64encode(b"\0" * 64).decode("ascii")
    with pytest.raises(RegistryError, match="signature"):
        load_catalog(json.dumps(envelope).encode("ascii"), public_hex(key))
    with pytest.raises(RegistryError, match="signature"):
        load_catalog(signed(key), public_hex(Ed25519PrivateKey.generate()))


@pytest.mark.parametrize("value", ["", "ab", "g" * 64, "ab " * 32])
def test_public_key_requires_raw_hex(key, value):
    with pytest.raises(RegistryError, match="32-byte hex"):
        load_catalog(signed(key), value)


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": True},
        {"schema_version": "other/v1"},
        {"revision": 0},
        {"revision": "1"},
        {"generated_at": "2026-09-03T12:00:00"},
        {"generated_at": "2026-09-03T12:00:00-07:00"},
        {"workflows": [entry_data(), entry_data()]},
    ],
)
def test_strict_catalog_schema_refuses_malformed_input(key, change):
    with pytest.raises(ValueError):
        load_catalog(signed(key, catalog_data(**change)), public_hex(key))


@pytest.mark.parametrize(
    "change, message",
    [
        ({"expires_at": "2000-01-01T00:00:00Z"}, "expired"),
        (
            {"generated_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
            "future",
        ),
        (
            {
                "generated_at": (datetime.now(UTC) + timedelta(minutes=4)).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
            },
            "follow generation",
        ),
    ],
)
def test_expiry_and_generation_skew_are_enforced(key, change, message):
    with pytest.raises(ValueError, match=message):
        load_catalog(signed(key, catalog_data(**change)), public_hex(key))


@pytest.mark.parametrize(
    "payload",
    [b'{"revision":1,"revision":2}', b'{"revision":NaN}', b"[]", b'{"x":"\xff"}'],
)
def test_payload_json_is_ascii_unique_and_finite(key, payload):
    with pytest.raises(RegistryError):
        load_catalog(signed(key, payload), public_hex(key))


def test_envelope_is_strict_bounded_and_canonical_base64(key):
    envelope = json.loads(signed(key))
    envelope["extra"] = True
    with pytest.raises(ValueError):
        load_catalog(json.dumps(envelope).encode("ascii"), public_hex(key))
    envelope.pop("extra")
    envelope["payload_b64"] += "\n"
    with pytest.raises(RegistryError, match="base64"):
        load_catalog(json.dumps(envelope).encode("ascii"), public_hex(key))
    with pytest.raises(RegistryError, match="2 MB"):
        load_catalog(b" " * (MAX_CATALOG_BYTES + 1), public_hex(key))


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../escape"},
        {"application": "../../shell"},
        {"version": "01.0.0"},
        {"version": "1.0.0-01"},
        {"version": "1.0"},
        {"runtime_version": "1.35.0"},
        {"workflow_schema": "foreign/v1"},
        {"cid": raw_cid(b"another block")},
        {"size_bytes": 1_000_001},
        {"size_bytes": True},
        {"license": ""},
        {"extra": "metadata"},
        {"compatibility": {"browser": {"nested": "value"}}},
        {"verification": {"level": "trusted", "description": "unsupported claim"}},
    ],
)
def test_entry_schema_rejects_unsupported_or_inconsistent_metadata(changes):
    with pytest.raises(ValueError):
        WorkflowEntry.model_validate(entry_data(**changes))


def test_fetch_signed_catalog_with_mock_transport(key, transport):
    requests = transport(httpx.Response(200, content=signed(key)))
    catalog = fetch_catalog("https://catalog.example/workflows", public_hex(key))
    assert catalog.workflows[0].id == "poster"
    assert len(requests) == 1
    assert requests[0].method == "GET"


@pytest.mark.parametrize(
    "url",
    [
        "http://catalog.example/workflows",
        "http://localhost/catalog",
        "file:///etc/passwd",
        "https://user:password@catalog.example/",
        "https://catalog.example/#fragment",
        "https://catalog.example/\nunsafe",
    ],
)
def test_fetch_rejects_unsafe_urls_before_network(key, transport, url):
    requests = transport(httpx.Response(200, content=signed(key)))
    with pytest.raises(RegistryError):
        fetch_catalog(url, public_hex(key))
    assert requests == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://other.example/catalog"}),
        httpx.Response(200, headers={"content-length": str(MAX_CATALOG_BYTES + 1)}),
        httpx.Response(200, content=b" " * (MAX_CATALOG_BYTES + 1)),
        httpx.Response(200, headers={"content-length": "-1"}),
        httpx.Response(200, headers={"content-length": "10"}, content=b"short"),
        httpx.Response(200, headers={"content-encoding": "unsupported"}),
    ],
)
def test_redirects_sizes_and_encoded_responses_are_refused(key, transport, response):
    requests = transport(response)
    with pytest.raises(RegistryError):
        fetch_catalog("http://127.0.0.1:7332/catalog", public_hex(key))
    assert len(requests) == 1


def test_install_exact_block_without_execution_or_policy_changes(tmp_path, transport):
    data = workflow_bytes()
    entry = WorkflowEntry.model_validate(entry_data(data))
    requests = transport(httpx.Response(200, content=data))
    policy = tmp_path / "policy.json"
    policy.write_text('{"approved_workflow_digests": []}', encoding="ascii")
    destination = install_workflow(entry, tmp_path)
    assert destination == tmp_path / "workflow-poster.json"
    assert destination.read_bytes() == data
    assert policy.read_text("ascii") == '{"approved_workflow_digests": []}'
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "policy.json",
        "workflow-poster.json",
    ]
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v0/block/get"
    assert dict(requests[0].url.params) == {"arg": entry.cid}


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:5001",
        "https://remote.example:5001",
        "http://127.1:5001",
        "http://2130706433:5001",
        "http://127.0.0.1:5001/proxy",
        "http://127.0.0.1:5001?arg=another",
        "http://user@127.0.0.1:5001",
    ],
)
def test_kubo_is_literal_loopback_only(tmp_path, transport, url):
    requests = transport(httpx.Response(200, content=workflow_bytes()))
    with pytest.raises(RegistryError):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path, url)
    assert requests == []
    assert list(tmp_path.iterdir()) == []


def test_kubo_accepts_literal_ipv6(tmp_path, transport):
    requests = transport(httpx.Response(200, content=workflow_bytes()))
    install_workflow(
        WorkflowEntry.model_validate(entry_data()), tmp_path, "http://[::1]:5001/"
    )
    assert requests[0].url.host == "::1"


@pytest.mark.parametrize("data", [b"short", b" " * len(workflow_bytes())])
def test_block_size_or_hash_mismatch_leaves_no_artifact(tmp_path, transport, data):
    transport(httpx.Response(200, content=data))
    with pytest.raises(RegistryError, match="size|SHA-256"):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "data",
    [
        b"not JSON",
        workflow_bytes(includes={"private": "../private.json"}),
        workflow_bytes(id="different"),
        workflow_bytes(application="windows"),
        workflow_bytes(workflow={"schema_version": 2, "name": "empty", "steps": []}),
    ],
)
def test_invalid_or_mismatched_workflow_never_installs(tmp_path, transport, data):
    transport(httpx.Response(200, content=data))
    with pytest.raises(ValueError):
        install_workflow(WorkflowEntry.model_validate(entry_data(data)), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_install_refuses_existing_file_without_network(tmp_path, transport):
    destination = tmp_path / "workflow-poster.json"
    destination.write_bytes(b"original")
    requests = transport(httpx.Response(200, content=workflow_bytes()))
    with pytest.raises(RegistryError, match="overwrite"):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path)
    assert destination.read_bytes() == b"original"
    assert requests == []


def test_install_exclusive_create_refuses_racing_file(tmp_path, transport):
    destination = tmp_path / "workflow-poster.json"

    def concurrent_file(request):
        destination.write_bytes(b"another owner")
        return httpx.Response(200, content=workflow_bytes())

    transport(concurrent_file)
    with pytest.raises(RegistryError, match="overwrite"):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path)
    assert destination.read_bytes() == b"another owner"


def test_install_rejects_symlink_without_touching_target(tmp_path, transport):
    target = tmp_path / "private.txt"
    target.write_bytes(b"private")
    destination = tmp_path / "workflow-poster.json"
    try:
        destination.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable to this Windows test account")
    requests = transport(httpx.Response(200, content=workflow_bytes()))
    with pytest.raises(RegistryError, match="overwrite"):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path)
    assert target.read_bytes() == b"private"
    assert requests == []


def test_windows_reserved_id_has_safe_prefixed_filename(tmp_path, transport):
    data = workflow_bytes(id="con")
    transport(httpx.Response(200, content=data))
    destination = install_workflow(
        WorkflowEntry.model_validate(entry_data(data, id="con")), tmp_path
    )
    assert destination.name == "workflow-con.json"
    assert destination.read_bytes() == data


def test_chunked_oversize_download_is_stopped_before_install(tmp_path, transport):
    data = workflow_bytes()
    transport(httpx.Response(200, stream=httpx.ByteStream(data + b"extra")))
    with pytest.raises(RegistryError, match="byte limit"):
        install_workflow(WorkflowEntry.model_validate(entry_data(data)), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_missing_effect_contract_never_installs(tmp_path, transport):
    document = json.loads(workflow_bytes())
    document["workflow"]["steps"][0]["api_binding"]["effects"] = []
    data = json.dumps(document).encode("ascii")
    transport(httpx.Response(200, content=data))
    with pytest.raises(ValueError, match="effects"):
        install_workflow(WorkflowEntry.model_validate(entry_data(data)), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_network_failure_leaves_no_artifact(tmp_path, transport):
    def timeout(request):
        raise httpx.ReadTimeout("synthetic unavailable peer", request=request)

    transport(timeout)
    with pytest.raises(RegistryError, match="network request"):
        install_workflow(WorkflowEntry.model_validate(entry_data()), tmp_path)
    assert list(tmp_path.iterdir()) == []
