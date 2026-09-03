# Windows execution and calibration

L1ght5p33d's Windows provider composes pywinauto 0.6.9 with the existing
OpenAdapt Flow image matcher and local RapidOCR. It runs on an unlocked,
interactive Windows desktop. It does not launch applications through workflows,
steal foreground focus, bypass UAC, or send captured images to an AI service.

## Run the harmless reference workflow

Install the developer preview, then run:

```powershell
l1ght5p33d demo windows
```

Click **L1ght5p33d Creative Fixture** once when it opens. The command waits up
to 60 seconds for normal foreground activation. It compiles the bundled original
WinForms fixture with Windows' .NET Framework compiler, creates a local
calibration image of its synthetic canvas, writes a reviewable ASCII workflow,
and runs that document through the same policy, provider, Flow interpreter,
verification and receipt path as other workflows.

The three steps fill an artwork title through UIA, invoke the Apply title button,
and stamp a drawn canvas using a declared template fallback after an accessible
button selector fails. Every step has fresh UI readback. The program prints its
temporary output folder containing the generated document, calibration metadata,
and execution receipts. These are synthetic local assets; they never enter Git.
The result is `completed_ui_verified`, which confirms the displayed state rather
than an independent persisted file. This fixture intentionally has no file,
network, music, account, or publishing functions.

The installed demo includes its source and requires no repository checkout.
`examples/l1ght5p33d/windows-creative.json` is the same readable shape with
placeholder local paths. Use the demo-generated document for actual execution.
Launching the demo authorizes only its generated fixture document and exact
digest; it does not grant permission to control other desktop applications.

## Identity and selector policy

Configuration requires an exact executable path and a full-match title regular
expression. An optional PID or HWND narrows the initial attachment. After first
attachment, L1ght5p33d pins the PID, process creation time, and HWND. Before
input it checks the executable, title, bounds, display, target-window DPI,
monitor DPI, visibility and foreground state again. Native handle discovery is
filtered before UIA inspection, avoiding traversal through unrelated processes.

Selectors are bounded JSON arrays, with this ordering:

1. UIA automation ID, name/title, class, or control type.
2. Optional Win32 control identification.
3. Local exact-line OCR or unique template matching.
4. Explicitly enabled fractional coordinates inside the verified window.

The first selector must be semantic. An ambiguous semantic match halts rather
than dropping to a visual guess. OCR requires one exact normalized text line
and sufficient recognition confidence. Templates must have distinguishing
structure and exactly one match at the calibrated scale. Confidence defaults to
0.95 and cannot be lowered below 0.8. Relative coordinates are disabled unless
the locally approved configuration sets `allow_relative: true`; the selector
must declare `anchor: "window"` and strictly interior fractions. Absolute screen
coordinates are not accepted as a workflow selector.

```json
{
  "selectors": [
    {"method": "uia", "auto_id": "stampButton", "control_type": "Button"},
    {"method": "template", "template": "stamp.png", "confidence": 0.98}
  ]
}
```

The provider exposes `fill`, `click`, `read`, and `assert_text`. Fill and read
require semantic controls. UIA buttons use native Invoke; other semantic
controls and visual targets may use input at a checked location. Before pointer
input, a native hit-test confirms that another window does not cover the target.
Click delivery alone remains `delivered_unverified` until its declared effect
is read. A failed verification after input is uncertain and is never blindly
repeated. This distinction also applies to slow or unresponsive applications.

## Personal calibration

Put personal templates under a dedicated folder beneath your local L1ght5p33d
state directory, outside the repository. Set `template_root` to that folder in
the locally reviewed workflow configuration. Only PNG files resolved inside that
folder are readable; traversal, symlink escape, oversized images and low-detail
templates are refused. No screenshot export operation is exposed over MCP.

`WindowsProvider.calibrate(path, theme="...")` is a local developer helper that
writes window identity, bounds, target and monitor DPI, theme annotation, and
schema version. It does not capture images. The synthetic demo separately
captures only its own known canvas. Browser zoom calibration belongs to the
browser provider; its Windows metadata field is explicitly `null`.

For a real application, capture the smallest distinctive anchor through an
explicit local calibration session and review it before enabling a fallback.
Calibrate again after theme, font, DPI, or zoom changes. Template matching uses
the calibrated 1:1 size; it fails safely instead of silently accepting another
scale. Keep a target on one display when its visual region would otherwise span
monitors with different DPI. Cross-display visual qualification remains a
separate test requirement.

## Verification and troubleshooting

Run deterministic contracts without a foreground desktop:

```powershell
python -m pytest packages/l1ght5p33d/tests/test_windows_provider.py -q
```

Run the real native test from a checkout with the package installed:

```powershell
$env:L1GHT5P33D_WINDOWS_LIVE = "1"
python -m pytest packages/l1ght5p33d/tests/test_windows_live.py -q
```

The native test explicitly focuses only its own synthetic fixture during setup.
Some desktop hosts deny this activation. That is an environment limitation:
use `l1ght5p33d demo windows` and click the fixture manually. Automated CI
qualification should run the native test with an interactive desktop and should
not set `L1GHT5P33D_ALLOW_NO_FOREGROUND`. Developers may set that variable to
`1` to record an explicit skip on a restricted local host; a skip is never a
passing native-input qualification.

Typical refusals identify the needed recovery:

| Refusal | Recovery |
| --- | --- |
| Window is not foreground | Focus the authorized window, then resume. |
| Expected one window; found zero or several | Correct the executable, title, PID or HWND. |
| Process identity changed | Review the restarted application and start a new run. |
| Ambiguous selector or template | Add a stable automation ID or a more distinctive local anchor. |
| Window geometry or DPI changed | Stop, recalibrate, and approve the changed document. |
| Input delivered; postcondition unobserved | Inspect state before deciding whether retry is safe. |
| COM-compatible worker required | Use the packaged CLI worker, rather than embedding into an incompatible COM apartment. |

Global event recording is not part of this preview. The recorder plan is to
integrate or translate existing semantic events from `pywinauto_recorder`, then
require explicit effect annotations and policy validation. Raw generated Python
will not become an executable workflow through an import shortcut.
