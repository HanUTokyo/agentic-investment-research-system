"""Controlled Phase 1 valuation acceptance run inside the Docker sandbox."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.agents import ValuationAgent
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.contracts import Evidence, Uncertainty, ValuationReport
from app.llm import build_nooa_router_llm


class AdditionalScenarioDecision(BaseModel):
    run_additional_scenario: bool
    scenario_type: Literal["BEAR", "BULL"] | None = None
    reason: str


class ShortSynthesis(BaseModel):
    conclusion: str
    uncertainty: str


BASE = {
    "baseCashFlow": 128000000000,
    "initialGrowthRatePct": 7.0,
    "discountRatePct": 8.5,
    "terminalGrowthRatePct": 2.5,
    "projectionYears": 10,
    "marginOfSafetyPct": 20.0,
    "baseCashFlowMode": "MANUAL",
    "growthMode": "CUSTOM_LINEAR",
    "discountRateMode": "MANUAL_RATE",
}
BEAR = {
    "baseCashFlow": 110000000000,
    "initialGrowthRatePct": 2.0,
    "discountRatePct": 9.5,
    "terminalGrowthRatePct": 2.0,
    "projectionYears": 10,
    "marginOfSafetyPct": 30.0,
    "baseCashFlowMode": "MANUAL",
    "growthMode": "CUSTOM_LINEAR",
    "discountRateMode": "MANUAL_RATE",
}
BULL = {
    **BASE,
    "baseCashFlow": 140000000000,
    "initialGrowthRatePct": 10.0,
    "discountRatePct": 8.0,
    "terminalGrowthRatePct": 3.0,
    "marginOfSafetyPct": 10.0,
}


async def main() -> None:
    settings = get_settings()
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    agent = ValuationAgent(stock, llm=build_nooa_router_llm(settings))
    try:
        current = await agent.get_current_valuation("AAPL")
        base = await agent.run_valuation_scenario("AAPL", "BASE", BASE)
        decision = await router.complete_structured(
            [
                {
                    "role": "system",
                    "content": "Return JSON only: run_additional_scenario, scenario_type, reason. If the supplied warning means a material evidence gap, choose true and BEAR. Do not use numbers.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"model": base.scenario.selected_model, "warnings": base.scenario.warnings}
                    ),
                },
            ],
            AdditionalScenarioDecision,
            temperature=0,
            max_tokens=120,
        )
        scenarios = [base.scenario]
        if decision.run_additional_scenario:
            if decision.scenario_type not in {"BEAR", "BULL"}:
                raise RuntimeError("model selected a scenario outside the allowlist")
            assumptions = BEAR if decision.scenario_type == "BEAR" else BULL
            scenarios.append(
                (
                    await agent.run_valuation_scenario("AAPL", decision.scenario_type, assumptions)
                ).scenario
            )
        synthesis = await router.complete_structured(
            [
                {
                    "role": "system",
                    "content": "Return JSON only: conclusion and uncertainty. Use supplied evidence only. Do not use digits or make numerical claims.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "model": current.selected_model,
                            "warning": base.scenario.warnings,
                            "additional_scenario": decision.scenario_type,
                        }
                    ),
                },
            ],
            ShortSynthesis,
            temperature=0,
            max_tokens=160,
        )
        report = ValuationReport(
            symbol="AAPL",
            conclusion=synthesis.conclusion,
            valuation_basis=current.selected_model or "unavailable",
            engine_version=current.engine_version,
            scenario_results=scenarios,
            market_implied_assumptions=await agent.solve_market_implied_assumptions("AAPL"),
            evidence=[
                Evidence(
                    claim="Java selected the valuation basis.",
                    source_path="get_current_valuation.selected_model",
                    value=current.selected_model,
                ),
                Evidence(
                    claim="Java evaluated the BASE scenario.",
                    source_path="run_valuation_scenario.BASE.intrinsic_value_per_share",
                    value=base.scenario.intrinsic_value_per_share,
                ),
            ],
            uncertainties=[
                Uncertainty(
                    description=synthesis.uncertainty,
                    severity="high",
                    source_path="run_valuation_scenario.BASE.warnings",
                )
            ],
            warnings=base.scenario.warnings,
            tool_calls=agent.tool_calls,
            trace_id=agent.trace_id,
            generated_at=datetime.now(UTC),
        )
        print(
            json.dumps(
                {
                    "event": "phase1_valuation_acceptance",
                    "decision": decision.model_dump(),
                    "report": report.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await stock.aclose()
        await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
