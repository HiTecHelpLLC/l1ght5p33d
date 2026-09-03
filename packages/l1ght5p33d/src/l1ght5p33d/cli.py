"""Local operator entry point. Normal workflows have no shell command."""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from l1ght5p33d.discovery import load_discovery
from l1ght5p33d.planning import build_run_plan, render_run_plan
from l1ght5p33d.policy import PermissionDenied, Policy, digest, load_policy
from l1ght5p33d.service import WorkflowService, local_home, write_json
from l1ght5p33d.workflow import load_workflow, validate_document, workflow_schema


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True), flush=True)


def _confirm(review: str) -> None:
    """Human confirmation is intentionally absent from MCP/JSON-RPC."""
    print(review, flush=True)
    if not sys.stdin.isatty():
        raise PermissionDenied(
            "Approval needs an interactive local terminal. AI clients must present "
            "the plan to the user and must not approve on the user's behalf."
        )
    try:
        answer = input("Approve exactly the plan and changes above? Type APPROVE: ")
    except (EOFError, KeyboardInterrupt) as exc:
        raise PermissionDenied("Approval cancelled; no permission granted") from exc
    if answer != "APPROVE":
        raise PermissionDenied("Approval declined; no permission granted")


def _wait(service: WorkflowService, run: dict[str, Any]) -> int:
    run_id = run["run_id"]
    offset = 0
    try:
        while True:
            logs = service.get_execution_log(run_id, offset)
            for event in logs:
                logging.info(
                    "%s: %s (%s ms; %s)",
                    event["step_id"],
                    event["result"],
                    event["duration_ms"],
                    event["selector_method"],
                )
            offset += len(logs)
            status = service.get_execution_status(run_id)
            if status["done"]:
                _print(status)
                print(f"Receipt directory: {service.runs[run_id]['directory']}")
                return 0 if status["status"].startswith("completed_") else 1
            time.sleep(0.05)
    except KeyboardInterrupt:
        service.abort_workflow(run_id)
        print(
            "Cancellation requested. Finishing any current verification.",
            file=sys.stderr,
        )
        service.runs[run_id]["thread"].join(timeout=65)
        _print(service.get_execution_status(run_id))
        return 130


def _run_file(
    path: Path,
    policy: Policy,
    state: Path | None = None,
    variables: list[str] | None = None,
    dry_run: bool = False,
    *,
    _fixture_demo: bool = False,
) -> int:
    doc = load_workflow(path)
    service = WorkflowService(path.parent, policy, state_root=state)
    if variables:
        service.set_workflow_variables(
            doc.id, dict(item.split("=", 1) for item in variables)
        )
    run = service.run_workflow(doc.id, dry_run=dry_run)
    if dry_run:
        _print(run)
        return 0
    if not _fixture_demo:
        _confirm(render_run_plan(run["plan"]))
    else:
        print("Running the bundled synthetic fixture demonstration only.")
    service.approve_run_plan(
        run["plan_id"], run["plan"]["plan_digest"], local_operator=True
    )
    run = service.run_workflow(doc.id, plan_id=run["plan_id"])
    return _wait(service, run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="l1ght5p33d",
        description="Local creation workflows; no model calls on routine execution",
    )
    parser.add_argument("--version", action="version", version="L1ght5p33d 0.1.0")
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="Search a signed workflow register")
    catalog.add_argument("url")
    catalog.add_argument("--public-key", type=Path, required=True)
    catalog.add_argument("--query", default="")
    install = commands.add_parser(
        "install-workflow",
        help="Fetch a reviewed version through local Kubo; never run it",
    )
    install.add_argument("workflow_id")
    install.add_argument("--version", required=True)
    install.add_argument("--catalog", required=True)
    install.add_argument("--public-key", type=Path, required=True)
    install.add_argument("--workflows", type=Path, required=True)
    install.add_argument("--kubo-url", default="http://127.0.0.1:5001")
    patch_command = commands.add_parser("approve-patch")
    patch_command.add_argument("patch_id")
    patch_command.add_argument("--workflows", type=Path, required=True)
    patch_command.add_argument("--policy", type=Path, required=True)
    review = commands.add_parser(
        "review-run", help="Display and approve one exact run locally"
    )
    review.add_argument("plan_id")
    review.add_argument("--workflows", type=Path, required=True)
    review.add_argument("--policy", type=Path)
    review.add_argument("--state", type=Path)
    for name in ("validate", "run", "approve-workflow"):
        command = commands.add_parser(name)
        command.add_argument("workflow", type=Path)
        command.add_argument("--policy", type=Path, required=name == "approve-workflow")
        if name == "run":
            command.add_argument("--var", action="append", default=[])
            command.add_argument("--dry-run", action="store_true")
    for name in ("list", "serve", "rpc"):
        command = commands.add_parser(name)
        command.add_argument("--workflows", type=Path, required=True)
        command.add_argument("--policy", type=Path)
        command.add_argument("--discovery", type=Path)
        if name == "serve":
            command.add_argument("--port", type=int, default=7331)
            command.add_argument("--token-file", type=Path)
    midi = commands.add_parser("midi")
    midi.add_argument("folder", type=Path)
    midi.add_argument("--reference-wav", type=Path)
    midi.add_argument("--config", type=Path)
    midi.add_argument("--out", type=Path, required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("kind", choices=["browser", "bandlab", "windows"])
    demo.add_argument("--headful", action="store_true")
    schema = commands.add_parser("schema")
    schema.add_argument("--out", type=Path, required=True)
    live = commands.add_parser("bandlab-live")
    live.add_argument("--manifest", type=Path, required=True)
    live.add_argument("--selectors", type=Path, required=True)
    live.add_argument("--url", required=True)
    live.add_argument("--profile", default="bandlab")
    live.add_argument("--channel", choices=["chrome", "msedge"], default="chrome")
    live.add_argument("--project-name", default="L1ght5p33d Import")
    live.add_argument("--policy", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--run", action="store_true")
    login = commands.add_parser("bandlab-login")
    login.add_argument("--profile", default="bandlab")
    login.add_argument("--channel", choices=["chrome", "msedge"], default="chrome")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(message)s")
    try:
        if args.command in {"catalog", "install-workflow"}:
            from l1ght5p33d.registry import fetch_catalog, install_workflow

            if args.public_key.stat().st_size > 256:
                raise ValueError("Public-key file must contain one 32-byte hex key")
            public_key = args.public_key.read_text("ascii").strip()
            register = fetch_catalog(
                args.url if args.command == "catalog" else args.catalog, public_key
            )
            if args.command == "catalog":
                query = args.query.casefold()
                _print(
                    [
                        entry.model_dump(mode="json")
                        for entry in register.workflows
                        if query
                        in " ".join(
                            [
                                entry.id,
                                entry.title,
                                entry.description,
                                entry.application,
                            ]
                        ).casefold()
                    ]
                )
                return 0
            matches = [
                entry
                for entry in register.workflows
                if entry.id == args.workflow_id and entry.version == args.version
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Select one exact workflow id and version from the register"
                )
            installed = install_workflow(matches[0], args.workflows, args.kubo_url)
            _print(
                {
                    "status": "installed_not_approved",
                    "path": str(installed),
                    "id": args.workflow_id,
                    "version": args.version,
                    "sha256": matches[0].sha256,
                    "executed": False,
                }
            )
            return 0
        if args.command == "approve-patch":
            policy = load_policy(args.policy)
            service = WorkflowService(args.workflows, policy)
            patch_path = service.state_root / "patches" / f"{args.patch_id}.json"
            if not re.fullmatch(r"[0-9a-f]{32}", args.patch_id):
                raise ValueError("Invalid patch id")
            patch = json.loads(patch_path.read_text("ascii"))
            original = load_workflow(service._path(patch["workflow_id"]))
            proposed = validate_document(json.loads(patch["content"]))
            if (
                digest(original) != patch["old_digest"]
                or digest(proposed) != patch["new_digest"]
            ):
                raise PermissionDenied(
                    "Patch content or original changed; propose a fresh diff"
                )
            actual_diff = "".join(
                difflib.unified_diff(
                    original.model_dump_json(indent=2).splitlines(True),
                    proposed.model_dump_json(indent=2).splitlines(True),
                    fromfile="original",
                    tofile="proposed",
                )
            )
            service._patches[args.patch_id] = patch
            # Quote the diff so untrusted text cannot control the terminal.
            _confirm(
                json.dumps({"patch_diff": actual_diff}, ensure_ascii=True, indent=2)
            )
            result = service.approve_workflow_patch(
                args.patch_id, local_operator=True, expected_digest=patch["new_digest"]
            )
            write_json(args.policy, policy.model_dump(mode="json"))
            _print(result)
            return 0
        if args.command == "review-run":
            service = WorkflowService(
                args.workflows, load_policy(args.policy), state_root=args.state
            )
            record = service.get_run_plan(args.plan_id)
            if record["status"] != "awaiting_approval":
                raise PermissionDenied(
                    "Plan is not awaiting approval; prepare a fresh plan"
                )
            _confirm(render_run_plan(record["plan"]))
            _print(
                service.approve_run_plan(
                    args.plan_id, record["plan"]["plan_digest"], local_operator=True
                )
            )
            return 0
        if args.command == "bandlab-login":
            from l1ght5p33d.providers.bandlab import bandlab_login

            bandlab_login(profile_name=args.profile, channel=args.channel)
            return 0
        if args.command == "schema":
            write_json(args.out, workflow_schema())
            return 0
        if args.command == "midi":
            from l1ght5p33d.midi import build_manifest, write_manifest

            config = json.loads(args.config.read_text("ascii")) if args.config else None
            manifest = build_manifest(
                args.folder, reference_wav=args.reference_wav, config=config
            )
            write_manifest(manifest, args.out)
            _print(
                {
                    "manifest": str(args.out),
                    "files": len(manifest.get("imports", [])),
                    "manual_review": manifest.get("manual_review", []),
                }
            )
            return 0
        if args.command == "bandlab-live":
            from l1ght5p33d.providers.bandlab import build_bandlab_workflow

            manifest = json.loads(args.manifest.read_text("ascii"))
            selectors = json.loads(args.selectors.read_text("ascii"))
            document = build_bandlab_workflow(
                manifest,
                url=args.url,
                mode="live",
                project_name=args.project_name,
                provider_config={
                    "selectors": selectors,
                    "selectors_reviewed": True,
                    "profile": args.profile,
                    "channel": args.channel,
                },
            )
            write_json(args.out, document)
            print(f"Review workflow: {args.out}")
            if args.run:
                return _run_file(args.out, load_policy(args.policy))
            return 0
        if args.command in {"validate", "run", "approve-workflow"}:
            doc = load_workflow(args.workflow)
            policy = (
                load_policy(args.policy)
                if not args.policy or args.policy.exists()
                else Policy()
            )
            if args.command == "approve-workflow":
                # This command is explicitly local. It displays and binds exact capabilities.
                config = doc.configuration.get(doc.application, doc.configuration)
                if doc.application not in policy.applications:
                    policy.applications.append(doc.application)
                for key in ("url", "project_url", "fixture_url"):
                    if value := config.get(key):
                        parsed = urlsplit(value)
                        origin = f"{parsed.scheme}://{parsed.netloc}"
                        if origin not in policy.allowed_origins:
                            policy.allowed_origins.append(origin)
                for root in config.get("read_roots", []):
                    normalized = str(Path(root).resolve(strict=True))
                    if normalized not in policy.read_roots:
                        policy.read_roots.append(normalized)
                policy.approved_workflow_digests.append(digest(doc))
                policy.check_workflow(doc)
                _confirm(
                    "Proposed application/file/origin permission grant; each run also needs approval.\n"
                    + render_run_plan(build_run_plan(doc, policy, {}))
                )
                write_json(args.policy, policy.model_dump(mode="json"))
                _print(
                    {
                        "approved_digest": digest(doc),
                        "application": doc.application,
                        "origins": policy.allowed_origins,
                        "read_roots": policy.read_roots,
                    }
                )
                return 0
            if args.command == "validate":
                policy.check_workflow(doc, require_approval=False)
                _print({"valid": True, "id": doc.id, "digest": digest(doc)})
                return 0
            return _run_file(
                args.workflow, policy, variables=args.var, dry_run=args.dry_run
            )
        if args.command == "demo":
            import tempfile

            with tempfile.TemporaryDirectory(prefix="l1ght5p33d-demo-") as temporary:
                root = Path(temporary)
                if args.kind == "browser":
                    from l1ght5p33d.examples import browser_workflow
                    from l1ght5p33d.fixtures.creative import serve_creative_fixture

                    with serve_creative_fixture() as url:
                        path = root / "poster.json"
                        write_json(
                            path, browser_workflow(url, headless=not args.headful)
                        )
                        return _run_file(
                            path,
                            Policy(
                                approved_workflow_digests=[digest(load_workflow(path))]
                            ),
                            _fixture_demo=True,
                        )
                if args.kind == "bandlab":
                    from l1ght5p33d.fixtures.bandlab import start_fixture
                    from l1ght5p33d.midi import build_manifest, generate_synthetic_midi
                    from l1ght5p33d.providers.bandlab import build_bandlab_workflow

                    midi_root = root / "midi"
                    generate_synthetic_midi(midi_root)
                    manifest = build_manifest(midi_root)
                    with start_fixture() as url:
                        path = root / "bandlab.json"
                        write_json(
                            path,
                            build_bandlab_workflow(
                                manifest,
                                url=url,
                                provider_config={"headless": not args.headful},
                            ),
                        )
                        return _run_file(
                            path,
                            Policy(
                                applications=["bandlab"],
                                read_roots=[str(midi_root)],
                                approved_workflow_digests=[digest(load_workflow(path))],
                            ),
                            _fixture_demo=True,
                        )
                from l1ght5p33d.fixtures.windows_demo import run_demo

                return run_demo()
        service = WorkflowService(
            args.workflows,
            load_policy(args.policy),
            discovery=load_discovery(args.discovery),
        )
        if args.command == "list":
            _print(service.list_workflows())
        elif args.command == "rpc":
            from l1ght5p33d.mcp_server import run_json_rpc

            run_json_rpc(service)
        elif args.command == "serve":
            import uvicorn

            from l1ght5p33d.mcp_server import create_app

            token = os.environ.get("L1GHT5P33D_SESSION_TOKEN")
            if not token:
                token_path = args.token_file or local_home() / "session.token"
                token_path.parent.mkdir(parents=True, exist_ok=True)
                if token_path.exists():
                    token = token_path.read_text("ascii").strip()
                else:
                    token = secrets.token_urlsafe(32)
                    token_path.write_text(token, "ascii")
                    os.chmod(token_path, 0o600)
                print(
                    f"Session token is in {token_path}; keep this file private.",
                    file=sys.stderr,
                )
            uvicorn.run(
                create_app(service, token, port=args.port),
                host="127.0.0.1",
                port=args.port,
                log_level="warning",
            )
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"L1ght5p33d: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
