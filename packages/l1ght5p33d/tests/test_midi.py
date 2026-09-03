from __future__ import annotations

import hashlib
from pathlib import Path

import mido
import pytest

from l1ght5p33d.midi import (
    analyze_midi,
    build_manifest,
    generate_synthetic_midi,
    write_manifest,
)


def test_manifest_preserves_sources_and_classifies(tmp_path: Path) -> None:
    paths = generate_synthetic_midi(tmp_path)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    manifest = build_manifest(tmp_path)
    assert manifest["expected_track_count"] == 2
    assert [item["category"] for item in manifest["imports"]] == ["drums", "bass"]
    assert manifest["project_tempo"] == 120
    assert manifest["reviewed"] is False
    assert manifest["imports"][0]["analysis"]["empty_tracks"] == [0]
    assert manifest["imports"][0]["analysis"]["tracks"][1]["velocity_range"] == [83, 83]
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    } == before
    destination = tmp_path / "manifest.json"
    write_manifest(manifest, destination)
    destination.read_text(encoding="ascii")


def test_tempo_changes_and_zero_velocity_note_off(tmp_path: Path) -> None:
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack(
        [
            mido.MetaMessage("set_tempo", tempo=500000),
            mido.Message("note_on", note=60, velocity=100),
            mido.Message("note_on", note=60, velocity=0, time=480),
            mido.MetaMessage("set_tempo", tempo=1000000),
            mido.Message("note_on", note=62, velocity=64),
            mido.Message("note_off", note=62, time=480),
        ]
    )
    midi.tracks.append(track)
    path = tmp_path / "tempo.mid"
    midi.save(path)
    result = analyze_midi(path)
    assert result["duration_seconds"] == 1.5
    assert result["note_count"] == 2
    assert result["tracks"][0]["unclosed_notes"] == 0
    assert result["tracks"][0]["note_range"] == [60, 62]
    assert build_manifest(tmp_path)["project_tempo"] is None


def test_track_limit_counts_nonempty_tracks_not_files(tmp_path: Path) -> None:
    paths = generate_synthetic_midi(tmp_path)
    midi = mido.MidiFile(paths[0])
    midi.tracks.append(mido.MidiFile(paths[1]).tracks[1])
    midi.save(paths[0])
    paths[1].unlink()
    assert build_manifest(tmp_path)["expected_track_count"] == 2
    with pytest.raises(ValueError, match="exceeds configured limit"):
        build_manifest(tmp_path, config={"track_limit": 1})


def test_type_two_is_inspected_but_not_automatically_imported(tmp_path: Path) -> None:
    path = generate_synthetic_midi(tmp_path)[0]
    midi = mido.MidiFile(path)
    midi.type = 2
    midi.save(path)
    assert analyze_midi(path)["duration_seconds"] is None
    with pytest.raises(ValueError, match="type-2"):
        build_manifest(tmp_path)


def test_processing_never_silently_alters_sources(tmp_path: Path) -> None:
    generate_synthetic_midi(tmp_path)
    with pytest.raises(ValueError, match="Destructive"):
        build_manifest(tmp_path, config={"quantize": True})


def test_empty_and_invalid_midi(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No .mid"):
        build_manifest(tmp_path)
    path = tmp_path / "bad.mid"
    path.write_bytes(b"not midi")
    with pytest.raises((OSError, EOFError)):
        analyze_midi(path)


def test_program_and_expressive_metadata(tmp_path: Path) -> None:
    midi = mido.MidiFile(type=0)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("program_change", program=48),
                mido.Message("control_change", control=64, value=127),
                mido.Message("pitchwheel", pitch=100),
                mido.Message("note_on", note=70, velocity=50),
                mido.Message("note_off", note=70, time=480),
            ]
        )
    )
    path = tmp_path / "part.mid"
    midi.save(path)
    track = analyze_midi(path)["tracks"][0]
    assert track["classification"]["category"] == "strings"
    assert track["controller_numbers"] == [64]
    assert track["pitchwheel_count"] == 1
