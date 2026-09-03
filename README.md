# L1ght5p33d

[![L1ght5p33d CI](https://github.com/HiTecHelpLLC/l1ght5p33d/actions/workflows/l1ght5p33d-ci.yml/badge.svg)](https://github.com/HiTecHelpLLC/l1ght5p33d/actions/workflows/l1ght5p33d-ci.yml)

**Create, discover, adapt, combine and run reusable computer workflows.**

L1ght5p33d is a **Windows-first local execution companion for AI**. The v0.2.0
developer preview connects workflow discovery, verified downloads, local review
and execution: the AI prepares the task, you review its summary and approve,
and the companion runs it locally with observable outcome checks. All steps are
available to inspect or edit before approval.

L1ght5p33d extends OpenAdapt Flow with a local workflow library, application
adapters and controls for people and AI systems. It handles repetitive work in
browsers and Windows desktop software. AI helps author, find, parameterize,
inspect and repair workflows; routine execution makes **zero model calls**.
Instructions are versioned ASCII JSON files you can edit, share and run without AI.

BandLab MIDI importing is the first reference integration, not the product's
scope. A browser poster workflow and Windows creative-brief workflow demonstrate
the same application-independent core. More workflows belong in the library;
new applications belong behind adapters, without changing the execution engine.

The built-in THEBEST source is the public
[curated GitHub library](https://github.com/HiTecHelpLLC/l1ght5p33d-workflows).
It currently contains **one synthetic browser poster workflow**. The companion
downloads packs on demand, verifies their curator signature and exact bytes,
and keeps inactive downloads in a managed local cache. A signed review never
approves a run. See the [companion guide](docs/companion.md).

The THEBEST website register and public P2P registry are **not deployed**.
Advanced operator-configured signed catalogs can still retrieve workflows through
local Kubo into the operator's own library, outside the managed cache. SoundFlow,
REAPER and n8n recipes require their own runner or an explicit integration.

**Windows 11 first; developer preview.** The BandLab sequence is exercised against
a local fixture; authenticated live BandLab and native Windows input qualification
remain pending. The curated signature covers its recorded Windows 11 synthetic
browser test and older pinned runtime, not blanket v0.2.0 compatibility. Hosted
Ubuntu CI is neither local WSL evidence nor native Linux desktop qualification;
WSL GUI support is not claimed. See [acceptance and limits](docs/acceptance.md).

Download the [v0.2.0 developer preview](https://github.com/HiTecHelpLLC/l1ght5p33d/releases/tag/v0.2.0)
for this guided companion. Its [release notes](docs/releases/v0.2.0.md) record
passing Windows/Ubuntu checks and installation evidence. The immutable `v0.1.0`
tag and assets remain unchanged.

## Windows quick start

Install Python 3.12 and Git, then run in PowerShell:

```powershell
git clone https://github.com/HiTecHelpLLC/l1ght5p33d.git
cd l1ght5p33d
.\scripts\install-l1ght5p33d.ps1
.\packages\l1ght5p33d\.venv\Scripts\python.exe -X utf8 -m l1ght5p33d try
```

The installer uses the committed transitive `uv.lock` and downloads Chromium
once. `try` prepares the fixed synthetic poster fixture and opens a local review
page. Review the summary and explicitly approve the exact plan when ready. All
steps and inputs are available to inspect or edit; expanding them is optional.
Opening the page does not approve or run the workflow.
The CLI activates UTF-8 mode automatically on Windows for upstream checkpoints.

For an AI client, activate the environment and run `l1ght5p33d serve`. It manages
its local folders by default. `prepare_task` fetches or reuses a verified pack and
returns the review URL; `get_task_status` follows approval and execution.
See [MCP setup](docs/mcp.md). The existing `demo browser`, `demo bandlab` and
`demo windows` commands remain developer fixtures.

Releases contain a wheel, sdist and Windows developer-preview ZIP. No Python or
browser binary is bundled. `python -m pip install <downloaded-wheel>` also works
under Python 3.12; use the ZIP installer for the fully locked dependency set.
The package is not yet published to PyPI.

## Current capabilities

- Variables, typed parameters, graph conditions, bounded loops, subflows, effect
  assertions and exception paths through the existing OpenAdapt Flow runtime.
- CLI and localhost MCP: discover, validate, run, step, pause, resume, abort,
  inspect receipts, and propose a readable workflow patch.
- On-demand THEBEST pack discovery and signature verification, a local review
  page with editable variables and authored workflow copies, and complete
  per-run plans with explicit single-use approval. Changing inputs or actions
  invalidates the old approval. See [workflow review](docs/workflow-review.md).
- Download cache with a configurable 90-day inactivity period. Actual execution
  refreshes last use; browsing does not. Active, pinned, modified and untracked
  content is protected. Authored copies and receipts are outside cache expiry.
- Playwright role/label selectors, explicit fallback chains and dedicated Chrome
  or Edge profiles. Input delivery and verified outcomes are separate facts.
- Windows UIA with exact executable/PID/HWND/title/DPI/display/foreground checks;
  local OCR and template matching when semantic controls are absent.
- Local MIDI tempo/time-signature/type/channel/program/track/note analysis,
  heuristic classification, source hashes and reviewable manifests.
- BandLab ordered import, track naming/instruments, reference WAV/offset/mute,
  tempo, save and receipts, proven against the functional fixture.
- SDK recovery from reviewed native pending checkpoints, rechecking previous
  effects before continuing. Uncertain imports are not blindly retried.
- Signed workflow catalogs with exact-version, hash-checked P2P retrieval through
  optional Kubo. Installed files need separate local execution approval.

Runs write text logs, JSONL receipts, status, sealed bundles and native Flow
reports/checkpoints beneath `%LOCALAPPDATA%\L1ght5p33d`. GUI readback is labelled
`completed_ui_verified`; it is not independent proof of remote persistence.
Interrupted or uncertain runs remain halted/aborted.

## Architecture and prior art

This is a **history-preserving downstream fork of
[OpenAdapt Flow](https://github.com/OpenAdaptAI/openadapt-flow)**. Its original MIT
copyright and source are retained. The creator extension is separately packaged
under [`packages/l1ght5p33d`](packages/l1ght5p33d); inherited source remains in
`openadapt_flow`. The extension pins the published Flow 1.34.0 wheel. The retained
source snapshot was preparing 1.35.0; tests deliberately import the released wheel.

```mermaid
flowchart LR
  A[ASCII workflow / AI authoring] --> B[Schema + local permissions]
  B --> C[OpenAdapt Flow Replayer]
  C --> D[Registered providers]
  D --> E[API / DOM / Windows UIA]
  E --> F[Local OCR / templates / anchored geometry]
  C --> G[Effects + labelled UI readback]
  G --> H[Receipts / checkpoints / reviewed recovery]
  I[CLI / localhost MCP] --> B
```

Playwright, pywinauto, OpenCV/RapidOCR, Mido and the official MCP Python SDK supply
specialized capabilities. No new general automation interpreter was built.
Native ASCII JSON preserves one identity/effect/resume model; Robot Framework
was spiked but a second interpreter was rejected. Read the
[prior-art report](docs/prior-art.md), [ADR](docs/adr/0001-extend-openadapt-flow.md)
and [technical spikes](docs/l1ght5p33d/technical-spikes.md).

[THEBEST register and P2P distribution](docs/adr/0002-thebest-register-and-p2p.md)
add optional discovery and transport around that runtime. No new P2P engine is
built, and ordinary local workflows need neither a registry nor an IPFS node.
The [registry operator guide](docs/registry-operations.md) covers publication,
signing, explicit seeding and the default-disabled THEBEST integration.

## Editable workflows

Examples live in [`examples/l1ght5p33d`](examples/l1ght5p33d). Each action names
a registered provider, selector chain, variables and expected effect. The full
[workflow specification](docs/l1ght5p33d/workflow-spec.md) explains native graphs,
includes, conditions, recovery and the versioned envelope.

With the virtual environment activated:

```powershell
l1ght5p33d validate .\workflows\my-workflow.json
l1ght5p33d approve-workflow .\workflows\my-workflow.json --policy .\policy.private.json
l1ght5p33d run .\workflows\my-workflow.json --policy .\policy.private.json --dry-run
l1ght5p33d run .\workflows\my-workflow.json --policy .\policy.private.json --var title="My poster"
```

Review the file before issuing its exact local digest grant. CLI-generated
synthetic demos grant only their own generated workflow for that run.

## AI control and privacy

```powershell
l1ght5p33d serve
```

Connect an MCP client to `http://127.0.0.1:7331/mcp` with an Authorization bearer
header containing the private session token. The CLI prints the token file's
location, never its contents. Host/Origin validation and bounded requests protect
the loopback service. `l1ght5p33d rpc` offers local line-oriented JSON-RPC.
See [interface documentation](docs/mcp.md).

Use `--workflows`, `--state` or `--policy` to select operator-managed locations,
and `--cache-retention-days 180` to change download retention (1-3650 days).
The review flow requires explicit confirmation and exposes no run-approval MCP
method. Its URL contains a capability, so an authorized client could imitate the
approval request. Agents must leave confirmation to the user; this is a local
trust boundary, not cryptographic proof of human presence. See
[review boundaries](docs/companion.md#review-trust-boundary).

Screenshots stay local and are not returned by the creator MCP tools. No model,
cloud telemetry or paid provider is configured. Users enter credentials only in
the application's normal login UI. Credential-bearing workflow parameters are
refused in this preview because upstream durable metadata is not a secret store.
Profiles, calibration, images and receipts stay outside Git by default.

Workflow files cannot import Python, execute a shell, register code or grant
filesystem/application access. Installed providers are trusted code, not sandboxed
plugins. Executable edits require local approval; remote patch approval cannot
expand that authority. One automation run may be active per service. Account
creation, purchases, social engagement, publishing and distribution are outside
the provided BandLab adapter.

## BandLab reference

```powershell
l1ght5p33d midi C:\MyMidi --out manifest.json --reference-wav C:\MyMidi\reference.wav
l1ght5p33d bandlab-login --profile bandlab --channel chrome
```

Review the manifest, then follow the manual live-validation command in
[the BandLab guide](docs/bandlab.md). Classification is heuristic; audio-derived
MIDI is not ground-truth instrumentation. Source files are not modified and
quantization is not applied automatically. Track limits, mappings, order, naming
and alignment are editable. Unsupported live widgets stop for review.

The fixture proves the intended sequence, not today's private BandLab DOM.
Automatic hard-crash reconstruction, an integrated recorder-to-provider compiler,
broader native app qualification and a plugin marketplace remain
[roadmap](docs/ROADMAP.md) items.

## Development

```powershell
.\scripts\install-l1ght5p33d.ps1 -Developer
cd packages\l1ght5p33d
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
.\.venv\Scripts\mypy.exe
```

GitHub-hosted Windows/Ubuntu CI runs tests, real browser fixtures, clean-wheel first runs,
formatting, typing, Gitleaks, vulnerability/license scans, and actual archive
inspection. Interactive native input has a separate qualification command.
Upstream deployment workflows are preserved in `.github/upstream-workflows`.

See [contributing](CONTRIBUTING.md), [adapter guide](docs/adapter-development.md),
[recorder/calibration](docs/recorder-calibration.md), [troubleshooting](docs/troubleshooting.md),
[security](SECURITY.md), [conduct](CODE_OF_CONDUCT.md), [license](LICENSE), and
[third-party notices](THIRD_PARTY_NOTICES.md). Inherited repository-only AGPL
benchmark material is excluded from creator distributions.

L1ght5p33d is unofficial and unaffiliated with OpenAdapt, BandLab, Suno,
Microsoft or any automated application. Product names belong to their owners;
no endorsement is implied.
