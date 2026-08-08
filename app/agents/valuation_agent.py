from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from app.contracts import (
    CompanySnapshot,
    FinancialHistory,
    ValuationEvaluation,
    ValuationReport,
    ValuationSnapshot,
)
from app.contracts.models import ToolCallSummary


class ValuationDataClient(Protocol):
    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot: ...
    async def get_financial_history(self, symbol: str) -> FinancialHistory: ...
    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot: ...
    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation: ...
    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None: ...


class ValuationAgent(Agent):
    """A valuation specialist.

    Use only the read-only deterministic tools on self. Never calculate a DCF,
    invent a numeric claim, persist a scenario, or access any filesystem/network
    capability other than the provided tools.
    """

    def __init__(self, data_client: ValuationDataClient, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._data_client = data_client
        self.trace_id = str(uuid4())
        self.tool_calls: list[ToolCallSummary] = []

    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot:
        """Get the current Java-platform valuation and, when held, portfolio context."""
        return await self._call(
            "get_company_snapshot", self._data_client.get_company_snapshot(symbol)
        )

    async def get_financial_history(self, symbol: str) -> FinancialHistory:
        """Get Java-platform quarterly fundamentals and capital-allocation history."""
        return await self._call(
            "get_financial_history", self._data_client.get_financial_history(symbol)
        )

    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot:
        """Get the Java valuation engine's authoritative current valuation output."""
        return await self._call(
            "get_current_valuation", self._data_client.get_current_valuation(symbol)
        )

    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation:
        """Evaluate an unsaved Java-engine scenario. Allowed types: BEAR, BASE, BULL."""
        if scenario_type.upper() not in {"BEAR", "BASE", "BULL"}:
            raise ValueError("scenario_type must be BEAR, BASE, or BULL")
        return await self._call(
            "run_valuation_scenario",
            self._data_client.run_valuation_scenario(symbol, scenario_type, assumptions),
        )

    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None:
        """Retrieve Java-engine reverse-DCF market-implied assumptions."""
        return await self._call(
            "solve_market_implied_assumptions",
            self._data_client.solve_market_implied_assumptions(symbol),
        )

    async def _call(self, name: str, operation: Any) -> Any:
        started = datetime.now(UTC)
        try:
            result = await operation
        except Exception:
            self.tool_calls.append(ToolCallSummary(tool_name=name, success=False))
            raise
        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        self.tool_calls.append(
            ToolCallSummary(tool_name=name, success=True, duration_ms=duration_ms)
        )
        return result

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5, max_retries=1)))
    async def investigate(self, question: str, symbol: str) -> ValuationReport:
        """Investigate {question} for {symbol} using evidence first.

        Fetch the current valuation before making a conclusion. Run another scenario
        only when it resolves an evidence gap. Every numeric conclusion needs an
        Evidence item whose source_path points to a deterministic tool result.
        Return a complete typed ValuationReport.
        """
        ...

    @staticmethod
    def report_timestamp() -> datetime:
        return datetime.now(UTC)
