# v0.1.0 acceptance and evidence

Tests import published OpenAdapt Flow 1.34.0 under Python 3.12. This preview does
not claim to requalify every inherited OpenAdapt target or hosted service.

| Criterion | Evidence / boundary |
| --- | --- |
| ASCII parse/validate/execute | Strict envelope/native schema; actual runtime tests |
| AI control | MCP tools/list/tools/call, token/Origin rejection; CLI/JSON-RPC |
| Semantic selectors first | Real Playwright; Windows UIA/Win32 before local vision |
| Logs and outcomes | JSONL/text, actual Flow reports/checkpoints, truthful evidence tiers |
| Fallback/refusal | Missing selectors, ambiguity, wrong origins, weak/duplicate matches |
| Step/pause/resume/abort | Cooperative controls and real browser service step-mode test |
| Durable recovery | Actual upstream approval/revalidation/resume, without duplicate completed write |
| MIDI manifest | Synthetic SMF track/channel/tempo analysis and source hashes |
| BandLab path | Chromium SMF/WAV import, mappings/name/offset/mute/save, separate fixture store checks |
| Non-BandLab browser | Local poster editor with role/label selectors and fallback |
| Non-BandLab Windows | Packaged WinForms creative fixture and UIA/vision contracts |
| Reproducible installation | Direct pins, transitive lock, real wheel/sdist and clean-wheel first runs |
| Quality/security | Windows/Linux CI tests, formatting/types, secret/dependency/license scans |
| Optional shared workflow discovery | Signed catalog, key pinning, expiry, exact version, schema and byte limits |
| Actual P2P transport | Two isolated Kubo peers; HTTP catalog discovery and CLI install; no execution grant |
| THEBEST register integration | Default-disabled PHP route; synthetic signature/schema/request tests |

Exact test counts and CI links are recorded in release notes. One optional native
input test requires an explicitly available foreground desktop. On the development
host, executable/PID/HWND/DPI identification worked but Windows refused foreground
activation; input was skipped instead of weakening the check. Run
`l1ght5p33d demo windows` and focus the harmless fixture. See [windows.md](windows.md).

GitHub's Windows runner is Windows Server, not a clean Windows 11 VM. Fresh package
installation is tested on Windows/Linux CI; qualification on another physical
Windows 11 machine remains a matrix item. Python 3.12 and Git are prerequisites.

No live BandLab login or import was attempted during initial development. Fixture
evidence is not live evidence. Normal user login and reviewed current selectors
are required for the command in [bandlab.md](bandlab.md). Custom live widgets may
need adapter calibration. Partial imports and save rejection remain failures.
