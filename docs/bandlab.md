# BandLab MIDI reference integration

CreateRelay is unofficial and unaffiliated with BandLab or Suno. This adapter is one reference integration; the core interpreter has no BandLab dependency.

The automated reference path runs against an original local Studio fixture. It imports actual synthetic Standard MIDI File bytes through Chromium's file input, creates observable tracks and regions, renames them, selects instruments, aligns offsets, mutes an optional reference WAV, saves, and checks visible state. Tests also query the fixture's separate saved-project store. **The live BandLab interface has not been authenticated or validated in this release.** Fixture coverage proves the complete workflow contract, not that its selectors match the current live site.

## Local MIDI inspection

```powershell
createrelay midi C:\Music\SunoMidi --out C:\Music\import-manifest.json
```

The manifest records source SHA-256, type, PPQN, tempo events, time signatures, track/channel/program data, note and velocity ranges, note counts, duration, empty tracks, controller numbers and pitch-wheel events. Program/channel values are explicitly zero-based. No source bytes are rewritten. Type-2 asynchronous MIDI can be inspected but cannot be automatically imported; there is no unambiguous single project timeline. SMPTE-divided files stop for conversion rather than guessing time units.

Classification is a proposal: GM percussion channel, names, GM program family, note range and polyphony provide progressively weaker evidence. Low-confidence results, conflicting tempo maps and unmatched note events appear in `manual_review`. Read this list and check every proposed instrument. Audio-derived transcription can have errors; naming a part does not restore a missing performance.

Use `build_manifest(folder, reference_wav=..., config=...)` from Python for reference WAV and custom settings. The configuration controls track order, name template, instrument map, track/duration limits, reference offset and mute. Source timing, velocities, controllers and expressive data are preserved. `quantize=true`, velocity processing, effects, gain and pan processing are currently rejected with an explicit message rather than silently applied. Those production operations need a future reviewed provider implementation.

The CLI accepts `--reference-wav C:\Music\reference.wav` and `--config mapping.json` for the same settings. A complete synthetic demonstration is one command:

```powershell
createrelay demo bandlab --headful
```

Current documented BandLab limits are 16 tracks, or 32 with Membership, and 15 minutes in both cases. Count nonempty MIDI tracks plus the reference, not just files. Multi-channel files may have different live import fan-out and are flagged for review. [Official limits](https://help.bandlab.com/hc/en-us/articles/115002945433-Track-and-Project-Duration-Limits).

## Fixture contract and test coverage

The bundled local fixture contains no copied BandLab code or artwork and contacts no cloud service. It models the documented New Project, Import Audio/MIDI, track/region, instrument, offset/mute and save behaviors. Its file parser handles SMF track chunks, meta events and running status, and creates only tracks with notes. It deliberately does not synthesize audio.

Fixture fault switches are URL parameters: `missing_selector=1` exercises a declared semantic-to-DOM fallback; `ambiguous_selector=1` refuses duplicate targets; `wrong_identity=1` refuses the wrong page; `partial_import=1`, `import_delay=500` and `reject_save=1` exercise uncertainty and failed saves. `track_limit=N` sets the simulated app limit independently of workflow preflight.

```powershell
cd packages\createrelay
python -m pytest tests/test_midi.py tests/test_bandlab.py -q
```

`test_native_flow_replayer_drives_real_browser` runs the native OpenAdapt Flow interpreter, not a second workflow engine. `test_full_browser_import_reference_and_independent_saved_store` additionally verifies the persisted fixture project through its HTTP store. The production provider still advertises verification tier 4 because it reads the same browser page. A visible Saved indication is evidence from the app UI; the receipt does not upgrade it to an independently verified production save.

## Preparing a live validation

1. Analyze and review the manifest; set `reviewed` to `true` only after checking source paths, hashes, track counts, order, tempo and instruments.
2. Use a dedicated Chrome or Edge profile outside Git. The normal browser handles authentication and persistent session data. CreateRelay does not accept login credentials, inspect password fields or automate account creation.
3. Calibrate the live Studio selectors in a private JSON file containing only the locator map below. The explicit `bandlab-live` command marks that supplied map `selectors_reviewed=true`; use it only after reviewing the controls. `channel` is `chrome` or `msedge`. If needed, edit the generated workflow's `studio_path_pattern` and `saved_text` to match observed Studio state before granting approval. No live selectors are claimed as verified defaults.
4. Generate a reviewable workflow using the command below. It is ordinary ASCII JSON and remains editable without an AI connection.
5. Review the readable workflow and grant its exact policy digest through the local operator interface. Start it, complete any authentication checkpoint in the normal browser, and confirm the correct project. Do not provide a password to the assistant or CLI.

```powershell
createrelay bandlab-login --profile bandlab --channel chrome
createrelay bandlab-live --manifest C:\Music\import-manifest.json --selectors C:\Music\bandlab-selectors.json --url https://www.bandlab.com/studio --profile bandlab --channel chrome --policy C:\Music\policy.json --out C:\Music\bandlab-workflow.json
createrelay approve-workflow C:\Music\bandlab-workflow.json --policy C:\Music\policy.json
createrelay run C:\Music\bandlab-workflow.json --policy C:\Music\policy.json
```

After the exact generated document has been approved, the manual live-validation command is `createrelay run C:\Music\bandlab-workflow.json --policy C:\Music\policy.json`. Every rerun still checks the approved digest and source hashes. `bandlab-live --run` combines preparation and execution only when that exact workflow already has approval. The Python helper remains available as `build_bandlab_workflow(...)` plus `save_workflow(...)`.

`bandlab-login` waits for Enter in the terminal while you sign in through the normal browser. It closes only its login tab afterward. The live provider launches or attaches to Chrome/Edge in known vendor installation locations with the exact dedicated profile, verifies that process identity, and uses a loopback-only debugging connection. Disconnecting the CLI preserves the browser and unsaved Studio tabs. Close the dedicated browser when finished to end its local debugging exposure; do not reuse your everyday browser profile.

`build_bandlab_workflow` also supports `project_action="open"` and an explicit `existing_track_count`; it checks the expected starting count before import. The default creates a new empty project. It refuses to create over observed tracks and never silently deletes existing content.

The local selector file maps the following names to ordered locator chains: `studio`, `project_name`, `new_project`, `open_project`, `tempo`, `import`, `save`, `save_status`, `track`, `track_name`, `instrument`, `offset`, `muted`, `region`. Each entry uses one of:

```json
{"method":"role","role":"button","name":"Import Audio/MIDI"}
{"method":"label","name":"Tempo"}
{"method":"text","name":"Saved"}
{"method":"css","value":"input[type=file]"}
```

Semantic selectors run before CSS. Every single-target selector must match exactly one visible control. This provider currently expects a file input for imports, editable project/track names and tempo/offset fields, a native instrument select, a mute checkbox, and readable saved/region state. Live custom menus or canvas-only controls may need an additional calibrated action strategy; do not claim they work merely because the fixture does. Missing capabilities stop at a recoverable checkpoint instead of clicking guessed coordinates.

Each import hashes the approved file immediately before upload, validates its path against read roots, checks track capacity, and verifies the resulting track/region count. A delayed or partial import becomes delivery uncertainty. It is never retried blindly. Inspect the project for already-created tracks before resuming to avoid duplicates.

Save failure leaves the live page open for recovery. Do not close Studio until the user has confirmed their work is safe. BandLab explicitly documents sync/save failures and recommends preserving the open project. [Saving issues](https://help.bandlab.com/hc/en-us/articles/115002945193-Saving-Issues).

## Remaining live qualification

- Verify current Studio URL and accessible controls in the user's signed-in dedicated profile.
- Import one small reviewed MIDI and confirm track/region count, names, instrument and timeline placement.
- Confirm tempo is represented correctly, especially files with non-4/4 signatures or multiple tempo events.
- Test multi-track and multi-channel fan-out before a larger batch.
- Import a reference WAV and verify audible alignment; imported audio may contain leading silence. [Import documentation](https://help.bandlab.com/hc/en-us/articles/900003008403-Importing-Audio-and-MIDI-Files).
- Save a private revision, independently reopen it, verify persisted tracks, then record the exact browser/app revision and selector calibration. Publishing, distribution and social engagement are outside this adapter.

Authentication, copyrighted music, session cookies, browser profiles, selector calibration screenshots and personal manifests must stay outside Git. The software sends no screenshots to an AI provider by default.
