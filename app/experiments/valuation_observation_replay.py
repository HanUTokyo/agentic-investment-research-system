"""Four-level replay probe for NOOA continuation after Java valuation observations."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Literal

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from pydantic import BaseModel, Field

from app.agents.valuation_projection import (
    CompactValuationObservation,
    project_compact_valuation,
    project_trimmed_valuation,
)
from app.contracts import ValuationSnapshot

Variant = Literal["A", "B", "C", "D"]


class ObservationAcknowledgement(BaseModel):
    symbol: str = Field(min_length=1)
    observation_kind: str = Field(min_length=1)
    controller_observed: Literal[True]


class ReplaySource:
    """A deterministic observation source; it has no model or financial logic."""

    def __init__(
        self,
        kind: str,
        resolver: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        self.kind = kind
        self._resolver = resolver
        self.calls = 0
        self.latency_ms: float | None = None

    async def resolve(self) -> dict[str, Any]:
        self.calls += 1
        started = perf_counter()
        result = await self._resolver()
        self.latency_ms = (perf_counter() - started) * 1000
        return result

    async def preview(self) -> dict[str, Any]:
        """Resolve deterministic input for metrics without counting a tool call."""
        return await self._resolver()


class ValuationObservationReplayAgent(Agent):
    """Minimal controller replay. It exposes one deterministic observation tool."""

    def __init__(self, source: ReplaySource, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._source = source

    async def get_observation(self) -> dict[str, Any]:
        """Return the preselected deterministic observation exactly once."""
        if self._source.calls >= 1:
            raise RuntimeError("observation tool may be called only once")
        return await self._source.resolve()

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=3, max_retries=1, max_tokens=512))
    )
    async def acknowledge(self) -> ObservationAcknowledgement:
        """Verify controller continuation through native return_result only.

        First call execute_python. In that cell call exactly
        `observation = await self.get_observation()`. Then call
        `return_result(ObservationAcknowledgement(symbol=observation["symbol"],
        observation_kind=observation["kind"], controller_observed=True))` from
        the same cell. Do not calculate, analyze, summarize, or use any other
        tools. Do not return prose or construct a result outside native
        return_result.
        """
        ...


def make_source(
    variant: Variant,
    *,
    fixed_compact: CompactValuationObservation,
    stock_fetch: Callable[[], Awaitable[ValuationSnapshot]],
) -> ReplaySource:
    """Construct one of A-D with deterministic-only projections."""

    async def tiny() -> dict[str, Any]:
        return {"kind": "tiny", "symbol": fixed_compact.symbol}

    async def compact() -> dict[str, Any]:
        return {"kind": "compact_fixed", **fixed_compact.model_dump(mode="json")}

    async def trimmed() -> dict[str, Any]:
        raw = await stock_fetch()
        return {"kind": "trimmed_live", **project_trimmed_valuation(raw).model_dump(mode="json")}

    async def live_compact() -> dict[str, Any]:
        raw = await stock_fetch()
        return {"kind": "compact_live", **project_compact_valuation(raw).model_dump(mode="json")}

    resolvers: dict[Variant, tuple[str, Callable[[], Awaitable[dict[str, Any]]]]] = {
        "A": ("tiny", tiny),
        "B": ("compact_fixed", compact),
        "C": ("trimmed_live", trimmed),
        "D": ("compact_live", live_compact),
    }
    kind, resolver = resolvers[variant]
    return ReplaySource(kind, resolver)


def observation_metrics(observation: dict[str, Any]) -> dict[str, int]:
    encoded = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return {"observation_bytes": len(encoded.encode()), "nesting_depth": _depth(observation)}


def _depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0
