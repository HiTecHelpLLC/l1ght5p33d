# Local control interfaces

The official MCP Python SDK supplies JSON schema and Streamable HTTP.
`l1ght5p33d serve --workflows DIR --policy FILE` binds only to
`127.0.0.1:7331/mcp`. Every HTTP method requires `Authorization: Bearer TOKEN`.
Read the private token file reported by the CLI into your client configuration;
never share it. `L1GHT5P33D_SESSION_TOKEN` can supply a token instead (minimum
32 characters). Host and Origin must identify the loopback server. No wildcard
CORS is enabled. This trusted local service must not be proxied publicly.

| Tool | Arguments / behavior |
| --- | --- |
| search_workflow_catalog | `query`, optional `application`/`limit`; candidates from operator-pinned catalogs |
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
Add `--discovery discovery.json` to `serve` or `rpc` for signed remote discovery.
The local startup file supplies trusted registry names, URLs and Ed25519 keys;
MCP accepts no new trust roots, URLs or destination paths. Downloads use the
existing bounded Kubo client and fixed workflow folder, with provenance receipts.
Search is literal candidate matching, not a guarantee that the workflow matches
the user's intent. The AI must inspect actual steps and clarify ambiguity.
See the [workflow library](workflow-library.md) and [human review contract](workflow-review.md).

There is no `approve_run_plan` MCP/JSON-RPC method. A local human reviews the
complete plan with `review-run`, then the client can start that unchanged,
single-use plan. Setting variables, changing a workflow or policy, or changing
an input file invalidates the previous plan. Calling `run_workflow` without an
approved plan cannot create a provider or send input.

`l1ght5p33d rpc --workflows DIR --policy FILE` exposes the same method allowlist
as newline-delimited JSON-RPC 2.0 over stdin/stdout:

```json
{"jsonrpc":"2.0","id":1,"method":"list_workflows","params":{}}
```

The process must stay alive for active runs. Local OS process access authorizes
this direct CLI interface; the session token applies to HTTP. JSON-RPC excludes
the `local_operator` approval argument. Native durable recovery requires an exact
pending checkpoint, fresh providers and operator-reviewed `ApprovalRecord`; see
[workflow specification](l1ght5p33d/workflow-spec.md#durable-recovery).
