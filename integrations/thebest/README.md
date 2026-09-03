# Signed workflow registry draft

This endpoint is a local draft and is disabled by default. No server setting,
marketplace listing, navigation, submission route, account flow or economy code
is changed. Deployment and live activation require a separate operator decision.

`GET /api/workflows/` and `HEAD /api/workflows/` can serve a complete curated
L1ght5p33d catalog. The directory index works with the existing local PHP router.
With no enable flag, every method returns `404`. Enabled mutation methods return
`405`. An enabled but missing, expired, malformed or unverifiable catalog returns
a generic `503` response without paths, key material or parser details.

## Operator configuration

Only configure these values after reviewing the exact catalog and deciding to
activate this route. The implementation reads process environment variables or
constants already defined by the host; it does not load account/economy settings.

| Setting | Contract |
| --- | --- |
| `THEBEST_WORKFLOW_REGISTRY_ENABLED` | `1` or `true` explicitly enables serving; otherwise disabled |
| `THEBEST_WORKFLOW_CATALOG` | Absolute path to an existing catalog file **outside the public web root** |
| `THEBEST_WORKFLOW_REGISTRY_PUBLIC_KEY` | 64 hexadecimal characters representing the pinned 32-byte Ed25519 public key |

PHP sodium must be enabled. Keep the signing private key offline; this web route
needs only the public key. Publish a reviewed catalog by atomically replacing its
private file. Do not place catalog files, signing keys or captured workflow state
under the web root. No key, catalog or activation setting is provided here.

## Wire contract

The file is at most 2,000,000 bytes and contains exactly:

```json
{"payload_b64":"<canonical standard base64>","signature_b64":"<canonical standard base64>"}
```

The detached Ed25519 signature covers the **decoded payload bytes**, not a
reformatted JSON object. Its decoded length is 64 bytes. The ASCII JSON payload
contains exactly `schema_version`, `revision`, `generated_at`, `expires_at` and
`workflows`. Version is `l1ght5p33d-catalog/v1`; revision is a positive integer.
Dates use UTC `YYYY-MM-DDTHH:MM:SS[.fraction]Z` or `+00:00`, with up to six fraction
digits. Expiry must be later than generation and the current time; generation
may be no more than five minutes ahead of the server clock.

There are at most 500 entries, unique by `(id, version)`. Each entry contains:

| Field | Contract |
| --- | --- |
| `id`, `application` | Lowercase identifier matching `[a-z][a-z0-9_-]{0,63}` |
| `version` | Standard SemVer, at most 80 characters |
| `title`, `description` | Title 1–200, description 0–4000 Unicode characters |
| `workflow_schema`, `runtime_version` | `l1ght5p33d/v1` and `1.34.0` |
| `license` | Reviewed license declaration, 1–100 characters |
| `sha256` | 64 lowercase hexadecimal characters |
| `cid` | CIDv1 lowercase base32, raw codec, sha2-256; must encode exactly `sha256` |
| `size_bytes` | Integer from 1 through 1,000,000 |
| `compatibility` | Object with at most 32 string entries; keys 1–64 and values 0–200 characters |
| `verification` | Exactly `level` (`fixture`, `local` or `live`) and `description` (1–4000 characters) |

Unknown structured fields and duplicate JSON keys, including escaped duplicates,
are rejected in both the envelope and payload. Descriptive verification claims remain
operator assertions; the registry does not run or certify workflows. The client
retrieves the exact CID from its local Kubo node, checks bytes/hash/size and
requires separate local workflow permission approval. The index contains no
artifact URLs, arbitrary server file paths or executable snippets.

Successful GET returns the original file bytes unchanged. HEAD returns the same
headers and Content-Length with no body. Responses use `Cache-Control: no-store`;
queries do not filter/re-sign the payload. Clients filter the verified index
locally and pin their own trusted key. The preview checks expiry and installs an
explicit workflow version, but does not persist a monotonic catalog revision
counter. A still-valid older signed index can therefore be replayed. Full rollback
protection and revocation are not implemented; expiry and exact version selection
are the current limits.

## Local verification

```powershell
php -l api/workflows/_catalog.php
php -l api/workflows/index.php
php -l tests/workflow-registry.php
php tests/workflow-registry.php
```

Tests create temporary synthetic keys and catalog bytes outside the repository,
then remove the file. They cover signature tampering, canonical base64, expiry,
clock skew, schema, duplicate entries, CID/hash agreement, private path bounds,
disabled behavior, GET/HEAD parity, mutation refusal and unchanged query results.
If a Windows PHP install has sodium present but disabled, enable its installed
`php_sodium.dll` for that test process with PHP's `-d extension=...` option. Do not
change production configuration to make a local test pass.

The expected preview health endpoint is `http://localhost:3001/api/status`.
No deployment or live activation is performed by these tests.

## Attribution

This original integration is Copyright (c) 2026 L1ght5p33d contributors and is
provided under the MIT license. It does not include unrelated THE BEST site code.
