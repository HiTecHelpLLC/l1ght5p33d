# Discover, review, approve, execute

The AI does the searching. It starts with installed workflows and configured
signed catalogs, checks candidates against the user's stated outcome, and stages
an exact version without executing it. A title, description or signature is not
proof that the workflow does the requested task. Unknown goals, target projects,
production choices or side effects require clarification.

For example, "make a song" does not authorize uploading it to YouTube. Public
Suno templates sometimes include publication, external generation services and
fixed musical defaults. A BandLab prototype may choose the first matching
instrument. These behaviors must be inspected in the executable steps.

## Before every normal run

1. The AI identifies the intended result and supplies declared variables.
2. `prepare_workflow_run` builds a deterministic plan from the actual workflow.
   It lists effective defaults, application/window/browser settings, startup and
   cleanup, every action, arguments, selectors, expected effects and control
   paths. Author descriptions are marked untrusted. Declared file inputs and
   local visual templates are hashed.
3. The AI presents the full plan to the user. Branches are not falsely presented
   as one certain execution path. This preview blocks unresolved action/effect
   values, including dynamic scopes that the planner cannot fully expand.
4. The local user runs the review command below, reads the plan, and types
   `APPROVE`. Cancellation, EOF and noninteractive input grant no approval.
5. The AI calls `run_workflow` with that plan ID. The service rechecks workflow,
   effective values, policy, provider settings and file hashes before it opens
   an application. The approval expires after 15 minutes and is consumed once.
6. Inputs are checked again before file actions. Changed content stops the run.
   Normal pause/resume stays inside the same frozen run. A changed plan needs
   another review; durable halted-run recovery keeps its separate native gates.

```powershell
l1ght5p33d review-run PLAN_ID --workflows C:\Workflows --policy C:\Workflows\policy.json
```

Use `--state DIRECTORY` only when the service was created with a non-default
local state directory. The review command does not start the workflow. A direct
`l1ght5p33d run FILE --var name=value --policy FILE` displays and confirms the
same plan interactively, then runs it. `run --dry-run` produces the complete plan
without needing a previous workflow approval or opening an application.

MCP and JSON-RPC have no run-approval method. AI clients must never invoke the
local approval commands, answer the prompt, or write approval files on behalf
of the user. Plan approval is separate from the application's capability policy.
If new roots, origins or providers are needed, `approve-workflow` displays that
proposed grant and requires confirmation before saving the policy. Patch review
regenerates the actual diff before confirmation.

## Limits and trust boundary

The numbered preview is followed by complete structured details. It is a local
terminal review, not yet an integrated chat approval button or graphical review
panel. The client should explain the actions in plain language without omitting
the complete machine-derived plan. This is not a guarantee that an author wrote
a sufficiently clear description or that natural-language intent can be inferred.

The operator's OS account owns policy, workflow and approval files. An
unrestricted process running as that same user can tamper with the program or
simulate terminal input. The local gate separates the restricted MCP client
from approval; it is not cryptographic proof of human presence against a
compromised local account. Digests detect stale/corrupted review content and
single-use claims prevent normal concurrent replay of an approval.

Built-in `demo` commands and automated tests explicitly authorize only their own
generated synthetic fixtures. There is no downloaded-workflow flag that bypasses
review by claiming to be a fixture. The library may contain foreign-runtime
references, but automatic conversion or arbitrary provider installation is not
implemented. Live application qualification is still separate from passing a
local fixture test.
