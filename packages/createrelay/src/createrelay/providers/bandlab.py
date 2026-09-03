"""Unofficial Studio import provider; fixture verified, live selectors operator calibrated."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from createrelay.providers.base import ProviderRefused

FIXTURE_SELECTORS: dict[str, list[dict[str, str]]] = {
    "studio": [{"method": "role", "role": "main", "name": "Studio"}],
    "project_name": [{"method": "label", "name": "Project name"}],
    "new_project": [{"method": "role", "role": "button", "name": "New Project"}],
    "open_project": [{"method": "role", "role": "button", "name": "Open Project"}],
    "tempo": [{"method": "label", "name": "Tempo"}],
    "import": [
        {"method": "label", "name": "Import Audio/MIDI"},
        {"method": "css", "value": 'input[type="file"][accept=".mid,.midi,.wav"]'},
    ],
    "save": [{"method": "role", "role": "button", "name": "Save"}],
    "save_status": [{"method": "label", "name": "Save status"}],
    "track": [{"method": "label", "name": "Track"}],
    "track_name": [{"method": "label", "name": "Track name"}],
    "instrument": [{"method": "label", "name": "Instrument"}],
    "offset": [{"method": "label", "name": "Offset seconds"}],
    "muted": [{"method": "label", "name": "Muted"}],
    "region": [{"method": "label", "name": "Region"}],
}


def _browser_binary(channel: str) -> Path:
    """Only installed vendor locations, never an executable supplied by a workflow."""
    relative = {
        "chrome": "Google/Chrome/Application/chrome.exe",
        "msedge": "Microsoft/Edge/Application/msedge.exe",
    }.get(channel)
    if relative is None:
        raise ProviderRefused("Browser channel must be chrome or msedge")
    for base in (
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if base and (Path(base) / relative).is_file():
            return (Path(base) / relative).resolve()
    raise ProviderRefused(
        f"Installed {channel} executable was not found in vendor locations"
    )


def _connect_dedicated(
    playwright: Any, profile: Path, channel: str
) -> tuple[Any, Any, dict[str, Any]]:
    """Attach only to an exact dedicated profile, or launch a detached vendor browser.

    The browser outlives the CLI, preserving unsaved work after failure. CDP binds
    only to loopback; the session token requirement applies to the separate MCP
    server. OS-user processes can access this dedicated debugging port while open.
    """
    import psutil

    binary = _browser_binary(channel)
    profile = profile.resolve()
    if any((parent / ".git").exists() for parent in [profile, *profile.parents]):
        raise ProviderRefused("Dedicated browser profile must be outside Git")
    profile.mkdir(parents=True, exist_ok=True)
    marker = f"--user-data-dir={profile}"
    process = None
    for candidate in psutil.process_iter(["pid", "name"]):
        if candidate.info["name"].lower() != binary.name.lower():
            continue
        try:
            arguments = candidate.cmdline()
            if (
                marker.lower() in [argument.lower() for argument in arguments]
                and not any(argument.startswith("--type=") for argument in arguments)
                and Path(candidate.exe()).resolve() == binary
            ):
                process = candidate
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    active_port = profile / "DevToolsActivePort"
    if active_port.exists() and active_port.resolve().parent != profile:
        raise ProviderRefused(
            "Dedicated profile debugging metadata escaped the profile directory"
        )
    old_mtime = active_port.stat().st_mtime_ns if active_port.exists() else None
    launched = process is None
    if process is not None and not any(
        argument.startswith("--remote-debugging-port=")
        for argument in process.cmdline()
    ):
        raise ProviderRefused(
            "This dedicated profile is open without debugging; close it and retry"
        )
    if launched:
        child = subprocess.Popen(
            [
                str(binary),
                marker,
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            if os.name == "nt"
            else 0,
            close_fds=True,
        )
        process = psutil.Process(child.pid)
    deadline = time.monotonic() + 20
    port = None
    while time.monotonic() < deadline:
        if active_port.is_file() and (
            not launched or active_port.stat().st_mtime_ns != old_mtime
        ):
            lines = active_port.read_text(encoding="ascii").splitlines()
            if (
                len(lines) >= 2
                and lines[0].isdigit()
                and lines[1].startswith("/devtools/browser/")
            ):
                port = int(lines[0])
                if 1 <= port <= 65535:
                    break
        time.sleep(0.1)
    if port is None:
        raise ProviderRefused(
            "Dedicated browser did not expose its local debugging port; close that profile and retry"
        )
    browser = playwright.chromium.connect_over_cdp(
        f"http://127.0.0.1:{port}", timeout=10000
    )
    context = browser.contexts[0]
    # Vendor launchers can exit after spawning the actual browser process.
    # Re-identify the running root process after CDP is ready, never log the bootstrap PID.
    process = None
    for candidate in psutil.process_iter(["pid", "name"]):
        if candidate.info["name"].lower() != binary.name.lower():
            continue
        try:
            arguments = candidate.cmdline()
            if (
                marker.lower() in [argument.lower() for argument in arguments]
                and any(
                    argument.startswith("--remote-debugging-port=")
                    for argument in arguments
                )
                and not any(argument.startswith("--type=") for argument in arguments)
                and Path(candidate.exe()).resolve() == binary
            ):
                process = candidate
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if process is None:
        raise ProviderRefused("Dedicated browser process identity was unavailable")
    identity = {
        "process_id": process.pid,
        "executable": str(binary),
        "dedicated_profile": str(profile),
        "debugging_host": "127.0.0.1",
    }
    return browser, context, identity


def bandlab_login(profile_name: str = "bandlab", channel: str = "chrome") -> None:
    """Explicit normal browser login: the operator enters credentials only in the browser."""
    from playwright.sync_api import sync_playwright

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", profile_name):
        raise ValueError("Profile must be a simple local name")
    profile = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "CreateRelay"
        / "profiles"
        / profile_name
    )
    with sync_playwright() as playwright:
        _, context, _ = _connect_dedicated(playwright, profile, channel)
        page = context.new_page()
        page.goto("https://www.bandlab.com", wait_until="domcontentloaded")
        input(
            "Sign in normally in the dedicated browser. No credentials are read. Press Enter here when finished: "
        )
        page.close()
    # Disconnect only. Other Studio tabs and the dedicated browser remain open.


class BandLabProvider:
    """Bounded operations in one dedicated page; all observations stay local."""

    name = "bandlab"
    operations = frozenset(
        {
            "open_studio",
            "create_project",
            "open_project",
            "set_tempo",
            "import_file",
            "configure_track",
            "save",
        }
    )
    effect_tier = (
        4  # Same-page UI readback, never represented as independent persistence.
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.mode = self.config.get("mode", "fixture")
        if self.mode not in {"fixture", "live"}:
            raise ValueError("BandLab mode must be fixture or live")
        self.url = self.config.get("url", "")
        parsed = urlparse(self.url)
        if self.mode == "fixture":
            if parsed.scheme != "http" or parsed.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("Fixture URL must be an explicit localhost HTTP URL")
            self.selectors = {**FIXTURE_SELECTORS, **self.config.get("selectors", {})}
        else:
            if parsed.scheme != "https" or parsed.hostname != "www.bandlab.com":
                raise ValueError("Live URL must use https://www.bandlab.com")
            self.selectors = self.config.get("selectors", {})
            if not self.config.get("selectors_reviewed"):
                raise ValueError(
                    "Live operation requires reviewed local selector calibration"
                )
        self.origin = (parsed.scheme, parsed.hostname, parsed.port)
        self.read_roots = [
            Path(path).resolve(strict=True)
            for path in self.config.get("read_roots", [])
        ]
        self.timeout_ms = min(max(int(self.config.get("timeout_ms", 5000)), 100), 60000)
        self._playwright: Any = None
        self._context: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._attempts: list[dict[str, Any]] = []
        self._imported: dict[str, list[int]] = {}
        self._failed = False
        self._process_identity: dict[str, Any] = {}

    def _open(self) -> None:
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        if self.mode == "fixture":
            self._browser = self._playwright.chromium.launch(
                headless=self.config.get("headless", True)
            )
            self._context = self._browser.new_context()
        else:
            profile = Path(
                self.config.get("profile_dir")
                or Path(os.environ.get("LOCALAPPDATA", Path.home()))
                / "CreateRelay"
                / "profiles"
                / "bandlab"
            ).resolve()
            # Dedicated profiles must not be stored under a Git checkout.
            if any(
                (parent / ".git").exists() for parent in [profile, *profile.parents]
            ):
                raise ProviderRefused("Dedicated browser profile must be outside Git")
            channel = self.config.get("channel", "msedge")
            if channel not in {"chrome", "msedge"}:
                raise ProviderRefused("Live browser channel must be chrome or msedge")
            profile.mkdir(parents=True, exist_ok=True)
            self._browser, self._context, self._process_identity = _connect_dedicated(
                self._playwright, profile, channel
            )
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._page.goto(self.url, wait_until="domcontentloaded")

    def _check_identity(self) -> None:
        if self._page is None:
            raise ProviderRefused("Studio is not open")
        current = urlparse(self._page.url)
        if (current.scheme, current.hostname, current.port) != self.origin:
            raise ProviderRefused(
                "Page left the approved application origin; no input delivered"
            )
        if self.mode == "live" and not re.search(
            self.config.get("studio_path_pattern", r"^/(studio|mix-editor)(/|$)"),
            current.path,
        ):
            raise ProviderRefused(
                "Manual authentication required: sign in normally and open the requested Studio project"
            )
        self._resolve("studio")

    def _locator(self, root: Any, selector: dict[str, str]) -> Any:
        if selector["method"] == "role":
            return root.get_by_role(
                selector["role"], name=selector.get("name"), exact=True
            )
        if selector["method"] == "label":
            return root.get_by_label(selector["name"], exact=True)
        if selector["method"] == "text":
            return root.get_by_text(selector["name"], exact=True)
        if selector["method"] == "css":
            return root.locator(selector["value"])
        raise ProviderRefused(
            "Only DOM/ARIA/text/CSS selectors are supported by this adapter"
        )

    def _resolve(self, key: str, root: Any = None, *, multiple: bool = False) -> Any:
        root = root or self._page
        chain = self.selectors.get(key, [])
        # Config cannot put broad CSS ahead of the available semantic selectors.
        chain = sorted(chain, key=lambda item: item["method"] == "css")
        for selector in chain:
            candidate = self._locator(root, selector)
            count = candidate.count()
            self._attempts.append({"key": key, "selector": selector, "matches": count})
            if count > 1 and not multiple:
                raise ProviderRefused(
                    f"Ambiguous {key}: {count} matches; refusing arbitrary first match"
                )
            if (count == 1 or multiple) and (multiple or candidate.is_visible()):
                return candidate
        raise ProviderRefused(
            f"No unique visible {key} selector; recalibration checkpoint required"
        )

    def _file(self, args: dict[str, Any]) -> Path:
        path = Path(args["path"]).resolve(strict=True)
        if not any(path.is_relative_to(root) for root in self.read_roots):
            raise ProviderRefused("Import path is outside the approved read roots")
        if path.suffix.lower() not in {".mid", ".midi", ".wav"}:
            raise ProviderRefused("Only MIDI and WAV imports are allowed")
        if (
            not args.get("sha256")
            or hashlib.sha256(path.read_bytes()).hexdigest() != args["sha256"]
        ):
            raise ProviderRefused(
                "Media changed after manifest review; regenerate and review the manifest"
            )
        return path

    def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if operation not in self.operations:
            raise ProviderRefused("Unknown BandLab operation")
        if self._failed:
            raise ProviderRefused(
                "Previous delivery is uncertain; inspect the project and start a newly reviewed run"
            )
        self._attempts = []
        if operation == "open_studio":
            self._open()
            self._check_identity()
        else:
            self._check_identity()
            if operation in {"create_project", "open_project"}:
                name = self._resolve("project_name")
                button = self._resolve(
                    "new_project" if operation == "create_project" else "open_project"
                )
                # Creating in a populated Studio would discard work in the fixture and may replace it live.
                if (
                    operation == "create_project"
                    and self._resolve("track", multiple=True).count()
                ):
                    raise ProviderRefused(
                        "Project has existing tracks; create/open an empty project manually"
                    )
                name.fill(str(args["name"]))
                button.click()
            elif operation == "set_tempo":
                bpm = float(args["bpm"])
                if not 40 <= bpm <= 240:
                    raise ProviderRefused("Tempo outside calibrated 40-240 BPM range")
                target = self._resolve("tempo")
                target.fill(str(bpm))
                target.press("Tab")
            elif operation == "import_file":
                path = self._file(args)
                expected = int(args["expected_tracks"])
                rows = self._resolve("track", multiple=True)
                before = rows.count()
                if before + expected > int(self.config.get("track_limit", 16)):
                    raise ProviderRefused(
                        "Import would exceed configured project track limit"
                    )
                digest = args["sha256"]
                if digest in self._imported:
                    raise ProviderRefused(
                        "This manifest file was already imported in this session; inspect before replay"
                    )
                target = self._resolve("import")
                target.set_input_files(str(path))
                # This wait is bounded. A timeout after delivery is uncertain and never auto-retried.
                from playwright.sync_api import expect

                try:
                    expect(rows).to_have_count(
                        before + expected, timeout=self.timeout_ms
                    )
                    for index in range(before, before + expected):
                        if (
                            self._resolve(
                                "region", rows.nth(index), multiple=True
                            ).count()
                            < 1
                        ):
                            raise RuntimeError(
                                "Imported track has no independently visible region"
                            )
                except Exception:
                    self._failed = True
                    raise
                self._imported[digest] = list(range(before, before + expected))
            elif operation == "configure_track":
                rows = self._resolve("track", multiple=True)
                index = int(args["index"])
                if index < 0 or index >= rows.count():
                    raise ProviderRefused(
                        "Track index is outside observed imported tracks"
                    )
                row = rows.nth(index)
                targets = {
                    key: self._resolve(selector, row)
                    for key, selector in [
                        ("name", "track_name"),
                        ("instrument", "instrument"),
                        ("offset_seconds", "offset"),
                        ("muted", "muted"),
                    ]
                    if key in args
                }
                if "name" in targets:
                    targets["name"].fill(str(args["name"]))
                if "instrument" in targets:
                    targets["instrument"].select_option(label=str(args["instrument"]))
                if "offset_seconds" in targets:
                    targets["offset_seconds"].fill(str(float(args["offset_seconds"])))
                if "muted" in targets:
                    targets["muted"].set_checked(bool(args["muted"]))
            elif operation == "save":
                self._resolve("save").click()
                from playwright.sync_api import expect

                try:
                    expect(self._resolve("save_status")).to_have_text(
                        self.config.get("saved_text", "Saved"), timeout=self.timeout_ms
                    )
                except Exception:
                    self._failed = True
                    raise
        action_key = {
            "open_studio": "studio",
            "create_project": "new_project",
            "open_project": "open_project",
            "set_tempo": "tempo",
            "import_file": "import",
            "configure_track": next(
                (
                    selector
                    for field, selector in [
                        ("name", "track_name"),
                        ("instrument", "instrument"),
                        ("offset_seconds", "offset"),
                        ("muted", "muted"),
                    ]
                    if field in args
                ),
                "track",
            ),
            "save": "save",
        }[operation]
        successful = next(
            (
                attempt
                for attempt in reversed(self._attempts)
                if attempt["matches"] == 1 and attempt["key"] == action_key
            ),
            {},
        )
        return {
            "action": operation,
            "delivered": True,
            "selector_chain": self._attempts,
            "selector_method": successful.get("selector", {}).get("method", "dom"),
            "window": {
                "url": self._page.url,
                "title": self._page.title(),
                "origin_verified": True,
                "browser_channel": self.config.get("channel", "chromium"),
                "dedicated_page": True,
                **self._process_identity,
            },
            "confidence": 1.0,
            "fallback_used": successful.get("selector", {}).get("method") == "css",
            "verification": "Fresh provider effect observation follows",
            "fixture": self.mode == "fixture",
        }

    def inspect(self) -> dict[str, Any]:
        if self._page is None:
            return {"studio_ready": False, "track_count": 0, "saved": False}
        self._check_identity()
        rows = self._resolve("track", multiple=True)
        state: dict[str, Any] = {
            "studio_ready": True,
            "track_count": rows.count(),
            "project_name": self._resolve("project_name").input_value(),
            "tempo": float(self._resolve("tempo").input_value()),
            "saved": self._resolve("save_status").inner_text().strip()
            == self.config.get("saved_text", "Saved"),
            "url": self._page.url,
            "tracks": [],
        }
        for index in range(rows.count()):
            row = rows.nth(index)
            track = {
                "name": self._resolve("track_name", row).input_value(),
                "instrument": self._resolve("instrument", row).input_value(),
                "offset_seconds": float(self._resolve("offset", row).input_value()),
                "muted": self._resolve("muted", row).is_checked(),
                "region_count": self._resolve("region", row, multiple=True).count(),
            }
            state["tracks"].append(track)
            for field, value in track.items():
                state[f"track_{index}_{field}"] = value
        return state

    def close(self) -> None:
        # Preserve unsaved live browser state for user recovery; stop control, not the user's app.
        if self.mode == "live" and self._page is not None:
            if self._playwright is not None:
                self._playwright.stop()
            self._page = self._context = self._browser = self._playwright = None
            return
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None


def build_bandlab_workflow(
    manifest: dict[str, Any],
    *,
    url: str,
    project_name: str = "CreateRelay Import",
    mode: str = "fixture",
    provider_config: dict[str, Any] | None = None,
    project_action: str = "create",
    existing_track_count: int = 0,
) -> dict[str, Any]:
    """Build an ordinary native Flow document; the existing Replayer executes it."""
    from openadapt_flow.ir import ActionKind, ApiBinding, Step, Workflow
    from openadapt_flow.runtime.effects.effect import Effect

    if not manifest.get("imports"):
        raise ValueError("Manifest has no nonempty MIDI files to import")
    if mode == "live" and not manifest.get("reviewed"):
        raise ValueError(
            "Live import requires a reviewed manifest (set reviewed=true after inspection)"
        )
    if project_action not in {"create", "open"}:
        raise ValueError("project_action must be create or open")
    if existing_track_count < 0 or (
        project_action == "create" and existing_track_count
    ):
        raise ValueError("Existing tracks require an explicit open-project workflow")
    if (
        existing_track_count + manifest["expected_track_count"]
        > manifest["configuration"]["track_limit"]
    ):
        raise ValueError(
            "Existing project plus imports would exceed configured track limit"
        )
    roots = [manifest["source_folder"]]
    if manifest.get("reference"):
        roots.append(str(Path(manifest["reference"]["path"]).parent))
    config = {
        "mode": mode,
        "url": url,
        "read_roots": roots,
        "track_limit": manifest["configuration"]["track_limit"],
        "manual_review": list(manifest.get("manual_review", [])),
        **(provider_config or {}),
    }
    steps: list[Step] = []

    def add(operation: str, args: dict[str, Any], **effects: Any) -> None:
        steps.append(
            Step(
                id=f"{len(steps) + 1:02d}_{operation}",
                intent=operation.replace("_", " "),
                action=ActionKind.WAIT,
                api_binding=ApiBinding(
                    kind="tool",
                    url_template="bandlab",
                    method=operation,
                    body_template=args,
                    on_unavailable="halt",
                    effects=[
                        Effect.model_validate(
                            {
                                "kind": "field_equals",
                                "match": {"provider": "bandlab"},
                                "field": field,
                                "value": str(value),
                                "timeout_s": 5,
                            }
                        )
                        for field, value in effects.items()
                    ],
                ),
            )
        )

    add("open_studio", {}, studio_ready=True)
    add(
        "create_project" if project_action == "create" else "open_project",
        {"name": project_name},
        project_name=project_name,
        track_count=existing_track_count,
    )
    if manifest.get("project_tempo") is not None:
        add(
            "set_tempo",
            {"bpm": manifest["project_tempo"]},
            tempo=float(manifest["project_tempo"]),
        )
    count = existing_track_count
    reference = manifest.get("reference")
    if reference:
        add(
            "import_file",
            {key: reference[key] for key in ("path", "sha256", "expected_tracks")},
            track_count=count + 1,
        )
        count += 1
        add(
            "configure_track",
            {
                "index": count - 1,
                "name": reference["name"],
                "offset_seconds": reference["offset_seconds"],
            },
            **{
                f"track_{count - 1}_name": reference["name"],
                f"track_{count - 1}_offset_seconds": float(reference["offset_seconds"]),
            },
        )
    for item in manifest["imports"]:
        count += item["expected_tracks"]
        add(
            "import_file",
            {key: item[key] for key in ("path", "sha256", "expected_tracks")},
            track_count=count,
        )
        for index, settings in enumerate(
            item["track_settings"], start=count - item["expected_tracks"]
        ):
            add(
                "configure_track",
                {"index": index, **settings},
                **{
                    f"track_{index}_{field}": value for field, value in settings.items()
                },
            )
    if reference and reference["muted"]:
        add(
            "configure_track",
            {"index": existing_track_count, "muted": True},
            **{f"track_{existing_track_count}_muted": True},
        )
    add("save", {}, saved=True, track_count=count)
    return {
        "schema_version": "createrelay/v1",
        "id": "bandlab-import",
        "application": "bandlab",
        "description": "Import reviewed MIDI with verified track/region effects; unofficial integration",
        "configuration": {"bandlab": config},
        "workflow": Workflow(
            name="BandLab MIDI import",
            steps=steps,
            created_at=manifest.get("created_at", "1970-01-01T00:00:00+00:00"),
        ).model_dump(mode="json"),
    }


def save_workflow(document: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(document, indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )
