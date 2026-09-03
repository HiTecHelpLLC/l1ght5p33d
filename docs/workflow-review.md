# Discover, review, approve, execute

The AI does the searching. It starts with installed workflows, THEBEST's curated
GitHub packs and configured signed catalogs, checks candidates against the user's
stated outcome, and stages an exact version without executing it. A title,
description or signature is not
proof that the workflow does the requested task. Unknown goals, target projects,
production choices or side effects require clarification.

For example, "make a song" does not authorize uploading it to YouTube. Public
Suno templates sometimes include publication, external generation services and
fixed musical defaults. A BandLab prototype may choose the first matching
instrument. These behaviors must be inspected in the executable steps.

## Before every normal run

1. The AI identifies the intended result and supplies declared variables.
2. `prepare_task` fetches or reuses an exact reviewed pack and prepares it;
   `prepare_workflow_run` prepares an already registered workflow. Both build a
   deterministic plan from the actual workflow.
   It lists effective defaults, application/window/browser settings, startup and
   cleanup, every action, arguments, selectors, expected effects and control
   paths. Author descriptions are marked untrusted. Declared file inputs and
   local visual templates are hashed.
3. Over HTTP MCP, the AI opens the returned local review URL for the user. The
   page starts with a summary and exposes the complete steps and structured plan.
   Branches are not falsely presented as one certain execution path. This preview
   blocks unresolved action/effect values, including dynamic scopes that the
   planner cannot fully expand. Variable edits create a fresh plan; full workflow
   edits save an authored copy without the original curator signature.
4. The user reviews the summary, optionally inspects or edits the complete steps,
   and explicitly confirms through the page, or runs the terminal command below
   and types `APPROVE`. Agents must not perform this confirmation on the user's
   behalf. Merely viewing the plan grants
   nothing. Terminal cancellation, EOF and noninteractive input grant no approval.
5. The page starts the confirmed plan, or after terminal review the AI calls
   `run_workflow` with that plan ID. The service rechecks workflow,
   effective values, policy, provider settings and file hashes before it opens
   an application. The approval expires after 15 minutes and is consumed once.
6. Inputs are checked again before file actions. Changed content stops the run.
   Normal pause/resume stays inside the same frozen run. A changed plan needs
   another review; durable halted-run recovery keeps its separate native gates.

```powershell
l1ght5p33d review-run PLAN_ID --workflows C:\Workflows --policy C:\Workflows\policy.json
```

Use `--state DIRECTORY` only when the service was created with a non-default
local state directory, and use the same permission policy as the service. The
review command does not start the workflow. A direct
`l1ght5p33d run FILE --var name=value --policy FILE` displays and confirms the
same plan interactively, then runs it. `run --dry-run` produces the complete plan
without needing a previous workflow approval or opening an application.

MCP and JSON-RPC have no run-approval method. AI clients must never invoke the
local approval commands, answer the prompt, submit the browser approval POST or
write approval files on behalf of the user. Plan approval is separate from the
application's capability policy.
If new roots, origins or providers are needed, `approve-workflow` displays that
proposed grant and requires confirmation before saving the policy. Patch review
regenerates the actual diff before confirmation.

`l1ght5p33d rpc` is a stdin/stdout process and does not start a review web server.
Its `prepare_task` result includes `review_url: null`,
`review_mode: "local_terminal"`, the complete plan and `local_review` arguments
for `review-run`. Use the returned plan ID, workflow root and state root with
the same policy as the RPC process. No browser review capability remains active
for that RPC response. `serve` and `try` provide the HTTP browser-review path.

## Limits and trust boundary

The browser page and terminal preview expose complete structured details. The
client should explain the actions in plain language without omitting the actual
plan. This does not guarantee that an author wrote a sufficiently clear
description or that natural-language intent can be inferred.

The HTTP review URL contains a short-lived per-plan capability. An authorized
MCP client that receives it could imitate the browser's approval POST. The
server cannot prove that a human clicked the button. Leaving confirmation to
the user is the intended review interaction and a rule for cooperating agents.

The operator's OS account owns policy, workflow and approval files. An
unrestricted process running as that user can tamper with the program or simulate
input. This is not an isolation or cryptographic human-presence boundary.
Host/Origin and capability checks reject unauthorized cross-site requests;
digests detect stale or changed plans, and single-use claims prevent normal
concurrent replay of an approval. Review URLs should remain private.

Built-in `demo` commands and automated tests explicitly authorize only their own
generated synthetic fixtures. There is no downloaded-workflow flag that bypasses
review by claiming to be a fixture. The library may contain foreign-runtime
references, but automatic conversion or arbitrary provider installation is not
implemented. Live application qualification is still separate from passing a
local fixture test.
