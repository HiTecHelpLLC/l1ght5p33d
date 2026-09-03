"""Windows UIA provider with fail-closed native identity and local fallbacks.

This provider attaches to an application the operator opened. It has no shell,
process-launch, credentials, network, or screenshot-export operation.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .base import ProviderRefused
from .vision import VisualSelectorError, match_template, match_text, template_path


@dataclass(frozen=True)
class WindowIdentity:
    executable: str
    process_id: int
    hwnd: int
    title: str
    class_name: str
    bounds: tuple[int, int, int, int]
    display: str
    monitor_bounds: tuple[int, int, int, int]
    dpi: int
    foreground: bool
    monitor_dpi: tuple[int, int] = (96, 96)


class WindowsProvider:
    name = "windows"
    effect_tier = 4
    operations = frozenset({"fill", "click", "read", "assert_text"})

    def __init__(self, configuration: dict[str, Any]) -> None:
        self.config = dict(configuration)
        self._hwnd: int | None = None
        self._pid: int | None = None
        self._create_time: float | None = None
        self._last_receipt: dict[str, Any] | None = None
        self._com_thread = threading.local()
        if not self.config.get("executable") or not self.config.get("title_re"):
            raise ProviderRefused(
                "Windows configuration requires executable and title_re"
            )
        self.executable = os.path.normcase(
            str(Path(self.config["executable"]).resolve())
        )
        self.title_pattern = re.compile(self.config["title_re"])

    def _platform(self) -> None:
        if sys.platform != "win32":
            raise ProviderRefused(
                "The Windows provider requires an interactive Windows desktop"
            )
        if not getattr(self._com_thread, "initialized", False):
            import pythoncom

            try:
                pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            except Exception as exc:
                raise ProviderRefused(
                    "Windows UIA requires a dedicated COM-compatible worker thread"
                ) from exc
            self._com_thread.initialized = True

    def _identity(self, window: Any) -> WindowIdentity:
        import ctypes

        import psutil
        import win32api
        import win32gui

        native_libraries: Any
        if sys.platform == "win32":
            native_libraries = ctypes.windll
        else:
            raise ProviderRefused("Native window identity requires Windows")

        pid = window.process_id()
        hwnd = int(window.handle)
        process = psutil.Process(pid)
        rect = tuple(int(n) for n in win32gui.GetWindowRect(hwnd))
        monitor_handle = win32api.MonitorFromWindow(hwnd, 2)
        monitor = win32api.GetMonitorInfo(monitor_handle)
        dpi_x, dpi_y = ctypes.c_uint(0), ctypes.c_uint(0)
        monitor_dpi_function = native_libraries.shcore.GetDpiForMonitor
        monitor_dpi_function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        monitor_dpi_function.restype = ctypes.c_long
        if (
            monitor_dpi_function(
                int(monitor_handle), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            )
            != 0
        ):
            raise ProviderRefused("Cannot inspect monitor DPI")
        dpi_function = native_libraries.user32.GetDpiForWindow
        dpi_function.argtypes = [ctypes.c_void_p]
        dpi_function.restype = ctypes.c_uint
        return WindowIdentity(
            executable=os.path.normcase(str(Path(process.exe()).resolve())),
            process_id=pid,
            hwnd=hwnd,
            title=win32gui.GetWindowText(hwnd),
            class_name=win32gui.GetClassName(hwnd),
            bounds=rect,  # type: ignore[arg-type]
            display=monitor["Device"],
            monitor_bounds=tuple(monitor["Monitor"]),
            dpi=int(dpi_function(hwnd)),
            foreground=win32gui.GetForegroundWindow() == hwnd,
            monitor_dpi=(dpi_x.value, dpi_y.value),
        )

    def _window(self, *, require_foreground: bool = True) -> tuple[Any, WindowIdentity]:
        self._platform()
        import psutil
        import win32gui
        import win32process
        from pywinauto import Desktop

        try:
            desktop = Desktop(backend="uia", allow_magic_lookup=False)
            # Enumerate native handles first. Traversing the entire desktop UIA
            # tree can invoke unrelated applications' broken COM providers.
            # Only the already-authorized process crosses into UIA below.
            handles: list[int] = []
            win32gui.EnumWindows(lambda hwnd, _: handles.append(hwnd), None)
            matching: list[tuple[Any, WindowIdentity]] = []
            for hwnd in handles:
                if not win32gui.IsWindowVisible(hwnd):
                    continue
                if self._hwnd is not None and hwnd != self._hwnd:
                    continue
                if self.config.get("hwnd") and hwnd != int(self.config["hwnd"]):
                    continue
                if not self.title_pattern.fullmatch(win32gui.GetWindowText(hwnd)):
                    continue
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if self.config.get("process_id") and pid != int(
                    self.config["process_id"]
                ):
                    continue
                if (
                    os.path.normcase(str(Path(psutil.Process(pid).exe()).resolve()))
                    != self.executable
                ):
                    continue
                candidate = desktop.window(handle=hwnd).wrapper_object()
                identity = self._identity(candidate)
                if identity.executable == self.executable:
                    matching.append((candidate, identity))
            if len(matching) != 1:
                raise ProviderRefused(
                    f"Expected one authorized window; found {len(matching)}"
                )
            window, identity = matching[0]
            created = psutil.Process(identity.process_id).create_time()
            if self._pid is not None and (
                identity.process_id != self._pid or created != self._create_time
            ):
                raise ProviderRefused(
                    "Attached process identity changed; start a new authorized run"
                )
            if require_foreground and not identity.foreground:
                raise ProviderRefused(
                    "Authorized window is not foreground; focus it manually and resume"
                )
            if (
                identity.dpi <= 0
                or identity.bounds[2] <= identity.bounds[0]
                or identity.bounds[3] <= identity.bounds[1]
            ):
                raise ProviderRefused("Authorized window has invalid bounds or DPI")
            expected_dpi = self.config.get("dpi")
            if expected_dpi is not None and identity.dpi != int(expected_dpi):
                raise ProviderRefused(
                    "DPI changed since calibration; recalibrate before visual actions"
                )
            self._hwnd, self._pid, self._create_time = (
                identity.hwnd,
                identity.process_id,
                created,
            )
            return window, identity
        except ProviderRefused:
            raise
        except Exception as exc:
            raise ProviderRefused(
                f"Cannot inspect authorized Windows target: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _semantic(window: Any, selector: dict[str, Any]) -> Any | None:
        method = selector.get("method", "uia")
        allowed = {
            "auto_id",
            "title",
            "title_re",
            "control_type",
            "class_name",
            "control_id",
        }
        criteria = {key: value for key, value in selector.items() if key != "method"}
        if not criteria or set(criteria) - allowed:
            raise ProviderRefused(
                "Semantic selector must contain only documented UIA/Win32 fields"
            )
        if method == "win32":
            from pywinauto import Desktop

            window = (
                Desktop(backend="win32").window(handle=window.handle).wrapper_object()
            )
        matches = [
            control
            for control in window.descendants(**criteria)
            if control.is_visible()
        ]
        if len(matches) > 1:
            raise ProviderRefused("Selector is ambiguous; no fallback or input is safe")
        return matches[0] if matches else None

    @staticmethod
    def _text(control: Any) -> str:
        if control.element_info.control_type == "Edit":
            try:
                return str(control.get_value())
            except (AttributeError, NotImplementedError):
                pass
        return str(control.window_text())

    @staticmethod
    def _png(window: Any) -> bytes:
        output = io.BytesIO()
        window.capture_as_image().save(output, format="PNG")
        return output.getvalue()

    def _resolve(
        self, window: Any, identity: WindowIdentity, selectors: Any
    ) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(selectors, list) or not selectors or len(selectors) > 8:
            raise ProviderRefused("A bounded selector chain is required")
        order = {"uia": 0, "win32": 1, "ocr": 2, "template": 2, "relative": 3}
        previous = -1
        attempts: list[dict[str, Any]] = []
        for selector in selectors:
            if not isinstance(selector, dict):
                raise ProviderRefused("Selectors must be JSON objects")
            method = selector.get("method", "uia")
            if method not in order or order[method] < previous:
                raise ProviderRefused(
                    "Selectors must use UIA/Win32 before visual and relative fallback"
                )
            if previous == -1 and method not in {"uia", "win32"}:
                raise ProviderRefused(
                    "The selector chain must attempt a semantic selector first"
                )
            previous = order[method]
            attempt: dict[str, Any] = {
                "selector": selector,
                "method": method,
                "result": "not_found",
            }
            attempts.append(attempt)
            if method in {"uia", "win32"}:
                control = self._semantic(window, selector)
                if control is not None:
                    if not control.is_enabled():
                        raise ProviderRefused("Selected control is disabled")
                    attempt["result"] = "matched"
                    return (
                        control,
                        {"selector_method": method, "confidence": 1.0},
                        attempts,
                    )
            elif method in {"ocr", "template"}:
                # Capture after the semantic miss; no cross-action screenshot cache.
                _, fresh = self._window()
                if fresh.bounds != identity.bounds or fresh.dpi != identity.dpi:
                    raise ProviderRefused(
                        "Window geometry changed during target resolution"
                    )
                png = self._png(window)
                threshold = float(selector.get("confidence", 0.95))
                try:
                    if method == "ocr":
                        match = match_text(
                            png, str(selector.get("text", "")), threshold=threshold
                        )
                    else:
                        if not self.config.get("template_root"):
                            raise ProviderRefused(
                                "Visual templates require a local calibration root"
                            )
                        path = template_path(
                            Path(self.config["template_root"]),
                            str(selector.get("template", "")),
                        )
                        match = match_template(
                            png, path.read_bytes(), threshold=threshold
                        )
                except (VisualSelectorError, OSError) as exc:
                    raise ProviderRefused(str(exc)) from exc
                if match is not None:
                    attempt["result"] = "matched"
                    return (
                        None,
                        {
                            "selector_method": method,
                            "confidence": match.confidence,
                            "point": match.point,
                            "matched_region": match.region,
                        },
                        attempts,
                    )
            else:
                if (
                    not self.config.get("allow_relative", False)
                    or selector.get("anchor") != "window"
                ):
                    raise ProviderRefused(
                        "Relative fallback requires explicit policy and a verified-window anchor"
                    )
                x, y = float(selector["x"]), float(selector["y"])
                if not 0 < x < 1 or not 0 < y < 1:
                    raise ProviderRefused(
                        "Relative target must be strictly inside the verified window"
                    )
                width, height = (
                    identity.bounds[2] - identity.bounds[0],
                    identity.bounds[3] - identity.bounds[1],
                )
                attempt["result"] = "matched"
                return (
                    None,
                    {
                        "selector_method": "relative",
                        "confidence": None,
                        "point": (int(x * width), int(y * height)),
                    },
                    attempts,
                )
        raise ProviderRefused(
            "No declared selector matched; inspect UI state and propose a reviewed patch"
        )

    def _point_guard(self, point: tuple[int, int], identity: WindowIdentity) -> None:
        import win32gui

        x, y = point
        left, top, right, bottom = identity.bounds
        if not left <= x < right or not top <= y < bottom:
            raise ProviderRefused("Input point escaped the authorized window")
        hit = win32gui.WindowFromPoint(point)
        if win32gui.GetAncestor(hit, 2) != identity.hwnd:
            raise ProviderRefused("Another window occludes the input target")

    def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if operation not in self.operations:
            raise ProviderRefused(f"Unsupported Windows operation: {operation}")
        started = time.monotonic()
        window, before = self._window()
        control, resolved, attempts = self._resolve(
            window, before, args.get("selectors")
        )
        _, current = self._window()
        if current.bounds != before.bounds or current.dpi != before.dpi:
            raise ProviderRefused(
                "Window moved while resolving the action; inspect and retry"
            )
        if operation in {"fill", "read", "assert_text"} and control is None:
            raise ProviderRefused(
                f"{operation} requires semantic readback; visual matches support click only"
            )
        verification: dict[str, Any] = {"performed": False}
        if operation in {"read", "assert_text"}:
            value = self._text(control)
            if operation == "assert_text" and value != str(args.get("text", "")):
                raise ProviderRefused(
                    "Observed control text does not equal expected text"
                )
            verification = {
                "performed": True,
                "method": "uia_readback",
                "value": value,
                "passed": True,
            }
        else:
            # Everything below this point may deliver input. Exceptions must be
            # treated by the runtime as uncertain delivery, never blind retries.
            if operation == "fill":
                if control.element_info.control_type != "Edit":
                    raise ProviderRefused(
                        "Fill is restricted to semantic Edit controls"
                    )
                value = str(args.get("text", ""))
                if len(value) > 100_000:
                    raise ProviderRefused(
                        "Fill text exceeds the 100000 character limit"
                    )
                control.set_edit_text(value)
                actual = self._text(control)
                if actual != value:
                    raise RuntimeError(
                        "Input delivered but Edit readback did not match"
                    )
                verification = {
                    "performed": True,
                    "method": "uia_value_readback",
                    "passed": True,
                }
            elif control is not None:
                rect = control.rectangle()
                self._point_guard((rect.mid_point().x, rect.mid_point().y), current)
                if (
                    resolved["selector_method"] == "uia"
                    and control.element_info.control_type == "Button"
                ):
                    # Native Invoke avoids mouse transit and preserves the
                    # semantic target. Its effect still requires readback.
                    control.invoke()
                else:
                    control.click_input()
            else:
                from pywinauto import mouse

                point = (
                    current.bounds[0] + resolved["point"][0],
                    current.bounds[1] + resolved["point"][1],
                )
                self._point_guard(point, current)
                mouse.click(coords=point)
            if args.get("verify"):
                spec = args["verify"]
                deadline = time.monotonic() + min(
                    max(float(spec.get("timeout_s", 3)), 0), 15
                )
                while True:
                    try:
                        fresh_window, _ = self._window()
                        check = self._semantic(fresh_window, spec["selector"])
                        passed = check is not None and self._text(check) == str(
                            spec["text"]
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "Input delivered; verification could not inspect the authorized window"
                        ) from exc
                    if passed:
                        verification = {
                            "performed": True,
                            "method": "independent_control_readback",
                            "passed": True,
                        }
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Input delivered but its declared postcondition was not observed"
                        )
                    time.sleep(0.05)
        result = {
            "action": operation,
            "window": asdict(current),
            "selector_chain": attempts,
            **resolved,
            "verification": verification,
            "result": "verified"
            if verification["performed"]
            else "delivered_unverified",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
        self._last_receipt = result
        return result

    def inspect(self) -> dict[str, Any]:
        window, identity = self._window()
        state: dict[str, Any] = {"window": asdict(identity)}
        for name, selector in self.config.get("observables", {}).items():
            if name in {"provider", "window"}:
                raise ProviderRefused("Observable name is reserved")
            control = self._semantic(window, selector)
            state[name] = self._text(control) if control is not None else None
        return state

    def calibrate(
        self, destination: Path, *, theme: str = "unspecified"
    ) -> dict[str, Any]:
        """Explicit local metadata only; caller controls the output permission."""
        _, identity = self._window()
        result = {
            "schema_version": "l1ght5p33d/calibration/v1",
            "window": asdict(identity),
            "theme": theme,
            "browser_zoom": None,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2), encoding="ascii")
        return result

    def close(self) -> None:
        """Release attachment state without closing the user's application."""
        self._hwnd = self._pid = None
        self._create_time = None
        if getattr(self._com_thread, "initialized", False):
            import pythoncom

            pythoncom.CoUninitialize()
            self._com_thread.initialized = False
