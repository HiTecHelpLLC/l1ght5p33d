# Architecture spikes and retained limits

Research and tests were run on 2026-09-03. These are scoped observations, not a
claim that upstream platforms or an authenticated BandLab session were all
qualified. The project fork preserves the upstream Git history; the separately
installable creator package pins the published `openadapt-flow==1.34.0` wheel.

## Candidate comparison

1. Robot Framework 7.4.2: `TestSuite.from_file_system` parsed an ASCII `.robot`
   variable/FOR/assertion example. Real execution and dry run each passed one
   test with return code 0. Robot is a viable language. It would still require
   building effect-aware durable governance already available in Flow.
2. Flow source 1.35.0 at the fork base: upstream
   `tests/test_replayer_api_actuator.py` passed **25 tests in 24.83 seconds**.
   This exercised real local API writes, independent effects, refusal and
   response-loss handling with no generative-model call.
3. Creator extension on the published 1.34.0 wheel: **36 focused tests passed in
   7.76 seconds** under Python 3.12 on Windows with UTF-8 mode. Import location
   was checked under the isolated package virtual environment's `site-packages`,
   so this result did not accidentally test the source checkout instead.

The 36 tests cover ASCII and native schema validation, unknown/duplicate keys,
safe include resolution, stable digests, graph validation, native branch/loop/
subflow execution, run parameter effects, real file-backed state verification,
receipt persistence and checkpoint reconciliation, credential rejection before
durable persistence, exact single stepping, pause/resume,
abort, failed effect refusal, delivery uncertainty, tier-4 evidence labels and
authenticated durable recovery without repeating a completed action. They also
exercise the real local Chromium fixture, a post-verification snapshot failure,
persisted patch review, exact executable approval and metadata approval boundaries.

The durable recovery test writes one verified fixture change, encounters a
before-input refusal on the second, rebuilds a replayer against the same store,
refuses an unapproved resume, then admits a named operator approval and completes
the second operation. The total delivery count is two, not three. This is a
real test of the native continuation gate, not an integer-index restart.

Reproduce from the creator package directory:

```powershell
python -X utf8 -m pytest tests/test_runtime.py tests/test_workflow.py tests/test_service.py -q
```

## Two discovered upstream compatibility issues

### Parameter-only graph decisions requested screenshots

Flow 1.34 `_select_transition` requested a settled frame even when every guard
only compared parameters. `_predicate_holds` also decoded a PNG viewport that
its parameter evaluator never consumed. A tool-only backend correctly refused
to invent a screenshot, exposing this path.

`ControlledReplayer` has a bounded compatibility shim: only when the upstream
`predicate_uses_frame` determination says **no visual evidence is needed**, it
supplies no image and delegates to the same native predicate evaluator and
transition interpreter. Frame evidence remains absent. Visual guards retain the
full real backend path. No custom branch/loop interpreter was introduced.

### Windows checkpoint decoding followed the system ANSI code page

The published checkpoint reader uses `Path.read_text()` without an explicit
encoding. During native resume, a UTF-8 smart quote written by upstream caused a
cp1252 `UnicodeDecodeError` on this machine. Re-running the identical tests with
`python -X utf8` resolved it. Windows launchers and CI must start Python in UTF-8
mode. No persisted evidence, signature or authorization gate was modified to
make the test pass.

## Evidence boundary

Fixture system-of-record reads prove only that fixture's state. The ordinary
browser, Windows and live BandLab providers normally return immediate UI
consistency (tier 4). They cannot assert remote persistence from a green Save
indicator. BandLab's authenticated live validation remains separately documented.

MCP pause/resume controls an active service process. A native halted checkpoint
can be recovered through the reviewed SDK recipe in the workflow specification.
An intentional abort stays terminal. Unexpected process death without a native
pending pause has no automatic recovery command and requires reconciliation.
Provider-specific compensation, broader recorder refinement and universal
cross-application provisioning remain explicit roadmap work.
