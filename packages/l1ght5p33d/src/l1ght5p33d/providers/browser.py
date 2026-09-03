"""Semantic browser actions bound to a dedicated browser context and origin."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from l1ght5p33d.providers.base import ProviderRefused


class BrowserProvider:
    name = "browser"
    operations = frozenset({"fill", "click", "select", "upload", "wait"})
    effect_tier = 4

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._pw = sync_playwright().start()
        channel = config.get("channel")
        if channel not in {None, "chrome", "msedge"}:
            raise ValueError("Browser channel must be chrome, msedge or omitted")
        self._browser = None
        if profile := config.get("profile"):
            self.context = self._pw.chromium.launch_persistent_context(
                str(Path(profile).resolve()),
                channel=channel,
                headless=config.get("headless", False),
                accept_downloads=False,
            )
        else:
            self._browser = self._pw.chromium.launch(
                channel=channel, headless=config.get("headless", True)
            )
            self.context = self._browser.new_context(accept_downloads=False)
        self.page = (
            self.context.pages[0] if self.context.pages else self.context.new_page()
        )
        self.page.set_default_timeout(min(float(config.get("timeout_s", 5)), 60) * 1000)
        self.page.goto(config["url"], wait_until="domcontentloaded")
        self._origin = self._url_origin(config["url"])
        self.last_receipt: dict[str, Any] = {}
        self._guard()

    @staticmethod
    def _url_origin(url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        return parsed.scheme, parsed.netloc

    def _guard(self) -> None:
        if self.page.is_closed() or self._url_origin(self.page.url) != self._origin:
            raise ProviderRefused(
                "Expected dedicated browser application is no longer active"
            )
        if not re.search(self.config.get("title_pattern", ".+"), self.page.title()):
            raise ProviderRefused(
                "Browser title does not match the approved application"
            )
        if len(self.context.pages) != 1:
            raise ProviderRefused(
                "Unexpected browser popup: inspect the dedicated session"
            )

    def _locator(self, selector: dict[str, Any]) -> Any:
        kind = selector["kind"]
        if kind == "role":
            return self.page.get_by_role(
                selector["role"], name=selector["name"], exact=True
            )
        if kind == "label":
            return self.page.get_by_label(selector["name"], exact=True)
        if kind == "test_id":
            return self.page.get_by_test_id(selector["value"])
        if kind == "css":
            return self.page.locator(selector["value"])
        raise ValueError("Browser selector must use role, label, test_id or css")

    def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        self._guard()
        if operation not in self.operations:
            raise ValueError("Unsupported browser operation")
        selectors = args.get("selectors", [])
        if not selectors:
            raise ValueError("A nonempty selector chain is required")
        attempted = []
        target = None
        for selector in selectors:
            attempted.append(selector)
            locator = self._locator(selector)
            count = locator.count()
            if count > 1:
                raise ProviderRefused(
                    "Ambiguous semantic selector; weaker fallback is unsafe"
                )
            try:
                locator.wait_for(
                    state="attached" if operation == "upload" else "visible",
                    timeout=750,
                )
            except PlaywrightTimeout:
                continue
            target = locator
            break
        if target is None:
            raise ProviderRefused("Selector chain exhausted before input delivery")
        self._guard()
        # Only selector discovery retries. Once input starts, do not try another target.
        if operation == "fill":
            target.fill(str(args["text"]))
        elif operation == "click":
            target.click()
        elif operation == "select":
            target.select_option(label=str(args["label"]))
        elif operation == "upload":
            target.set_input_files(args["files"])
        elif operation == "wait":
            target.wait_for(state="visible")
        self.last_receipt = {
            "application": self.inspect_identity(),
            "requested_action": operation,
            "selector_chain": attempted,
            "selector_method": attempted[-1]["kind"],
            "fallback_used": len(attempted) > 1,
            "confidence": 1.0,
            "input_delivered": operation != "wait",
            "verification": "pending readback",
        }
        return self.last_receipt

    def inspect_identity(self) -> dict[str, Any]:
        return {
            "title": self.page.title(),
            "url": self.page.url,
            "context_pages": len(self.context.pages),
            "target": "dedicated Playwright Page",
            "channel": self.config.get("channel", "chromium"),
        }

    def inspect(self) -> dict[str, Any]:
        self._guard()
        # Fixed program-owned observation. No workflow-supplied JavaScript or secrets.
        state = self.page.evaluate("""() => {
          const state = {title: document.title, heading: document.querySelector('h1')?.textContent || ''};
          for (const el of document.querySelectorAll('input,textarea,select,output,[role=status]')) {
            if (el.type === 'password') continue;
            const key = el.getAttribute('data-state') || el.name || el.id;
            if (key && !/secret|password|token|cookie/i.test(key)) state[key] = el.value ?? el.textContent;
          }
          return state;
        }""")
        return {**state, "provider": self.name}

    def close(self) -> None:
        self.context.close()
        if self._browser:
            self._browser.close()
        self._pw.stop()
