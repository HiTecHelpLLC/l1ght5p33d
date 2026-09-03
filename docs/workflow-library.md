# Build and reuse a workflow library

L1ght5p33d runs a local library of editable ASCII workflow files. Use that library
to discover an existing task, supply variables, adapt selectors or effects, and
combine compatible subflows. BandLab import, a browser poster editor and a Windows
creative fixture are reference workflows for the same general provider system.

The v0.2.0 companion discovers curated THEBEST packs from the public GitHub
workflow library, verifies detached review signatures, and downloads on demand
into a managed cache. An AI prepares the task; the user reviews its summary and
approves through the local page, with every step available to inspect or edit.
Local authored files and advanced signed
catalog/Kubo imports remain available. A hosted community register, executable
provider installation and automatic format conversion require further work.

## Prepare a reviewed public pack

Start `l1ght5p33d serve` with its managed defaults and connect your AI client.
`search_curated_workflows` finds candidate packs; `prepare_task` accepts an exact
ID/version, declared variables and `source="thebest"`. It reuses valid cached
bytes or downloads and verifies the pack, then returns a local review URL over
HTTP MCP. Line-oriented `rpc` returns the plan and local terminal-review arguments;
it does not start a web server.
`get_task_status(plan_id)` follows the review and execution outcome. Use
`l1ght5p33d try` for the fixed local poster fixture and its first review page.

The source is [the public curated GitHub repository](https://github.com/HiTecHelpLLC/l1ght5p33d-workflows),
currently with one `poster-demo@0.1.0` synthetic browser fixture. Its `main` index
is an untrusted list of candidates. The runtime's shipped THEBEST key verifies
the curator identity/role, expiry and exact workflow, review and evidence hashes.
It does not trust a key or schema downloaded with a pack. Signed qualification
scope, author provenance and local execution approval remain separate facts.
The existing signature records the older pinned runtime's Windows 11 synthetic
browser test; it makes no live BandLab or blanket v0.2.0 qualification claim.

The review page starts with a summary and provides the complete actual steps.
Changing variables creates a new plan. Editing the full workflow saves an
authored local copy, preserves the original and does not transfer the curator's
signature. Every execution needs explicit, single-use approval bound to that
plan's workflow, inputs and permissions. There is no run-approval MCP method, but
an authorized client with the review URL could imitate the local approval POST.
Agents must leave confirmation to the user. This is not a cryptographic
human-presence check; see the [review trust boundary](companion.md#review-trust-boundary).

Downloaded packs expire from the cache after 90 days without execution by
default; set `--cache-retention-days` on `serve` to 1-3650 days. Only actual
execution refreshes last use. Active, pinned, modified and untracked content is
protected, and authored copies and receipts are never expired by this cache.
Signature expiry is independent and is checked again before cached use. Inspect
`get_cache_status` for cache state. See the [companion guide](companion.md).

THEBEST's website register and public P2P registry are not deployed. The public
GitHub library is the connected source; no public pinning service is promised.

## Discover local workflows

Choose a folder containing reviewed workflow documents. After installing
L1ght5p33d, list the checked-in examples from the repository root:

```powershell
l1ght5p33d list --workflows .\examples\l1ght5p33d
```

This lists `bandlab-import`, `poster-demo` and `windows-creative`, including their
descriptions, parameters, named steps, schemas and normalized document digests.
Listing does not open an application or grant permission to execute.

To use your own library, replace the path with its local folder. The registry
examines the first 500 top-level `.json` files in sorted order. It skips invalid
or non-workflow documents, refuses duplicate workflow IDs, and ignores resolved
files outside that folder. Nested files can supply explicitly included subflows;
they are not separately discovered. If a file is missing from the list, run
`l1ght5p33d validate PATH` to see its validation error.

An AI client can call `list_workflows` and `describe_workflow` through the
[local MCP or JSON-RPC interface](mcp.md). They expose the selected local library,
not a computer-wide file search. The CLI `list` command includes descriptions;
the separate `catalog` command searches a configured signed remote register.

## Advanced: operator-configured catalogs and Kubo

For native signed catalogs, AI clients can call `search_workflow_catalog` and
`download_workflow` after the
operator starts MCP/JSON-RPC with `--discovery discovery.json`. They do the
searching; the user reviews the proposed execution, not a list of manual search
instructions. The startup configuration has this shape (replace the example
URL and key with a reviewed publisher):

```json
{
  "schema_version": "l1ght5p33d-discovery/v1",
  "registries": [
    {
      "name": "reviewed-publisher",
      "url": "https://registry.example/catalog.json",
      "public_key_hex": "REPLACE_WITH_THE_REVIEWED_64_CHARACTER_HEX_KEY"
    }
  ],
  "kubo_url": "http://127.0.0.1:5001"
}
```

These imports go into the operator's workflow library, not the companion's
managed cache, and are not subject to its 90-day retention policy.

The AI cannot change these trust roots through the control interface. Search
returns candidate metadata and individual source failures, never automatic
approval or a semantic suitability guarantee. Every ordinary run now requires
the [complete, parameter-bound human review](workflow-review.md).

Obtain the publisher's Ed25519 public key through a channel you trust and save
its 32 raw bytes as 64 hexadecimal characters in a local file. A key delivered
inside the catalog cannot establish that catalog's identity. Given a configured
catalog URL and an existing workflow folder, the commands are:

```powershell
l1ght5p33d catalog https://registry.example/catalog.json --public-key .\publisher.pub --query poster
l1ght5p33d install-workflow poster-demo --version 0.1.0 --catalog https://registry.example/catalog.json --public-key .\publisher.pub --workflows .\workflows
```

The URL and ID above are examples, not an available public service. Choose an
exact ID/version from your publisher's returned catalog. The proposed THEBEST
register needs its own deployment and operator review; this guide does not claim
that a public THEBEST endpoint is active.

Catalog requests use HTTPS, with literal loopback HTTP available for local
testing. The client verifies the signature over the exact payload bytes before
parsing its metadata, enforces expiry, and rejects unknown schema/runtime
versions. Search matches ID, title, description or application text. It does not
install code or search arbitrary websites.

Installation uses an already-running local Kubo node, by default
`http://127.0.0.1:5001`; `--kubo-url` can choose another literal loopback origin.
Kubo supplies peer discovery and transfer. L1ght5p33d calls only
[`block/get`](https://docs.ipfs.tech/reference/kubo/rpc/#api-v0-block-get), then
independently checks the downloaded bytes against the catalog's size, SHA-256
and CIDv1 raw-block address. It validates the ASCII workflow schema and matching
ID/application before writing `workflow-ID.json` with exclusive creation.
Redirects, proxies, oversized transfers, includes, symlink destinations and
overwrites are refused. The destination folder must already exist.

Catalog v1 installs a single JSON file. It does not bundle templates, music,
browser profiles or executable providers. Review any required local assets and
calibration listed by the publisher. Installing a file neither executes it nor
changes local policy. A valid signature establishes publisher identity, not
correctness, license suitability or permission to run.

The catalog carries a positive revision and expires, but the client does not yet
persist a minimum accepted revision. Operators needing rollback protection
should pin a reviewed catalog revision outside this preview. Kubo availability
and connected peers determine whether the named block can be retrieved; a CID
does not guarantee permanent hosting.

## Create and adapt a file

Copy a compatible example or write a document using the
[workflow specification](l1ght5p33d/workflow-spec.md). Export the installed version's
machine-readable schema for editor validation:

```powershell
l1ght5p33d schema --out .\workflow.schema.json
l1ght5p33d validate .\examples\l1ght5p33d\browser-poster.json
```

Use `schema_version: "l1ght5p33d/v1"` around native Flow schema v2. Give each
document a unique ID and useful description. Declare reusable input defaults in
`workflow.params`, use `{name}` in provider arguments, and keep application
identity, selectors and effect checks explicit. Save as ASCII; JSON Unicode
escapes can represent other text. Provider configuration is reviewed local data
and is not parameter-substituted in the preview.

The service currently provisions one installed provider per document: browser,
Windows or BandLab. An application-specific operation requires a provider that
implements it; describing an operation in JSON does not create that capability.
See [provider development](adapter-development.md) when existing operations are
insufficient.

Robot `.robot` files, raw OpenAdapt recordings/bundles, generated Python and other
RPA formats do not automatically run through this registry. Translate the desired
behavior into supported bindings with observable effects, validate it and review
its permissions. Keep the source license and attribution when adapting material.

## Combine compatible subflows

An `includes` map imports another workflow as a named native Flow subflow:

```json
"includes": {"prepare": "common/prepare.json"}
```

Use `workflow.program` with a `subflow_call` state naming `prepare`; use either a
program graph or linear `steps`, not both. The
[composition specification](l1ght5p33d/workflow-spec.md#conditions-loops-subflows-and-imports)
describes native branches, loops and parameter scope.

The included file must stay under the importing file's folder and have exactly
the same application and configuration. It must be self-contained without its
own subflows. Step IDs remain unique across the combined workflow. Cycles, path
escapes and conflicting names are refused. Resolved subflows enter the approval
digest, so changing an included action requires review again.

Cross-application provisioning and automatic parameter/result wiring between
arbitrary downloaded workflows are not implemented. Author the shared parameter
contract explicitly and test the composed behavior.

## Review, authorize and run

Validation checks the schema and policy; it does not prove a live selector or
outcome. Review the actual application, local file roots, selector chain and
expected effects before granting the exact document. For a workflow you have
prepared at `workflows\my-workflow.json` with a declared `title` parameter:

```powershell
l1ght5p33d validate .\workflows\my-workflow.json
l1ght5p33d approve-workflow .\workflows\my-workflow.json --policy .\policy.json
l1ght5p33d run .\workflows\my-workflow.json --policy .\policy.json --dry-run
l1ght5p33d run .\workflows\my-workflow.json --policy .\policy.json --var "title=My creation"
```

The first validation uses default browser/loopback permissions. For another
provider or origin, supply a reviewed policy with `--policy`. The local
`approve-workflow` command records the exact digest and declared application,
origins and read roots in that policy. Review those grants before invoking it.
Dry-run also requires the grant and delivers no input. Runtime values must be
declared parameters; credential variables are refused. Authenticate manually.

The illustrative example files expect their fixtures and local paths to exist.
For the guided first run, use `l1ght5p33d try`; it prepares its harmless fixture
and leaves approval to the user. `demo browser`, `demo bandlab` and `demo windows`
remain separate developer test commands with fixed synthetic content.

AI clients can set variables, propose a readable patch, monitor receipts, and
pause, step or abort runs. Executable edits need fresh local approval. In-process
resume and [reviewed durable recovery](l1ght5p33d/recovery.md) have different
requirements; interrupted or uncertain actions are not assumed successful.

## Share a reviewed workflow pack

Share ordinary files through a GitHub repository or pull request. Keep additional
metadata in a companion README; the strict workflow envelope rejects invented
fields. Include:

- A license, attribution and provenance for workflows, templates and fixtures.
- The tested L1ght5p33d release or commit, envelope/native schema versions,
  provider requirements, OS, browser channel and application version or date.
- A task description, declared variables, application assumptions, required
  file roots and calibration instructions without personal paths or credentials.
- Observable success criteria, synthetic fixture tests and their results;
  distinguish local fixture evidence from live qualification.
- Known failure states, manual checkpoints and guidance for inspecting possible
  effects before retrying an uncertain action.

Pin the reviewed revision when reusing a pack. Review changed files and
permissions before approving the new digest. Keep policies, session tokens,
profiles, personal assets, captured images and execution logs outside the shared
pack. A workflow file is reviewable data; any separately installed provider is
trusted executable code. See [security](../SECURITY.md),
[recorder and calibration](recorder-calibration.md) and the [roadmap](ROADMAP.md).
