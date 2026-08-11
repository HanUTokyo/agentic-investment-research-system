import json

import httpx
import pytest
from pydantic import ValidationError

from app.clients.stock_platform import StockPlatformClient
from app.explicit_forecast_executor import ExplicitForecastExecutor
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)
from app.research_graph import ResearchDispatcher, build_research_graph


def _external_evidence() -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id="official-guidance",
        evidence={"claim": "Issuer FY outlook", "sourcePath": "external.issuer.guidance"},
        source="Issuer earnings release",
        source_type="external",
        provenance={"url": "https://issuer.example/release", "published_at": "2026-08-01"},
        numerical_authority="external_source",
    )


def _action(**request_updates: object) -> ResearchAction:
    request = {
        "capability": "EXPLICIT_FORECAST",
        "symbol": "ACME",
        "rationale": "Official operating outlook warrants Java forecast analysis.",
        "evidence_ids": ("official-guidance",),
        "analysis_mode": "DEFAULT_TEMPLATE_PREVIEW",
    }
    request.update(request_updates)
    return ResearchAction(
        action="REQUEST_VALUATION_ANALYSIS", reason="Assess operating outlook through Java.",
        valuation_analysis=request,
    )


def _preview(archetype: str = "MATURE_TECH_PLATFORM") -> dict[str, object]:
    track = {"equityValue": 123, "discountRate": 0.1, "terminalValue": 456}
    sensitivity = {"discountRates": [0.09], "terminalGrowthRates": [0.03], "equityValues": [[123]]}
    reverse = {"status": "UNAVAILABLE", "targetEquityValue": None, "impliedDiscountRate": None}
    scenario = {
        "fcff": track,
        "fcfe": track,
        "fcffSensitivity": sensitivity,
        "fcfeSensitivity": sensitivity,
        "fcffReverseDcf": reverse,
        "fcfeReverseDcf": reverse,
        "operatingSchedule": [{"year": 1}],
    }
    return {
        "symbol": "ACME",
        "forecastMode": "EXPLICIT_OPERATING_FORECAST",
        "archetype": archetype,
        "readiness": "READY_WITH_CAVEATS",
        "missingInputs": ["NWC assumption"],
        "templateVersion": "forecast-3",
        "scenarios": {"BEAR": scenario, "BASE": scenario, "BULL": scenario},
    }


class _ForecastClient:
    def __init__(self, template: dict[str, object] | None = None, preview: dict[str, object] | None = None) -> None:
        self.template = template or {"eligibility": "AVAILABLE", "suggestedArchetype": "MATURE_TECH_PLATFORM", "templateVersion": "forecast-3"}
        self.preview = preview or _preview()
        self.calls: list[tuple[str, str]] = []

    async def get_forecast_template(self, symbol: str) -> dict[str, object]:
        self.calls.append(("template", symbol))
        return self.template

    async def preview_explicit_forecast(self, symbol: str, *, archetype: str) -> dict[str, object]:
        self.calls.append(("preview", f"{symbol}:{archetype}"))
        return self.preview


@pytest.mark.asyncio
async def test_dispatches_default_template_preview_and_preserves_originating_evidence() -> None:
    client = _ForecastClient()
    executor = ExplicitForecastExecutor(client)  # type: ignore[arg-type]
    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_external_evidence(),))
    updated = await ResearchDispatcher(valuation_analysis_executor=executor).dispatch(case.select(_action()))

    forecast = updated.evidence[-1]
    summary = json.loads(str(forecast.evidence.value))
    assert client.calls == [("template", "ACME"), ("preview", "ACME:MATURE_TECH_PLATFORM")]
    assert executor.invocation_count == 1
    assert forecast.numerical_authority == "deterministic_valuation"
    assert forecast.originating_evidence_ids == ("official-guidance",)
    assert forecast.provenance["originating_evidence_ids"] == "official-guidance"
    assert forecast.provenance["effective_input_fingerprint"].startswith("sha256:")
    assert updated.executed_actions[-1].effective_input_fingerprint == forecast.provenance["effective_input_fingerprint"]
    assert summary["scenarios"]["BASE"]["fcff"]["equityValue"] == 123
    assert updated.evidence[0].evidence_id == "official-guidance"
    assert updated.evidence[0].evidence.claim == "Issuer FY outlook"


def test_contract_allows_only_default_explicit_forecast_without_model_inputs() -> None:
    with pytest.raises(ValidationError):
        _action(capability="WACC")
    with pytest.raises(ValidationError):
        _action(analysis_mode="CUSTOM")
    with pytest.raises(ValidationError):
        _action(evidence_ids=())
    with pytest.raises(ValidationError):
        _action(archetype="HIGH_GROWTH")
    with pytest.raises(ValidationError):
        _action(revenue_growth_rate=0.2)
    with pytest.raises(ValidationError):
        ResearchAction(action="REQUEST_VALUATION_ANALYSIS", reason="x", valuation_analysis=_action().valuation_analysis, wacc=0.1)


@pytest.mark.asyncio
async def test_rejects_nonexistent_or_nonexternal_originating_evidence() -> None:
    executor = ExplicitForecastExecutor(_ForecastClient())  # type: ignore[arg-type]
    empty = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"})
    with pytest.raises(IllegalResearchTransition, match="must exist"):
        await executor(empty, _action())

    deterministic = ResearchEvidence(
        evidence_id="official-guidance", evidence={"claim": "java", "sourcePath": "java.x"},
        source="Java", source_type="deterministic_valuation", numerical_authority="deterministic_valuation",
    )
    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(deterministic,))
    with pytest.raises(IllegalResearchTransition, match="external evidence"):
        await executor(case, _action())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template", "preview", "message"),
    [
        ({"eligibility": "INELIGIBLE", "suggestedArchetype": "MATURE_TECH_PLATFORM", "templateVersion": "forecast-3"}, None, "not eligible"),
        ({"eligibility": "AVAILABLE", "templateVersion": "forecast-3"}, None, "lacks suggestedArchetype"),
        (None, {"symbol": "ACME", "archetype": "MATURE_TECH_PLATFORM"}, "malformed Java"),
        (None, {**_preview(), "readiness": "NOT_READY"}, "not ready"),
    ],
)
async def test_rejects_ineligible_unready_and_malformed_java_responses(
    template: dict[str, object] | None, preview: dict[str, object] | None, message: str
) -> None:
    executor = ExplicitForecastExecutor(_ForecastClient(template, preview))  # type: ignore[arg-type]
    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_external_evidence(),))
    with pytest.raises(IllegalResearchTransition, match=message):
        await executor(case, _action())


@pytest.mark.asyncio
async def test_rejects_identical_default_preview_as_duplicate_noop() -> None:
    client = _ForecastClient()
    executor = ExplicitForecastExecutor(client)  # type: ignore[arg-type]
    initial = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_external_evidence(),))
    updated = await ResearchDispatcher(valuation_analysis_executor=executor).dispatch(initial.select(_action()))
    with pytest.raises(IllegalResearchTransition, match="DUPLICATE_NOOP_ACTION"):
        await executor(updated, _action())
    assert client.calls == [
        ("template", "ACME"),
        ("preview", "ACME:MATURE_TECH_PLATFORM"),
        ("template", "ACME"),
    ]


@pytest.mark.asyncio
async def test_next_controller_iteration_sees_deterministic_forecast_evidence() -> None:
    class Controller:
        def __init__(self) -> None:
            self.visible: list[tuple[str, ...]] = []

        async def decide(self, case: ResearchCase) -> ResearchAction:
            self.visible.append(tuple(item.evidence_id for item in case.evidence))
            if len(case.evidence) == 1:
                return _action()
            return ResearchAction(action="DELEGATE_SPECIALIST", reason="Forecast evidence received.")

    controller = Controller()
    executor = ExplicitForecastExecutor(_ForecastClient())  # type: ignore[arg-type]
    graph = build_research_graph(controller, ResearchDispatcher(valuation_analysis_executor=executor))
    initial = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"}, evidence=(_external_evidence(),), max_iterations=2)
    with pytest.raises(IllegalResearchTransition, match="no specialist"):
        await graph.ainvoke({"case": initial}, config={"configurable": {"thread_id": "forecast-visible"}})
    assert controller.visible[0] == ("official-guidance",)
    assert len(controller.visible[1]) == 2


@pytest.mark.asyncio
async def test_stock_client_sends_only_java_suggested_archetype(settings) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=_preview())

    client = StockPlatformClient(
        settings, httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stock.test")
    )
    await client.preview_explicit_forecast("acme", archetype="MATURE_TECH_PLATFORM")
    assert payloads == [{"archetype": "MATURE_TECH_PLATFORM"}]
