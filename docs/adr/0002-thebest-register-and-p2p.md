# ADR 0002: THEBEST workflow register with optional Kubo distribution

Date: 2026-09-03. Status: accepted for an opt-in developer preview; production
THEBEST activation and public seed availability require operator deployment.

## Context and prior art

The product is a general library for creating, finding, adapting, composing and
running OpenAdapt-based computer workflows. BandLab is its first reference,
not a constraint on the catalog. The user offered THEBEST as a register for
workflows distributed peer to peer. Existing creator stores and OpenAdapt's
capture sharing are acknowledged in [the current research](../research/registry-p2p.md).
Targeted research did not identify an existing public OpenAdapt catalog matching
this complete design; this is not a claim to invent workflow sharing.

## Decision

THEBEST serves a signed, versioned metadata index. The open-source L1ght5p33d
client discovers entries there and retrieves exact content through an operator's
local [Kubo daemon](https://docs.ipfs.tech/reference/kubo/rpc/). OpenAdapt Flow
remains the execution engine. We do not implement a new P2P protocol, remote
execution service, cryptocurrency, payment mechanism or mandatory cloud runner.

The first protocol distributes one standalone ASCII workflow JSON per entry.
Its SHA-256, CIDv1 raw-block identity, size, schema, runtime version, application,
license, compatibility notes and verification level are signed together. This
deliberately excludes executable plugins, archives, local templates and includes
until package-dependency and evidence handling are separately specified.

The client pins an Ed25519 public key explicitly chosen by the operator. It
verifies the signature and expiry before trusting metadata, fetches only a
bounded block from a literal loopback Kubo endpoint, recomputes the digest/CID,
validates the workflow and installs without overwriting any existing workflow.
Download grants no execution authority. Existing exact-workflow approvals still
apply, and changing application/configuration requires a new local grant.

THEBEST's endpoint serves an operator-reviewed signed catalog. Its initial
publication process is file-based; there are no anonymous upload endpoints or
automatic acceptance of publisher claims. A future author submission/moderation
UI can use the same protocol. Other registries can implement the open contract.

## Consequences

- THEBEST is a central discovery and moderation register; the file transport is
  decentralized. This is not a fully decentralized trust system.
- [IPFS content requires pinning](https://docs.ipfs.tech/concepts/persistence/)
  on available peers. P2P alone does not guarantee continued availability.
- [IPFS is public](https://docs.ipfs.tech/concepts/privacy-and-encryption/).
  Participants may expose requested CIDs and network addresses, and downloaded
  blocks may be cached/served by their daemon. Only intentionally public
  workflow files belong there; credentials, profiles and captures stay local.
- Signatures authenticate the selected register and bytes, not a workflow's
  safety or fitness for a user's environment. Verification levels remain
  explicit, including fixture-only evidence.
- Existing local files remain runnable without THEBEST, IPFS or an AI provider.
  A missing peer, expired index, unsupported runtime, or invalid signature fails
  the download; it does not silently select another version or grant permission.
- Production hosting, signer key custody/rotation, signed revocations, ongoing
  pinning and author governance remain operational requirements before a public
  network launch. The preview uses bounded signed expiry and exact version
  selection, and does not claim a complete software-update trust framework.

## Evidence

Unit tests exercise signature tampering, expiry, malformed metadata, wrong
hashes, unsafe paths and overwrite attempts. A separate two-node Kubo
qualification transfers a synthetic workflow over a loopback peer connection;
it tests actual block exchange without advertising private material publicly.
The THEBEST PHP route is default-disabled and tested with temporary signer keys.
See the release notes for the exact candidate's results.
