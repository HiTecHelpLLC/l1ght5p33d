# Operate a workflow register

THEBEST can register public workflow metadata while IPFS peers distribute exact
versions. The client and default-disabled PHP integration are implemented; no
production THEBEST register or public seed service is activated by installation.
The [architecture decision](adr/0002-thebest-register-and-p2p.md) explains the
existing projects reused and the preview's trust/availability limits.

## Author and review

Create a standalone ASCII workflow using the [library guide](workflow-library.md).
Run its fixture or authorized live qualification, and record precisely which
environment passed. Remove personal paths, content and authentication state.
Keep local calibration outside the shared artifact. Catalog v1 accepts one
workflow JSON up to 1 MB, without includes, templates or executable plugins.

The following commands run in the source checkout with its development virtual
environment activated. They do not invoke an AI or change an application.

```powershell
python scripts/workflow-catalog.py entry --workflow examples/l1ght5p33d/browser-poster.json --version 0.1.0 --license MIT --title "Browser poster example" --compatibility "fixture=bundled poster editor" --verification-level fixture --verification-description "Synthetic browser fixture; configure its URL before local approval" --reviewed --out entry.json
```

The entry pins the file's exact bytes. Its license and verification description
are reviewed publisher declarations, not automatically certified facts. Combine
one or more entries into a JSON array saved as `entries.json`. For one entry:

```powershell
python -c "import json; json.dump([json.load(open('entry.json'))], open('entries.json', 'w'), ensure_ascii=True)"
```

## Sign the register

Use an existing private directory outside all Git checkouts and the web root.
The key generator refuses overwrite and restricts the private file to the current
Windows user before writing key bytes. On POSIX it uses mode 0600.

```powershell
python scripts/workflow-catalog.py keygen --private-out C:/WorkflowKeys/register.key
python scripts/workflow-catalog.py sign --entries entries.json --key C:/WorkflowKeys/register.key --revision 1 --expires-days 7 --out catalog.json
```

The `.key` file contains private key material and stays offline. Only the
`public_key_hex` printed by keygen belongs in clients' public-key files and the
server configuration. Publish that public key through an independently trusted
channel. The client does not accept a replacement key advertised by the catalog
it is trying to verify. Sign a new catalog revision before expiry. Persistent
rollback protection, revocations and automated key rotation are future work.

## Make the artifact available

Install [Kubo 0.43.0](https://github.com/ipfs/kubo/releases/tag/v0.43.0) separately,
review its peer-network configuration, and run an operator-managed node whose
administration API stays on loopback. Explicitly seed only the reviewed file:

```powershell
python scripts/workflow-catalog.py seed --workflow examples/l1ght5p33d/browser-poster.json --reviewed --kubo-url http://127.0.0.1:5001
```

This pins the raw block and checks the CID returned by Kubo. Keep at least one
approved seed online; independent pins improve availability. P2P does not
guarantee permanence or secrecy, and peers may retain copies after delisting.
No personal screen captures, music, profiles or credentials should be seeded.
The first protocol has no automatic public upload or background daemon startup.

## Serve metadata from THEBEST

The portable original PHP route is in [integrations/thebest](../integrations/thebest).
It requires PHP 8.2+ with sodium, an outside-webroot signed catalog file, the
public key and an explicit enable flag. It serves exact signed bytes through
`GET /api/workflows/`; it does not store private signing keys, accept anonymous
submissions, meter executions or access users' computers.

Install and configure that reviewed integration using THEBEST's deployment
process. The site's local instructions require specific go-live authorization
before adding public routes. Until then it remains a local draft. No default
catalog URL is silently enabled in the L1ght5p33d client.

After a register is live, use the signed `catalog` and `install-workflow` commands
in the [consumer guide](workflow-library.md#discover-and-download-shared-files).
Downloading installs an inactive file. Adapt it to the local environment,
validate it, approve the exact workflow and then explicitly run it.

## Repeat the real transfer test

With a reviewed Kubo executable available:

```powershell
python scripts/qualify-p2p.py --kubo C:/Tools/Kubo/ipfs.exe
```

The qualification creates two temporary loopback peers with public discovery
disabled, proves the receiver initially lacks the block, transfers a synthetic
workflow, checks its signed identity and bytes, and stops both owned daemons.
It does not execute the workflow or qualify public-internet peer reachability.
Windows/Linux CI runs the same transport proof and the PHP catalog contract tests.
