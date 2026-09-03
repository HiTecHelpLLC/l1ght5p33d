# L1ght5p33d roadmap

Future milestones below are planned work. The current-preview section describes
the implemented scope; release notes record its completed checks. Acceptance uses
verified outcomes and reproducible fixtures; live qualification is separate.
L1ght5p33d is a general foundation for creating, discovering, adapting, combining
and running reusable computer workflows. BandLab is the first application
reference; the workflow library and provider contracts serve other applications.

## Next product milestone

**An AI discovers a THEBEST-reviewed creator workflow, verifies the exact pack,
checks the local environment, shows the complete plan, obtains human approval,
executes it on Windows and returns a verified result or actionable recovery.**

The v0.2.0 companion now connects on-demand curated downloads, exact pack
verification, a managed cache and the local review page. It keeps author identity,
curator test scope and human approval separate. The next useful milestone is a
qualified everyday creator outcome beyond the fixed poster fixture:

1. Qualify the original BandLab task in an authorized live session: import at
   least one synthetic MIDI, verify its track/region and saved state, and document
   recovery from an interrupted import. The admitted poster example is a test
   fixture, not evidence of a completed everyday creator task.
2. Qualify the library against the distinct v0.2.0 runtime and record new evidence
   for that environment. Existing curator signatures retain their original
   source-runtime and fixture scope; release packaging cannot extend a signature.
3. Give the product a front-facing THEBEST page with a clear Windows installation
   path, reviewed workflow examples, source links and precise maturity labels.
   The website explains and distributes; the installed companion owns local
   execution and approval. Apply THEBEST's visual-design and publication process.
4. Deploy the public register and connect optional P2P delivery. Define
   hosting/pinning availability, key rotation,
   revocation and stale application compatibility before broad distribution.

Keep scope Windows-first. Local Windows 11 fixture evidence, hosted Windows
Server/Ubuntu CI and WSL are distinct environments. Neither headless Ubuntu CI
nor access to WSL establishes native Linux desktop automation support.

The guided local companion uses the public GitHub library today. These priorities
do not imply an active THEBEST website register or public P2P service. No new
execution engine is needed for this milestone.

## Current developer preview

- On-demand THEBEST curated packs with exact detached-signature, review and
  evidence verification. The initial public collection has one browser fixture.
- Local review page with a summary, complete steps, variable editing and authored
  workflow copies. Exact single-use approval stays with the human; copies do not
  inherit the source curator signature.
- Managed download cache: 90 days without execution by default, configurable
  1-3650 days. Active, pinned, modified and untracked content is protected;
  authored copies and receipts are outside eviction. Only execution refreshes use.
- `try` prepares the fixed local fixture and review page; `serve` uses managed
  defaults, with `prepare_task`, `get_task_status` and `get_cache_status` for AI.
- Native OpenAdapt Flow workflows inside strict ASCII JSON registry envelopes.
- Local folder discovery with descriptions, parameters, steps and document
  digests through the CLI, JSON-RPC and MCP. Files can be edited and shared
  through Git; reviewed same-application subflows can be combined with `includes`.
- A signed-catalog CLI client with text search and exact-version installation
  of one verified JSON block through local Kubo. Installation grants no execution
  permission and does not install provider code. These advanced imports go to the
  operator's library, outside the managed curated-pack cache.
- Registered browser, Windows and BandLab providers; no workflow shell command.
- CLI, local JSON-RPC and token-protected loopback MCP control.
- Typed effects, receipts, active pause/step/resume/abort, and an SDK path for
  reviewed durable continuation.
- Local MIDI analysis/classification and reviewable manifests; BandLab import
  orchestration exercised against a synthetic fixture.
- Browser creative and native Windows UIA/template fixtures. Native input on the
  initial host remains pending foreground access.

See the [workflow library guide](workflow-library.md) for what works today.
The preview does not claim an active public community register. Hosted catalog
moderation, executable provider packages and automatic conversion from other
automation formats remain separate work.

## Next: grow the general workflow library

1. Add small, tested workflow packs for asset organization, image/video editing,
   DAWs, browser design tools, project preparation and exports.
2. Make local discovery easier with capability metadata, tags and compatibility
   filters. Keep execution tied to reviewed files and installed providers.
3. Improve authoring and composition: reusable parameter contracts, reviewed
   cross-application provider provisioning and clearer subflow diagnostics.
4. Qualify a hosted community register and its publishing process, including
   licenses, provenance, fixture tests and application compatibility. Add key
   rotation, persistent minimum-revision checks and moderation before broad
   distribution. Discovery must not silently install code, grant permissions or
   run a workflow.

## Qualify reference applications

1. Complete authenticated BandLab qualification: MIDI import, track/region
   evidence, naming, supported tempo controls, instruments, reference handling,
   save and saved-state evidence.
2. Run Windows input tests on an unlocked Windows 11 desktop, including Chrome
   and Edge, DPI changes, overlapping windows and mixed-monitor layouts.
3. Interrupt imports deliberately and verify explicit reconciliation before
   continuation. Preserve musical timing/expression; destructive processing
   stays opt-in.
4. Add independent save/export verifiers where an authorized API or inspectable
   local output exists.

## Recorder and authoring

- Start from an existing compatible workflow when possible. Use AI to describe,
  select, adapt or compose it; deterministic execution remains useful offline.
- Translate inherited OpenAdapt recordings/native bundles into registered
  operations with reviewed selector and effect contracts.
- Evaluate `pywinauto_recorder` for semantic Windows events instead of building
  another raw-coordinate recorder.
- Capture bounded before/after state, timing, identity and local anchors while
  excluding credential entry.
- Extend the local review UI with composition, richer diffs and checkpoint recovery.

The preview does not have an integrated one-click record-to-registry workflow.

## Providers and distribution

- Versioned, separately installable provider entry points with capability and
  compatibility tests.
- Community workflow packs with attribution, schemas, synthetic fixtures and
  declared application assumptions.
- Improved Windows installation, diagnostics and calibration while retaining
  ordinary editable text files and a useful CLI.

## Reliability and boundaries

- More failure-injection coverage for slow updates, duplicates, theme changes,
  lost focus, malformed files and partial execution.
- Explicit cleanup/rollback contracts where applications support them; no
  generic undo guarantee is claimed today.
- Better redacted diagnostics and bounded retry policies.
- Routine execution stays independent of mandatory cloud or paid AI. Repairs
  remain proposals subject to schema and local permission checks.

Account creation, credential entry, artificial social activity, plays,
distribution and purchasing remain outside the BandLab adapter's scope.
