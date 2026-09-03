# Inspected recovery of a halted workflow

Pause and resume through MCP control the current service process. A paused run
finishes its active action and verification before waiting at the next boundary.
`run_step` grants one action. `abort_workflow` is terminal; it never resumes or
changes a previously completed result into an aborted one.

After a selector failure or application change, inspect the JSONL receipts,
native Flow report and application state. Input delivery, effect verification
and persistence verification are separate facts. An uncertain MIDI import must
not be retried until the operator knows whether the track already exists.

The service records native durable state under
`%LOCALAPPDATA%\L1ght5p33d\runs\<run-id>\flow`. Its sealed workflow bundle is in
the adjacent `bundle` folder. Keep this local state outside Git: even without
credential parameters it contains project titles, file paths and other workflow
data. Credential/secret parameters are refused in this preview; authentication
takes place manually in the dedicated application profile.

## Native SDK continuation

The preview exposes an operator/developer recovery function, not an unattended
crash restart command. Create a fresh authorized provider registry with exactly
the same application, account/session and observable contracts. Check the current
policy's exact workflow digest approval and filesystem/origin grants. Inspect
the pending pause and reconcile any delivered action before issuing an approval.

Run the following in UTF-8 mode (`python -X utf8 recovery_script.py`). The variables
`flow_dir`, `providers`, `policy`, `operator_identity` and `reviewed_resolution`
must be supplied from the reviewed local run. Provider construction depends on
the application; see its adapter guide. Do not accept these values from an
untrusted workflow or remote MCP argument.

```python
from openadapt_flow.runtime.durable.approval import issue_resume_approval
from openadapt_flow.runtime.durable.checkpoint import CheckpointStore
from openadapt_flow.runtime.durable.program_checkpoint import bundle_version

from l1ght5p33d.providers.base import ProviderVerifier, ToolActuator
from l1ght5p33d.runtime import ControlledReplayer, resume_from_checkpoint

store = CheckpointStore(flow_dir)
manifest = store.read_manifest()
pending = store.read_pending()
if pending is None:
    raise RuntimeError("No native pending pause; reconcile this run manually")

# Inspect the pending pause, receipts and each provider's fresh inspect() result
# here. A named operator must resolve the specific failure before this call.
approval = issue_resume_approval(
    pending,
    approver=operator_identity,
    resolution=reviewed_resolution,
    bundle_version=bundle_version(manifest.bundle_dir),
    run_id=manifest.run_id,
    workflow_name=manifest.workflow_name,
    run_dir=flow_dir,
)
replayer = ControlledReplayer(
    api_actuator=ToolActuator(providers, policy_check=policy.action),
    effect_verifier=ProviderVerifier(providers),
    durable=True,
)
try:
    report = resume_from_checkpoint(flow_dir, replayer, approval=approval)
    print(report.model_dump_json(indent=2))
finally:
    for provider in providers.values():
        provider.close()
```

Flow binds the approval to the exact run, bundle, pending pause and inputs and
rechecks previously verified effects before another action. A changed bundle,
divergent effect or unapproved continuation fails closed. Do not edit checkpoint
files, bypass the approval gate, call `resume_from` with an integer index or use
the upstream CLI by itself: it cannot reconstruct L1ght5p33d's provider registry.

The test `test_native_durable_resume_requires_approval_and_revalidates` exercises
this exact gate with a separate file-backed fixture. One action succeeds, the
second is refused before input, an unapproved resume fails, then a reviewed resume
finishes the second action. There are exactly two deliveries, so the completed
first action is not repeated.

A hard process loss without a native pending pause requires manual reconciliation.
Automatic reconstruction after such a crash and a guided recovery UI remain
roadmap work. Every final managed receipt reports whether its verified native
checkpoint was actually found; an in-progress receipt marks checkpoint creation
as pending rather than claiming persistence before the engine writes it.
