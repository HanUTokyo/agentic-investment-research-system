"""Deterministic Phase 2C adapter for Java's default explicit-forecast preview."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.clients.stock_platform import StockPlatformClient
from app.contracts import Evidence
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)

_SCENARIOS = ("BEAR", "BASE", "BULL")


class ExplicitForecastExecutor:
    """Execute one Java-owned default-template preview without state-write authority."""

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
        if action.action != "REQUEST_VALUATION_ANALYSIS" or action.valuation_analysis is None:
            raise IllegalResearchTransition(
                "explicit forecast executor accepts REQUEST_VALUATION_ANALYSIS only"
            )
        request = action.valuation_analysis
        if request.capability != "EXPLICIT_FORECAST" or request.analysis_mode != "DEFAULT_TEMPLATE_PREVIEW":
            raise IllegalResearchTransition("unsupported valuation analysis request")
        symbol = str(case.valuation_context.get("symbol", "")).strip().upper()
        if not symbol or request.symbol.strip().upper() != symbol:
            raise IllegalResearchTransition("valuation analysis symbol must match valuation_context.symbol")
        by_id = {item.evidence_id: item for item in case.evidence}
        if any(evidence_id not in by_id for evidence_id in request.evidence_ids):
            raise IllegalResearchTransition("valuation analysis evidence_ids must exist in ResearchCase")
        if any(by_id[evidence_id].source_type != "external" for evidence_id in request.evidence_ids):
            raise IllegalResearchTransition(
                "valuation analysis must be motivated by external evidence"
            )
        template = await self._stock_platform.get_forecast_template(symbol)
        self._observe("forecast_template", template)
        archetype = self.template_archetype(template)
        fingerprint = self.effective_input_fingerprint(symbol, template, archetype)
        if self._has_effective_input(case, fingerprint, template, archetype):
            raise IllegalResearchTransition(
                "DUPLICATE_NOOP_ACTION: default explicit forecast has identical effective inputs"
            )
        self.invocation_count += 1
        # Deliberately only this field: Java retains every numerical/default assumption.
        self._observe("forecast_request", {"archetype": archetype})
        preview = await self._stock_platform.preview_explicit_forecast(symbol, archetype=archetype)
        self._observe("forecast_preview", preview)
        summary = self.preview_summary(preview, symbol, archetype)
        calculated_at = datetime.now(UTC)
        return (
            ResearchEvidence(
                evidence=Evidence(
                    claim=f"Java explicit forecast preview for {symbol}",
                    source_path="java.forecast_preview.default_template",
                    value=json.dumps(summary, sort_keys=True, separators=(",", ":")),
                ),
                source="Java Stock Platform explicit forecast",
                source_type="deterministic_valuation",
                retrieved_at=calculated_at,
                claim_scope=("valuation_analysis", "explicit_forecast"),
                provenance={
                    "template_endpoint": f"/api/valuations/{symbol}/forecast-template",
                    "preview_endpoint": f"/api/valuations/{symbol}/forecast-preview",
                    "template_version": str(summary["template_version"]),
                    "archetype": archetype,
                    "analysis_mode": request.analysis_mode,
                    "effective_input_fingerprint": fingerprint,
                    "originating_action_id": action.action_id,
                    "originating_evidence_ids": ",".join(request.evidence_ids),
                },
                numerical_authority="deterministic_valuation",
                originating_evidence_ids=request.evidence_ids,
            ),
        )

    def _observe(self, step: str, value: dict[str, Any]) -> None:
        if self._on_step is not None:
            self._on_step(step, value)

    @staticmethod
    def template_archetype(template: dict[str, Any]) -> str:
        if template.get("eligibility") != "AVAILABLE":
            raise IllegalResearchTransition("forecast template is not eligible")
        archetype = template.get("suggestedArchetype")
        if not isinstance(archetype, str) or not archetype:
            raise IllegalResearchTransition("forecast template lacks suggestedArchetype")
        return archetype

    @staticmethod
    def effective_input_fingerprint(
        symbol: str, template: dict[str, Any], archetype: str
    ) -> str:
        version = template.get("templateVersion")
        if not isinstance(version, str) or not version:
            raise IllegalResearchTransition("forecast template lacks templateVersion")
        effective_inputs = {
            "capability": "EXPLICIT_FORECAST",
            "analysis_mode": "DEFAULT_TEMPLATE_PREVIEW",
            "symbol": symbol.upper(),
            "template_version": version,
            "archetype": archetype,
            "overrides": None,
        }
        encoded = json.dumps(effective_inputs, sort_keys=True, separators=(",", ":"))
        return f"sha256:{sha256(encoded.encode()).hexdigest()}"

    @staticmethod
    def _has_effective_input(
        case: ResearchCase, fingerprint: str, template: dict[str, Any], archetype: str
    ) -> bool:
        version = template["templateVersion"]
        for item in case.evidence:
            if "explicit_forecast" not in item.claim_scope:
                continue
            provenance = item.provenance
            if provenance.get("effective_input_fingerprint") == fingerprint:
                return True
            # Phase 2C evidence predates fingerprint persistence.  Its Java template
            # version, Java-selected archetype, and default mode establish the same
            # effective input identity without mutating historical artifacts.
            if (
                provenance.get("analysis_mode") == "DEFAULT_TEMPLATE_PREVIEW"
                and provenance.get("template_version") == version
                and provenance.get("archetype") == archetype
            ):
                return True
        return any(execution.effective_input_fingerprint == fingerprint for execution in case.executed_actions)

    @staticmethod
    def preview_summary(
        preview: dict[str, Any], symbol: str, expected_archetype: str,
        analysis_mode: str = "DEFAULT_TEMPLATE_PREVIEW",
    ) -> dict[str, Any]:
        required = ("forecastMode", "archetype", "readiness", "templateVersion", "scenarios")
        if any(key not in preview for key in required):
            raise IllegalResearchTransition("malformed Java forecast preview response")
        if preview.get("symbol") not in {symbol, symbol.lower()}:
            raise IllegalResearchTransition("forecast preview symbol does not match request")
        if preview["archetype"] != expected_archetype:
            raise IllegalResearchTransition("forecast preview did not use Java suggestedArchetype")
        if preview["readiness"] in {"NOT_READY", "UNAVAILABLE"}:
            raise IllegalResearchTransition("forecast preview is not ready")
        scenarios = preview["scenarios"]
        if not isinstance(scenarios, dict) or set(scenarios) != set(_SCENARIOS):
            raise IllegalResearchTransition("forecast preview must contain BEAR, BASE, and BULL")

        compact_scenarios: dict[str, dict[str, Any]] = {}
        for label in _SCENARIOS:
            result = scenarios[label]
            if not isinstance(result, dict):
                raise IllegalResearchTransition("malformed Java forecast scenario")
            compact_scenarios[label] = {
                "fcff": ExplicitForecastExecutor._track(result.get("fcff")),
                "fcfe": ExplicitForecastExecutor._track(result.get("fcfe")),
                "fcff_sensitivity": ExplicitForecastExecutor._sensitivity(
                    result.get("fcffSensitivity")
                ),
                "fcfe_sensitivity": ExplicitForecastExecutor._sensitivity(
                    result.get("fcfeSensitivity")
                ),
                "fcff_reverse_dcf": ExplicitForecastExecutor._reverse_dcf(
                    result.get("fcffReverseDcf")
                ),
                "fcfe_reverse_dcf": ExplicitForecastExecutor._reverse_dcf(
                    result.get("fcfeReverseDcf")
                ),
                "operating_schedule_years": len(result.get("operatingSchedule", [])),
            }
        missing = preview.get("missingInputs", [])
        if not isinstance(missing, list):
            raise IllegalResearchTransition("malformed Java forecast missingInputs")
        return {
            "capability": "EXPLICIT_FORECAST",
            "analysis_mode": analysis_mode,
            "forecast_mode": preview["forecastMode"],
            "template_version": preview["templateVersion"],
            "archetype": expected_archetype,
            "readiness": preview["readiness"],
            "missing_inputs": missing,
            "warnings": ExplicitForecastExecutor._warnings(preview),
            "scenarios": compact_scenarios,
        }

    @staticmethod
    def _track(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or "equityValue" not in value:
            raise IllegalResearchTransition("malformed Java valuation track")
        return {
            key: value.get(key)
            for key in (
                "cashFlowDefinition",
                "discountRateType",
                "discountRate",
                "terminalValue",
                "enterpriseValue",
                "netDebtBridge",
                "equityValue",
            )
        }

    @staticmethod
    def _sensitivity(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not isinstance(value.get("equityValues"), list):
            raise IllegalResearchTransition("malformed Java sensitivity grid")
        discount_rates = value.get("discountRates")
        terminal_growth_rates = value.get("terminalGrowthRates")
        equity_values = value["equityValues"]
        if (
            not isinstance(discount_rates, list)
            or not isinstance(terminal_growth_rates, list)
            or not discount_rates
            or not terminal_growth_rates
            or len(equity_values) != len(discount_rates)
            or any(not isinstance(row, list) or len(row) != len(terminal_growth_rates) for row in equity_values)
        ):
            raise IllegalResearchTransition("malformed Java sensitivity grid")
        middle_row = equity_values[len(equity_values) // 2]
        return {
            "dimensions": [len(discount_rates), len(terminal_growth_rates)],
            "discount_rate_range": [discount_rates[0], discount_rates[-1]],
            "terminal_growth_rate_range": [terminal_growth_rates[0], terminal_growth_rates[-1]],
            "central_equity_value": middle_row[len(middle_row) // 2],
        }

    @staticmethod
    def _reverse_dcf(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not isinstance(value.get("status"), str):
            raise IllegalResearchTransition("malformed Java reverse DCF")
        return {
            key: value.get(key)
            for key in ("status", "targetEquityValue", "impliedDiscountRate")
        }

    @staticmethod
    def _warnings(preview: dict[str, Any]) -> list[str]:
        warnings = preview.get("warnings", [])
        if not isinstance(warnings, list):
            raise IllegalResearchTransition("malformed Java forecast warnings")
        return warnings
