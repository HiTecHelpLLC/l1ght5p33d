"""Reject incompatible or unknown distribution-level license declarations."""

import json
import sys

ALLOWED = {
    "3-Clause BSD License",
    "Apache Software License",
    "Apache-2.0",
    "Apache-2.0 OR BSD-2-Clause",
    "Apache-2.0 OR BSD-3-Clause",
    "BSD License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
    "DFSG approved; MIT License",
    "MIT",
    "MIT AND PSF-2.0",
    "MIT License",
    "MIT-0",
    "MIT-CMU",
    "MPL-2.0",
    "MPL-2.0 AND MIT",
    "Mozilla Public License 2.0 (MPL 2.0)",
    "PSF-2.0",
    "Python Software Foundation License",
    "ISC",
    "ISC License (ISCL)",
}

with open(sys.argv[1], encoding="utf-8-sig") as handle:
    rows = json.load(handle)
if not isinstance(rows, list) or not rows:
    raise SystemExit("License inventory must contain installed distributions")
bad = [row["Name"] for row in rows if row.get("License") not in ALLOWED]
if bad:
    raise SystemExit("License review required: " + ", ".join(bad))
print(
    f"Reviewed declarations: {len(rows)} distributions; no unknown/GPL/SSPL declarations"
)
