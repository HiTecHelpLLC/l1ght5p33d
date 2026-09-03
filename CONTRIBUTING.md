# Contributing to L1ght5p33d

L1ght5p33d extends OpenAdapt Flow with a local creative-automation package.
Prefer small, verified operations and reuse the native workflow runtime. Claims
should name the tested environment and distinguish fixtures, UI readback,
independent outcomes and pending live validation.

## Development

Use Python 3.12. The application and dependency lock are under
`packages/l1ght5p33d`; upstream source/history remain at repository root. With
`uv` installed, run from the application directory:

```powershell
cd packages/l1ght5p33d
uv sync --frozen --all-extras
uv run --frozen python -m playwright install chromium
uv run --frozen python -m ruff check src tests
uv run --frozen python -m ruff format --check src tests
uv run --frozen python -m mypy
uv run --frozen python -m pytest tests -q
```

The native Windows test requires an unlocked interactive desktop and an explicit
flag; see [docs/windows.md](docs/windows.md). Authentication for live apps is
manual. A skipped native/live test is not a passing qualification.

## Changes and tests

- Use descriptive Conventional Commit subjects and sign off with `git commit -s`.
  Do not claim authorship of code you did not write or have a right to contribute.
- Explain behavior, validation and material limitations in pull requests.
- Test changes, especially identity, policy, ambiguity, uncertain delivery and
  effect verification.
- Generate files in temporary directories. Never regenerate fixtures into
  tracked paths during tests. Synthetic music/UI fixtures need clear provenance.
- Do not weaken checks to make a failing workflow appear successful. Add a human
  checkpoint when an effect cannot be observed reliably.

Workflow contributions should include application compatibility, their license,
synthetic tests and observable success criteria. See the
[workflow library guide](docs/workflow-library.md),
[provider development](docs/adapter-development.md) and the
[roadmap](docs/ROADMAP.md) for extension guidance.

## License and package boundary

New contributions use the repository's MIT license. Preserve upstream copyright,
license and attribution. Do not copy unlicensed or incompatible snippets. Update
third-party notices and dependency review when adding components.

Do not ship AGPL benchmark files in a wheel or source distribution. Retained
upstream reference environments are not part of the L1ght5p33d package. Do not
copy, adapt, vendor, embed or redistribute GPL, AGPL, LGPL, SSPL,
source-available or field-of-use-restricted material in those artifacts without
the reviewed approval required by the inherited package-boundary instructions.
Running an external app is separate from redistributing its code.

Build and inspect both application archives from repository root:

```powershell
uv build --project packages/l1ght5p33d --out-dir dist/l1ght5p33d
python scripts/l1ght5p33d_package_check.py dist/l1ght5p33d
```

Keep dependency, license and secret scanning enabled. Publish only the candidate
that passed required checks.

The [original upstream guide](docs/upstream/CONTRIBUTING.md) is preserved for
provenance and upstream work. Its corporate CLA and upstream release process
are not newly imposed by a L1ght5p33d pull request. Existing file-local notices
and non-negotiable package exclusions still apply.

## Community

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities through
[SECURITY.md](SECURITY.md), not a public reproduction. L1ght5p33d and its
integrations are [unofficial](docs/trademark-disclaimer.md).
