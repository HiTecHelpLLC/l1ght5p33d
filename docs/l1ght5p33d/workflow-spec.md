# L1ght5p33d workflow specification v1

L1ght5p33d stores workflows in ASCII JSON files. The file is a small strict
envelope around the existing OpenAdapt Flow schema v2. No AI connection is
needed to parse, validate or run it. Non-ASCII application text can use JSON
Unicode escapes. Generate the complete machine schema with:

```powershell
python -X utf8 -m l1ght5p33d schema --out workflow.schema.json
```

The creation of a second workflow interpreter was deliberately avoided. Flow
already supplies graph execution, typed parameters, verification, checkpoint
integrity and governed recovery. Robot Framework was tested successfully; its
more concise syntax would require another translation and execution contract.
See [prior art](../prior-art.md) and [technical spikes](technical-spikes.md).

## Envelope and a minimal workflow

```json
{
  "schema_version": "l1ght5p33d/v1",
  "id": "creative-title",
  "description": "Set the local creative fixture title and read it back",
  "application": "browser",
  "configuration": {
    "url": "http://127.0.0.1:8765/"
  },
  "workflow": {
    "schema_version": 2,
    "name": "creative-title",
    "params": {"title": "My creation"},
    "steps": [
      {
        "id": "set-title",
        "intent": "Set the title on the verified application",
        "action": "wait",
        "api_binding": {
          "kind": "tool",
          "method": "fill",
          "url_template": "browser",
          "on_unavailable": "halt",
          "body_template": {
            "selectors": [{"kind": "role", "role": "textbox", "name": "Project title"}],
            "text": "{title}"
          },
          "effects": [
            {
              "kind": "field_equals",
              "match": {"provider": "browser"},
              "field": "project_title",
              "value": {"param": "title"},
              "timeout_s": 5
            }
          ]
        }
      }
    ]
  }
}
```

This fragment expects an application textbox named `Project title` with HTML
`name="project_title"`; use `l1ght5p33d demo browser` for the complete served
fixture. Selector and observable syntax belongs to its provider.

Required envelope fields are `id`, `application`, and `workflow`; version defaults
to `l1ght5p33d/v1`. `description`, `configuration`, and `includes` are optional.
Identifiers use lowercase letters, digits, underscores and hyphens, start with
a letter, and contain at most 64 characters. Unknown schema properties and
duplicate JSON keys are refused. Files are limited to 2 MB and include depth
to eight levels. A missing native `created_at` receives a fixed epoch value so
the same editable file always produces the same approval digest.

`action: "wait"` is the native GUI alternative placeholder. The actual operation
is the existing Flow tool binding. `on_unavailable: "halt"` makes the placeholder
unreachable: an unavailable provider cannot fall through to an invented click.
The binding requires a registered provider, registered operation and explicit
effect contract. URLs, module paths and scripts cannot be provider names.

## Parameters, selectors and verification

`workflow.params` supplies string defaults; `param_specs` provides Flow's typed
parameter declarations. The CLI accepts `--var title=Value`; the service rejects
undeclared variables. Provider arguments support `{name}` placeholders. A whole
placeholder preserves its scalar type; embedded placeholders produce text.
Attribute traversal, index access, conversions and format specifications are
refused. Configuration is explicit local environment data, not a Python program.

The preview rejects declared secret parameters and credential-like parameter
names before writing a native bundle or run. Ordinary Flow durable parameters
are plaintext, so authentication must happen manually in the application.
Do not put credentials into ordinary parameter values or configuration. Receipts
also redact secret-like fields, but redaction is not a credential store.

Effects use Flow `ValueExpr`: a bare string or `{"literal":"value"}` is a literal;
`{"param":"title"}` checks the value supplied for this run. Every provider effect
must identify the invoked provider in `match.provider`. The provider's `inspect()`
performs a fresh read; Flow's existing effect judge evaluates the result.

An operation returning successfully proves input delivery. It does not establish
that the requested state was reached. A field/count/assertion must also pass.
Effect tiers preserve their real strength:

| Tier | Evidence | What it establishes |
| --- | --- | --- |
| 1 | Independent authoritative store | Separate API, database or file read |
| 2 | Independent session | Separate read-only application session |
| 3 | Persisted state reacquisition | Different UI path reloads persisted state |
| 4 | Immediate screen | Current DOM/UIA/OCR consistency only |

Browser, Windows and live BandLab readback normally use tier 4. A Save indicator
can pass while backend persistence remains unverified. The local fixture's
independent store can provide tier 1. A successful lower-tier preview is never
reported as a production Flow `VERIFIED` transaction.

Selectors should prefer authorized application APIs, DOM roles/labels, Windows
UIA, then explicit local visual fallback. The Windows provider implements
window-scoped OCR/template fallback and guarded relative positions. It refuses
ambiguity and context changes. Do not use absolute desktop coordinates.

## Conditions, loops, subflows and imports

Use either native `workflow.steps` or `workflow.program`, not both. A program
has `entry` and `states`. Flow validates missing targets, duplicate identifiers,
state payloads, reachable terminals and unsafe unconditional cycles. The runtime
enforces loop limits and a total execution budget.

Native `branch` transitions can use `param_equals`, `and`, `or`, or `not`; visual
predicates need a real observation backend. Native `loop` states bind rows from
`data_sources` or runtime worklists and call a named `subflows` graph. A subflow
returns at its success terminal; row parameters are scoped by the existing
interpreter. The provider action receipt is structured output available in the
execution log. Arbitrary assignment from that receipt into new workflow variables
is not exposed in the preview; declare effects and worklist inputs explicitly.

`includes` maps a local subflow name to a relative workflow file:

```json
"includes": {"prepare": "common/prepare.json"}
```

The included file must remain under the importing workflow's folder, match its
application and configuration, and be self-contained. Linear imported steps are
lifted using Flow's existing `lift_to_program`. A `subflow_call` state refers to
the include name. Resolved subflows enter the exact approval digest. Path escapes,
include cycles, duplicate names and implicit application changes are rejected.

The service currently instantiates one application provider per workflow. Flow
supports multi-surface composition, but an arbitrary multi-application creator
workflow is not yet automatically provisioned by the local service.

## Timeouts, retries, cleanup and approval

Provider selector waits and declared effect timeouts are bounded. Retry selector
resolution before input only; never repeat an import or save after uncertain
delivery. A known before-delivery refusal differs from an exception after input
may have begun. Failed effects halt the run and leave review evidence.

Use Flow exception handlers for ordinary recoverable failures. Safety halts and
control cancellation cannot be routed to a success terminal. The service always
closes its provider on exit. Compensation/rollback requires an application-specific
verified operation; the preview does not claim it can undo arbitrary user edits.
Deletion, publishing, purchases, shell execution and account/social operations
are unavailable through the normal creator provider surface.

`run --dry-run` validates schemas and permission policy without input. It cannot
prove a live selector exists. Step mode, pause and resume work through the local
service. A pause takes effect at the next action boundary; the active action
finishes verification. A step permit runs exactly one action and pauses again.
Abort is terminal for that run and is never presented as success.

Every workflow, including a localhost fixture, requires a local operator grant
for its exact digest. AI patches are proposed as text, validated, diffed and
preserved alongside the original. All executable changes, including selectors,
effects and defaults, and application/configuration changes need new local
approval. A metadata-only change can inherit approval from an already approved
original; it cannot approve previously unapproved actions. An AI cannot add
filesystem roots or register new executable code through a workflow.

## Durable recovery

Flow writes sealed bundle/checkpoint identities and effect evidence. The service
stores these under its local run directory, outside Git. MCP `resume_workflow`
resumes an in-process pause; it does not restart a halted run after a crash.

Reviewed durable recovery is available through the Python SDK. This is an
operator/developer integration surface: reconstruct the **same authorized**
providers, inspect the exact pending pause and live state, then issue an approval
and pass it through Flow's existing gate. Do not use the upstream CLI alone for
creator workflows; it cannot reconstruct the L1ght5p33d provider registry.

```python
from openadapt_flow.runtime.durable.approval import issue_resume_approval
from openadapt_flow.runtime.durable.checkpoint import CheckpointStore
from openadapt_flow.runtime.durable.program_checkpoint import bundle_version
from l1ght5p33d.runtime import resume_from_checkpoint

# flow_dir is the original run's flow/ directory. fresh_replayer contains the
# reviewed provider registry, ToolActuator, ProviderVerifier and current policy.
store = CheckpointStore(flow_dir)
manifest = store.read_manifest()
pending = store.read_pending()
approval = issue_resume_approval(
    pending,
    approver=operator_identity,
    resolution=reviewed_resolution,
    bundle_version=bundle_version(manifest.bundle_dir),
    run_id=manifest.run_id,
    workflow_name=manifest.workflow_name,
    run_dir=flow_dir,
)
report = resume_from_checkpoint(flow_dir, fresh_replayer, approval=approval)
```

Approval is bound to the exact bundle, run, pending pause and inputs. Flow re-reads
previously verified effects before executing another action. A changed bundle,
divergent effect, expired pause, uncertain delivery, rejected run or absent
checkpoint is refused. A hard process loss without a native pending pause requires
manual reconciliation; automatic crash reconstruction is a roadmap item. Do not
edit checkpoint files or call `resume_from` directly.

Windows processes must run in UTF-8 mode (`python -X utf8 ...` or `PYTHONUTF8=1`)
for the pinned Flow 1.34 checkpoint reader. See the reproduced compatibility issue
in [technical spikes](technical-spikes.md) and the full [recovery guide](recovery.md).
