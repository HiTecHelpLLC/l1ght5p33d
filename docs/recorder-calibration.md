# Recorder and calibration status

L1ght5p33d inherits OpenAdapt Flow's recording and compilation foundation.
Upstream recording can produce a native Flow bundle. That bundle is not
automatically a L1ght5p33d registry document: the managed surface accepts
registered bindings with declared effects, policy validation, and local approval
of the exact document.

The preview supports hand-authored and program-generated ASCII workflows,
discovery from a local folder, editing existing files, and composition through
reviewed same-application subflows. Start with the
[workflow library](workflow-library.md): a reusable workflow can supply most of
a new task before anything needs to be recorded. An AI can help select a file,
set declared variables or propose a patch; routine execution needs no model.

Integrated recording-to-provider translation and a hosted community register
remain planned. A signed-catalog client can already download a reviewed version
through local Kubo, without authorizing its execution. Captured clicks, foreign
workflow formats and generated Python are not automatically executable through
the managed registry.

## Planned recorder output

Recording should fill gaps in the reusable library and help repair changed
interfaces. An explicit user-started session should collect:

- Foreground executable, PID, HWND, title, hierarchy, bounds, display and DPI.
- Timestamped mouse/keyboard events and window-relative positions.
- Accessible controls with stable IDs, names, roles and labels.
- Local OCR anchors and cropped templates when semantic controls are absent.
- Before/after structured state and proposed assertions of the intended effect.

Authoring will consolidate events, replace coordinate-only input with semantic
targets, assign named steps/variables, and require review of uncertain effects.
Observation does not grant permission to change applications, expand filesystem
access or publish content.

`pywinauto_recorder` is a candidate for Windows event capture. Generated Python
would be translated into restricted operations, not executed as an imported
workflow. Record its version, license and platform limitations before adoption.

## Calibration available now

`WindowsProvider.calibrate(destination, theme="...")` writes local metadata:
schema version, window identity, bounds, display, target/monitor DPI and theme.
It does not capture an image or infer browser zoom. The Windows demo separately
captures only its known synthetic canvas into a temporary local folder.

Keep real templates under a dedicated local `template_root` outside Git. Only
bounded PNG files inside that root are accepted, with a unique match at the
calibrated 1:1 scale. OCR reads pixels locally and requires one exact normalized
text match above its confidence threshold. Neither path uploads screenshots.

Browser calibration currently means reviewing profile, channel, origin, title
and semantic selectors. BandLab live generation takes an explicit reviewed
selector file. A general browser zoom/theme wizard is planned.

## Review and reuse

1. Find a compatible local workflow or create an ASCII document for an installed
   provider. Identify the steps that need new selectors or recording.
2. Use a fixture or harmless action in your authorized session. Inspect only the
   relevant application region, excluding credentials.
3. Prefer stable accessibility selectors and document visual fallbacks.
4. Verify fresh outcome state; a click establishes only input delivery.
5. Review the ASCII diff, application assumptions and permissions before local
   approval. Combine reviewed subflows where their configuration matches.
6. Share licensed workflows and synthetic fixtures with compatibility and test
   information; keep personal calibration, profiles,
   images and session data local.

Recalibrate after UI, DPI, theme, font or zoom changes. Shared workflows can
describe anchors without distributing private captures. See
[Windows execution](windows.md) and [provider development](adapter-development.md).
