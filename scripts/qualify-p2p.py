#!/usr/bin/env python3
"""Prove signed HTTP catalog discovery and P2P installation through the real CLI.

Uses an operator-supplied Kubo executable. Only a bundled synthetic workflow is
seeded between two peers, with no bootstrap, delegated routing, MDNS or public
listeners. A bounded local HTTP fixture serves the signed catalog. The consumer
CLI discovers and installs the workflow without approving or running it. The
HTTP server, temporary repositories and owned daemons stop before success prints.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from l1ght5p33d.registry import raw_cid


class CatalogServer:
    """Expose only the signed in-memory catalog, never a filesystem directory."""

    def __init__(self, envelope: bytes):
        self.requests = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(3)

            def do_GET(self) -> None:
                if self.path != "/catalog":
                    self.send_error(404)
                    return
                fixture.requests += 1
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(envelope)))
                self.end_headers()
                self.wfile.write(envelope)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="qualification-catalog",
        )
        self.url = f"http://127.0.0.1:{self.server.server_port}/catalog"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        if self.thread.ident is not None:
            self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("Owned catalog server did not stop")


def consumer_cli(*args: str) -> Any:
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "l1ght5p33d", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError("Consumer CLI refused the test: " + result.stderr[-2000:])
    return json.loads(result.stdout)


class Node:
    def __init__(self, executable: Path, root: Path):
        self.executable = executable
        self.root = root
        self.environment = {**os.environ, "IPFS_PATH": str(root)}
        # Do not inherit another node's API address or request Origin override.
        self.environment.pop("API_ORIGIN", None)
        self.process: subprocess.Popen[bytes] | None = None
        self.log: Any = None
        self.url = ""
        self.identity: dict[str, Any] = {}

    def command(self, *args: str) -> str:
        result = subprocess.run(
            [str(self.executable), *args],
            env=self.environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.stdout.strip()

    def post(self, endpoint: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(
            trust_env=False, follow_redirects=False, timeout=15
        ) as client:
            response = client.post(self.url + "/api/v0/" + endpoint, **kwargs)
            response.raise_for_status()
            return response

    def start(self) -> None:
        self.command("init", "--empty-repo", "--profile=test")
        config_file = self.root / "config"
        config = json.loads(config_file.read_text(encoding="utf-8"))
        config["Bootstrap"] = []
        config["Discovery"] = {"MDNS": {"Enabled": False}}
        config["Addresses"]["API"] = "/ip4/127.0.0.1/tcp/0"
        config["Addresses"]["Gateway"] = "/ip4/127.0.0.1/tcp/0"
        config["Addresses"]["Swarm"] = ["/ip4/127.0.0.1/tcp/0"]
        config["Addresses"]["Announce"] = []
        config["Addresses"]["AppendAnnounce"] = []
        config["Routing"]["Type"] = "none"
        config["Routing"]["DelegatedRouters"] = []
        config.setdefault("Peering", {})["Peers"] = []
        config.setdefault("Swarm", {})["DisableNatPortMap"] = True
        config["Swarm"]["EnableHolePunching"] = False
        config.setdefault("AutoNAT", {})["ServiceMode"] = "disabled"
        config.setdefault("AutoTLS", {})["Enabled"] = False
        config.setdefault("AutoConf", {})["Enabled"] = False
        config.setdefault("Ipns", {})["UsePubsub"] = False
        config.setdefault("Pubsub", {})["Enabled"] = False
        config_file.write_text(json.dumps(config), encoding="utf-8")
        self.log = (self.root / "qualification.log").open("wb")
        self.process = subprocess.Popen(
            [str(self.executable), "daemon", "--routing=none"],
            env=self.environment,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Isolated Kubo daemon exited before becoming ready")
            api_file = self.root / "api"
            if api_file.is_file():
                parts = api_file.read_text().strip().split("/")
                if len(parts) != 5 or parts[:4] != ["", "ip4", "127.0.0.1", "tcp"]:
                    raise RuntimeError("Unexpected non-loopback Kubo API")
                self.url = f"http://127.0.0.1:{int(parts[4])}"
                try:
                    self.identity = self.post("id").json()
                    return
                except httpx.HTTPError:
                    pass
            time.sleep(0.1)
        raise TimeoutError("Isolated Kubo did not become ready in 20 seconds")

    def stop(self) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.post("shutdown")
                    self.process.wait(timeout=5)
                except (httpx.HTTPError, subprocess.TimeoutExpired):
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=5)
        finally:
            if self.log:
                self.log.close()

    def has_local(self, cid: str) -> bool:
        return any(
            json.loads(line).get("Ref") == cid
            for line in self.post("refs/local").text.splitlines()
            if line
        )


def qualify(executable: Path) -> dict[str, Any]:
    workflow = (
        Path(__file__).resolve().parents[1] / "examples/l1ght5p33d/browser-poster.json"
    )
    raw = workflow.read_bytes()
    source = json.loads(raw.decode("ascii"))
    cid = raw_cid(raw)
    key = Ed25519PrivateKey.generate()
    now = datetime.now(UTC)
    payload = json.dumps(
        {
            "schema_version": "l1ght5p33d-catalog/v1",
            "revision": 1,
            "generated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "workflows": [
                {
                    "id": source["id"],
                    "version": "0.1.0",
                    "title": "Synthetic poster workflow",
                    "description": source["description"],
                    "application": source["application"],
                    "workflow_schema": source["schema_version"],
                    "runtime_version": "1.34.0",
                    "license": "MIT",
                    "cid": cid,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                    "compatibility": {"fixture": "bundled browser poster"},
                    "verification": {
                        "level": "fixture",
                        "description": "Synthetic bundled example; this test proves transfer only",
                    },
                }
            ],
        },
        ensure_ascii=True,
        sort_keys=True,
    ).encode("ascii")
    envelope = json.dumps(
        {
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "signature_b64": base64.b64encode(key.sign(payload)).decode("ascii"),
        }
    ).encode("ascii")
    with tempfile.TemporaryDirectory(prefix="l1ght5p33d-p2p-") as temporary:
        root = Path(temporary)
        nodes = [Node(executable, root / "source"), Node(executable, root / "receiver")]
        catalog_server = CatalogServer(envelope)
        try:
            catalog_server.start()
            public_key_file = root / "catalog.pub"
            public_key_file.write_text(
                key.public_key().public_bytes_raw().hex(), encoding="ascii"
            )
            for node in nodes:
                node.start()
            producer, receiver = nodes
            version = producer.command("version", "--number")
            if version != "0.43.0":
                raise RuntimeError(
                    f"This qualification is pinned to Kubo 0.43.0, got {version}"
                )
            if receiver.has_local(cid):
                raise RuntimeError("Receiver already contains the workflow block")
            if any(
                p.read_bytes() == raw
                for p in (receiver.root / "blocks").rglob("*.data")
            ):
                raise RuntimeError("Receiver blockstore already has the source bytes")
            seeded = producer.post(
                "block/put",
                params={"cid-codec": "raw", "mhtype": "sha2-256", "pin": "true"},
                files={"file": ("workflow.json", raw, "application/json")},
            ).json()
            if seeded.get("Key") != cid:
                raise RuntimeError("Producer stored an unexpected CID")
            addresses = [
                item
                for item in producer.identity["Addresses"]
                if item.startswith("/ip4/127.0.0.1/tcp/")
            ]
            if len(addresses) != 1:
                raise RuntimeError("Expected exactly one loopback producer address")
            peer = addresses[0]
            if "/p2p/" not in peer:
                peer += "/p2p/" + producer.identity["ID"]
            receiver.post("swarm/connect", params={"arg": peer})
            peers = receiver.post("swarm/peers").json().get("Peers", [])
            if len(peers) != 1 or peers[0]["Peer"] != producer.identity["ID"]:
                raise RuntimeError("Receiver connected to unexpected peers")
            discovered = consumer_cli(
                "catalog",
                catalog_server.url,
                "--public-key",
                str(public_key_file),
                "--query",
                "poster",
            )
            if (
                not isinstance(discovered, list)
                or len(discovered) != 1
                or discovered[0].get("id") != source["id"]
                or discovered[0].get("cid") != cid
            ):
                raise RuntimeError(
                    "Consumer CLI did not discover the expected workflow"
                )
            if receiver.has_local(cid):
                raise RuntimeError("Discovery unexpectedly downloaded the workflow")
            (root / "installed").mkdir()
            started = time.monotonic()
            installed = consumer_cli(
                "install-workflow",
                source["id"],
                "--version",
                "0.1.0",
                "--catalog",
                catalog_server.url,
                "--public-key",
                str(public_key_file),
                "--workflows",
                str(root / "installed"),
                "--kubo-url",
                receiver.url,
            )
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            destination = root / "installed" / f"workflow-{source['id']}.json"
            if (
                installed.get("status") != "installed_not_approved"
                or installed.get("executed") is not False
                or Path(installed.get("path", "")).resolve() != destination.resolve()
                or catalog_server.requests != 2
            ):
                raise RuntimeError(
                    "Consumer CLI did not report the expected inactive install"
                )
            if destination.read_bytes() != raw or not receiver.has_local(cid):
                raise RuntimeError(
                    "Received workflow failed byte or blockstore verification"
                )
            result = {
                "result": "verified_p2p_transfer",
                "kubo_version": version,
                "cid": cid,
                "bytes": len(raw),
                "duration_ms": duration_ms,
                "timing_scope": "CLI process start through verified installation",
                "catalog_http_requests": catalog_server.requests,
                "cli_discovery_verified": True,
                "cli_install_status": installed["status"],
                "receiver_had_block_before": False,
                "receiver_has_block_after": True,
                "signature_verified": True,
                "installed_bytes_match": True,
                "peers": 2,
                "network": "loopback-only; bootstrap/MDNS/routing disabled",
                "workflow_executed": False,
            }
        except Exception:
            for node in nodes:
                if node.log:
                    node.log.flush()
                log_file = node.root / "qualification.log"
                if log_file.is_file():
                    print(log_file.read_text(errors="replace")[-4000:], file=sys.stderr)
            raise
        finally:
            # Every process handle belongs to this invocation. No process-name kills.
            errors = []
            for node in reversed(nodes):
                try:
                    node.stop()
                except Exception as exc:
                    errors.append(str(exc))
            try:
                catalog_server.stop()
            except Exception as exc:
                errors.append(str(exc))
            if errors:
                raise RuntimeError("Owned daemon cleanup failed: " + "; ".join(errors))
    result["owned_daemons_stopped"] = True
    result["catalog_server_stopped"] = True
    result["temporary_repositories_removed"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubo", type=Path, required=True)
    args = parser.parse_args()
    try:
        executable = args.kubo.expanduser().resolve(strict=True)
        if not executable.is_file():
            raise ValueError("--kubo must name the verified executable")
        print(json.dumps(qualify(executable), indent=2))
        return 0
    except (
        ValueError,
        OSError,
        RuntimeError,
        httpx.HTTPError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"P2P qualification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
