import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
    RevenueGuidance,
)
from app.research_graph import ResearchDispatcher
from app.revenue_guidance_forecast_executor import RevenueGuidanceForecastExecutor


def _guidance(year: int = 2027, symbol: str = "ACME") -> ResearchEvidence:
    guidance = RevenueGuidance(
        symbol=symbol, metric="REVENUE", representation="ABSOLUTE_FY_RANGE",
        low=Decimal("110"), high=Decimal("130"), currency="USD", target_fiscal_year=year,
        raw_fact="FY2027 revenue is expected to be between $110 and $130.",
        published_at=datetime(2026, 8, 1, tzinfo=UTC), source_url="https://issuer.example/guidance",
    )
    return ResearchEvidence(
        evidence_id="guidance", evidence={"claim": "Issuer FY revenue guidance", "sourcePath": "external.issuer.guidance"},
        source="Issuer earnings release", source_type="external", numerical_authority="external_source",
        provenance={"url": guidance.source_url, "published_at": "2026-08-01"}, revenue_guidance=guidance,
    )


def _action(**updates: object) -> ResearchAction:
    request = {
        "capability": "EXPLICIT_FORECAST", "symbol": "ACME", "rationale": "Guidance warrants a bounded test.",
        "evidence_ids": ("guidance",), "analysis_mode": "EVIDENCE_GROUNDED_OVERRIDE",
        "assumption_application": "YEAR_1_REVENUE_GUIDANCE",
    }
    request.update(updates)
    return ResearchAction(action="REQUEST_VALUATION_ANALYSIS", reason="Apply revenue guidance.", valuation_analysis=request)


def _driver(growth: str) -> dict[str, object]:
    return {"revenueGrowthRate": growth, "ebitMargin": "0.2", "taxRate": "0.2", "depreciationAndAmortizationRate": "0.05", "capexRate": "0.1", "changeInNetWorkingCapitalRate": "0"}


def _template(year: int = 2027) -> dict[str, object]:
    drivers = [_driver("0.1"), _driver("0.09"), _driver("0.08"), _driver("0.07"), _driver("0.06")]
    return {
        "eligibility": "AVAILABLE", "suggestedArchetype": "MATURE_TECH_PLATFORM",
        "temporalContext": {"availability": "FISCAL_LABEL_AVAILABLE", "forecastPeriods": [{"ordinalYear": 1, "fiscalYear": year, "fiscalPeriod": "FY"}]},
        "templates": {"MATURE_TECH_PLATFORM": {"baseInputs": {"startingRevenue": "100", "waccRate": "0.1", "terminalGrowthRate": "0.02", "debtFinancingPolicy": {"type": "TARGET_DEBT_FINANCING_RATIO"}}, "scenarios": {"BASE": {"explicitOperatingDrivers": drivers}}}},
    }


def _preview() -> dict[str, object]:
    track = {"equityValue": 100, "discountRate": 0.1, "terminalValue": 200}
    sensitivity = {"discountRates": [0.09], "terminalGrowthRates": [0.03], "equityValues": [[100]]}
    reverse = {"status": "UNAVAILABLE"}
    scenario = {"fcff": track, "fcfe": track, "fcffSensitivity": sensitivity, "fcfeSensitivity": sensitivity, "fcffReverseDcf": reverse, "fcfeReverseDcf": reverse, "operatingSchedule": [{"year": 1}]}
    return {"symbol": "ACME", "forecastMode": "EXPLICIT_OPERATING_FORECAST", "archetype": "MATURE_TECH_PLATFORM", "readiness": "READY_WITH_CAVEATS", "missingInputs": [], "templateVersion": "v1", "scenarios": {"BEAR": scenario, "BASE": scenario, "BULL": scenario}}


class _Client:
    def __init__(self, template: dict[str, object] | None = None) -> None:
        self.template = template or _template()
        self.calls: list[dict[str, object]] = []

    async def get_forecast_template(self, _symbol: str) -> dict[str, object]:
        return self.template

    async def preview_explicit_forecast(self, _symbol: str, *, archetype: str, scenarios=None) -> dict[str, object]:
        self.calls.append({"archetype": archetype, "scenarios": scenarios})
        return _preview()


@pytest.mark.asyncio
async def test_deterministically_applies_midpoint_to_base_year_one_only() -> None:
    client = _Client()
    executor = RevenueGuidanceForecastExecutor(client)  # type: ignore[arg-type]
    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_guidance(),))
    updated = await ResearchDispatcher(valuation_analysis_executor=executor).dispatch(case.select(_action()))

    assert client.calls[0] == {"archetype": "MATURE_TECH_PLATFORM", "scenarios": None}
    override = client.calls[1]["scenarios"]
    assert set(override) == {"BASE"}
    drivers = override["BASE"]["explicitOperatingDrivers"]
    assert drivers[0]["revenueGrowthRate"] == "0.2"
    assert drivers[1:] == _template()["templates"]["MATURE_TECH_PLATFORM"]["scenarios"]["BASE"]["explicitOperatingDrivers"][1:]
    summary = json.loads(str(updated.evidence[-1].evidence.value))
    assert summary["assumption_application"] == "YEAR_1_REVENUE_GUIDANCE"
    assert updated.evidence[-1].numerical_authority == "deterministic_valuation"
    assert updated.evidence[-1].originating_evidence_ids == ("guidance",)


def test_contract_forbids_model_numbers_and_other_assumptions() -> None:
    with pytest.raises(ValidationError):
        _action(assumption_application="WACC")
    with pytest.raises(ValidationError):
        _action(year_1_growth=0.2)
    with pytest.raises(ValidationError):
        _action(analysis_mode="EVIDENCE_GROUNDED_OVERRIDE", assumption_application=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guidance_year", "template_value", "message"),
    [(2028, _template(), "does not align"), (2027, {**_template(), "temporalContext": {"availability": "UNAVAILABLE"}}, "unavailable")],
)
async def test_rejects_temporal_mismatch_or_unavailable_context(guidance_year, template_value, message) -> None:
    executor = RevenueGuidanceForecastExecutor(_Client(template_value))  # type: ignore[arg-type]
    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_guidance(guidance_year),))
    with pytest.raises(IllegalResearchTransition, match=message):
        await executor(case, _action())


@pytest.mark.asyncio
async def test_rejects_symbol_and_missing_guidance_provenance() -> None:
    executor = RevenueGuidanceForecastExecutor(_Client())  # type: ignore[arg-type]
    mismatch = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_guidance(symbol="OTHER"),))
    with pytest.raises(IllegalResearchTransition, match="does not match"):
        await executor(mismatch, _action())
    no_guidance = ResearchEvidence(evidence_id="guidance", evidence={"claim": "x", "sourcePath": "external.x"}, source="SEC", source_type="external", numerical_authority="external_source")
    with pytest.raises(IllegalResearchTransition, match="incomplete"):
        await executor(ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(no_guidance,)), _action())
