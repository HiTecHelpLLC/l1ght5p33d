# Prior art and foundation evaluation

Research date: 2026-09-03. See docs/adr/0001-extend-openadapt-flow.md for the resulting decision. These independent research sections preserve primary sources, compatibility cautions and observed maintenance evidence.

# Foundation evaluation

Research date: 2026-09-03. Primary sources were inspected live through GitHub REST repository metadata, releases, issue trackers, source files, official documentation and PyPI JSON. Dates below are retrieval-time observations, not promises of future support. No third-party code was copied into a new engine. GitHub authentication was checked and the active account is HiTecHelpLLC.

## Decision

Fork and extend **OpenAdaptAI/openadapt-flow**, preserving its complete Git history and MIT notices. OpenAdapt's current architecture materially differs from its older research monolith: OpenAdapt is now a launcher, and Flow is a maintained deterministic compiler/runtime with structural selectors, local vision, typed workflow graphs, effects, durable checkpoints and governed repair. Reimplementing these in Robot Framework would duplicate the very foundation the user asked to reuse. Robot remains an excellent language, but adding a second interpreter would complicate checkpoint semantics and safety. Flow's native JSON workflow IR is ordinary ASCII when serialized with escaped non-ASCII characters; it carries explicit schemas, typed parameters, branches, loops and subflows. Add a concise creator-facing envelope and tools, not a second execution engine.

The preferred execution extension is an allowlisted `ApiBinding(kind="tool", on_unavailable="halt")` provider. The existing Replayer accepts an actuator and effect verifier. Browser uploads, MIDI analysis and local application operations can enter through this documented binding seam; the existing runtime still handles program sequencing, effect checks and receipts. Add cooperative controls at the existing step boundary. Do not expose the legacy WAA Python-execution endpoint as the creator workflow API.

## OpenAdaptAI/OpenAdapt

- Repository: https://github.com/OpenAdaptAI/OpenAdapt . MIT; compatible with a permissive derivative when inherited notices are preserved. The current repository is a launcher and compatibility package; the frozen legacy monolith remains under `legacy/`.
- Maintenance: not archived; last observed commit 2026-09-03. Stable GitHub release v1.16.0 published 2026-08-26. [Release](https://github.com/OpenAdaptAI/OpenAdapt/releases/tag/v1.16.0). Its [release-health issue](https://github.com/OpenAdaptAI/OpenAdapt/issues/1138) records unreleased/incomplete-publication status; do not equate main with the latest supported wheel.
- OS and capabilities: Python 3.10-3.12, optional Windows UIA, macOS accessibility, Linux AT-SPI, browser and RDP capabilities. Actual execution resides in Flow; capture and agent interfaces are separate packages.
- Workflow/AI: demonstration capture -> compile -> bundle -> rehearsal or governed execution; model-free healthy replay; agent-facing interface and CLI. Raw recordings stay local by default. Cross-backend workflows compose child bundles instead of pretending one recording transfers across surfaces.
- Verification/recovery: explicit VERIFIED, HALTED_BEFORE_EFFECT, RECONCILIATION_REQUIRED and other outcomes; repair candidates require governed promotion. Native/remote deployments are qualified per task/environment, not blanket product claims.
- Reuse/missing/recommendation: reuse architectural contracts and optional capture ecosystem; **do not fork this launcher** as the runtime foundation. Fork its actual Flow engine. Creator authoring, MIDI and BandLab are missing. [Current source README](https://github.com/OpenAdaptAI/OpenAdapt/blob/main/README.md).

## OpenAdaptAI/openadapt-flow (discovered successor)

- Repository: https://github.com/OpenAdaptAI/openadapt-flow . MIT package code. Repository-only openIMIS benchmark adaptations retain AGPL-3.0-only; wheels/sdists explicitly exclude them. Preserve [THIRD_PARTY_NOTICES](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/THIRD_PARTY_NOTICES.md), inherited licenses and build exclusions. Do not redistribute benchmark material as MIT.
- Maintenance/maturity: not archived, observed commit 2026-09-03; release v1.34.0 published 2026-08-28, PyPI 1.34.0. Main was already 1.35.0 during inspection. There is active [release-health tracking](https://github.com/OpenAdaptAI/openadapt-flow/issues/303). Its small community and rapid version growth are risks; version numbers alone do not establish maturity.
- Platform: browser through Playwright, Windows agent/UIA protocol, native macOS, Linux AT-SPI, remote display adapters. Python >=3.10,<3.13 because of validated OCR dependencies. The [package metadata](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/pyproject.toml) uses Pydantic, NumPy, OpenCV, Pillow, RapidOCR ONNX Runtime, httpx, PyYAML, cryptography and openadapt-types. Browser support is optional.
- Source inspection: [resolver.py](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/openadapt_flow/runtime/resolver.py) implements structural first, then local template, global template, OCR, geometry and optional grounding. Ambiguous structural candidates are a refusal, not a reason to choose a weaker ambiguous visual candidate. Template threshold is 0.985; OCR text ratio floor 0.9. The relative fallback is evidence anchored. Optional model egress is guarded in the constructor and disabled by default.
- Workflow format: [IR source](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/openadapt_flow/ir.py) and [workflow-program design](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/docs/design/WORKFLOW_PROGRAM_IR.md): JSON bundle schema v2; named states, typed params, branches, bounded loops/worklists, subflows, guards, waits, exception handlers, effects and API/tool bindings. Human editable and inspectable without AI. Existing action enum includes click, double/right click, drag, type, select option, key/hotkey, wait and scroll; there is no native upload action.
- Execution/recovery: [Replayer](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/openadapt_flow/runtime/replayer.py) receives `backend`, `vision`, `effect_verifier`, `api_actuator`, `durable`, etc. `run()` interprets both linear and graph workflows. Durable verified checkpoints reconstruct completed results and resume the same execution identity. Direct `resume_from` is guarded; use the authenticated [durable resume API](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/openadapt_flow/runtime/durable/resume.py). There was no simple public cooperative pause/step callback in the inspected Replayer; a small boundary extension is needed.
- Reusable actuation seam: `ApiBinding.kind` already accepts `tool`/`mcp`, not only HTTP; `on_unavailable="halt"` prevents inventing a GUI fallback. The [actuator result contract](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/openadapt_flow/runtime/actuators/api.py) distinguishes pre-delivery unavailability, delivered input and uncertain delivery; uncertain writes are verified instead of retried blindly. An allowlisted tool actuator can add uploads without extending the engine's action enum or storing arbitrary Python in workflows.
- Caveats: Windows backend contains legacy WAA execute compatibility as well as narrow typed UIA endpoints; creator-facing code must use local typed adapters and never surface execute. Native evidence is environment-specific. Screenshot-based checks prove screen state, not server persistence; a BandLab saved indicator must be reported at its actual evidence tier. [Limits](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/docs/LIMITS.md) and [verification claims](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/docs/VERIFICATION.md) explicitly distinguish these.
- Recommendation: **fork properly and extend**. Missing: creator-native CLI/MCP permission surface, concise editable creator workflows, MIDI manifest/classification, semantic file imports, BandLab reference mapping, user-requested controls and clean Windows preview packaging.

## Robot Framework

- Repository: https://github.com/robotframework/robotframework . Apache-2.0 with Nokia/Foundation notices. Permissively compatible. Not archived; observed commit 2026-09-03; stable 7.4.2 released 2026-03-03, 7.5b1 prerelease 2026-07-17. [Releases](https://github.com/robotframework/robotframework/releases). PyPI 7.4.2, Python >=3.8.
- Mature cross-platform execution and reporting framework. `.robot` plain-text workflows support variables, reusable user keywords/resources, parameters/returns, IF, FOR, WHILE, TRY/EXCEPT/FINALLY, timeouts, assertions and retry keywords. Dry run validates keyword/argument structure. None requires an AI provider. [User guide](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html).
- Browser/UIA/OCR/CV capabilities come from libraries, not core. Core has no mandatory dependencies beyond Python. Public [TestSuiteBuilder](https://github.com/robotframework/robotframework/blob/master/src/robot/running/builder/builders.py) parses files into executable/modifiable suites, with model visitors for inspection. Python libraries and listener APIs are strong extension points.
- Core pass/fail and teardown behavior does not itself distinguish input delivery from a verified application effect. Durable resumability, exact permission-bound patch approval, selector confidence/window identity and localhost tokened MCP would need substantial product layers. Arbitrary library imports and evaluation are unsuitable for an untrusted workflow surface unless constrained.
- Maintenance evidence beyond releases: current [report escaping issue](https://github.com/robotframework/robotframework/issues/5774) shows active tracker use; repository source copyright/Apache notices were inspected.
- Recommendation: **compose only if a Robot authoring bridge is later requested**. Reject as primary engine for this project because current Flow already contains more of the requested safety/resume architecture. Robot's stronger concise text syntax does not outweigh maintaining two execution semantics.

## RPA Framework

- Repository: https://github.com/robocorp/rpaframework . Apache-2.0. Not archived; observed commit 2026-08-29. PyPI main package 33.0.1 uploaded 2026-08-23, Python >=3.10,<3.14. Monorepo releases are per package; the latest repository tag is not necessarily the umbrella package version. [Releases](https://github.com/robocorp/rpaframework/releases).
- Mature Robot/Python keyword libraries for browser, Windows, desktop, files, APIs and office workloads. Browser layers include Selenium and Playwright; Windows library uses `uiautomation` and `comtypes`; recognition support includes local OCR/template matching. Cross-platform capability depends on each library, with Windows/Office features OS-specific.
- [Windows source](https://github.com/robocorp/rpaframework/blob/master/packages/windows/src/RPA/Windows/__init__.py) exposes names, AutomationId, control type, class and rectangles; can install `rpaframework-windows` independently. This is a reusable provider, not a full authoring/resume engine. Workflow syntax is Python or Robot. Assertions, waits and locators exist; permission governance and durable effect-aware resume remain application responsibilities. No mandatory AI provider.
- Packaging caveat: [issue 1352](https://github.com/robocorp/rpaframework/issues/1352) reports a stale Office dependency blocking modern installations; [1351](https://github.com/robocorp/rpaframework/pull/1351) works on Python 3.14. Broad umbrella installation adds unrelated connectors and avoidable conflicts.
- Recommendation: **compose optional focused providers only**, with exact version/license audit. Do not install the whole framework solely for one UIA operation. Existing Flow vision/Playwright reuse and a small typed Windows adapter are narrower.

## Microsoft Playwright and Playwright MCP

- Repositories: https://github.com/microsoft/playwright and https://github.com/microsoft/playwright-mcp . Both Apache-2.0, actively maintained, not archived. Observed commits 2026-09-03. Playwright GitHub v1.62.1 released 2026-07-30; Python package PyPI 1.62.0 uploaded 2026-07-31 (do not assume language packages share a patch release). MCP 0.0.80 released 2026-09-01.
- Windows/macOS/Linux browser control, Chromium/Chrome/Edge plus Firefox/WebKit. DOM/ARIA role/label locators, accessibility snapshots, file inputs, browser context profiles and API requests. No Windows native UIA or local OCR/template engine in Playwright itself. [Actions](https://playwright.dev/python/docs/input) directly support file inputs and file-chooser events, avoiding unverified OS-dialog coordinates.
- Verification: actionability auto-waits for uniqueness, visibility, stability, input reception and enabled state as relevant. Retrying assertions verify observable effects separately; workflows must explicitly declare them. [Auto-waiting](https://playwright.dev/python/docs/actionability). Reuse semantic locators and assertions, avoid force-clicking around ambiguity.
- Workflow format: normal programming languages/test source and recorder-generated code. MCP supplies agent tools and snapshots, not a deterministic workflow state machine with durable business-effect resume. The MCP repository now [routes issues to Playwright](https://github.com/microsoft/playwright-mcp/issues/1664). Browser tool access alone is not a file/application permission sandbox.
- Recommendation: **compose Playwright Python through Flow and narrow creator providers**. Do not run generic Playwright MCP as the platform's entire control surface; expose validated workflows via the project-owned MCP API. This avoids unrestricted evaluations and hides local screenshots from the AI by default.

## trycua/cua

- Repository: https://github.com/trycua/cua . MIT base; optional third-party licenses differ. README identifies OmniParser CC-BY-4.0 and optional `cua-agent[omni]` ultralytics AGPL-3.0. Exclude that extra from a permissive default distribution. [License boundary](https://github.com/trycua/cua/blob/main/README.md).
- Active monorepo, observed commit 2026-09-03; many separately versioned packages/nightlies. Latest inspected driver nightly 0.23.3 (2026-09-03), fleet 0.1.1 (2026-09-02); PyPI cua-computer 0.5.19 (2026-06-18, Python >=3.12,<3.14), cua-agent 0.8.4 (2026-06-24, >=3.11,<3.14). These dates describe components, not one stable product release.
- OS: full-desktop sandboxes/SDKs for macOS/Linux/Windows, local and remote infrastructure. [Driver source README](https://github.com/trycua/cua/blob/main/libs/cua-driver/README.md) describes a native Rust driver with MCP stdio, CLI, Python/TypeScript generated bindings, bounded permission mode and explicit existing-profile permission. The driver is broader than a screenshot-only agent loop and is worth following for native integrations.
- Workflow/AI: agent SDKs, model integrations, accessibility/native actions and browser integration. The repository is oriented around agent execution, sandboxes and benchmarks; it does not provide the same editable, durable deterministic workflow/effect qualification foundation as Flow. OCR/visual grounding is optional and component/model dependent. No claim is made that all optional agent configurations are local.
- Verification/recovery: native target/input contracts and bounded capability manifests exist; task-level effects and creation-workflow receipts still need a higher layer. Current [custom canvas target-input RFC](https://github.com/trycua/cua/issues/3531) and [window-title bug](https://github.com/trycua/cua/issues/3502) show active integration work and surface limits.
- Recommendation: **defer optional driver provider**, not primary engine. It may improve future cross-platform background input, but adds a Rust SDK/package boundary unnecessary for the first Windows/Playwright preview.

## Technical spike plan and acceptance interpretation

1. Prove Flow can invoke an injected allowlisted tool actuator and independent verifier without any model or native screenshot dependency, retaining its own Replayer/report.
2. Parse a minimal Robot resource/control-flow example to confirm the alternative works, then document why its missing durable governance layer dominates the choice.
3. Exercise cooperative before-step controls on a real Flow run, including abort before the next action and a failed verifier that never reports success.
4. Prove browser import via a local fixture file input and separately assert the created region/track and saved indicator. Live BandLab remains a task-specific manual qualification; fixture success is never relabeled live success.

The current stable package is a better bootstrap than arbitrary HEAD for dependency discovery. A fork may deliberately retain full latest history while documenting its exact base SHA and preview validation. Preserve upstream source files, notices and benchmark exclusions; do not advertise inherited experimental surfaces as newly validated creator features.


# Desktop execution, visual fallback, and recorder prior art

Research date: 2026-09-03. Sources include live GitHub REST repository, release and commit metadata, GitHub source files, official documentation, PyPI, and issue trackers. Repository `pushed_at` can reflect branches or metadata and is not treated as the date of the latest default-branch commit. A newly published historical release is not proof of new engine development. Findings below are engineering assessments, not endorsements of upstream marketing claims. No upstream source was copied into a product repository during this research.

## Recommendation

Compose a mature deterministic workflow foundation with narrowly scoped providers. For Python, pywinauto is the strongest directly reusable Windows UIA/Win32 execution layer examined. FlaUI is the strongest alternative when a .NET provider is justified. Reuse OpenCV template matching and a local OCR provider for declared fallbacks. Existing providers must still enforce verified window identity, selector ambiguity checks, fresh evidence, explicit postconditions, and checkpoint semantics.

OculiX provides substantially more visual automation than a new implementation should recreate, including Robot keywords, recording and MCP. However, it is visual-first, has a JVM boundary, and its inspected dependency graph includes GPLv2 TigerVNC. Do not bundle it on the strength of its MIT repository label alone. OpenRPA already supplies a complete RPA engine but would impose a different XAML/.NET authoring model and MPL obligations. Jarvisonix is relevant BandLab prior art, but its source is a nondeterministic cloud-model prototype, not an execution foundation. These conclusions do not decide among Robot Framework, OpenAdapt, and other foundations evaluated in the companion report.

## pywinauto/pywinauto

- Repository: [pywinauto](https://github.com/pywinauto/pywinauto).
- License: BSD-3-Clause since 0.6.0; older releases were LGPL. Use 0.6.9 with preserved notices in an Apache-2.0 original composition. Do not silently treat pre-0.6 code as BSD. [License](https://github.com/pywinauto/pywinauto/blob/0.6.9/LICENSE).
- Maintenance and maturity: GitHub and [PyPI](https://pypi.org/project/pywinauto/0.6.9/) report 0.6.9, released 2025-01-06. Default-branch commit was `18d2a95cebed2f0061ab4e4c80c3a76ece5dd4f3`, dated 2026-05-23. This is a mature library with ongoing maintenance, but long release intervals and substantial outstanding issues. [Release](https://github.com/pywinauto/pywinauto/releases/tag/0.6.9), [commit](https://github.com/pywinauto/pywinauto/commit/18d2a95cebed2f0061ab4e4c80c3a76ece5dd4f3).
- OS and selectors: production GUI backends are Windows Win32 and UIA. Low-level mouse/keyboard support on Linux does not imply equivalent Linux accessibility. Application instances can be scoped to a process; selectors include title, regular expression, class, automation ID, control type, process and handle. Desktop scope exists for multi-process applications. Browser accessibility is possible but Playwright should remain the browser provider. [Getting started](https://pywinauto.readthedocs.io/en/latest/getting_started.html), [selector source](https://github.com/pywinauto/pywinauto/blob/18d2a95cebed2f0061ab4e4c80c3a76ece5dd4f3/pywinauto/findwindows.py).
- OCR/CV, format, AI: normal Python calls, no workflow language, first-class MCP service, or OCR/template engine in core. Screenshot capture is available with Pillow. Semantic recording is an external project.
- Verification/recovery: `wait` and `wait_not` can check existence, visibility, enabled and active state. `wait_until`, `wait_until_passes`, timeouts and CPU-idle waits are reusable primitives. An application-specific assertion must establish the effect of an input. [Wait documentation](https://pywinauto.readthedocs.io/en/latest/wait_long_operations.html), [timings source](https://github.com/pywinauto/pywinauto/blob/18d2a95cebed2f0061ab4e4c80c3a76ece5dd4f3/pywinauto/timings.py).
- Issue evidence: [#1479](https://github.com/pywinauto/pywinauto/issues/1479) reports Python 3.13 escape warnings; [#332](https://github.com/pywinauto/pywinauto/issues/332) tracks script generation. Pin and test Python/dependencies instead of equating `pip install` with validated Windows 11 support.
- Reuse/missing/recommendation: compose as the Windows provider. Add executable/PID/HWND checks, DPI/display metadata, foreground checks for injected input, exact-match policy, ordered fallbacks, structured receipts, policy and safe resumability. Avoid magic fuzzy selectors for consequential controls.

## oculix-org/Oculix

- Repository: [OculiX](https://github.com/oculix-org/Oculix). Active continuation of SikuliX under oculix-org, preserving `org.sikuli.*` lineage.
- License: repository code is MIT. The inspected [API POM](https://github.com/oculix-org/Oculix/blob/02ea8844483a83a2963db8016cd7ad421e15bc91/API/pom.xml) declares `tigervnc-java-oculix:2.0.1` and explicitly labels it GPLv2; this dependency is not marked optional in the inspected block. JNativeHook and other native dependencies also require an artifact-level license inventory. Apache-2.0 compatibility of the complete shipped runtime is therefore not established by MIT at the top level. [TigerVNC fork](https://github.com/oculix-org/tigervnc-java-oculix).
- Maintenance/releases: live API identifies v4.0.0 stable on 2026-07-09 and v4.1.0-rc1 on 2026-08-26. Latest repository push was 2026-09-03, while inspected master was `02ea8844483a83a2963db8016cd7ad421e15bc91` dated 2026-07-08; development and RC branches explain the distinction. [Stable](https://github.com/oculix-org/Oculix/releases/tag/v4.0.0), [RC](https://github.com/oculix-org/Oculix/releases/tag/v4.1.0-rc1).
- OS/capabilities/format: Windows, macOS, Linux; Java API and IDE scripting, including Jython, JRuby and Robot runners. OpenCV pattern matching, local Tesseract via Legerix, optional OCR providers, VNC and ADB. It locates pixels/text rather than browser DOM or UIA controls. Images accompany scripts. The API/IDE runtime split in 4.0 means a pure Java API integration need not load the scripting runtime. [Changelog](https://github.com/oculix-org/Oculix/blob/02ea8844483a83a2963db8016cd7ad421e15bc91/CHANGELOG.md).
- Actual source: [OculixKeywords.java](https://github.com/oculix-org/Oculix/blob/02ea8844483a83a2963db8016cd7ad421e15bc91/API/src/main/java/org/sikuli/script/OculixKeywords.java) implements region-bound operations, match scores, image counts, timeouts and pluggable OCR. This is tangible reuse, not only a README proposal. [Recorder source](https://github.com/oculix-org/Oculix/tree/02ea8844483a83a2963db8016cd7ad421e15bc91/API/src/main/java/org/sikuli/support/recorder) contains structured actions and code generators.
- MCP/verification: optional MCP supports visual commands and signed chained JSONL audit. Audit integrity proves what was recorded; it does not by itself prove an application saved a project. Find/wait/vanish/stability and similarity checks can underpin explicit postconditions. [MCP module](https://github.com/oculix-org/Oculix/tree/02ea8844483a83a2963db8016cd7ad421e15bc91/MCP).
- Issue/release evidence: [#444](https://github.com/oculix-org/Oculix/issues/444) and 4.1.0-rc1 document window provenance and mixed-DPI fixes. The RC removes a three-second capture cache that could falsely report stability from stale images; some cross-monitor DPI cases remain limited. [#160](https://github.com/oculix-org/Oculix/issues/160) is a future semantic visual-intelligence proposal, not delivered accessibility coverage.
- Reuse/missing/recommendation: consider a separately installed provider after transitive-license and runtime testing. Do not fork it as the whole product: application policy, semantic-first selection, patch approval, workflow schema, checkpoints and MIDI are separate concerns. Do not ship the GPL VNC path in an allegedly all-permissive bundle without resolving licensing.

## SikuliX: historical upstream and mirror

- Repositories: [RaiMan/SikuliX1](https://github.com/RaiMan/SikuliX1) now resolves to [oculix-org/SikuliX1](https://github.com/oculix-org/SikuliX1). The current mirror describes itself as historical/read-only and directs new development and issues to OculiX. Its GitHub `archived` flag was false at inspection; that flag does not override the documented maintenance status.
- License/maturity: MIT repository; preserve lineage and inspect bundled native-library licenses. Mirror v2.0.5 was published 2026-04-02, with default-branch documentation commit `c6f1799` on 2026-05-15. This should not be described as a new 2026 feature release of the legacy engine. [Releases](https://github.com/oculix-org/SikuliX1/releases).
- OS/capabilities/format: Windows/macOS/Linux, JVM, scripts with image assets, Jython/Java and other JVM languages. OpenCV matching and Tesseract OCR; no semantic DOM/UIA selection. [Project documentation](https://sikulix-2014.readthedocs.io/en/latest/index.html).
- Verification/recovery: regions, similarity scores, waits, disappearance observations, `exists`, `FindFailed`, configurable scan/time limits and event observers. Region coordinates in legacy APIs have no native application identity. [Region documentation](https://sikulix-2014.readthedocs.io/en/latest/region.html).
- AI/MCP/reuse/missing/recommendation: core predates modern MCP. Useful pattern API and prior-art concepts; prefer maintained OculiX for a JVM visual provider. Do not fork historical SikuliX for this product or use its default global-region behavior as an input-safety guarantee.

## open-rpa/openrpa

- Repository: [OpenRPA](https://github.com/open-rpa/openrpa).
- License: [MPL-2.0](https://github.com/open-rpa/openrpa/blob/b78115e45bcfdc1a22398662bac355fdd52fac87/LICENSE), a file-level copyleft license. An OpenRPA fork must preserve MPL-covered source obligations and notices; relabeling a fork Apache-2.0 would be wrong. It can participate in a compliant larger work. Dependency obligations remain separate.
- Maintenance/maturity: latest release 1.4.57.13 and default-branch commit `b78115e45bcfdc1a22398662bac355fdd52fac87` are 2025-06-03; `pushed_at` was 2026-04-15. Hundreds of historical releases establish maturity but not a current high release cadence. [Release](https://github.com/open-rpa/openrpa/releases/tag/1.4.57.13), [commit](https://github.com/open-rpa/openrpa/commit/b78115e45bcfdc1a22398662bac355fdd52fac87).
- OS and architecture: Windows desktop RPA designer, .NET/Windows Workflow Foundation activities, XAML workflows and selectors. Browser extension/native messaging, Windows UIA via FlaUI, recorder, image/OCR, Office, Java, terminal and other plugins. Offline execution is documented; OpenFlow provides optional orchestration. [Wiki](https://github.com/open-rpa/openrpa/wiki), [solution](https://github.com/open-rpa/openrpa/blob/b78115e45bcfdc1a22398662bac355fdd52fac87/OpenRPA.sln).
- Source inspection: [WindowsSelector.cs](https://github.com/open-rpa/openrpa/blob/b78115e45bcfdc1a22398662bac355fdd52fac87/OpenRPA.Windows/WindowsSelector.cs) filters process names/session/process IDs and UIA properties. [GetElement.cs](https://github.com/open-rpa/openrpa/blob/b78115e45bcfdc1a22398662bac355fdd52fac87/OpenRPA.Windows/Activities/GetElement.cs) has min/max result counts, timeouts, retry lookup, responsiveness checks and explicit `ElementNotFoundException`; activities support breakable loops.
- Vision: [image project](https://github.com/open-rpa/openrpa/blob/b78115e45bcfdc1a22398662bac355fdd52fac87/OpenRPA.Image/OpenRPA.Image.csproj) references Emgu.CV 4.1.1.3497 and describes OCR/image recording. Verify that dependency's precise distribution license before adopting the plugin; it is not made permissive by OpenRPA's repository license.
- AI/MCP/verification: no narrow token-authenticated localhost MCP workflow-control surface was established by inspected core. Workflow conditions, exceptions, activities and debugging provide recovery foundations; project-specific durable resume/idempotency and postconditions still require design. The current [issue view](https://github.com/open-rpa/openrpa/issues) has limited open activity, not proof of flawless Windows compatibility.
- Reuse/missing/recommendation: extend OpenRPA if visual XAML desktop authoring is the main objective. For the requested inspectable ASCII agent-facing workflow product, compose its underlying mature libraries instead. Its full desktop designer/runtime would be a disproportionate fork and would change the chosen workflow model.

## laygofiona/jarvisonix (BandLab-specific prior art)

- Repository: [JarviSonix](https://github.com/laygofiona/jarvisonix), a Hack the North submission combining humming, MIDI conversion, voice input and BandLab automation. [MIT license](https://github.com/laygofiona/jarvisonix/blob/2fd2dc5698fc0d2bd32aef6519dcc00d1c05fa05/LICENSE.md); inherited TryCua authorship remains visible in package metadata.
- Maintenance/maturity: no GitHub releases; default-branch commit `2fd2dc5698fc0d2bd32aef6519dcc00d1c05fa05` is 2025-09-27 and no later push was found. Treat as a prototype; the large inherited history is not a measure of application maturity. [Commits](https://github.com/laygofiona/jarvisonix/commits/main/).
- OS/capabilities/format: [cua.py](https://github.com/laygofiona/jarvisonix/blob/2fd2dc5698fc0d2bd32aef6519dcc00d1c05fa05/cua.py) creates a Linux Docker computer from a floating `latest` image, uploads MIDI into Downloads and submits a prompt. It hardcodes an Anthropic computer-use model. Ollama enhances instructions but does not remove that external-model call. It does not implement Windows UIA, declarative deterministic replay, per-import track assertions or independent saved-state verification. End-of-stream is printed as completion.
- AI/MCP and licensing scope: [pyproject.toml](https://github.com/laygofiona/jarvisonix/blob/2fd2dc5698fc0d2bd32aef6519dcc00d1c05fa05/pyproject.toml) retains CUA workspace packages and OpenAI/Anthropic dependencies. The README's local-only description should not be repeated without the source qualification. Vapi is also part of the demonstrated voice flow.
- Reuse/missing/recommendation: reject as a foundation; cite as proof that the creator use case has prior art. Author a new licensed adapter against documented BandLab behavior and live DOM calibration. Do not inherit unverified prompt-completion receipts, cloud image interpretation, floating images or a music-specific core.

## Additional candidates discovered

### FlaUI/FlaUI

[FlaUI](https://github.com/FlaUI/FlaUI) is MIT and a mature .NET wrapper for Windows UIA2/UIA3, with Win32/WinForms/WPF/Store-app coverage. v5.0.0 was released 2025-02-25; repository push was 2026-08-13. It supplies application attach/launch, patterns, process/window scope, conditions and structured properties. It has no mandatory cloud, workflow language, browser DOM engine, OCR or general workflow MCP. [Release](https://github.com/FlaUI/FlaUI/releases/tag/v5.0.0), [license](https://github.com/FlaUI/FlaUI/blob/main/LICENSE).

Reusable retry/wait utilities support explicit checks; wrapper success remains distinct from application outcome. Current issues include [UIA3 vs UIA2 datagrid differences #713](https://github.com/FlaUI/FlaUI/issues/713), [access denied #745](https://github.com/FlaUI/FlaUI/issues/745), and [transitive dependency updates #736](https://github.com/FlaUI/FlaUI/issues/736). Recommendation: compose as an optional .NET provider if pywinauto cannot meet an observed integration need; do not introduce a mixed runtime without a measured reason.

### beuaaa/pywinauto_recorder

[pywinauto_recorder](https://github.com/beuaaa/pywinauto_recorder) is MIT, Windows-specific, and records accessibility paths into editable Python. It resolves path ambiguity and uses element-relative offsets. No normal browser DOM provider, completed OCR engine or AI/MCP control is established. [Recorder design](https://github.com/beuaaa/pywinauto_recorder/blob/master/docs/pywinauto_recorder_exe.rst), [source](https://github.com/beuaaa/pywinauto_recorder/blob/2ddc68645f30842c623f36f407083200589ce397/pywinauto_recorder/recorder.py).

GitHub release 0.6.8 is dated 2024-03-14, while current PyPI 0.6.8 files were uploaded 2024-07-11. Default-branch commit was 2025-10-02; last push 2026-01-10. [PyPI](https://pypi.org/project/pywinauto-recorder/), [releases](https://github.com/beuaaa/pywinauto_recorder/releases). [Open issues](https://github.com/beuaaa/pywinauto_recorder/issues) include recording freezes (#68), drag/drop (#65), and proposed OCR (#46); presence of [Calculator tests](https://github.com/beuaaa/pywinauto_recorder/blob/master/tests/tests_Calculator.py) does not establish compatibility with every Windows 11 install.

Recommendation: consider an optional recorder integration/importer, with source-preserving translation to restricted workflows. Generated Python cannot be automatically treated as safe workflow input. Missing features include local template capture/verification, policy validation, secret exclusion, structured before/after effects, and durable execution checkpoints.

### aisingapore/TagUI

[TagUI](https://github.com/aisingapore/TagUI) is Apache-2.0 and uses readable `.tag` workflows with browser and Sikuli-based visual automation across Windows/macOS/Linux. This is relevant declarative RPA prior art. Latest GitHub release v6.110.0 is dated 2022-06-20; default-branch commit was 2025-03-02 and last repository push 2026-07-21. [Releases](https://github.com/aisingapore/TagUI/releases), [source launcher](https://github.com/aisingapore/TagUI/blob/91aeb07f8e75ff400cc1444b7e485dd800d6c3f3/src/tagui).

The launcher confirms a mixed shell/JavaScript/Python/JVM environment, self-update behavior, and executable extensions. Waits/checks and visual errors exist; no purpose-built schema/policy/MCP/checkpoint package meeting this task was established. [Documentation](https://tagui.readthedocs.io/en/latest/), [issues](https://github.com/aisingapore/TagUI/issues). Recommendation: reject as the selected foundation because aging release/install structure and broad script execution add work compared with a mature current Python foundation. License review of its bundled runtime remains necessary.

## Cross-cutting acceptance lessons

1. Use semantic selectors scoped to verified process/window identity first. Template confidence alone cannot establish application identity.
2. Preserve complete native-window provenance through visual cropping and region transformations; mixing logical and physical DPI units is a known source of errors.
3. Read fresh state for effect verification. Reusing a cached screenshot can create false stability and false success.
4. Treat retries separately for read/selector failures and already-delivered non-idempotent input. Do not click Import twice because the first outcome was slow.
5. Explicitly stop on ambiguous selectors and unsupported widgets. Both UIA and CV have documented edge cases.
6. Recording should produce draft semantic actions and proposed verifications, followed by validation; it should not authorize arbitrary generated Python.
7. Repository license, transitive library license, native binary license and application terms are distinct checks.
8. Report offline, fixture and live validation separately. A fixture proves orchestration/provider contracts, not the current BandLab DOM.


# Creator automation prior-art research

Research snapshot: 2026-09-03. Read-only GitHub API, repository source, issue/release listings, GitHub repository/code/topic search, PyPI/npm endpoints, and official BandLab help were inspected. No third-party code was copied. Search absence is not proof that no project exists; repository search indexes metadata differently from code search, and results contain unrelated projects and spam.

## Search evidence and naming

Authenticated `gh auth status` succeeded for HiTecHelpLLC with repo/workflow scopes. Repository name queries used `GET /search/repositories?q=NAME+in:name`; package checks used PyPI `/pypi/NAME/json` and npm registry `/NAME`.

| Candidate | GitHub name matches | PyPI | npm | Decision |
| --- | ---: | --- | --- | --- |
| craftrelay | 2 (miguel-m-barreto/CraftRelay, NicDev-Studios/CraftRelay) | 404 | 404 | Avoid |
| loompilot | 1 (ilyamirin/LoomPilot) | 404 | 404 | Avoid |
| taskweft | 18, including an existing taskweft automation/MCP organization | 404 | 404 | Avoid |
| createrelay | 0 | 404 | 404 | Recommended neutral repository/package name |

This checks collisions, not trademark clearance or reservation. A general web search finds `CreateRelay` as an AWS SES API method and generic relay factory function, not an identified competing automation product. [AWS API method](https://docs.aws.amazon.com/sesmailmanager/latest/APIReference/API_CreateRelay.html), [GitHub name query](https://github.com/search?q=createrelay+in%3Aname&type=repositories), [PyPI endpoint](https://pypi.org/pypi/createrelay/json), [npm endpoint](https://registry.npmjs.org/createrelay).

Additional GitHub repository queries: `bandlab midi` (5 matches), `bandlab automation` (4), `creator rpa` (14), `declarative desktop automation` (4), `topic:record-and-replay` (23), `topic:desktop-automation` (708). Inspected top recent results and targeted code search `BandLab MIDI`. General web searches covered `site:github.com BandLab MIDI automation import`, BandLab Playwright/Selenium, AI record/replay desktop workflows, declarative desktop automation, verified GUI automation, and creative RPA. Exact phrase search is sparse and not sufficient alone; the user-specified jarvisonix was found through web/README inspection despite absent metadata-query hits.

## Relevant additional projects

| Repository and license | Activity and maturity | OS / execution / workflow | AI, verification and recovery | Reuse / missing requirements / recommendation |
| --- | --- | --- | --- | --- |
| [laygofiona/jarvisonix](https://github.com/laygofiona/jarvisonix), MIT | Last push 2025-09-27; no releases returned; 0 open issues; demonstration repository | Linux Docker CUA browser session; hum to MIDI through Basic Pitch, Python prompts; no declarative deterministic workflow | Ollama prompt enhancement; actual `cua.py` selects an Anthropic model; completion log follows model run without independent import/save proof | Relevant BandLab experiment, not reusable workflow foundation. MIT compatible with attribution, but no code reused. Reject as foundation; learn requirements. |
| [vectora-foundry/clickweave](https://github.com/vectora-foundry/clickweave), MIT | Archived; last push 2026-08-04; no releases returned; 3 open issues | Visual node graphs, desktop recording and normalized OS events; early-development desktop automation | MCP, AI planning; recorded tool calls can replay deterministically | Closely related concept, but archived and experimental. Reject foundation. A search snippet still portrayed it as active, showing why API metadata was checked. |
| [video-db/open-record-replay](https://github.com/video-db/open-record-replay), no detected license | Last push 2026-07-10; no releases; 0 open issues | Native accessibility events plus optional video; generated SKILL.json/SKILL.md; macOS/Windows paths referenced | MCP; LLM compiles recordings; optional video sent to VideoDB | Useful recorder concept, but absent license and cloud-oriented compilation prevent reuse. Do not copy code. Reject dependency. |
| [dcc-mcp/dcc-mcp-core](https://github.com/dcc-mcp/dcc-mcp-core), MIT | Active 2026-09-03; latest release v0.20.22 2026-08-29; 27 open issues/PRs at query | Rust/Python; Windows UIA and exact-window PID/HWND/DPI controls; Linux/macOS components; YAML tools and native workflow specs | MCP/REST/CLI, semantic controls, scoped raw input, checkpoints/jobs, audit and verification; record/compile/replay; snapshots send PNG plus tree by default | Strong creator control-plane candidate; dozens of DCC integrations. Consider future API provider integration. Missing BandLab/browser DOM-first adapter, explicit screenshot suppression policy and selected project's IR integration; significant Rust/runtime scope. Compare with OpenAdapt Flow spike before deciding, not with old OpenAdapt alone. |
| [Hyperyond/Hover](https://github.com/Hyperyond/Hover), Apache-2.0 | Last push 2026-07-14; vscode-v0.45.0 release same day; 0 open issues | Browser/CDP, grounded role/name then test ID/text selectors; writes ordinary Playwright test specs | MCP and AI authoring; deterministic replay; local human-reviewed selector healing | Good browser record-to-code pattern. Compose Playwright directly for mixed desktop/browser runtime; do not fork browser test product as full engine. |
| [seldonframe/reelier](https://github.com/seldonframe/reelier), MIT | Last push 2026-08-25; v1.0.0 2026-07-24; 15 open issues | Node CLI and Docker; tool-call traces compiled to reusable skill artifacts | MCP proxy recording; deterministic replay, per-step drift checks and signed receipts; writes separately granted | Relevant receipt and recording design; no native UIA/vision/BandLab adapter. Consider optional interoperability, not complete GUI runtime foundation. |
| [ugarchance/record-and-replay-skill](https://github.com/ugarchance/record-and-replay-skill), MIT | Last push 2026-08-08; no releases returned | Browser Playwright + desktop OpenAdapt; scripts and editable agent skill | Agent-neutral recording/skill compilation for Codex/Claude/opencode | Relevant thin composition example; agent skill rather than full policy-bound execution service. Do not substitute instructions for verified runner. |
| [lahfir/agent-desktop](https://github.com/lahfir/agent-desktop), Apache-2.0 | Active 2026-09-03; v0.8.4 2026-08-28 | Rust CLI; native accessibility refs and JSON envelopes; currently macOS, Windows/Linux planned | Snapshot-qualified refs, actionability checks, stale/ambiguous target errors, scoped traces | Good identity-contract reference; reject Windows 11 foundation because Windows support is planned. |
| [x7-u/cakewalk-next-mcp](https://github.com/x7-u/cakewalk-next-mcp), MIT | Last push 2026-09-02; no release returned | Python/MCP; Windows Win32 input and project/MIDI parsing; Cakewalk Next, not BandLab Web | Vetted command shortcuts; status checks; README distinguishes key delivery from save success | Potential separate future application adapter. Narrow app, no general declarative workflow foundation. Do not confuse Cakewalk Next with Studio Web. |
| [jeremychadabbott/Bandlab](https://github.com/jeremychadabbott/Bandlab), GPL-3.0 | Last push 2024-07-22; no releases returned | One Python play-track automation script | No required deterministic creation/import engine | Reject; artificial playback is outside product scope. GPL code not copied into permissive composition. |

The `creator rpa` search was dominated by creator outreach/social scheduling, which is outside this project scope. BandLab results also included account engagement/autoplay bots and suspicious proprietary software download repositories; none were used or executed.

### Code and issue findings

jarvisonix [cua.py](https://github.com/laygofiona/jarvisonix/blob/main/cua.py) constructs a Linux Docker CUA computer and `ComputerAgent(model="anthropic/claude-3-5-sonnet-20240620")`. Its README's claim of no cloud dependencies must not be carried into this project's architecture decision. The script prints completed after the agent iteration, without independently checking tracks or saved state. [PR 8](https://github.com/laygofiona/jarvisonix/pull/8) concerns prompt improvements and removing API keys; no contents of historical credentials were inspected.

DCC MCP's [workflow guide](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/workflows.md) describes foreach/parallel/branch/tool/approve, bounded retries, cancellation, SQLite persistence and resume from completed step outputs. Its older recovery section says interruption is terminal while a later section documents `workflows_resume`; this documentation drift needs a spike rather than assumptions. [Issue 2417](https://github.com/dcc-mcp/dcc-mcp-core/issues/2417) reports response mis-correlation on 2026-09-03. That is a reported risk, not proof every configuration is affected. [Python workflow_yaml.py](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/python/dcc_mcp_core/workflow_yaml.py) is a separate task/step conversation-definition layer, so do not mistake it for the Rust execution engine.

## Current BandLab contract from official documentation

- Web imports MIDI and WAV. Initial New Track page has Import Audio/MIDI; existing projects offer drag/drop or the composition import control. Documentation notes possible leading imported-audio silence, so reference alignment cannot assume every WAV starts exactly at zero. [Import instructions](https://help.bandlab.com/hc/en-us/articles/900003008403-Importing-Audio-and-MIDI-Files).
- Current standard limit is 16 tracks and 15 minutes; Membership raises tracks to 32, not duration. Keep both configurable and count actual created tracks, including a reference WAV. A type-1 MIDI may contain several nonempty tracks; do not assume file count equals track count. [Limits](https://help.bandlab.com/hc/en-us/articles/115002945433-Track-and-Project-Duration-Limits), [format support](https://help.bandlab.com/hc/en-us/articles/360036010533-Supported-Import-and-Export-File-Formats).
- Virtual instruments are chosen from the instrument panel; use externally editable names/categories and verify selected instrument state. Do not hardcode a screenshot coordinate. [Virtual instruments](https://help.bandlab.com/hc/en-us/articles/46380376077593-Using-BandLab-Virtual-Instruments).
- Tempo is available from the transport metronome dropdown; documented metronome range is 40-240 BPM. Use this as a default guard and require calibrated selector support. [Metronome](https://help.bandlab.com/hc/en-us/articles/115002960274-Using-the-Metronome).
- Web Ctrl+S saves a revision, Enter moves the playhead to the beginning, Shift+M mutes, and G toggles snap. These are fallback shortcuts only after exact app and state verification; avoid destructive Q quantization. [Shortcuts](https://help.bandlab.com/hc/en-us/articles/360021363353-Studio-Keyboard-Shortcuts).
- Saving may fail or remain processing; a save click/shortcut is not proof. BandLab recommends preserving the open Studio when saving fails. Do not auto-close on failure. [Saving issues](https://help.bandlab.com/hc/en-us/articles/115002945193-Saving-Issues).
- Search found a [BandLab Swagger landing page](https://swagger.bandlab.io/) pointing to a test API documentation host, but did not establish a supported, authorized public Studio project-import API contract. Do not reverse engineer private endpoints or assume the presence of Swagger authorizes them. Browser DOM is the first proven public interaction layer here.

Official help has changed recently; live controls/selectors are not established by documentation alone. No authenticated BandLab DOM was inspected in this research.

## Proposed BandLab adapter and faithful local fixture

Use the chosen maintained runner's action-provider boundary; never put application names in engine conditionals. The provider should accept a reviewed MIDI import manifest and an editable selector/instrument configuration. It should dispatch via the generic browser adapter, observe scoped DOM state, and return a distinct delivered/verified outcome. Any uncertainty becomes a checkpoint with structured diagnostic fields.

1. MIDI analysis is local/read-only: parse time-signature and tempo events with absolute tick and seconds conversion, track/channel/program metadata, note bounds/counts, duration and empty tracks. Preserve source bytes. Drums use channel 10 (zero-based 9) as strong evidence; program/name/range heuristics classify other parts with confidence and review reasons.
2. Manifest records immutable source hashes, nonempty-track expectations, order, proposed names, configurable instruments, tempo conflicts, reference path and offset, and track/duration limit checks. No implicit quantization or velocity changes.
3. Dedicated Chrome/Edge persistent profile stays outside Git. Manual authentication checkpoint precedes Studio inspection. Restrict allowed origin, URL patterns and expected Studio identity. No login interaction or credentials.
4. File import uses `set_input_files` or `expect_file_chooser` where calibrated. Before/after visible track/region state must establish the expected new artifacts. Do not retry import blindly after timeout; inspect for partial effects to avoid duplicates.
5. Naming, instrument selection, offset/alignment, reference mute and save each have independent verification. Unsupported controls produce manual review and a non-success state until resolved. A local fixture must not imply live selector compatibility.

Faithful fixture: localhost Studio-style DOM implementing new/open project, tempo, real file-input events, async imports parsing synthetic SMF header/track count, visible tracks and regions, names/instrument selectors, reference offset/mute, unsaved/saving/saved state and saved project persistence. Add switches for delayed import, ambiguous or missing semantic selector, rejected save, partial import, track limit and wrong page identity. The generic provider must interact through Playwright's actual browser DOM and validate rendered state; a Python mock returning success without UI effects is insufficient.

Also build a small local browser creative fixture (e.g. scene/card editor with title, layers and verified saved artifact) and Windows UIA fixture (e.g. native editable document/form with a verified state label, plus locally rendered template/OCR fallback). Synthetic inputs should be generated programmatically. CI exercises fixtures, while one documented live command opens the dedicated profile and blocks for normal sign-in/calibration before import. Live validation must still be listed as pending until actually observed.

## Naming and workflow-sharing addendum (2026-09-03)

The CreateRelay name searches above are preserved as historical research. After
the user's later request for Lightspeed or a leetspeak variant, the selected name
became **L1ght5p33d**, repository and package slug `l1ght5p33d`. The new
[name research](research/name-update.md) records the GitHub, PyPI and npm checks:
the selected spelling had zero GitHub repository-name matches and HTTP 404
responses from both registries at query time. These are snapshot observations,
not a reservation, trademark clearance or exhaustive uniqueness claim.

The same search discovered
[smartcomputer-ai/lightspeed](https://github.com/smartcomputer-ai/lightspeed), an
Apache-2.0 agent-session orchestration system. The name report documents its
architecture and why its durable agent-event replay does not replace the
selected OpenAdapt Flow foundation for learned GUI workflows with postconditions.

The [workflow-sharing appendix](research/workflow-sharing.md) compares SoundFlow,
ReaPack, ComfyUI and OpenAdapt Agent. Discoverable macros, reusable creation
graphs, shared packages and MCP workflow libraries are established prior art.
L1ght5p33d's scope is a general platform to author, find, edit, compose and run
local automation; BandLab is the first reference integration. Neither workflow
sharing nor a unique community network is claimed as an invention. The appendix
also distinguishes engine licenses from individual package licenses and records
that no commercial scripts or unlicensed workflow content were copied.

The later [registry and P2P research](research/registry-p2p.md) evaluates the
proposed THEBEST register. It found existing OpenAdapt capture transfer and
hosted artifact ingest, but no matching public compiled-workflow P2P catalog in
the targeted search. It recommends reusing Kubo for optional content-addressed
distribution rather than building a transport protocol; no registry or site
integration is represented as implemented.
