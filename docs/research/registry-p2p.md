# Public workflow registry and P2P distribution research

Checked 2026-09-03 after the user proposed THEBEST as a register for workflows
distributed over a peer-to-peer network. This is research and a proposed
integration boundary. No registry, P2P client or THEBEST site change is
implemented by this document.

## What the search established

Targeted GitHub repository searches for `openadapt registry` and
`openadapt workflow sharing` each returned zero matches. Web queries included
`site:github.com/OpenAdaptAI workflow registry sharing P2P IPFS`,
`site:github.com "openadapt-flow" "registry"`, and
`site:github.com "openadapt" "peer-to-peer"`. Source inspection covered Flow,
Agent distribution documentation, Capture's sharing implementation, and Desktop's
design document. No matching public catalog of downloadable, compiled OpenAdapt
workflows with P2P distribution was found in those searches. This is not proof
that no such service exists, and does not mean OpenAdapt lacks sharing.

Additional authenticated GitHub searches returned zero repositories for
`"openadapt" "P2P"`, zero code results for `"ipfs"` inside
`OpenAdaptAI/openadapt-flow`, and eight `"registry"` code results inside
`OpenAdaptAI/openadapt-agent`. The relevant Agent results describe package/MCP
distribution. Counts reflect search indexing and query scope, not an exhaustive
audit of all branches or every OpenAdapt deployment.

Existing capabilities include:

- [OpenAdapt Agent distribution](https://github.com/OpenAdaptAI/openadapt-agent/blob/main/docs/DISTRIBUTION.md)
  distinguishes its public MCP server package from operator-owned bundles.
  Registry listings advertise the capability; private workflow bundles stay in
  a launch-time local directory. The document explicitly scopes Agent to a local
  single-user bridge, separate from the proprietary hosted control plane.
- [OpenAdapt Flow](https://github.com/OpenAdaptAI/openadapt-flow) already provides
  optional hosted authentication, sanitized-artifact review, governed bundle
  ingest and break reporting through `app.openadapt.ai`. This is relevant hosted
  sharing infrastructure, although the inspected interface did not establish a
  public P2P community catalog. Reuse Flow's bundle validation and reviewed
  artifact boundaries rather than designing another execution format.
- [OpenAdapt Capture share.py](https://github.com/OpenAdaptAI/openadapt-capture/blob/main/openadapt_capture/share.py)
  implements `capture share send/receive`: zip a recording directory and invoke
  Magic Wormhole for transfer. This is real ad-hoc transfer code, not a public
  workflow index. It also installs a missing transfer dependency and extracts
  received archives; it is not a ready-made restricted package importer to
  expose through this project's narrow MCP interface.
- [OpenAdapt Desktop DESIGN](https://github.com/OpenAdaptAI/openadapt-desktop/blob/main/DESIGN.md)
  identifies that existing Magic Wormhole support and discusses IPFS among
  proposed storage backends. Its design proposals do not demonstrate a deployed
  public compiled-workflow network.

## Reuse mature distribution components

[IPFS Kubo](https://github.com/ipfs/kubo) is an active Go implementation with
Windows support, local CLI/RPC, peer discovery, content-addressed retrieval and
pinning. Metadata showed a push on 2026-09-03 and
[v0.43.0](https://github.com/ipfs/kubo/releases/tag/v0.43.0) released 2026-08-03.
Its [license](https://github.com/ipfs/kubo/blob/master/LICENSE) describes a
transition: earlier contributions can be MIT-only, while newer contributions
are dual MIT/Apache-2.0. Do not mislabel the whole history Apache-only. Prefer a
separately installed, version-pinned node with verified release checksums;
review notices if bundling binaries later.

Kubo can retrieve and verify the blocks identified by a CID. At least one
reachable provider must keep the content available; a CID alone does not host
anything. Pinning retains data, so availability needs an explicit seed/pinning
plan. These are transport guarantees, not proof of safe workflow behavior,
publisher identity, licensing or application compatibility.
[Kubo installation](https://docs.ipfs.tech/install/command-line/),
[data lifecycle](https://docs.ipfs.tech/concepts/lifecycle/).

[Magic Wormhole](https://github.com/magic-wormhole/magic-wormhole), MIT, is useful
for direct person-to-person exchange and already reused by OpenAdapt Capture.
It uses a mailbox service and optionally a transit relay; it is not a persistent
searchable catalog or a guarantee of serverless direct connectivity.

## Proposed THEBEST boundary

THEBEST could provide an opt-in searchable register of public package metadata:
author, source, license, version, supported engine/adapters, declared permissions,
content CID/digest, and reviewed qualification evidence. A separate local client
could retrieve the exact package through Kubo, validate its manifest and archive
boundaries, show the workflow and permission diff, and require local approval
before execution. Downloading must not install code, run workflows or expand
permissions implicitly. This is a proposed design, not a completed capability.

Keep version entries immutable. A newer catalog entry must not silently replace
an approved local workflow. Signatures bind a publisher to bytes; they do not
make the bytes safe. Catalog removal or revocation can block new local admissions
without promising deletion of copies held by independent peers.

Public IPFS encrypts transport, not stored content, and exposes provider/CID
metadata. Only intentionally public, reviewed packages belong there. Personal
recordings, profiles, screenshots, secrets and private production files must
remain local by default. A running Kubo node may reprovide retrieved content;
the client must make network participation explicit. Its administrative RPC
endpoint must remain private, separate from any public retrieval gateway.
[Privacy model](https://docs.ipfs.tech/concepts/privacy-and-encryption/),
[gateway and RPC separation](https://docs.ipfs.tech/how-to/replace-public-gateways-with-self-hosted-ipfs/).

Recommendation: extend the existing OpenAdapt-based project with a separately
reviewed package/catalog layer and mature transport if this scope proceeds.
THEBEST can be the initial register without changing the local-first runner into
a mandatory hosted service. Do not build a new P2P protocol or describe existing
capture transfer, hosted ingest, or community workflow sharing as nonexistent.
