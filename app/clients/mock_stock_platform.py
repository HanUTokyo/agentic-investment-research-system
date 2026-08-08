import json
from pathlib import Path
from typing import Any

from app.contracts import CompanySnapshot, FinancialHistory, ValuationEvaluation, ValuationSnapshot


class MockStockPlatformClient:
    """Synthetic-only replacement for local demos and CI."""

    def __init__(self, fixture_root: Path) -> None:
        self._fixture_root = fixture_root

    async def readiness(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot:
        return ValuationSnapshot.model_validate(self._load("valuation.json", symbol))

    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot:
        return CompanySnapshot.model_validate(self._load("company_snapshot.json", symbol))

    async def get_financial_history(self, symbol: str) -> FinancialHistory:
        return FinancialHistory.model_validate(self._load("financial_history.json", symbol))

    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation:
        _ = assumptions
        payload = self._load("valuation_evaluation.json", symbol)
        payload["scenario"]["scenarioType"] = scenario_type.upper()
        return ValuationEvaluation.model_validate(payload)

    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None:
        return (await self.run_valuation_scenario(symbol, "BASE")).reverse_dcf

    def _load(self, filename: str, symbol: str) -> dict[str, Any]:
        payload = json.loads((self._fixture_root / filename).read_text())
        payload["symbol"] = symbol.upper()
        return payload
