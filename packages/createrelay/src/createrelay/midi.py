"""Read-only Standard MIDI File analysis and reviewable import manifests."""

from __future__ import annotations

import hashlib
import json
import re
import wave
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mido

DEFAULT_CONFIG: dict[str, Any] = {
    "track_limit": 16,
    "duration_limit_seconds": 900,
    "track_order": [
        "drums",
        "bass",
        "chords",
        "keys",
        "guitar",
        "strings",
        "melody",
        "misc",
    ],
    "instruments": {
        "drums": "Standard Drum Kit",
        "bass": "Finger Bass",
        "chords": "Grand Piano",
        "keys": "Grand Piano",
        "guitar": "Acoustic Guitar",
        "strings": "String Ensemble",
        "melody": "Grand Piano",
        "misc": "Grand Piano",
    },
    "name_template": "{index:02d} {category} - {name}",
    "reference_offset_seconds": 0.0,
    "mute_reference": True,
    "quantize": False,
    "velocity_processing": "preserve",
    "effects": [],
    "pan": None,
    "gain": None,
}


def _classify(
    names: str,
    channels: list[int],
    programs: list[int],
    notes: list[int],
    max_polyphony: int,
) -> dict[str, Any]:
    """Heuristic proposals, deliberately distinct from authoritative MIDI data."""
    if 9 in channels:
        return {
            "category": "drums",
            "confidence": 0.98,
            "reason": "GM percussion channel 10",
        }
    terms = {
        "drums": r"drum|percussion|kick|snare|hi.?hat",
        "bass": r"bass",
        "guitar": r"guitar|gtr",
        "strings": r"string|violin|cello|viola",
        "keys": r"piano|keys|organ|keyboard",
        "chords": r"chord|harmony|pad",
        "melody": r"melody|lead|vocal",
    }
    for category, pattern in terms.items():
        if re.search(pattern, names, re.I):
            return {
                "category": category,
                "confidence": 0.85,
                "reason": "track/file name",
            }
    groups = [
        (range(32, 40), "bass"),
        (range(24, 32), "guitar"),
        (range(40, 56), "strings"),
        (range(0, 24), "keys"),
    ]
    for numbers, category in groups:
        if programs and all(program in numbers for program in programs):
            return {
                "category": category,
                "confidence": 0.8,
                "reason": "GM program family",
            }
    if notes and max(notes) <= 55:
        return {"category": "bass", "confidence": 0.6, "reason": "low note range"}
    if max_polyphony >= 3:
        return {
            "category": "chords",
            "confidence": 0.55,
            "reason": "simultaneous notes",
        }
    if notes:
        return {
            "category": "melody",
            "confidence": 0.5,
            "reason": "pitched note content",
        }
    return {"category": "misc", "confidence": 0.0, "reason": "no notes"}


def analyze_midi(path: str | Path) -> dict[str, Any]:
    """Analyze one SMF without modifying timing, velocity, controllers or source bytes."""
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Expected a .mid or .midi file")
    if source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("MIDI exceeds the 32 MiB analysis limit")
    midi = mido.MidiFile(source)
    if midi.ticks_per_beat <= 0:
        raise ValueError(
            "SMPTE division is not supported; convert to PPQN for import review"
        )
    tracks, tempos, signatures, warnings = [], [], [], []
    for index, track in enumerate(midi.tracks):
        ticks, max_polyphony = 0, 0
        active: Counter[tuple[int, int]] = Counter()
        notes: list[int] = []
        velocities: list[int] = []
        channels: set[int] = set()
        programs: list[dict[str, int]] = []
        controls: set[int] = set()
        pitchwheel_count = 0
        unmatched_off = 0
        for message in track:
            ticks += message.time
            if hasattr(message, "channel"):
                channels.add(message.channel)
            if message.type == "set_tempo":
                if message.tempo <= 0:
                    raise ValueError("MIDI contains a non-positive tempo")
                tempos.append(
                    {
                        "track": index,
                        "tick": ticks,
                        "microseconds_per_quarter": message.tempo,
                        "bpm_quarter": round(mido.tempo2bpm(message.tempo), 6),
                    }
                )
            elif message.type == "time_signature":
                signatures.append(
                    {
                        "track": index,
                        "tick": ticks,
                        "numerator": message.numerator,
                        "denominator": message.denominator,
                    }
                )
            elif message.type == "program_change":
                programs.append(
                    {
                        "tick": ticks,
                        "channel": message.channel,
                        "program": message.program,
                    }
                )
            elif message.type == "control_change":
                controls.add(message.control)
            elif message.type == "pitchwheel":
                pitchwheel_count += 1
            elif message.type == "note_on" and message.velocity > 0:
                notes.append(message.note)
                velocities.append(message.velocity)
                active[(message.channel, message.note)] += 1
                max_polyphony = max(max_polyphony, sum(active.values()))
            elif message.type in {"note_off", "note_on"}:
                key = (message.channel, message.note)
                if active[key]:
                    active[key] -= 1
                else:
                    unmatched_off += 1
        program_numbers = sorted({event["program"] for event in programs})
        classification = _classify(
            f"{source.stem} {track.name}",
            sorted(channels),
            program_numbers,
            notes,
            max_polyphony,
        )
        tracks.append(
            {
                "index": index,
                "name": track.name,
                "channels_zero_based": sorted(channels),
                "programs_zero_based": program_numbers,
                "program_changes": programs,
                "note_count": len(notes),
                "note_range": [min(notes), max(notes)] if notes else None,
                "velocity_range": [min(velocities), max(velocities)]
                if velocities
                else None,
                "end_tick": ticks,
                "empty": not notes,
                "max_polyphony": max_polyphony,
                "controller_numbers": sorted(controls),
                "pitchwheel_count": pitchwheel_count,
                "unclosed_notes": sum(active.values()),
                "unmatched_note_off": unmatched_off,
                "classification": classification,
            }
        )
        if sum(active.values()) or unmatched_off:
            warnings.append(
                f"Track {index}: unmatched note-on/off events require review"
            )
        if len(channels) > 1:
            warnings.append(
                f"Track {index}: multiple MIDI channels; confirm live track fan-out"
            )
    if midi.type == 2:
        duration = None
        warnings.append(
            "Type 2 has asynchronous tracks; no single project duration or import plan inferred"
        )
    else:
        duration = round(midi.length, 6)
    tempo_values = {event["microseconds_per_quarter"] for event in tempos}
    if len(tempo_values) > 1:
        warnings.append(
            "Tempo map changes: a single Studio tempo cannot represent the complete map"
        )
    return {
        "path": str(source),
        "filename": source.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "midi_type": midi.type,
        "ticks_per_beat": midi.ticks_per_beat,
        "tempo_events": sorted(
            tempos, key=lambda event: (event["tick"], event["track"])
        ),
        "time_signatures": signatures,
        "default_tempo_bpm_quarter": 120,
        "tracks": tracks,
        "empty_tracks": [track["index"] for track in tracks if track["empty"]],
        "nonempty_track_count": sum(not track["empty"] for track in tracks),
        "note_count": sum(track["note_count"] for track in tracks),
        "duration_seconds": duration,
        "warnings": warnings,
        "source_modified": False,
    }


def build_manifest(
    folder: str | Path,
    reference_wav: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect a folder and propose an ordered import manifest for human review."""
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("MIDI folder must be a directory")
    settings = {**DEFAULT_CONFIG, **(config or {})}
    if settings["quantize"] or settings["velocity_processing"] != "preserve":
        raise ValueError(
            "Destructive MIDI processing is not implemented; sources are always preserved"
        )
    for field in ("effects", "pan", "gain"):
        if settings[field]:
            raise ValueError(
                f"Production processing '{field}' is not implemented; use an explicit future provider"
            )
    order = settings["track_order"]
    analyses = [
        analyze_midi(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.suffix.lower() in {".mid", ".midi"}
    ]
    if not analyses:
        raise ValueError("No .mid or .midi files found in the folder")
    imports: list[dict[str, Any]] = []
    review: list[str] = []
    for analysis in analyses:
        review.extend(
            f"{analysis['filename']}: {warning}" for warning in analysis["warnings"]
        )
        if analysis["midi_type"] == 2:
            raise ValueError(
                f"{analysis['filename']}: type-2 asynchronous MIDI requires manual conversion"
            )
        if not analysis["nonempty_track_count"]:
            review.append(f"{analysis['filename']}: no notes; omitted from import")
            continue
        nonempty = [track for track in analysis["tracks"] if not track["empty"]]
        category = nonempty[0]["classification"]["category"]
        imports.append(
            {
                "path": analysis["path"],
                "sha256": analysis["sha256"],
                "kind": "midi",
                "category": category,
                "expected_tracks": len(nonempty),
                "tracks": nonempty,
                "analysis": analysis,
            }
        )
    imports.sort(
        key=lambda item: (
            order.index(item["category"]) if item["category"] in order else len(order),
            Path(item["path"]).name.lower(),
        )
    )
    index = 1
    for item in imports:
        item["track_settings"] = []
        for track in item["tracks"]:
            category = track["classification"]["category"]
            name = track["name"] or Path(item["path"]).stem
            item["track_settings"].append(
                {
                    "name": settings["name_template"].format(
                        index=index, category=category, name=name
                    ),
                    "instrument": settings["instruments"].get(category, "Grand Piano"),
                    "offset_seconds": 0.0,
                }
            )
            if track["classification"]["confidence"] < 0.8:
                review.append(
                    f"{name}: uncertain {category} classification; confirm instrument"
                )
            index += 1
    reference = None
    if reference_wav is not None:
        reference_path = Path(reference_wav).resolve(strict=True)
        if reference_path.suffix.lower() != ".wav":
            raise ValueError("Reference must be a WAV file")
        with wave.open(str(reference_path), "rb") as audio:
            reference_duration = audio.getnframes() / audio.getframerate()
        reference = {
            "path": str(reference_path),
            "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            "kind": "audio",
            "expected_tracks": 1,
            "name": "Reference",
            "duration_seconds": reference_duration,
            "offset_seconds": settings["reference_offset_seconds"],
            "muted": settings["mute_reference"],
        }
    count = sum(item["expected_tracks"] for item in imports) + bool(reference)
    if count > settings["track_limit"]:
        raise ValueError(
            f"Expected {count} tracks exceeds configured limit {settings['track_limit']}"
        )
    durations = [item["duration_seconds"] or 0 for item in analyses]
    if reference:
        durations.append(reference["duration_seconds"])
    if max(durations, default=0) > settings["duration_limit_seconds"]:
        raise ValueError("Media exceeds configured project duration limit")
    tempos = {
        event["bpm_quarter"]
        for analysis in analyses
        for event in analysis["tempo_events"]
    }
    if len(tempos) > 1:
        review.append(
            "Conflicting/variable tempos: project tempo left for manual review"
        )
    return {
        "schema_version": "createrelay.midi/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_folder": str(root),
        "imports": imports,
        "reference": reference,
        "expected_track_count": count,
        "project_tempo": next(iter(tempos))
        if len(tempos) == 1
        else (120 if not tempos else None),
        "configuration": settings,
        "manual_review": review,
        "sources_preserved": True,
        "classification_is_heuristic": True,
        "reviewed": False,
    }


def write_manifest(manifest: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )


def generate_synthetic_midi(folder: str | Path) -> list[Path]:
    """Original synthetic fixtures: two short public-test melodies, never personal music."""
    destination = Path(folder)
    destination.mkdir(parents=True, exist_ok=True)
    result = []
    for name, channel, program, notes in [
        ("drums", 9, 0, [36, 38, 42, 38]),
        ("bass", 0, 33, [36, 40, 43, 40]),
    ]:
        midi = mido.MidiFile(type=1)
        tempo = mido.MidiTrack()
        tempo.extend(
            [
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("time_signature"),
            ]
        )
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name))
        track.append(mido.Message("program_change", channel=channel, program=program))
        for note in notes:
            track.extend(
                [
                    mido.Message(
                        "note_on", channel=channel, note=note, velocity=83, time=7
                    ),
                    mido.Message(
                        "note_off", channel=channel, note=note, velocity=0, time=473
                    ),
                ]
            )
        midi.tracks.extend([tempo, track])
        path = destination / f"{name}.mid"
        midi.save(path)
        result.append(path)
    return result
