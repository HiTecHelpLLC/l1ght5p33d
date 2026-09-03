# L1ght5p33d roadmap

This roadmap describes planned work, not delivered capabilities. Acceptance uses
verified outcomes and reproducible fixtures; live qualification is separate.
L1ght5p33d is a general foundation for creating, discovering, adapting, combining
and running reusable computer workflows. BandLab is the first application
reference; the workflow library and provider contracts serve other applications.

## Current developer preview

- Native OpenAdapt Flow workflows inside strict ASCII JSON registry envelopes.
- Local folder discovery with descriptions, parameters, steps and document
  digests through the CLI, JSON-RPC and MCP. Files can be edited and shared
  through Git; reviewed same-application subflows can be combined with `includes`.
- A signed-catalog CLI client with text search and exact-version installation
  of one verified JSON block through local Kubo. Installation grants no execution
  permission and does not install provider code.
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
- Add an optional local UI for variables, composition, diffs and checkpoints.

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
