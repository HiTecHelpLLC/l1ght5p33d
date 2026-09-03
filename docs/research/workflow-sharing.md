# Workflow sharing and reusable creation knowledge

Research snapshot: 2026-09-03. This appendix covers established ways to discover,
edit, compose and share reusable creation workflows. L1ght5p33d's intended scope
is general local computer automation; BandLab MIDI importing is its first
application reference. Shared workflow libraries, reusable macros and agent
discovery already exist. This project does not claim to have invented them or
to possess a unique sharing network.

## SoundFlow

[SoundFlow](https://soundflow.org/) provides creator automation with editable
macros, JavaScript scripts, decks and triggers, particularly for macOS audio
production. Its [store](https://soundflow.org/store) organizes packages by
application, creator and production task, including session preparation,
composing and export. It is strong prior art for helping people find and reuse
automation rather than repeatedly teaching an agent the same task.

The application is proprietary, not an open-source engine we can fork. Its
[terms](https://soundflow.org/docs/legal/terms-and-conditions), sections 1.1 and
2.3, distinguish the application license from contributor content: contributions
are licensed to SoundFlow under MIT and two CC-BY versions, with further rights
granted to SoundFlow. This does not establish that every store package has an
unconditional reuse grant to this project. Check the individual package's actual
license, provenance and applicable terms. No commercial package or script has
been copied. Recommendation: learn from its catalog and composition experience;
do not adopt its proprietary runtime as the open-source foundation.

## ReaPack

[ReaPack](https://github.com/cfillion/reapack) is an established package manager
for REAPER. Its Windows, macOS and Linux build paths and reusable script/package
ecosystem demonstrate that distributing creator automation separately from the
host application is practical. The GitHub mirror is archived, but its
[README](https://github.com/cfillion/reapack/blob/master/README.md) explicitly
moves development to [Codeberg](https://codeberg.org/cfillion/reapack), with
[v2 development](https://codeberg.org/cfillion/reapack2) in a separate repository.
Archival here is not evidence of abandonment. GitHub metadata showed a last push
on 2026-06-03 and [v1.2.6](https://github.com/cfillion/reapack/releases/tag/v1.2.6)
released on 2025-09-08; current Codeberg activity was not independently inspected.

The manager is **LGPL-3.0-or-later**, explicitly stated in
[ABOUT.md](https://github.com/cfillion/reapack/blob/master/ABOUT.md). REAPER is a
separate host, and packages have their own licenses. A package manager's license
does not license everything it distributes. Recommendation: consider catalog
metadata, source provenance and pinned package versions as design references;
evaluate future interoperability through a separate REAPER adapter. No ReaPack
code or third-party scripts are copied into this permissive package.

## ComfyUI

[ComfyUI](https://github.com/Comfy-Org/ComfyUI) is an active local content creation
graph engine for Windows, Linux and macOS. GitHub metadata showed a push on
2026-09-03 and [v0.34.0](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.34.0)
released on 2026-08-26. It saves editable JSON workflows and supports reusable
nodes and subgraphs. Its scope is an AI content pipeline, rather than general
browser and Windows UIA interaction.

[Workflow templates](https://docs.comfy.org/custom-nodes/workflow_templates)
can ship alongside custom nodes as JSON examples and appear in the template
browser. [Subgraphs](https://docs.comfy.org/interface/features/subgraph) expose
inputs and outputs, support nesting, and can become reusable blueprints. These
are direct precedents for editable, composable workflows and discoverable
examples.

The core is [GPL-3.0](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE).
Custom nodes, models and shared assets may have separate terms; neither blanket
permissive licensing nor blanket GPL licensing of every workflow file follows
from the engine's license. Recommendation: consider a future separately running
ComfyUI application adapter using its documented API. Do not vendor its engine,
unlicensed workflows or model assets into L1ght5p33d.

## Public OpenAdapt references

Follow-up search on 2026-09-03 confirmed that OpenAdapt publishes a
[public workflow reference catalog](https://openadapt.ai/workflows) and a
[template gallery](https://openadapt.ai/templates). The catalog covers synthetic
OpenEMR, Frappe Lending and openIMIS environments and explicitly calls itself a
reference catalog, not a marketplace. The gallery also includes descriptive
patterns that require recording and qualification on the user's own application.

There are actual downloadable bundles, including the
[MockMed triage workflow](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/public-demo/evidence-packs/mockmed-triage-v3/artifacts/bundle/workflow.json)
and its [complete evidence pack and setup](https://github.com/OpenAdaptAI/openadapt-flow/blob/main/public-demo/README.md).
The MockMed pack is MIT-licensed and contains a schema-2 workflow, local templates,
recording and verification evidence for its pinned synthetic environment.
These deliberately published references coexist with private user-owned bundles.
Private-by-default does not mean that all OpenAdapt workflows are private.

Native Flow bundles are not directly accepted by the current L1ght5p33d catalog
installer: it requires the project's ASCII envelope, provider configuration and
local permissions, and does not import arbitrary template directories. Reuse
requires explicit adaptation and environment qualification.

## OpenAdapt Agent

[OpenAdapt Agent](https://github.com/OpenAdaptAI/openadapt-agent) is especially
relevant because it exposes governed OpenAdapt Flow workflows through MCP and
portable Agent Skills. Its private bundle library supports workflow discovery,
descriptions and reports; typed run tools require explicit enabling. Execution,
policy, identity, verification, durable pauses and audit remain with Flow. The
repository is MIT licensed, unarchived, and showed a push on 2026-09-03; no GitHub
release was returned by the release query at research time.

The [README](https://github.com/OpenAdaptAI/openadapt-agent/blob/main/README.md)
documents read-only defaults and explicit protected-export controls. Emitted
Skills may include the original compiled bundle; they are not automatically
sanitized public artifacts. Recommendation: compare and compose with this
upstream bridge before adding another general agent discovery or Skill export
layer. L1ght5p33d extends the same workflow foundation with creator providers and
local packaging. It does not claim that MCP workflow libraries or governed
replay originated here.

## Implications for shared workflow packages

The following are design requirements for future catalog work, not claims that
a hosted registry or every metadata field is already implemented:

- Preserve author, source URL, license, content digest and dependency versions.
- Describe variables, application versions, adapter requirements, permissions,
  calibration needs and expected effects before a workflow is run.
- Treat downloaded workflows as untrusted input. Popularity and a familiar name
  do not establish compatibility, authorization or verified success.
- Keep personal files, browser profiles, credentials and captured images outside
  public packages. Publish reviewable changes without silently expanding access.
- Support authoring, finding, editing, composing and executing workflows across
  creative applications, while documenting each adapter's qualification level.

No code, scripts, workflows or media from the four ecosystems above were copied
for this research appendix. Links identify prior art and possible integration
boundaries; they do not imply affiliation or endorsement.
