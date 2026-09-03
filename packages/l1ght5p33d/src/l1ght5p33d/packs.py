"""Read-only curated packs, with detached THEBEST review verification.

Trust is deliberately shipped with the application and displayed in provenance.
A curator signature is a review claim, never permission to execute. No downloaded
code, dependency, command, template, or arbitrary URL is executed or followed.

The embedded entry schema and attestation checks derive from the MIT-licensed
HiTecHelpLLC/l1ght5p33d-workflows at 0759faca55e5ae79194e08f6c472a197644eabde:
schemas/entry.schema.json and scripts/attest.py.
Copyright (c) 2026 OpenAdapt.AI (MLDSAI Inc.)
Copyright (c) 2026 L1ght5p33d contributors (downstream additions)
The project's MIT LICENSE preserves the license and permission notice.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator

from l1ght5p33d.registry import RegistryError, _decode_base64, _download, _json_object
from l1ght5p33d.workflow import validate_document

LIBRARY_REPOSITORY = "https://github.com/HiTecHelpLLC/l1ght5p33d-workflows"
LIBRARY_REF = "main"
LIBRARY_BASE_URL = (
    "https://raw.githubusercontent.com/HiTecHelpLLC/l1ght5p33d-workflows/"
    + LIBRARY_REF
    + "/"
)
THEBEST_PUBLIC_KEY_HEX = (
    "800696f2b323bc64efc1a44c1220f64cf420aef73e1fe1631a720c7e75831a93"
)
MAX_WORKFLOW_BYTES = 65_536
MAX_METADATA_BYTES = 131_072
MAX_EVIDENCE_BYTES = 65_536
MAX_ATTESTATION_BYTES = 32_768
MAX_INDEX_BYTES = 65_536
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_ARTIFACTS = ("workflow", "metadata", "evidence")

# Exact published schema, embedded rather than trusting a downloaded schema.
_ENTRY_SCHEMA = json.loads(r"""{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/HiTecHelpLLC/l1ght5p33d-workflows/schemas/entry.schema.json",
  "title": "Reviewed local creation workflow",
  "type": "object",
  "properties": {
    "schema_version": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "const": "l1ght5p33d-curated-entry/v1"
    },
    "id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "pattern": "[a-z][a-z0-9_-]{0,63}"
    },
    "version": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "pattern": "[0-9]+\\.[0-9]+\\.[0-9]+"
    },
    "title": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000
    },
    "summary": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000
    },
    "status": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "enum": [
        "fixture-qualified"
      ]
    },
    "workflow": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "pattern": "workflows/[a-z][a-z0-9-]*\\.json"
    },
    "sha256": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "pattern": "[0-9a-f]{64}"
    },
    "license": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000,
      "const": "MIT"
    },
    "runtime": {
      "type": "object",
      "properties": {
        "project": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "l1ght5p33d"
        },
        "version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "0.1.0"
        },
        "commit": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "pattern": "[0-9a-f]{40}"
        },
        "flow_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "1.34.0"
        }
      },
      "required": [
        "project",
        "version",
        "commit",
        "flow_version"
      ],
      "additionalProperties": false
    },
    "provenance": {
      "type": "object",
      "properties": {
        "source_repository": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "https://github.com/HiTecHelpLLC/l1ght5p33d"
        },
        "source_commit": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "pattern": "[0-9a-f]{40}"
        },
        "source_path": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "copyright": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000
          },
          "minItems": 1,
          "maxItems": 20
        },
        "modifications": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        }
      },
      "required": [
        "source_repository",
        "source_commit",
        "source_path",
        "copyright",
        "modifications"
      ],
      "additionalProperties": false
    },
    "application": {
      "type": "object",
      "properties": {
        "provider": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "browser"
        },
        "fixture": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "l1ght5p33d.fixtures.creative"
        },
        "configuration": {
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "minLength": 1,
              "maxLength": 4000,
              "const": "http://127.0.0.1:7332"
            },
            "title_pattern": {
              "type": "string",
              "minLength": 1,
              "maxLength": 4000,
              "const": "L1ght5p33d Poster Studio"
            },
            "headless": {
              "type": "boolean",
              "const": true
            }
          },
          "required": [
            "url",
            "title_pattern",
            "headless"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "provider",
        "fixture",
        "configuration"
      ],
      "additionalProperties": false
    },
    "defaults": {
      "type": "object",
      "properties": {
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        }
      },
      "required": [
        "title"
      ],
      "additionalProperties": false
    },
    "test_scope": {
      "type": "object",
      "properties": {
        "kind": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "local-browser-fixture"
        },
        "command": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "const": "python scripts/qualify_browser.py --synthetic-fixture-only"
        },
        "runtime_commit": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000,
          "pattern": "[0-9a-f]{40}"
        },
        "environment_substitutions": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000
          },
          "minItems": 1,
          "maxItems": 20
        },
        "checks": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000
          },
          "minItems": 1,
          "maxItems": 20
        },
        "limitations": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000
          },
          "minItems": 1,
          "maxItems": 20
        }
      },
      "required": [
        "kind",
        "command",
        "runtime_commit",
        "environment_substitutions",
        "checks",
        "limitations"
      ],
      "additionalProperties": false
    },
    "explicit_local_approval_required": {
      "type": "boolean",
      "const": true
    },
    "reviewed_steps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "pattern": "[a-z][a-z0-9_-]{0,63}"
          },
          "intent": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000
          },
          "provider": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "const": "browser"
          },
          "operation": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "enum": [
              "fill",
              "select",
              "click"
            ]
          },
          "arguments": {
            "type": "object",
            "properties": {
              "selectors": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "kind": {
                      "type": "string",
                      "minLength": 1,
                      "maxLength": 4000,
                      "enum": [
                        "label",
                        "role"
                      ]
                    },
                    "name": {
                      "type": "string",
                      "minLength": 1,
                      "maxLength": 4000
                    },
                    "role": {
                      "type": "string",
                      "minLength": 1,
                      "maxLength": 4000,
                      "enum": [
                        "button"
                      ]
                    }
                  },
                  "required": [
                    "kind",
                    "name"
                  ],
                  "additionalProperties": false
                },
                "minItems": 1,
                "maxItems": 5
              },
              "text": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4000
              },
              "label": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4000
              }
            },
            "required": [
              "selectors"
            ],
            "additionalProperties": false
          },
          "effects": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "kind": {
                  "type": "string",
                  "minLength": 1,
                  "maxLength": 4000,
                  "const": "field_equals"
                },
                "match": {
                  "type": "object",
                  "properties": {
                    "provider": {
                      "type": "string",
                      "minLength": 1,
                      "maxLength": 4000,
                      "const": "browser"
                    }
                  },
                  "required": [
                    "provider"
                  ],
                  "additionalProperties": false
                },
                "field": {
                  "type": "string",
                  "minLength": 1,
                  "maxLength": 4000
                },
                "value": {
                  "anyOf": [
                    {
                      "type": "string",
                      "maxLength": 4000
                    },
                    {
                      "type": "object",
                      "required": [
                        "param"
                      ],
                      "properties": {
                        "param": {
                          "type": "string",
                          "pattern": "[a-zA-Z_][a-zA-Z0-9_]*",
                          "maxLength": 64
                        }
                      },
                      "additionalProperties": false
                    }
                  ]
                },
                "timeout_s": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 3
                }
              },
              "required": [
                "kind",
                "match",
                "field",
                "value",
                "timeout_s"
              ],
              "additionalProperties": false
            },
            "minItems": 1,
            "maxItems": 5
          }
        },
        "required": [
          "id",
          "intent",
          "provider",
          "operation",
          "arguments",
          "effects"
        ],
        "additionalProperties": false
      },
      "minItems": 1,
      "maxItems": 20
    }
  },
  "required": [
    "schema_version",
    "id",
    "version",
    "title",
    "summary",
    "status",
    "workflow",
    "sha256",
    "license",
    "runtime",
    "provenance",
    "application",
    "defaults",
    "test_scope",
    "explicit_local_approval_required",
    "reviewed_steps"
  ],
  "additionalProperties": false
}""")
_ENTRY_VALIDATOR = Draft202012Validator(_ENTRY_SCHEMA)


class PackError(RegistryError):
    """Curated content failed transport, schema, signature or review coherence."""


@dataclass(frozen=True)
class ReviewedPack:
    workflow_id: str
    version: str
    workflow_bytes: bytes
    metadata_bytes: bytes
    evidence_bytes: bytes
    attestation_bytes: bytes
    metadata_path: str
    workflow_sha256: str
    pack_digest: str
    metadata: dict[str, Any]
    evidence: dict[str, Any]
    claims: dict[str, Any]
    provenance: dict[str, Any]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _object(raw: bytes, limit: int) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= limit:
        raise PackError("Curated JSON input is empty or exceeds its byte limit")
    try:
        return _json_object(raw)
    except (RegistryError, ValueError) as exc:
        raise PackError("Invalid curated ASCII JSON object") from exc


def _closed(value: Any, fields: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != fields:
        raise PackError(label + " has unknown or missing fields")


def _text(value: Any, limit: int, label: str) -> str:
    if (
        type(value) is not str
        or not 0 < len(value) <= limit
        or not value.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise PackError("Invalid " + label)
    return value


def _path(value: Any) -> str:
    name = _text(value, 240, "repository path")
    reserved = {"con", "prn", "aux", "nul", "clock$"} | {
        f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
    }
    if any(
        part in {"", ".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9._-]+", part)
        or part.endswith(".")
        or part.split(".", 1)[0].casefold() in reserved
        for part in name.split("/")
    ):
        raise PackError("Only canonical repository-relative paths are allowed")
    return name


def _time(value: Any) -> datetime:
    value = _text(value, 20, "UTC timestamp")
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
    ):
        raise PackError("Attestation timestamp must be UTC with seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise PackError("Invalid attestation calendar timestamp") from exc


def _verified_claims(raw: bytes, now: datetime | None) -> dict[str, Any]:
    envelope = _object(raw, MAX_ATTESTATION_BYTES)
    _closed(
        envelope,
        {"schema_version", "algorithm", "payload_b64", "signature_b64"},
        "Attestation envelope",
    )
    if (
        envelope["schema_version"] != "l1ght5p33d-attestation/v1"
        or envelope["algorithm"] != "Ed25519"
    ):
        raise PackError("Unsupported attestation schema or algorithm")
    try:
        payload = _decode_base64(_text(envelope["payload_b64"], 22_000, "payload"))
        signature = _decode_base64(_text(envelope["signature_b64"], 88, "signature"))
        if len(signature) != 64:
            raise PackError("Invalid Ed25519 signature size")
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(THEBEST_PUBLIC_KEY_HEX)
        ).verify(signature, payload)
    except (RegistryError, ValueError, InvalidSignature) as exc:
        raise PackError(
            "Attestation signature does not match shipped THEBEST trust"
        ) from exc
    claims = _object(payload, 16_000)
    if _canonical(claims) != payload:
        raise PackError("Signed claims must be canonical JSON")
    _closed(
        claims,
        {
            "schema_version",
            "identity",
            "role",
            "issued_at",
            "expires_at",
            "qualification",
        }
        | set(_ARTIFACTS),
        "Attestation claims",
    )
    if claims["schema_version"] != "l1ght5p33d-attestation-claims/v1":
        raise PackError("Unsupported attestation claims schema")
    if claims["identity"] != "thebest" or claims["role"] != "curator":
        raise PackError("THEBEST curator role and identity are required")
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        raise PackError("Verification time must be timezone-aware")
    issued, expires = _time(claims["issued_at"]), _time(claims["expires_at"])
    if issued > clock + timedelta(minutes=5) or expires <= clock or expires <= issued:
        raise PackError("Attestation is expired or has invalid issuance times")
    paths = []
    for kind in _ARTIFACTS:
        artifact = claims[kind]
        _closed(artifact, {"path", "sha256"}, kind)
        paths.append(_path(artifact["path"]))
        if not _SHA256.fullmatch(_text(artifact["sha256"], 64, "SHA-256")):
            raise PackError("Invalid attested SHA-256")
    if len(set(paths)) != len(paths):
        raise PackError("Attested workflow, metadata and evidence must be distinct")
    qualification = claims["qualification"]
    _closed(qualification, {"scope", "environment", "source_commit"}, "Qualification")
    _text(qualification["scope"], 400, "qualification scope")
    if not _COMMIT.fullmatch(
        _text(qualification["source_commit"], 40, "source commit")
    ):
        raise PackError("Qualification must bind a full source commit")
    environment = qualification["environment"]
    if type(environment) is not dict or not 1 <= len(environment) <= 16:
        raise PackError("Qualification environment must have 1 to 16 named fields")
    for name, value in environment.items():
        if not _IDENTIFIER.fullmatch(_text(name, 64, "environment property")):
            raise PackError("Invalid environment property")
        _text(value, 500, "environment value")
    return claims


def _check_hash(raw: bytes, claim: dict[str, str], label: str) -> None:
    if hashlib.sha256(raw).hexdigest() != claim["sha256"]:
        raise PackError(label + " SHA-256 does not match signed claim")


def _review(
    metadata_bytes: bytes,
    evidence_bytes: bytes,
    claims: dict[str, Any],
    metadata_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if _path(metadata_path) != claims["metadata"]["path"]:
        raise PackError("Signed metadata path does not match requested entry")
    metadata = _object(metadata_bytes, MAX_METADATA_BYTES)
    evidence = _object(evidence_bytes, MAX_EVIDENCE_BYTES)
    _check_hash(metadata_bytes, claims["metadata"], "Metadata")
    _check_hash(evidence_bytes, claims["evidence"], "Evidence")
    errors = list(_ENTRY_VALIDATOR.iter_errors(metadata))
    if errors:
        raise PackError(
            "Curated metadata does not match the published closed entry schema"
        )
    if (
        metadata["workflow"] != claims["workflow"]["path"]
        or metadata["sha256"] != claims["workflow"]["sha256"]
    ):
        raise PackError("Metadata workflow identity differs from signed claim")
    commit = metadata["runtime"]["commit"]
    if any(
        value != commit
        for value in (
            metadata["provenance"]["source_commit"],
            metadata["test_scope"]["runtime_commit"],
            claims["qualification"]["source_commit"],
        )
    ):
        raise PackError("Source/runtime commits disagree with the signed qualification")
    _path(metadata["provenance"]["source_path"])
    _closed(
        evidence,
        {
            "status",
            "purpose",
            "source_sha256",
            "runtime",
            "environment",
            "steps_verified",
            "semantic_fallback_verified",
            "independent_saved_state_verified",
            "model_calls",
            "user_workflow_approval_granted",
        },
        "Fixture evidence",
    )
    _text(evidence["purpose"], 4000, "evidence purpose")
    if (
        evidence["status"] != "fixture_qualified"
        or evidence["source_sha256"] != metadata["sha256"]
        or evidence["runtime"] != metadata["runtime"]
        or evidence["environment"] != claims["qualification"]["environment"]
        or type(evidence["steps_verified"]) is not int
        or evidence["steps_verified"] != len(metadata["reviewed_steps"])
        or evidence["semantic_fallback_verified"] is not True
        or evidence["independent_saved_state_verified"] is not True
        or type(evidence["model_calls"]) is not int
        or evidence["model_calls"] != 0
        or evidence["user_workflow_approval_granted"] is not False
    ):
        raise PackError(
            "Fixture evidence disagrees with reviewed workflow or qualification"
        )
    return metadata, evidence


def _workflow_review(raw: bytes, metadata: dict[str, Any]) -> None:
    document = _object(raw, MAX_WORKFLOW_BYTES)
    _closed(
        document,
        {
            "schema_version",
            "id",
            "description",
            "application",
            "configuration",
            "workflow",
        },
        "Curated workflow",
    )
    if (
        document["id"] != metadata["id"]
        or document["schema_version"] != "l1ght5p33d/v1"
        or document["description"] != metadata["summary"]
        or document["application"] != metadata["application"]["provider"]
        or document["configuration"] != metadata["application"]["configuration"]
    ):
        raise PackError(
            "Actual workflow identity/configuration differs from signed review"
        )
    native = document["workflow"]
    _closed(
        native, {"schema_version", "name", "params", "steps"}, "Curated native workflow"
    )
    if native["schema_version"] != 2 or native["params"] != metadata["defaults"]:
        raise PackError("Native schema or defaults differ from signed review")
    if type(native["steps"]) is not list or not 1 <= len(native["steps"]) <= 20:
        raise PackError("Curated native steps must be a bounded list")
    checklist = []
    for step in native["steps"]:
        _closed(step, {"id", "intent", "action", "api_binding"}, "Reviewed step")
        binding = step["api_binding"]
        _closed(
            binding,
            {
                "kind",
                "url_template",
                "method",
                "on_unavailable",
                "body_template",
                "effects",
            },
            "Reviewed binding",
        )
        if (
            step["action"] != "wait"
            or binding["kind"] != "tool"
            or binding["on_unavailable"] != "halt"
            or binding["url_template"] != "browser"
            or type(binding["method"]) is not str
            or binding["method"] not in {"fill", "select", "click"}
        ):
            raise PackError("Actual action is outside the library's reviewed scope")
        checklist.append(
            {
                "id": step["id"],
                "intent": step["intent"],
                "provider": binding["url_template"],
                "operation": binding["method"],
                "arguments": binding["body_template"],
                "effects": binding["effects"],
            }
        )
    if checklist != metadata["reviewed_steps"]:
        raise PackError(
            "Actual actions, selectors or effects differ from signed checklist"
        )
    try:
        validate_document(document)
    except ValueError as exc:
        raise PackError("Curated workflow failed runtime schema validation") from exc


def _provenance(metadata_path: str, claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": LIBRARY_REPOSITORY,
        "library_ref": LIBRARY_REF,
        "requested_source_base": LIBRARY_BASE_URL,
        "repository_head_authenticated": False,
        "metadata_path": metadata_path,
        "workflow_path": claims["workflow"]["path"],
        "evidence_path": claims["evidence"]["path"],
        "trust_source": "THEBEST public key shipped with this application",
        "public_key_hex": THEBEST_PUBLIC_KEY_HEX,
        "public_key_sha256": hashlib.sha256(
            bytes.fromhex(THEBEST_PUBLIC_KEY_HEX)
        ).hexdigest(),
        "identity": "thebest",
        "role": "curator",
        "issued_at": claims["issued_at"],
        "expires_at": claims["expires_at"],
        "qualification": claims["qualification"],
        "execution_approved": False,
        "tests_executed_by_verifier": False,
    }


def verify_pack(
    workflow_bytes: bytes,
    metadata_bytes: bytes,
    evidence_bytes: bytes,
    attestation_bytes: bytes,
    *,
    metadata_path: str | None = None,
    now: datetime | None = None,
) -> ReviewedPack:
    """Revalidate exact cached/downloaded bytes, including expiry, without any I/O."""
    claims = _verified_claims(attestation_bytes, now)
    metadata_path = metadata_path or claims["metadata"]["path"]
    metadata, evidence = _review(metadata_bytes, evidence_bytes, claims, metadata_path)
    if (
        not isinstance(workflow_bytes, bytes)
        or not 0 < len(workflow_bytes) <= MAX_WORKFLOW_BYTES
    ):
        raise PackError("Workflow is empty or exceeds its byte limit")
    _check_hash(workflow_bytes, claims["workflow"], "Workflow")
    _workflow_review(workflow_bytes, metadata)
    hashes = {
        "workflow": hashlib.sha256(workflow_bytes).hexdigest(),
        "metadata": hashlib.sha256(metadata_bytes).hexdigest(),
        "evidence": hashlib.sha256(evidence_bytes).hexdigest(),
        "attestation": hashlib.sha256(attestation_bytes).hexdigest(),
    }
    return ReviewedPack(
        workflow_id=metadata["id"],
        version=metadata["version"],
        workflow_bytes=workflow_bytes,
        metadata_bytes=metadata_bytes,
        evidence_bytes=evidence_bytes,
        attestation_bytes=attestation_bytes,
        metadata_path=metadata_path,
        workflow_sha256=hashes["workflow"],
        pack_digest=hashlib.sha256(_canonical(hashes)).hexdigest(),
        metadata=metadata,
        evidence=evidence,
        claims=claims,
        provenance=_provenance(metadata_path, claims),
    )


def _https_fetch(url: str, limit: int) -> bytes:
    return _download("GET", url, limit=limit)


class CuratedPackSource:
    """The fixed public library; only bounded GETs to its GitHub main-branch base.

    The injected fetcher and clock are local Python test hooks, not remote tool
    arguments. No trust-key or arbitrary-source URL is accepted. Index/branch
    contents are untrusted; exact artifact bytes require a valid curator signature.
    Expiry limits replay; no persistent revision rollback floor is implemented.
    """

    def __init__(
        self,
        *,
        fetcher: Callable[[str, int], bytes] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = fetcher or _https_fetch
        self._clock = clock or (lambda: datetime.now(UTC))

    def _get(self, path: str, limit: int) -> bytes:
        path = _path(path)
        try:
            raw = self._fetcher(LIBRARY_BASE_URL + path, limit)
        except RegistryError as exc:
            raise PackError("Curated pack download failed: " + str(exc)) from exc
        if not isinstance(raw, bytes) or not 0 < len(raw) <= limit:
            raise PackError("Curated download is empty or exceeds its byte limit")
        return raw

    def _reviews(
        self,
    ) -> list[tuple[bytes, bytes, bytes, dict[str, Any], dict[str, Any]]]:
        index = _object(self._get("index.json", MAX_INDEX_BYTES), MAX_INDEX_BYTES)
        _closed(
            index, {"schema_version", "description", "entries", "source_files"}, "Index"
        )
        if index["schema_version"] != "l1ght5p33d-curated-index/v1":
            raise PackError("Unsupported curated index schema")
        _text(index["description"], 4000, "index description")
        entries, sources = index["entries"], index["source_files"]
        for values, limit in ((entries, 20), (sources, 500)):
            if type(values) is not list or not 1 <= len(values) <= limit:
                raise PackError("Index paths exceed their count limit")
            paths = [_path(value) for value in values]
            if len(paths) != len(set(paths)):
                raise PackError("Duplicate index path")
        if not set(entries) <= set(sources) or any(
            not re.fullmatch(r"entries/[a-z][a-z0-9-]*\.json", path) for path in entries
        ):
            raise PackError("Index entries must be declared metadata paths")
        attestations = [path for path in sources if path.startswith("attestations/")]
        if len(attestations) != len(entries) or any(
            not re.fullmatch(r"attestations/[a-z][a-z0-9.-]*\.json", path)
            for path in attestations
        ):
            raise PackError("Each curated entry requires one detached attestation")
        results = []
        seen_paths: set[str] = set()
        seen_ids: set[tuple[str, str]] = set()
        for path in attestations:
            attestation = self._get(path, MAX_ATTESTATION_BYTES)
            claims = _verified_claims(attestation, self._clock())
            metadata_path = claims["metadata"]["path"]
            if metadata_path not in entries or metadata_path in seen_paths:
                raise PackError("Attestation does not bind a unique indexed entry")
            if any(claims[kind]["path"] not in sources for kind in _ARTIFACTS):
                raise PackError("Attested artifact is missing from the index")
            metadata_bytes = self._get(metadata_path, MAX_METADATA_BYTES)
            evidence_bytes = self._get(claims["evidence"]["path"], MAX_EVIDENCE_BYTES)
            metadata, evidence = _review(
                metadata_bytes, evidence_bytes, claims, metadata_path
            )
            identity = metadata["id"], metadata["version"]
            if identity in seen_ids:
                raise PackError("Duplicate signed workflow identity and version")
            seen_ids.add(identity)
            seen_paths.add(metadata_path)
            results.append(
                (metadata_bytes, evidence_bytes, attestation, metadata, claims)
            )
        return results

    def search(
        self, query: str, application: str | None = None
    ) -> list[dict[str, Any]]:
        """Search signed review metadata; workflow bytes are verified on fetch."""
        if (
            type(query) is not str
            or len(query) > 200
            or any(ord(char) < 32 or ord(char) == 127 for char in query)
        ):
            raise PackError("Search query must be at most 200 printable characters")
        if application is not None and not _IDENTIFIER.fullmatch(
            _text(application, 64, "application filter")
        ):
            raise PackError("Invalid application filter")
        tokens = query.casefold().split()
        results = []
        for _, _, _, metadata, claims in self._reviews():
            haystack = " ".join(
                (
                    metadata["id"],
                    metadata["title"],
                    metadata["summary"],
                    metadata["application"]["provider"],
                )
            ).casefold()
            if application and metadata["application"]["provider"] != application:
                continue
            if not all(token in haystack for token in tokens):
                continue
            results.append(
                {
                    "id": metadata["id"],
                    "version": metadata["version"],
                    "title": metadata["title"],
                    "description": metadata["summary"],
                    "application": metadata["application"]["provider"],
                    "license": metadata["license"],
                    "workflow_sha256": metadata["sha256"],
                    "review": metadata,
                    "provenance": _provenance(claims["metadata"]["path"], claims),
                    "verification": "curator_signature_metadata_and_evidence_verified",
                    "workflow_bytes_verified": False,
                    "execution_approved": False,
                }
            )
        return results

    def fetch(self, workflow_id: str, version: str) -> ReviewedPack:
        """Download exact reviewed bytes. Does not install or execute anything."""
        if not _IDENTIFIER.fullmatch(_text(workflow_id, 64, "workflow ID")):
            raise PackError("Invalid workflow ID")
        if not _VERSION.fullmatch(_text(version, 80, "workflow version")):
            raise PackError("Invalid workflow version")
        for (
            metadata_bytes,
            evidence_bytes,
            attestation,
            metadata,
            claims,
        ) in self._reviews():
            if (metadata["id"], metadata["version"]) == (workflow_id, version):
                raw = self._get(claims["workflow"]["path"], MAX_WORKFLOW_BYTES)
                pack = verify_pack(
                    raw,
                    metadata_bytes,
                    evidence_bytes,
                    attestation,
                    metadata_path=claims["metadata"]["path"],
                    now=self._clock(),
                )
                if (pack.workflow_id, pack.version) != (workflow_id, version):
                    raise PackError(
                        "Fetched pack identity differs from requested version"
                    )
                return pack
        raise PackError(
            "No current reviewed pack has that exact workflow ID and version"
        )
