# Name update and late-discovered prior art

Checked 2026-09-03 after the user's request for Lightspeed or an available leetspeak variant. Canonical selection: **L1ght5p33d**, repository/package slug `l1ght5p33d`. This supersedes the earlier CreateRelay working name.

## Collision checks

Queries used authenticated GitHub `GET /search/repositories?q=NAME+in:name`, PyPI `https://pypi.org/pypi/NAME/json`, npm `https://registry.npmjs.org/NAME`, and exact-name web searches. Counts are a snapshot, not a name reservation or exhaustive trademark search.

| Candidate | GitHub matches | PyPI status | npm status | Findings |
| --- | ---: | --- | --- | --- |
| `lightspeed` | 1,562 | HTTP 404 | HTTP 200 | Directly relevant existing `smartcomputer-ai/lightspeed`; also Red Hat Ansible Lightspeed and other products |
| `l1ghtspeed` | 15 | HTTP 404 | HTTP 404 | Existing personal namespace/repository matches |
| `l1ghtsp33d` | 1 | HTTP 404 | HTTP 404 | `COOLSITEHACKER/L1ghtSp33d-Breaker-ByPassHub`; avoid this association |
| **`l1ght5p33d`** | **0** | **HTTP 404** | **HTTP 404** | Recommended. Exact web search found an old user handle, no identified same-name automation product |
| `1ight5peed` | 0 | HTTP 404 | HTTP 404 | Alternative, but begins with a digit and cannot be an ordinary Python import identifier |

Evidence endpoints: [GitHub chosen-name query](https://github.com/search?q=l1ght5p33d+in%3Aname&type=repositories), [PyPI](https://pypi.org/pypi/l1ght5p33d/json), [npm](https://registry.npmjs.org/l1ght5p33d), [Ansible Lightspeed](https://github.com/ansible/ansible-lightspeed).

## Additional prior art: smartcomputer-ai/lightspeed

| Field | Finding |
| --- | --- |
| Repository | [smartcomputer-ai/lightspeed](https://github.com/smartcomputer-ai/lightspeed) |
| License | Apache-2.0; compatible as a separately attributed permissive dependency. No code copied or added as a dependency |
| Maintenance | Created 2026-02-09; last push 2026-09-03T16:50:45Z; unarchived; 91 stars; GitHub API open issue count 0 at query |
| Release maturity | Initial v0.1.0 on 2026-09-01; current active but early release |
| OS | Release assets are Linux x86_64 binaries; dedicated macOS 15 CI compiles/smokes Apple Silicon executables. No Windows package/native UIA support established |
| Architecture | Rust event-sourced agent core, Temporal runtime, Postgres event store, optional S3/CAS, TypeScript/React frontend |
| Workflow format | Persisted agent-session event logs and typed JSON-RPC contracts, with reusable agent profiles and virtual-filesystem skills; not a learned GUI selector/verification workflow language |
| Browser/UIA/OCR/vision | Tools and borrowed compute can host external capabilities, but repository filename search found no browser/Playwright/UIA/OCR adapter implementation; sole matching asset was a UI screenshot. Absence is not an exhaustive code proof |
| AI/MCP | Model-provider adapters, hosted/native MCP discovery and approval, configurable subagents, MCP control interface, typed JSON-RPC API |
| Verification/recovery | Durable session replay, cancellation/steering, approvals, tool deadlines and results. These are agent/session semantics; no equivalent of OpenAdapt Flow's typed GUI postconditions, local selector ladder and verified actuation contracts was established |
| Reusable components | Potential future external orchestration of L1ght5p33d via its narrow MCP interface; useful durable-session and content-addressed evidence patterns |
| Missing target requirements | Windows-first deterministic learned GUI replay, semantic/UIA then local visual fallback, native local MIDI/BandLab workflow, lightweight single-computer install, zero-model routine replay semantics |
| Recommendation | Consider as an optional supervisory orchestrator later; retain the OpenAdapt Flow foundation for this MVP. Do not fork it as the desktop engine and do not reuse its name |

The distinction is architectural: its deterministic core replays agent events to decide which LLM/tool effect to request next. It does not imply that newly executing a learned computer task is model-free or that every GUI action has an independent postcondition. The source [drive.rs](https://github.com/smartcomputer-ai/lightspeed/blob/main/crates/engine/src/core/drive.rs) emits provider/tool work from session state; [design.md](https://github.com/smartcomputer-ai/lightspeed/blob/main/docs/design.md) describes the event log, LLM context and effect-adapter boundary. Its Temporal/Postgres/fleet scope adds services that the selected local desktop runner does not need.

Inspected source surfaces: README, repository tree, `docs/design.md`, `crates/engine/src/core/drive.rs`, `.github/workflows/ci.yml`, `.github/workflows/macos.yml`, release assets, and recent PRs. [Release v0.1.0](https://github.com/smartcomputer-ai/lightspeed/releases/tag/v0.1.0) contains Linux CLI/server/envd/provider binaries and an SBOM. [PR 75](https://github.com/smartcomputer-ai/lightspeed/pull/75) covers envd distribution, session retention, CAS sweeping and native MCP batch work; [PR 73](https://github.com/smartcomputer-ai/lightspeed/pull/73) covers outbound environment registration and tool search, consistent with the fleet-control focus. These findings complement, rather than replace, the earlier prior-art evaluation and successful OpenAdapt Flow technical spike.
