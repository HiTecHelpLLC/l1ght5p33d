# Third-party notices

OpenAdapt Flow's original source code is licensed under the MIT License in
[`LICENSE`](LICENSE). Some content in a Git checkout or GitHub-generated source
archive has a different file-local license. Those files are not relicensed
under MIT and are excluded from published PyPI wheels and source distributions.

## openIMIS distribution configuration

The following files are adapted from the openIMIS Docker distribution:

- `benchmark/openimis_claims/compose.yml`
- `benchmark/openimis_claims/conf/nginx/openimis.conf`
- `benchmark/openimis_claims/conf/nginx/locations/backend.loc`
- `benchmark/openimis_claims/conf/nginx/locations/frontend.loc`
- `benchmark/openimis_claims/conf/nginx/variables/var.conf`

Upstream:

- Repository: <https://github.com/openimis/openimis-dist_dkr>
- Exact commit:
  [`cd6220d1f0578e56a589c47953250c2ad3d0caa5`](https://github.com/openimis/openimis-dist_dkr/tree/cd6220d1f0578e56a589c47953250c2ad3d0caa5)
- Exact upstream paths: the same `conf/nginx/...` paths listed above, without
  the local `benchmark/openimis_claims/` prefix; the combined local
  `compose.yml` is adapted from `compose.base.yml`, `compose.postgresql.yml`,
  and `compose.cache.yml`
- Upstream license: GNU Affero General Public License version 3
  (`AGPL-3.0-only`)
- Complete license copy:
  [`benchmark/openimis_claims/conf/nginx/LICENSE-AGPL-3.0.md`](benchmark/openimis_claims/conf/nginx/LICENSE-AGPL-3.0.md)

OpenAdapt adapted these configuration files for the synthetic, loopback-only
openIMIS reference environment on 2026-07-17. The local environment trims the
upstream distribution to the services required by the claims-intake reference
workflow and adds digest pinning and fail-closed local bindings.

Each adapted file carries an SPDX license identifier and exact source URLs.
The adapted files remain under `AGPL-3.0-only`; the repository's MIT license
continues to cover OpenAdapt-authored code outside file-local exceptions.

Published `openadapt-flow` wheels and source distributions exclude the complete
`benchmark/openimis_claims/` surface, its launcher/test, and this repository-only
notice. The package artifacts therefore contain no copied or adapted openIMIS
material and remain under the declared MIT package license. A Git source
checkout retains the isolated benchmark and this notice for reproducible
development evidence.

## L1ght5p33d downstream dependencies

L1ght5p33d additions use MIT and retain the inherited OpenAdapt copyright.
The creator wheel/sdist contains only packages/l1ght5p33d/src, its license,
metadata and the committed lock. It does not vendor the inherited AGPL
benchmark surface, browser profiles, personal media or captured screenshots.
The GitHub source checkout retains upstream history and its file-local notices.

| Component | Pinned direct version | Declared license | Use |
| --- | --- | --- | --- |
| OpenAdapt Flow | 1.34.0 | MIT | Existing replay, IR, verification and durable recovery |
| Playwright Python | 1.62.0 | Apache-2.0 | Browser selectors, input and dedicated profiles |
| pywinauto | 0.6.9 | BSD-3-Clause | Windows UIA/Win32 |
| Mido | 1.3.3 | MIT | MIDI parsing and synthetic fixtures |
| Pydantic | 2.13.5 | MIT | Typed validation |
| jsonschema | 4.26.0 | MIT | Strict schema validation |
| MCP Python SDK | 2.1.1 | MIT | Local MCP transport |
| Uvicorn | 0.52.4 | BSD-3-Clause | Loopback HTTP service |
| HTTPX | 0.28.1 | BSD-3-Clause | Local fixture checks |
| psutil | 7.2.2 | BSD-3-Clause | Exact process identity |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | Ed25519 workflow-catalog signatures |

OpenCV, RapidOCR/ONNX Runtime, Pillow, NumPy and other transitive components
are resolved in packages/l1ght5p33d/uv.lock. Distribution-level license metadata
is inventoried in docs/third-party-inventory.json. Some separate dependencies
(including certifi and build tooling) use MPL-2.0. They are installed unmodified
from their own distributions; their licenses and source notices remain with
those distributions. The creator MIT license does not relicense dependencies
or all native libraries bundled by upstream wheels. Consult each wheel's bundled
third-party notices when redistributing a combined offline environment.

No OculiX/SikuliX, OpenRPA, Jarvisonix, unlicensed recorder code, personal music,
or third-party application code was copied into the creator package. The
packaged browser/WinForms fixtures and generated MIDI are original MIT examples.
The pinned Gitleaks executable is downloaded only for development scanning,
hash-verified, and is not distributed as part of the creator package.

Optional peer-to-peer workflow retrieval uses a separately installed
[Kubo](https://github.com/ipfs/kubo) 0.43.0 daemon (Apache-2.0 OR MIT), through its
loopback HTTP API. No Kubo executable or IPFS source is bundled. THEBEST registry
integration files under `integrations/thebest` are original MIT contributions;
they do not include the THEBEST site's existing proprietary application code.
