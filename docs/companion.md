# Use the local companion

The v0.2.0 developer preview connects an AI's workflow selection to your own
review page and local execution. The AI can find a pack, supply inputs and prepare
the plan. You decide whether those exact actions should run.

## Try the complete review flow

After the [Windows installation](../README.md#windows-quick-start), activate the
installed environment and run:

```powershell
l1ght5p33d try
```

This prepares the fixed synthetic browser poster fixture and opens a local review
page. It does not grant approval automatically. Keep the companion running while
reviewing and executing the task. The fixture demonstrates title entry, palette
selection, a declared selector fallback and saved-state verification; it does
not produce an exported poster image or operate a commercial design application.

The page starts with a task summary you can review and approve. You can expand
the complete steps to inspect actual provider operations, selectors, inputs,
effects and permissions; opening those details is optional. Author-written
descriptions are labelled separately from the executable plan. Edit variables
and regenerate the plan if the inputs need changing. The full workflow editor
saves an authored local copy, preserves the downloaded original and requires a
fresh review. That copy does not inherit the original curator signature.

Approval is explicit and single-use, bound to the exact workflow, effective
variables, policy and inspected input files. Changed inputs, steps, policy or
files invalidate the prior approval. The review flow asks the local user to
confirm; agents must not assume consent or perform that confirmation themselves.
There is no run-approval MCP method. No provider is started by merely preparing
a plan.

## Review trust boundary

The returned review URL contains a short-lived capability for that plan. An
authorized MCP client that receives it could imitate the browser's approval
POST. The server cannot establish that a human clicked the button. Human review
is the intended interaction and a rule for cooperating agents, not a
cryptographic human-presence guarantee.

The local checks reject unauthorized cross-site requests, stale plans and normal
approval replay. They do not isolate the companion from an unrestricted process
running as the same OS user, which can access local files or simulate input.
Agents must present the plan and leave confirmation to the user, including when
they can operate the local browser or terminal. Keep review URLs private.

## Let an AI prepare a task

```powershell
l1ght5p33d serve
```

The service uses managed local folders by default. Connect your MCP client using
the private session token as described in [MCP setup](mcp.md). The normal sequence
over HTTP MCP is:

1. Call `search_curated_workflows` to search the built-in THEBEST source.
2. Call `prepare_task` with its exact ID/version and any declared variables.
   The service reuses a valid cached pack or downloads the required files,
   verifies them, and returns a local review URL.
3. Open that URL and review the summary. Inspect the full steps, change inputs or
   save an authored copy when useful, then explicitly approve the resulting plan.
4. Follow `get_task_status(plan_id)` for approval, execution and verification.
   Inspect receipts or failure details when a run stops.

Preparing, searching, downloading or opening a review page never approves a run.
A workflow description is a candidate match, not proof it fulfills an ambiguous
goal. The AI should resolve missing intent before preparing consequential work.

The currently admitted example is `poster-demo`, version `0.1.0`, from source
`thebest`. The public library has one synthetic fixture entry; there is no live
BandLab pack admitted yet. `try` supplies the fixed local fixture for the first
run. Preparing another task does not invent or provision an application that its
workflow expects to exist.

`l1ght5p33d rpc` is a separate line-oriented stdin/stdout process; it does not
start an HTTP server. Its `prepare_task` response has `review_url: null` and
`review_mode: "local_terminal"`, along with the exact plan and `local_review`
arguments identifying the plan, workflow folder and state folder. The user runs
`review-run` with those arguments and the same permission policy used by the RPC
service. After local confirmation, the client can start the unchanged approved
plan. Use `serve` or `try` for the browser review flow.

## Where packs come from

The built-in source is the public
[L1ght5p33d workflow repository](https://github.com/HiTecHelpLLC/l1ght5p33d-workflows)
on GitHub. Discovery reads its `main` branch over bounded HTTPS. The index is only
an untrusted list of candidate paths. A downloaded schema or script is never
loaded as trusted code. The runtime verifies THEBEST's detached curator signature,
expiry and exact workflow, review-metadata and evidence hashes before use.

THEBEST's initial public key ships with the application and is shown in pack
provenance. Its SHA-256 fingerprint over the 32 raw public-key bytes is:

```text
14c70511c35c423f046e79c1944cdc9ca8d06442202c516a18f67d6932895c84
```

The public key is a trust choice supplied by this distribution. It is never
replaced by a key from the downloaded pack or an MCP argument. A curator
signature binds review claims to exact bytes; it neither proves tests ran nor
grants local execution permission. Author signatures, curator review and your
run approval are separate facts. The current pack has a curator attestation;
no separate upstream author signature is claimed.

The existing signed evidence covers a synthetic browser fixture run locally on
Windows 11 with the source runtime recorded in the pack. It does not certify
every v0.2.0 environment, native Windows input, live BandLab, native Linux desktop
automation or WSL GUI support. GitHub-hosted Ubuntu CI is separate evidence.

Expiry is checked again when cached content is used. The preview has no persistent
minimum-revision floor, automatic revocation service or promise of permanent
hosting. An unexpired older signed pack can still be replayed by the source.
THEBEST's website register and public P2P registry are not deployed; GitHub is
the connected public source today.

## Cache and personal files

Downloaded packs use a managed cache under the companion's local state. The
default retention is **90 days without execution**, measured from download until
the first execution and from last use afterward. Searching, reading, preparing
or reviewing a pack does not refresh last use. Actual execution does.

```powershell
l1ght5p33d serve --cache-retention-days 180
```

The supported setting is 1-3650 days. `get_cache_status` exposes retention and
cached-pack state. Active or pinned packs are protected. Modified files and
untracked content are retained rather than deleted as known downloads. Authored
workflow copies and execution receipts live outside this eviction policy and
are never expired by it. Cache retention is separate from signature validity:
keeping or pinning an expired attestation cannot make it valid.

Use `--workflows`, `--state` and `--policy` when you need explicit local locations
or an operator-reviewed permission policy. Do not place personal authored files
inside the managed download cache. Normal execution remains local and makes no
model calls; first installation and missing-pack retrieval need network access.

Operator-configured native signed catalogs and Kubo remain an advanced route.
Their imports go into the operator's workflow library, outside the managed
90-day cache. See [workflow libraries](workflow-library.md) for that separate
configuration and [troubleshooting](troubleshooting.md) for runtime failures.
