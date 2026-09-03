"""Narrow provider bindings for the existing OpenAdapt Flow interpreter.

Providers are trusted installed Python code. Workflows select registered names;
they cannot import code, evaluate expressions, or invoke a shell.
"""

from __future__ import annotations

import copy
import re
import string
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from openadapt_flow.ir import ApiBinding
from openadapt_flow.runtime.actuators import (
    ActuationStatus,
    ApiActuationResult,
    ApiHaltKind,
)
from openadapt_flow.runtime.effects._common import judge_records
from openadapt_flow.runtime.effects.effect import Effect, EffectState, EffectVerdict
from openadapt_flow.verification import VerificationTier

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ProviderRefused(RuntimeError):
    """A provider proved no input was delivered and refused the operation."""


class Provider(Protocol):
    name: str
    operations: frozenset[str]
    effect_tier: int

    def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]: ...

    def inspect(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


PolicyCheck = Callable[[str, str, dict[str, Any]], None]


def substitute(value: Any, params: Mapping[str, Any]) -> Any:
    """Bind named scalars without Python format attribute/index traversal."""
    if isinstance(value, str):
        fields = list(string.Formatter().parse(value))
        for _, field, spec, conversion in fields:
            if field is not None and (
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field) or spec or conversion
            ):
                raise ProviderRefused(
                    "Only simple named parameter placeholders are allowed"
                )
        if len(fields) == 1 and fields[0][0] == "" and fields[0][1] is not None:
            return params[fields[0][1]]
        return value.format_map(dict(params))
    if isinstance(value, dict):
        return {key: substitute(item, params) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, params) for item in value]
    return value


class ToolActuator:
    """Translate Flow tool bindings into registered operations, exactly once."""

    substrate = "l1ght5p33d_tool"

    def __init__(
        self,
        providers: Mapping[str, Provider],
        *,
        policy_check: PolicyCheck | None = None,
    ) -> None:
        self.providers = dict(providers)
        self.policy_check = policy_check
        self.last_receipt: dict[str, Any] = {}
        for name, provider in self.providers.items():
            if not NAME.fullmatch(name) or provider.name != name:
                raise ValueError(
                    "Provider registry names must match their implementation"
                )

    def actuate(
        self, binding: ApiBinding, params: Mapping[str, Any]
    ) -> ApiActuationResult:
        self.last_receipt = {}
        summary = f"{binding.url_template}.{binding.method}"
        try:
            if (
                binding.kind != "tool"
                or binding.on_unavailable != "halt"
                or not NAME.fullmatch(binding.url_template)
                or not NAME.fullmatch(binding.method)
                or binding.headers
                or binding.query
            ):
                raise ProviderRefused(
                    "Only named fail-closed local tool bindings are allowed"
                )
            provider = self.providers[binding.url_template]
            if binding.method not in provider.operations:
                raise ProviderRefused("Operation is not registered by this provider")
            args = substitute(binding.body_template, params)
            if self.policy_check:
                self.policy_check(provider.name, binding.method, args)
        except (ProviderRefused, KeyError, ValueError, PermissionError) as exc:
            return ApiActuationResult(
                status=ActuationStatus.UNAVAILABLE,
                substrate=self.substrate,
                reason=f"{summary}: refused before delivery ({type(exc).__name__})",
                request_summary=summary,
            )
        try:
            receipt = provider.execute(binding.method, args)
            if not isinstance(receipt, dict):
                raise TypeError("Provider returned an invalid action receipt")
            self.last_receipt = copy.deepcopy(receipt)
        except ProviderRefused:
            return ApiActuationResult(
                status=ActuationStatus.UNAVAILABLE,
                substrate=self.substrate,
                reason=f"{summary}: provider refused before delivery",
                request_summary=summary,
            )
        except Exception as exc:
            return ApiActuationResult(
                status=ActuationStatus.HALT,
                halt_kind=ApiHaltKind.DELIVERY_UNCERTAIN,
                substrate=self.substrate,
                reason=f"{summary}: delivery uncertain ({type(exc).__name__}); never retry blindly",
                request_summary=summary,
            )
        return ApiActuationResult(
            status=ActuationStatus.ACTUATED,
            substrate=self.substrate,
            reason=f"{summary}: input delivered; outcome verification follows",
            request_summary=summary,
        )


class ProviderVerifier:
    """Fresh provider observations judged by Flow's existing effect semantics.

    UI providers MUST advertise tier 4. A tier-4 confirmed field is a screen
    consistency check, never independent persistence or a production VERIFIED run.
    Only a provider whose inspect method reads a separate authoritative store may
    advertise tier 1. Mixed providers retain per-effect tiers.
    """

    substrate = "l1ght5p33d_provider_state"
    independent_system_of_record = False

    def __init__(
        self, providers: Mapping[str, Provider], *, poll_interval_s: float = 0.05
    ):
        self.providers = dict(providers)
        self.poll_interval_s = poll_interval_s

    @property
    def verification_tier(self) -> VerificationTier:
        return VerificationTier(
            max((p.effect_tier for p in self.providers.values()), default=4)
        )

    def verification_tier_for(self, effect: Effect) -> VerificationTier:
        provider = self.providers.get(str(effect.match.get("provider", "")))
        return VerificationTier(provider.effect_tier if provider is not None else 4)

    def _read(self, names: list[str]) -> list[dict[str, Any]] | None:
        rows: list[dict[str, Any]] = []
        try:
            for name in names:
                state = self.providers[name].inspect()
                if not isinstance(state, dict):
                    return None
                rows.append({**copy.deepcopy(state), "provider": name})
        except Exception:
            return None
        return rows

    def capture_pre_state(self, context: Any = None) -> EffectState:
        records = self._read(list(self.providers))
        return EffectState(
            substrate=self.substrate,
            reachable=records is not None,
            records=records or [],
        )

    def capture_post_state(self, context: Any = None) -> EffectState:
        return self.capture_pre_state(context)

    def verify(
        self, expected: Effect, before: EffectState, context: Any = None
    ) -> EffectVerdict:
        name = str(expected.match.get("provider", ""))
        deadline = time.monotonic() + min(max(expected.timeout_s, 0), 60)
        tier = self.verification_tier_for(expected)
        substrate = (
            "independent_provider_store"
            if tier <= VerificationTier.INDEPENDENT_SESSION
            else "onscreen_same_surface"
        )
        while True:
            current = self._read([name]) if name in self.providers else None
            verdict = judge_records(expected, before, current, substrate=substrate)
            if verdict.confirmed or time.monotonic() >= deadline:
                return verdict
            time.sleep(self.poll_interval_s)
