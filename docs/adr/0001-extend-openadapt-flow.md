# ADR 0001: extend OpenAdapt Flow with bounded creator providers

Date: 2026-09-03. Status: accepted for the developer preview.

## Evidence and decision

Current GitHub source, releases, issues, registries and official documentation
were reviewed before creating this downstream repository. See
[prior art](../prior-art.md) and [technical spikes](../technical-spikes.md).
OpenAdaptAI/OpenAdapt is now a launcher; its current engine, openadapt-flow,
already supplies the requested deterministic replay, structural-first selectors,
local OCR/templates, recording, typed workflow graphs, effect verification and
durable recovery. Forking the historical OpenAdapt monolith or writing another
execution engine would discard that work.

CreateRelay is a history-preserving downstream fork from upstream commit
`0b1e6b2a8b7cc1641a8fad4a46e71860d051760a`. The original Git history, MIT
copyright, repository-only license notices and upstream source are retained.
The `upstream` remote points to the original project. The public downstream has
its own release namespace; upstream tags remain available from that remote.

The new separately packaged `createrelay` namespace adds a restricted provider
surface, creator workflows, MIDI analysis, a local control service and CLI.
It uses upstream `Replayer`, `Workflow`, `ApiBinding`, and effect-verifier
contracts. A controller gates step boundaries but delegates action execution
and workflow graph semantics to the inherited runtime. It does not reinterpret
screenshots with a model or introduce a second workflow interpreter.

## Why native ASCII JSON instead of Robot Framework

Robot 7.4.2 passed a parse/loop/assertion spike and offers more concise authoring.
However, translating its execution, exception and resume semantics into Flow's
identity/effect/checkpoint model would create two sources of truth. Native Flow
JSON preserves existing typed graph, guard, loop, subflow and effect contracts,
is ASCII when saved with `ensure_ascii=True`, can be edited without AI, and is
validated with Pydantic and a versioned CreateRelay envelope. This is a material
safety and maintenance advantage. A future Robot authoring compiler may emit
the same IR; a second independent runtime is out of scope.

## Reuse and boundaries

- Playwright provides DOM/ARIA selectors, dedicated Chrome/Edge profiles and
  semantic file uploads. pywinauto provides Windows UIA and Win32 identification.
- Flow's existing OpenCV/RapidOCR implementation supplies local visual fallback.
- Mido inspects MIDI locally; no personal music ships with the package.
- The official MCP Python SDK handles protocol transport. CreateRelay supplies
  loopback binding, session-token authentication and a bounded workflow registry.
- Provider calls use `ApiBinding.kind=tool`. This is a dispatch seam, not a
  claim that a DOM operation is an official application API. Receipts record
  the real selector method and actual evidence tier.
- GUI readback is labelled as GUI evidence. It never becomes independently
  verified server persistence by relabelling a successful click.

The original MIT license is retained because this is a fork. No AGPL benchmark
material is included in CreateRelay's wheel or sdist. OculiX, OpenRPA, the broad
RPA Framework distribution and cloud agents are not default dependencies.

## Consequences

The checkout is larger than the small creator extension because history and
source provenance are preserved. Upstream commands have their own documented
capabilities and must not be confused with CreateRelay's narrower permission
surface. Only the creator package and declared examples are covered by the
CreateRelay v0.1.0 acceptance matrix. Upstream production-admission claims are
not inherited by this developer preview.
