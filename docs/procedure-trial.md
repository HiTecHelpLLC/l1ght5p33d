# Poster procedure effectiveness trial

This procedure uses the installed OpenAdapt Flow runtime through L1ght5p33d's
normal service and browser provider. The application is our synthetic local
Poster Studio fixture, not a qualified third-party creative application.

## Procedure

1. Review the exact workflow and variables. Automated tests simulate this
   approval; normal usage still requires the local operator's approval.
2. Fill **Poster title** using its accessible label.
3. Select **Sunset** using the **Palette** label.
4. Click Save using the declared semantic selector chain. The fixture deliberately
   lacks the old button label, so the second selector must succeed.
5. Verify each field and the saved status through structured UI readback.
6. Independently check the application's backend state. Close the browser and
   fixture, then read the saved JSON and SVG to prove the data survived shutdown.

The editable ASCII workflow is generated from `examples.browser_workflow` into
each test's `workflows/poster.json`. Its loopback URL belongs to that test session;
rerunning the procedure generates a fresh URL. No screenshot or external model
is needed. The fixture writes only to the output directory supplied by the test
operator. Ordinary fixture use remains in memory unless that directory is set.

## Repeat the trial

After the developer installation in CONTRIBUTING.md, from
`packages/l1ght5p33d`:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_procedure_trial.py -q -s
```

Pytest prints timings and keeps each test's workflow, `measurement.json`, saved
poster files, and service receipts under its temporary directory. To choose an
artifact location, pass `--basetemp` with a NEW dedicated test directory: pytest
clears an existing directory at that location. Never use a personal asset folder.

## September 17, 2026 local Windows trial

| Attempt | Execution including browser startup | Total including fixture and verification |
| --- | ---: | ---: |
| 1 | 8.801 s | 9.788 s |
| 2 | 1.719 s | 2.533 s |
| 3 | 1.642 s | 2.464 s |

All nine steps were verified; all three runs used the declared fallback and
passed independent disk verification. An invalid-save test also passed: the
fixture returned an error without producing a saved artifact. Four tests passed
in 19.50 seconds. These are three observations, not a latency guarantee or an
AI-versus-robot benchmark. First-launch overhead needs separate measurement;
human approval time is excluded. No Linux certification or live BandLab result
is implied.

## Dependency PR review

At review time both open dependency PRs had failing checks and were left unmerged:

- [PR 9](https://github.com/HiTecHelpLLC/l1ght5p33d/pull/9): changes six exact
  version pins without changing `uv.lock`. The package check also hardcodes
  `openadapt-flow==1.34.0`, producing a misleading exact-pin error for the new
  version. Regenerate the lock, qualify the new foundation version, and update
  the expected package metadata together. A locked CI consistency check would
  prevent testing old dependencies while building metadata for new ones.
- [PR 6](https://github.com/HiTecHelpLLC/l1ght5p33d/pull/6): the Windows browser
  persistence test encountered `PermissionError` reading `DevToolsActivePort`.
  The startup poll currently reads that file without catching transient sharing
  errors. A bounded retry within the existing startup deadline, with a regression
  test for a temporarily locked file, is the proposed fix. This trial does not
  claim the PR is repaired or its action updates are qualified.
