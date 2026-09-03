"""Local operator entry point. Normal workflows have no shell command."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from createrelay.policy import Policy, digest, load_policy
from createrelay.service import WorkflowService, local_home, write_json
from createrelay.workflow import load_workflow, workflow_schema


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True), flush=True)


def _wait(service: WorkflowService, run: dict[str, Any]) -> int:
    run_id = run["run_id"]
    offset = 0
    try:
        while True:
            logs = service.get_execution_log(run_id, offset)
            for event in logs:
                logging.info("%s: %s (%s ms; %s)", event['step_id'], event['result'], event['duration_ms'], event['selector_method'])
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
    return _wait(service, run)


def main(argv: list[str] | None = None) -> int:
    if argv is None and sys.platform == "win32" and not sys.flags.utf8_mode:
        # Upstream checkpoint files are UTF-8; use that encoding on Windows too.
        os.execv(
            sys.executable,
            [sys.executable, "-X", "utf8", "-m", "createrelay", *sys.argv[1:]],
        )
    parser = argparse.ArgumentParser(
        prog="createrelay",
        description="Local creation workflows; no model calls on routine execution",
    )
    parser.add_argument("--version", action="version", version="CreateRelay 0.1.0")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)
    patch_command = commands.add_parser("approve-patch")
    patch_command.add_argument("patch_id")
    patch_command.add_argument("--workflows", type=Path, required=True)
    patch_command.add_argument("--policy", type=Path, required=True)
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
    live.add_argument("--project-name", default="CreateRelay Import")
    live.add_argument("--policy", type=Path, required=True)
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--run", action="store_true")
    login = commands.add_parser("bandlab-login")
    login.add_argument("--profile", default="bandlab")
    login.add_argument("--channel", choices=["chrome", "msedge"], default="chrome")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(message)s")
    try:
        if args.command == "approve-patch":
            policy = load_policy(args.policy)
            service = WorkflowService(args.workflows, policy)
            result = service.approve_workflow_patch(args.patch_id, local_operator=True)
            write_json(args.policy, policy.model_dump(mode="json"))
            _print(result)
            return 0
        if args.command == "bandlab-login":
            from createrelay.providers.bandlab import bandlab_login

            bandlab_login(profile_name=args.profile, channel=args.channel)
            return 0
        if args.command == "schema":
            write_json(args.out, workflow_schema())
            return 0
        if args.command == "midi":
            from createrelay.midi import build_manifest, write_manifest

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
            from createrelay.providers.bandlab import build_bandlab_workflow

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

            with tempfile.TemporaryDirectory(prefix="createrelay-demo-") as temporary:
                root = Path(temporary)
                if args.kind == "browser":
                    from createrelay.examples import browser_workflow
                    from createrelay.fixtures.creative import serve_creative_fixture

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
                        )
                if args.kind == "bandlab":
                    from createrelay.fixtures.bandlab import start_fixture
                    from createrelay.midi import build_manifest, generate_synthetic_midi
                    from createrelay.providers.bandlab import build_bandlab_workflow

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
                        )
                from createrelay.fixtures.windows_demo import run_demo

                return run_demo()
        service = WorkflowService(args.workflows, load_policy(args.policy))
        if args.command == "list":
            _print(service.list_workflows())
        elif args.command == "rpc":
            from createrelay.mcp_server import run_json_rpc

            run_json_rpc(service)
        elif args.command == "serve":
            import uvicorn

            from createrelay.mcp_server import create_app

            token = os.environ.get("CREATERELAY_SESSION_TOKEN")
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
        print(f"CreateRelay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
