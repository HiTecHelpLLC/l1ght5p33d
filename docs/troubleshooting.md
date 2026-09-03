# Troubleshooting

Start with run status, JSONL receipts and the readable execution log. The CLI
prints the receipt directory. MCP and local JSON-RPC expose
`get_execution_status`, `get_execution_log`, `inspect_ui_state` and
`explain_failure`. Service UI state is timestamped evidence from the last
completed action boundary, not a continuous live feed.

| Symptom | Recovery |
| --- | --- |
| Workflow absent from `list` | Put a valid ASCII workflow `.json` directly in the selected folder. Validate it explicitly to reveal errors; nested files and foreign formats are not automatically registered. See the [workflow library](workflow-library.md). |
| Exact digest grant required | Review the document, then run `l1ght5p33d approve-workflow workflow.json --policy policy.json`. Run with that policy. |
| Patch no longer passes policy | Review the diff and approve the new document locally. An old digest does not authorize new contents. |
| ASCII/schema error | Use ASCII JSON with Unicode escapes. Export the current schema with `l1ght5p33d schema --out workflow-schema.json`. |
| Credential variable rejected | Authenticate manually in the dedicated session. Passwords/tokens are not managed workflow parameters in this preview. |
| Browser executable missing | Run `python -m playwright install chromium` for fixtures; install Chrome or Edge for that live channel. |
| Wrong origin/title or unexpected popup | Inspect the dedicated session and restore the reviewed application state. |
| Windows target not foreground | Click the authorized window. Do not disable the foreground guard. |
| Ambiguous selector | Add a stable automation ID, class, control type or narrower application identity. |
| OCR/template miss | Check theme, DPI, font, zoom and local calibration. Review a more distinctive anchor. |
| Delivered input, unobserved effect | Inspect the application before retrying. An import/save may have happened despite a timeout. |
| Too many MIDI tracks | Review the manifest and use an appropriate limit or smaller batch. |
| BandLab manual review | Follow the listed checkpoint. Unsupported instruments, alignment and saved-state evidence are not assumed. |
| MCP host/origin/token rejection | Use the displayed loopback endpoint and local session token. Remote binding is unsupported. |

## Pause, cancellation and recovery

Pause takes effect at an action boundary. Step mode releases one action at a
time. Abort prevents subsequent actions and lets an already-delivered action's
verification finish. Killing a process during input can leave uncertain state;
interrupted work is not reported complete.

`resume_workflow` resumes an active paused run. It does not recreate a terminal
run after service restart. Durable continuation is an SDK operation:
`l1ght5p33d.runtime.resume_from_checkpoint` requires the matching Flow bundle,
fresh providers and an operator-reviewed `ApprovalRecord`. Revalidate current
application state first. There is no automatic crash recovery that guarantees
exactly-once input. See the [recovery guide](l1ght5p33d/recovery.md) and durable
tests in [`test_runtime.py`](../packages/l1ght5p33d/tests/test_runtime.py).

## Qualify the environment

```powershell
l1ght5p33d demo browser
l1ght5p33d demo bandlab
l1ght5p33d demo windows
```

Browser and BandLab demos use local synthetic fixtures. They do not test
BandLab's live interface or authentication. The Windows demo opens a synthetic
WinForms application and waits for a manual click to focus it.

On the initial development host, native identity inspection worked but Windows
denied programmatic foreground activation. Native input was not qualified there.
Use an unlocked interactive desktop and the command above; the dedicated test
is documented in [windows.md](windows.md). An environment skip is separate from
passing tests.

For authenticated BandLab qualification, follow [bandlab.md](bandlab.md). Live
selectors, tempo, import and saved-state evidence still need validation in a
user-controlled session. Do not put a password in a bug report or ask an agent
to inspect authentication storage.

## Report a problem

Include version, OS/browser, sanitized workflow, error classification, last
verified step, whether input was delivered, and a synthetic reproduction. Remove
personal filenames, music, screenshots and session data. Use the
[private process](../SECURITY.md) for security reports.
