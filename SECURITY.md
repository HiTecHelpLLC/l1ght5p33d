# L1ght5p33d security policy

L1ght5p33d controls local applications with the permissions of the user who
runs it. Installed Python providers are trusted code; the registry is a
restricted action interface, not an operating-system sandbox.

## Report privately

Do not post exploit details, credentials, session data, personal music or private
screenshots in public issues. Use
[GitHub private vulnerability reporting](https://github.com/HiTecHelpLLC/l1ght5p33d/security/advisories/new).
If unavailable, open an issue requesting a private contact without describing
the vulnerability. Include affected versions, impact, and a minimal synthetic
reproduction through the private channel.

Maintainers will assess reports and coordinate remediation and credit. There
is no guaranteed response-time service level. The supported security target is
the latest L1ght5p33d developer preview; there is no long-term-support branch.

## Managed execution boundary

- MCP binds to loopback, requires a session token, checks Host/Origin, and limits
  request bodies. Do not expose it through a remote proxy or share its token.
- Local JSON-RPC relies on access to the launched process as its capability.
- Registry workflows use schema-validated, named provider operations. Arbitrary
  shell execution, JavaScript evaluation, Python imports and unrestricted file
  access are not workflow commands.
- Executable workflows require approval of their exact digest in local policy.
  CLI demos grant only their generated harmless fixture documents. AI patch
  proposals cannot expand policy or self-authorize a changed document.
- Authentication is manual. The preview refuses credential variables in the
  managed interface. Do not put passwords or API keys in workflow files.
- Local image matching and OCR do not send screenshots to an external service.
  Structured UI text can contain private information; review receipts before
  sharing them.
- Ambiguous targets, changed identity and uncertain delivery halt. UI readback
  differs from independently confirmed persistence. Skipped or interrupted work
  must not be represented as success.

In-scope reports include permission bypass, unauthorized file/profile access,
credential disclosure, screenshot egress, origin/identity bypass, unsafe retry,
incorrect success claims and vulnerabilities in shipped dependencies.

## Data and supply chain

Keep session tokens, browser profiles, calibration images, credentials and
personal assets outside Git. Logs and workflow copies live locally and may
contain filenames or application text. Protect that directory with normal OS
permissions; local-first does not mean encrypted storage by default.

Dependencies are pinned and checked in CI. Inspect the actual wheel and source
archive before release. Do not ship copied AGPL benchmark material or other
incompatible third-party files in permissively licensed package artifacts.
Retaining upstream references/history does not waive those boundaries.

Shared catalogs use an operator-pinned Ed25519 key and expiry checks. A signature
establishes who signed the bytes, not whether the workflow is safe or correctly
licensed. The client verifies a Kubo raw block's CID, SHA-256 and size, validates
the workflow, and refuses overwrite. Installation never grants execution
permission. Provider code is not downloaded through this single-file mechanism.
No persistent minimum catalog revision is stored yet; an unexpired older signed
catalog can still be accepted. See the [workflow library](docs/workflow-library.md).

The original [upstream security policy](docs/upstream/SECURITY.md) is preserved
for provenance. Its reporting address and product-specific guarantees are not
L1ght5p33d's support channel or guarantees.
