from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from urllib.request import urlopen

import pytest

from createrelay.fixtures.bandlab import start_fixture
from createrelay.midi import build_manifest, generate_synthetic_midi
from createrelay.providers.bandlab import BandLabProvider, build_bandlab_workflow
from createrelay.providers.base import ProviderRefused
from createrelay.workflow import validate_document

pytestmark = pytest.mark.browser


def execute_document(provider: BandLabProvider, document: dict) -> None:
    for step in document["workflow"]["steps"]:
        binding = step["api_binding"]
        provider.execute(binding["method"], binding["body_template"])
        state = provider.inspect()
        for effect in binding["effects"]:
            literal = effect["value"]
            if isinstance(literal, dict):
                literal = literal["literal"]
            assert str(state[effect["field"]]) == literal


def test_full_browser_import_reference_and_independent_saved_store(
    tmp_path: Path,
) -> None:
    generate_synthetic_midi(tmp_path)
    reference = tmp_path / "reference.wav"
    with wave.open(str(reference), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 800)
    manifest = build_manifest(tmp_path, reference)
    with start_fixture() as url:
        document = build_bandlab_workflow(manifest, url=url)
        validate_document(document)
        provider = BandLabProvider(document["configuration"]["bandlab"])
        try:
            execute_document(provider, document)
            state = provider.inspect()
            assert state["track_count"] == 3
            assert state["saved"] is True
            assert state["track_0_muted"] is True
            assert state["track_1_instrument"] == "Standard Drum Kit"
            with urlopen(url.replace("/studio", "/api/project")) as response:
                projects = json.load(response)
            project = projects["CreateRelay Import"]
            assert len(project["tracks"]) == 3
            assert project["tracks"][0]["muted"] is True
            assert project["tracks"][2]["instrument"] == "Finger Bass"
        finally:
            provider.close()


def test_declared_dom_fallback_is_used(tmp_path: Path) -> None:
    generate_synthetic_midi(tmp_path)
    item = build_manifest(tmp_path)["imports"][0]
    with start_fixture() as url:
        provider = BandLabProvider(
            {"url": url + "?missing_selector=1", "read_roots": [str(tmp_path)]}
        )
        try:
            provider.execute("open_studio", {})
            receipt = provider.execute("import_file", item)
            import_attempts = [
                item for item in receipt["selector_chain"] if item["key"] == "import"
            ]
            assert [item["selector"]["method"] for item in import_attempts] == [
                "label",
                "css",
            ]
            assert import_attempts[0]["matches"] == 0
            assert provider.inspect()["track_count"] == 1
        finally:
            provider.close()


@pytest.mark.parametrize(
    "query,match",
    [("ambiguous_selector=1", "Ambiguous"), ("wrong_identity=1", "studio")],
)
def test_wrong_or_ambiguous_target_refuses(
    tmp_path: Path, query: str, match: str
) -> None:
    generate_synthetic_midi(tmp_path)
    item = build_manifest(tmp_path)["imports"][0]
    with start_fixture() as url:
        provider = BandLabProvider(
            {"url": url + "?" + query, "read_roots": [str(tmp_path)]}
        )
        try:
            with pytest.raises(ProviderRefused, match=match):
                provider.execute("open_studio", {})
                provider.execute("import_file", item)
        finally:
            provider.close()


def test_failed_save_never_looks_successful(tmp_path: Path) -> None:
    with start_fixture() as url:
        provider = BandLabProvider({"url": url + "?reject_save=1", "timeout_ms": 200})
        try:
            provider.execute("open_studio", {})
            with pytest.raises(Exception):
                provider.execute("save", {})
            assert provider.inspect()["saved"] is False
        finally:
            provider.close()


def test_partial_import_stops_uncertain(tmp_path: Path) -> None:
    generate_synthetic_midi(tmp_path)
    item = build_manifest(tmp_path)["imports"][0]
    with start_fixture() as url:
        provider = BandLabProvider(
            {
                "url": url + "?partial_import=1",
                "read_roots": [str(tmp_path)],
                "timeout_ms": 200,
            }
        )
        try:
            provider.execute("open_studio", {})
            with pytest.raises(Exception):
                provider.execute("import_file", item)
            assert provider.inspect()["track_count"] == 0
            with pytest.raises(ProviderRefused, match="Previous delivery"):
                provider.execute("import_file", item)
        finally:
            provider.close()


def test_manifest_hash_and_path_gate_precede_upload(tmp_path: Path) -> None:
    generate_synthetic_midi(tmp_path)
    item = build_manifest(tmp_path)["imports"][0]
    with start_fixture() as url:
        provider = BandLabProvider({"url": url, "read_roots": [str(tmp_path)]})
        try:
            provider.execute("open_studio", {})
            with pytest.raises(ProviderRefused, match="changed"):
                provider.execute("import_file", {**item, "sha256": "0" * 64})
            assert provider.inspect()["track_count"] == 0
            provider.read_roots = []
            with pytest.raises(ProviderRefused, match="read roots"):
                provider.execute("import_file", item)
        finally:
            provider.close()


def test_live_requires_review_and_origin(tmp_path: Path) -> None:
    generate_synthetic_midi(tmp_path)
    with pytest.raises(ValueError, match="reviewed manifest"):
        build_bandlab_workflow(
            build_manifest(tmp_path), url="https://www.bandlab.com/studio", mode="live"
        )
    with pytest.raises(ValueError, match="https://www.bandlab.com"):
        BandLabProvider({"url": "https://example.com", "mode": "live"})
    with pytest.raises(ValueError, match="calibration"):
        BandLabProvider({"url": "https://www.bandlab.com/studio", "mode": "live"})


def test_native_flow_replayer_drives_real_browser(tmp_path: Path) -> None:
    from createrelay.providers.base import ProviderVerifier, ToolActuator
    from createrelay.runtime import ControlledReplayer

    generate_synthetic_midi(tmp_path)
    with start_fixture() as url:
        document = validate_document(
            build_bandlab_workflow(build_manifest(tmp_path), url=url)
        )
        provider = BandLabProvider(document.configuration["bandlab"])
        registry = {"bandlab": provider}
        receipts = []
        player = ControlledReplayer(
            api_actuator=ToolActuator(registry),
            effect_verifier=ProviderVerifier(registry),
            receipt_sink=receipts.append,
            durable=True,
        )
        bundle = tmp_path / "bundle"
        document.workflow.save(bundle)
        try:
            report = player.run(
                document.workflow, bundle_dir=bundle, run_dir=tmp_path / "run"
            )
            assert report.model_calls == 0
            assert all(result.effect_verified for result in report.results), (
                report.model_dump()
            )
            assert len(report.results) == len(document.workflow.steps)
            assert provider.inspect()["saved"] is True
            assert len(receipts) == len(document.workflow.steps)
        finally:
            provider.close()


@pytest.mark.windows
@pytest.mark.skipif(
    sys.platform != "win32", reason="Known vendor browser paths are Windows only"
)
def test_detached_dedicated_profile_preserves_page_after_disconnect(
    tmp_path: Path,
) -> None:
    from playwright.sync_api import sync_playwright

    from createrelay.providers.bandlab import _browser_binary, _connect_dedicated

    try:
        _browser_binary("msedge")
    except ProviderRefused:
        pytest.skip("Edge is not installed in a known vendor location")
    with start_fixture() as url:
        first = sync_playwright().start()
        _, context, identity = _connect_dedicated(
            first, tmp_path / "isolated-profile", "msedge"
        )
        page = context.new_page()
        page.goto(url)
        first.stop()
        second = sync_playwright().start()
        browser, context, attached = _connect_dedicated(
            second, tmp_path / "isolated-profile", "msedge"
        )
        try:
            assert attached["process_id"] == identity["process_id"]
            assert any(page.url == url for page in context.pages)
            assert attached["debugging_host"] == "127.0.0.1"
        finally:
            browser.close()
            second.stop()


def test_workflow_regeneration_has_stable_approval_digest(tmp_path: Path) -> None:
    from createrelay.workflow import document_digest

    generate_synthetic_midi(tmp_path)
    manifest = build_manifest(tmp_path)
    one = validate_document(
        build_bandlab_workflow(manifest, url="http://127.0.0.1:9999/studio")
    )
    two = validate_document(
        build_bandlab_workflow(manifest, url="http://127.0.0.1:9999/studio")
    )
    assert document_digest(one) == document_digest(two)
