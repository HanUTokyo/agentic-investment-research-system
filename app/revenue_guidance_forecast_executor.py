"""Deterministic Phase 2D revenue-guidance to Java forecast override adapter."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.clients.stock_platform import StockPlatformClient
from app.contracts import Evidence
from app.explicit_forecast_executor import ExplicitForecastExecutor
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
    RevenueGuidance,
)

_POLICY = "MIDPOINT_V1"
_FORMULA = "YEAR_1_REVENUE_GROWTH_V1: midpoint(low, high) / startingRevenue - 1"


class RevenueGuidanceForecastExecutor:
    """Applies the sole Phase 2D mapping; it has no semantic-planning authority."""

    def __init__(
        self,
        stock_platform: StockPlatformClient,
        on_step: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._stock_platform = stock_platform
        self._on_step = on_step
        self.invocation_count = 0

    async def __call__(
        self, case: ResearchCase, action: ResearchAction
    ) -> tuple[ResearchEvidence, ...]:
        request = self._request(case, action)
        if any("evidence_grounded_override" in item.claim_scope for item in case.evidence):
            raise IllegalResearchTransition(
                "ResearchCase already contains an evidence-grounded forecast override"
            )
        evidence = self._guidance(case, request.evidence_ids)
        symbol = str(case.valuation_context.get("symbol", "")).strip().upper()
        template = await self._stock_platform.get_forecast_template(symbol)
        self._observe("forecast_template", template)
        archetype = ExplicitForecastExecutor.template_archetype(template)
        temporal = self._temporal_context(template, evidence)
        baseline = await self._stock_platform.preview_explicit_forecast(symbol, archetype=archetype)
        self._observe("default_forecast", baseline)
        scenarios, conversion = self._override(template, archetype, evidence, temporal)
        conversion["evidence_id"] = request.evidence_ids[0]
        self._observe("deterministic_conversion", conversion)
        adjusted_request = {"archetype": archetype, "scenarios": scenarios}
        self._observe("adjusted_forecast_request", adjusted_request)
        self.invocation_count += 1
        adjusted = await self._stock_platform.preview_explicit_forecast(
            symbol, archetype=archetype, scenarios=scenarios
        )
        self._observe("adjusted_forecast", adjusted)
        summary = ExplicitForecastExecutor.preview_summary(
            adjusted, symbol, archetype, analysis_mode="EVIDENCE_GROUNDED_OVERRIDE"
        )
        summary["assumption_application"] = "YEAR_1_REVENUE_GUIDANCE"
        summary["baseline"] = self._delta(baseline, adjusted)
        calculated_at = datetime.now(UTC)
        return (
            ResearchEvidence(
                evidence=Evidence(
                    claim=f"Java evidence-grounded revenue-guidance forecast for {symbol}",
                    source_path="java.forecast_preview.evidence_grounded_override",
                    value=json.dumps(summary, sort_keys=True, separators=(",", ":")),
                ),
                source="Java Stock Platform explicit forecast",
                source_type="deterministic_valuation",
                retrieved_at=calculated_at,
                claim_scope=(
                    "valuation_analysis",
                    "explicit_forecast",
                    "evidence_grounded_override",
                ),
                provenance={
                    "template_endpoint": f"/api/valuations/{symbol}/forecast-template",
                    "preview_endpoint": f"/api/valuations/{symbol}/forecast-preview",
                    "template_version": str(summary["template_version"]),
                    "archetype": archetype,
                    "analysis_mode": request.analysis_mode,
                    "assumption_application": request.assumption_application or "",
                    "originating_action_id": action.action_id,
                    "originating_evidence_ids": ",".join(request.evidence_ids),
                    "guidance_source_url": evidence.source_url,
                    "guidance_target_fiscal_year": str(evidence.target_fiscal_year),
                    "extraction_policy": _POLICY,
                    "conversion_formula": _FORMULA,
                    "modified_scenario": "BASE",
                },
                numerical_authority="deterministic_valuation",
                originating_evidence_ids=request.evidence_ids,
            ),
        )

    @staticmethod
    def _request(case: ResearchCase, action: ResearchAction):
        request = action.valuation_analysis
        if (
            action.action != "REQUEST_VALUATION_ANALYSIS"
            or request is None
            or request.capability != "EXPLICIT_FORECAST"
            or request.analysis_mode != "EVIDENCE_GROUNDED_OVERRIDE"
            or request.assumption_application != "YEAR_1_REVENUE_GUIDANCE"
        ):
            raise IllegalResearchTransition(
                "revenue guidance executor accepts its sole Phase 2D request"
            )
        symbol = str(case.valuation_context.get("symbol", "")).strip().upper()
        if not symbol or request.symbol.strip().upper() != symbol:
            raise IllegalResearchTransition(
                "valuation analysis symbol must match valuation_context.symbol"
            )
        if len(request.evidence_ids) != 1:
            raise IllegalResearchTransition(
                "YEAR_1_REVENUE_GUIDANCE requires exactly one evidence id"
            )
        return request

    @staticmethod
    def _guidance(case: ResearchCase, evidence_ids: tuple[str, ...]) -> RevenueGuidance:
        item = next((item for item in case.evidence if item.evidence_id == evidence_ids[0]), None)
        if item is None:
            raise IllegalResearchTransition(
                "valuation analysis evidence_ids must exist in ResearchCase"
            )
        if item.source_type != "external" or item.numerical_authority != "external_source":
            raise IllegalResearchTransition("revenue guidance must be external-source evidence")
        if not item.provenance or item.revenue_guidance is None:
            raise IllegalResearchTransition("revenue guidance provenance is incomplete")
        guidance = item.revenue_guidance
        symbol = str(case.valuation_context.get("symbol", "")).strip().upper()
        if guidance.symbol.upper() != symbol:
            raise IllegalResearchTransition("revenue guidance symbol does not match ResearchCase")
        if not guidance.source_url or not guidance.raw_fact:
            raise IllegalResearchTransition("revenue guidance source is incomplete")
        return guidance

    @staticmethod
    def _temporal_context(template: dict[str, Any], guidance: RevenueGuidance) -> dict[str, Any]:
        temporal = template.get("temporalContext")
        if (
            not isinstance(temporal, dict)
            or temporal.get("availability") != "FISCAL_LABEL_AVAILABLE"
        ):
            raise IllegalResearchTransition("forecast temporal context is unavailable")
        periods = temporal.get("forecastPeriods")
        if not isinstance(periods, list) or not periods:
            raise IllegalResearchTransition("forecast temporal context lacks Year-1")
        year_1 = periods[0]
        if (
            not isinstance(year_1, dict)
            or year_1.get("ordinalYear") != 1
            or year_1.get("fiscalPeriod") != "FY"
            or year_1.get("fiscalYear") != guidance.target_fiscal_year
        ):
            raise IllegalResearchTransition(
                "revenue guidance fiscal year does not align to forecast Year-1"
            )
        return temporal

    @staticmethod
    def _override(
        template: dict[str, Any],
        archetype: str,
        guidance: RevenueGuidance,
        temporal: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            selected = template["templates"][archetype]
            base = selected["baseInputs"]
            source_drivers = selected["scenarios"]["BASE"]["explicitOperatingDrivers"]
            starting_revenue = Decimal(str(base["startingRevenue"]))
        except (KeyError, TypeError, ArithmeticError) as exc:
            raise IllegalResearchTransition(
                "forecast template lacks deterministic BASE inputs"
            ) from exc
        if (
            starting_revenue <= 0
            or not isinstance(source_drivers, list)
            or len(source_drivers) != 5
        ):
            raise IllegalResearchTransition("forecast template has invalid revenue driver inputs")
        drivers = copy.deepcopy(source_drivers)
        if not isinstance(drivers[0], dict) or "revenueGrowthRate" not in drivers[0]:
            raise IllegalResearchTransition("forecast template lacks Year-1 revenue growth")
        midpoint = (guidance.low + guidance.high) / Decimal("2")
        growth = midpoint / starting_revenue - Decimal("1")
        original_growth = Decimal(str(drivers[0]["revenueGrowthRate"]))
        drivers[0]["revenueGrowthRate"] = str(growth)
        scenarios = {"BASE": {"explicitOperatingDrivers": drivers}}
        return scenarios, {
            "evidence_id": None,
            "raw_guidance_range": {"low": str(guidance.low), "high": str(guidance.high)},
            "guidance_currency": guidance.currency,
            "guidance_target_fiscal_year": guidance.target_fiscal_year,
            "forecast_year_1_fiscal_year": temporal["forecastPeriods"][0]["fiscalYear"],
            "period_alignment": "MATCH",
            "extraction_policy": _POLICY,
            "conversion_formula": _FORMULA,
            "starting_revenue": str(starting_revenue),
            "original_year_1_revenue_growth_rate": str(original_growth),
            "derived_year_1_revenue_growth_rate": str(growth),
            "modified_fields": ["scenarios.BASE.explicitOperatingDrivers[0].revenueGrowthRate"],
            "unchanged_fields_audit": "drivers[1:5], terminal driver, debt policy, and all base inputs retained from Java template",
        }

    @staticmethod
    def _delta(baseline: dict[str, Any], adjusted: dict[str, Any]) -> dict[str, Any]:
        def value(payload: dict[str, Any], scenario: str, track: str) -> Any:
            return payload.get("scenarios", {}).get(scenario, {}).get(track, {}).get("equityValue")

        return {
            "base_fcff_equity_value": {
                "default": value(baseline, "BASE", "fcff"),
                "adjusted": value(adjusted, "BASE", "fcff"),
            },
            "base_fcfe_equity_value": {
                "default": value(baseline, "BASE", "fcfe"),
                "adjusted": value(adjusted, "BASE", "fcfe"),
            },
        }

    def _observe(self, step: str, value: dict[str, Any]) -> None:
        if self._on_step is not None:
            self._on_step(step, value)
