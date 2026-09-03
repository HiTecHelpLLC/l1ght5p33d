# Local control interfaces

The official MCP Python SDK supplies JSON schema and Streamable HTTP.
`l1ght5p33d serve` uses managed local folders and binds MCP only to
`127.0.0.1:7331/mcp`. Optional `--workflows DIR`, `--state DIR` and `--policy FILE`
select operator-managed locations. `--cache-retention-days` accepts 1-3650 days
(default 90). MCP requests require `Authorization: Bearer TOKEN`.
Read the private token file reported by the CLI into your client configuration;
never share it. `L1GHT5P33D_SESSION_TOKEN` can supply a token instead (minimum
32 characters). Host and Origin must identify the loopback server. No wildcard
CORS is enabled. This trusted local service must not be proxied publicly.

| Tool | Arguments / behavior |
| --- | --- |
| search_curated_workflows | `query`, optional `application`; signature-verified THEBEST review candidates |
| search_workflow_catalog | `query`, optional `application`/`limit`; operator-configured native catalog candidates |
| prepare_task | `workflow_id`, exact `version`, optional `variables`, `source="thebest"`; verify/download or reuse pack; return plan plus HTTP review URL or RPC terminal-review arguments |
| get_task_status | `plan_id`; review, approval, execution and verification status |
| get_cache_status | Managed download inventory and retention; no eviction or execution grant |
| download_workflow | `registry_name`, `workflow_id`, exact `version`; inactive staging, no grant |
| prepare_workflow_run | `workflow_id`; full current-input review plan, no application startup |
| get_run_plan | `plan_id`; complete plan and local approval state |
| list_workflows | Validated registered IDs, descriptions, parameters and steps |
| describe_workflow | `workflow_id`; metadata and digest |
| validate_workflow | `workflow_id`; schema and policy |
| inspect_environment | Runtime and allowed providers; no account inspection |
| inspect_ui_state | `run_id`; structured state at last completed action boundary |
| set_workflow_variables | `workflow_id`, declared string `variables` |
| run_workflow | `workflow_id`, optional `step_mode`/`dry_run`, approved `plan_id`; missing plan prepares review instead of running |
| run_step | `run_id`; one action permit |
| pause_workflow | `run_id`; current verification finishes before pausing |
| resume_workflow | `run_id`; in-process pause only |
| abort_workflow | `run_id`; terminal cancellation, no thread kill |
| get_execution_status | `run_id`; lifecycle, counts, error |
| get_execution_log | `run_id`, `offset`, `limit` (1-200) |
| explain_failure | `run_id`; evidence and recovery direction |
| propose_workflow_patch | `workflow_id`, ASCII JSON `content`; validated readable diff |
| approve_workflow_patch | `patch_id`; no permission expansion; executable changes need local approval |

Snapshots include timestamps/freshness, never screenshots, cookies or credentials.
Registry tools accept IDs rather than arbitrary file paths. Includes remain in
the workflow folder. Proposals preserve originals and become stale when the
original digest changes. No tool can expand filesystem or application policy.
The built-in `thebest` source consumes curator-signed packs from the public
L1ght5p33d GitHub workflow library. The initial key ships with the application;
verified provenance exposes that trust choice, exact hashes, expiry and qualified
test scope. The library currently contains only the synthetic poster fixture.
`prepare_task` never approves or executes it. Over HTTP MCP, return its review URL
to the user and use `get_task_status` to follow the result; do not interpret
silence as consent. Line-oriented RPC uses terminal review as described below.

Add `--discovery discovery.json` to `serve` or `rpc` for advanced native catalogs.
The local startup file supplies trusted registry names, URLs and Ed25519 keys;
MCP accepts no new trust roots, URLs or destination paths. Downloads use the
existing bounded Kubo client and fixed operator workflow folder, with provenance
receipts. These native catalog imports are outside the managed download cache.
Search is literal candidate matching, not a guarantee that the workflow matches
the user's intent. The AI must inspect actual steps and clarify ambiguity.
See the [workflow library](workflow-library.md) and [human review contract](workflow-review.md).

There is no `approve_run_plan` MCP/JSON-RPC method. A local human reviews the
plan through the companion page or `review-run`. The page shows a summary that
can be approved directly, with optional complete-step details, editable variables
and a full workflow editor that saves a separate authored copy. Copies preserve
the source and do
not inherit its curator signature. Only the unchanged, explicitly approved,
single-use plan can execute. Setting variables, changing a workflow or policy, or changing
an input file invalidates the previous plan. Calling `run_workflow` without an
approved plan cannot create a provider or send input.

The HTTP review URL contains a short-lived per-plan capability. An authorized
MCP client that receives this URL could imitate the browser's approval POST;
the server does not prove a human was present. Agents must not submit that
confirmation or invoke terminal approval on the user's behalf. The review flow
and cooperating-client rule protect intended user consent, while origin checks,
plan binding and single-use claims reject unauthorized cross-site requests,
stale plans and normal replay. This is not isolation from an unrestricted
process running as the same OS user. Keep the review capability private.

Example MCP tool arguments for the admitted fixture (the local poster application
must be available; `l1ght5p33d try` prepares it for the guided first run):

```json
{"workflow_id":"poster-demo","version":"0.1.0","variables":{"title":"My poster"},"source":"thebest"}
```

Actual execution refreshes cached-pack last use. Search, plan preparation,
review and status calls do not. Active, pinned, modified or untracked content is
protected from expiry; authored copies and receipts are outside the cache policy.
See the [companion guide](companion.md) for source trust and cache details.

`l1ght5p33d rpc --workflows DIR --policy FILE` exposes the same method allowlist
as newline-delimited JSON-RPC 2.0 over stdin/stdout:

```json
{"jsonrpc":"2.0","id":1,"method":"list_workflows","params":{}}
```

This RPC process does not start HTTP or serve the review page. Its `prepare_task`
response includes `review_url: null`, `review_mode: "local_terminal"`, the complete
plan and `local_review` arguments for the plan ID, workflow root and state root.
The local user invokes `review-run` with those returned arguments and the same
policy used by the RPC service. For example:

```powershell
l1ght5p33d review-run PLAN_ID --workflows WORKFLOW_ROOT --state STATE_ROOT --policy POLICY_FILE
```

Use the returned paths, not a different checkout or state folder. If the RPC
service uses its default policy, omit `--policy` in the review command too.
After confirmation, call `run_workflow` with the unchanged approved `plan_id`.
Use HTTP `serve` or `try` when a browser review page is desired.

The process must stay alive for active runs. Local OS process access authorizes
this direct CLI interface; the session token applies to HTTP. JSON-RPC excludes
the `local_operator` approval argument. Native durable recovery requires an exact
pending checkpoint, fresh providers and operator-reviewed `ApprovalRecord`; see
[workflow specification](l1ght5p33d/workflow-spec.md#durable-recovery).
