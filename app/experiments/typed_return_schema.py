"""Measure where a controller stops reliably using native NOOA return_result."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Literal

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from pydantic import BaseModel

from app.contracts import Evidence, ValuationReport, ValuationScenario


class TinyResult(BaseModel):
    symbol: str
    score: int


class SimpleValuationResult(BaseModel):
    symbol: str
    conclusion: str
    confidence: Literal["low", "medium", "high"]
    current_price: float
    intrinsic_value: float


class ValuationReportLite(BaseModel):
    symbol: str
    valuation_basis: str
    current_price: float
    intrinsic_value: float
    scenarios: list[ValuationScenario]
    conclusion: str
    uncertainty: Literal["low", "medium", "high"]


class NestedEvidenceReport(ValuationReportLite):
    evidence: list[Evidence]


@dataclass
class ReturnTrace:
    level: str
    native_return_called: bool = False
    malformed_return_arguments: bool = False
    schema_validation_failed: bool = False
    markdown_or_text: bool = False
    empty_result: bool = False
    timeout: bool = False
    latency_ms: float = 0.0
    error: str | None = None

    def as_json(self) -> dict[str, object]:
        return asdict(self)


class AuditedReturnStrategy(CodeActStrategy):
    """Observe actual NOOA tool events without modifying model output or recovery."""

    async def _process_tool_calls(
        self, tool_calls: Any, runtime: Any, *args: Any, **kwargs: Any
    ) -> Any:
        trace: ReturnTrace = runtime.agent.return_trace
        for tool_call in tool_calls:
            if tool_call.name == "return_result":
                if str(tool_call.id).startswith("synthetic_"):
                    trace.markdown_or_text = True
                else:
                    trace.native_return_called = True
        return await super()._process_tool_calls(tool_calls, runtime, *args, **kwargs)


_CONFIG = CodeActConfig(
    max_iterations=3,
    max_retries=1,
    max_tokens=512,
    text_only_stop_behavior="return_result",
)


class TypedReturnExperimentAgent(Agent):
    """Five identical native-CodeAct paths with only return schema changed."""

    def __init__(self, level: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.return_trace = ReturnTrace(level=level)

    @strategy(AuditedReturnStrategy(config=_CONFIG))
    async def level_1(self, symbol: str) -> TinyResult:
        """Use native return_result only. Return TinyResult for AAPL with score 7. No prose."""
        ...

    @strategy(AuditedReturnStrategy(config=_CONFIG))
    async def level_2(self, symbol: str) -> SimpleValuationResult:
        """Use native return_result only. Return the requested synthetic valuation fields. No prose."""
        ...

    @strategy(AuditedReturnStrategy(config=_CONFIG))
    async def level_3(self, symbol: str) -> ValuationReportLite:
        """Use native return_result only. Return a synthetic lite valuation with one valid scenario. No prose."""
        ...

    @strategy(AuditedReturnStrategy(config=_CONFIG))
    async def level_4(self, symbol: str) -> NestedEvidenceReport:
        """Use native return_result only. Return level 3 plus one synthetic Evidence item. No prose."""
        ...

    @strategy(AuditedReturnStrategy(config=_CONFIG))
    async def level_5(self, symbol: str) -> ValuationReport:
        """Use native return_result only. Return a complete synthetic ValuationReport. No prose."""
        ...


LEVEL_METHODS = {
    "TinyResult": "level_1",
    "SimpleValuationResult": "level_2",
    "ValuationReportLite": "level_3",
    "NestedEvidenceReport": "level_4",
    "ValuationReport": "level_5",
}


async def run_level(agent: TypedReturnExperimentAgent, level: str) -> ReturnTrace:
    """Run one native CodeAct attempt and classify observed NOOA outcomes."""
    started = perf_counter()
    try:
        await getattr(agent, LEVEL_METHODS[level])("AAPL")
    except Exception as exc:  # Expected experimental failure modes are outcomes.
        text = str(exc)
        agent.return_trace.error = text[:500]
        agent.return_trace.timeout = "timeout" in text.lower()
        agent.return_trace.empty_result = "no content" in text.lower()
        agent.return_trace.schema_validation_failed = "validation failed" in text.lower()
        agent.return_trace.malformed_return_arguments = "invalid arguments" in text.lower()
        agent.return_trace.markdown_or_text |= (
            "plain text" in text.lower() or "got: str" in text.lower()
        )
    finally:
        agent.return_trace.latency_ms = (perf_counter() - started) * 1000
    return agent.return_trace
