"""Deterministic, report-facing projections of authoritative Java valuation DTOs."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.contracts import ValuationScenario, ValuationSnapshot


class CompactScenarioObservation(BaseModel):
    scenario_type: str
    selected_model: str | None
    valid: bool
    intrinsic_value_per_share: Decimal | None
    margin_of_safety_price: Decimal | None
    warnings: list[str] = Field(default_factory=list)


class CompactValuationObservation(BaseModel):
    symbol: str
    engine_version: str
    current_price: Decimal | None
    bear_value: Decimal | None
    base_value: Decimal | None
    bull_value: Decimal | None
    selected_model: str | None
    material_warnings: list[str] = Field(default_factory=list)
    scenarios: list[CompactScenarioObservation] = Field(default_factory=list)


def project_trimmed_valuation(raw: ValuationSnapshot) -> ValuationSnapshot:
    """Drop raw projection rows while preserving Phase-1 report fields exactly."""

    return ValuationSnapshot(
        symbol=raw.symbol,
        engine_version=raw.engine_version,
        selected_model=raw.selected_model,
        calculation_date=raw.calculation_date,
        data_quality=raw.data_quality,
        overview=raw.overview,
        scenarios=[
            ValuationScenario(
                scenario_type=scenario.scenario_type,
                selected_model=scenario.selected_model,
                valid=scenario.valid,
                intrinsic_value_per_share=scenario.intrinsic_value_per_share,
                margin_of_safety_price=scenario.margin_of_safety_price,
                warnings=scenario.warnings,
                resolved_assumptions=scenario.resolved_assumptions,
            )
            for scenario in raw.scenarios
        ],
        diagnostics=raw.diagnostics,
        missing_fields=raw.missing_fields,
        field_sources=raw.field_sources,
    )


def project_compact_valuation(raw: ValuationSnapshot) -> CompactValuationObservation:
    """Map Java facts to the smallest observation needed for the replay probe."""

    overview = raw.overview or {}
    warnings: list[str] = []
    data_quality = raw.data_quality or {}
    for reason in data_quality.get("reasons", []):
        if isinstance(reason, str):
            warnings.append(reason)
    for diagnostic in raw.diagnostics:
        if isinstance(diagnostic.get("message"), str):
            warnings.append(diagnostic["message"])
    for scenario in raw.scenarios:
        warnings.extend(scenario.warnings)
    return CompactValuationObservation(
        symbol=raw.symbol,
        engine_version=raw.engine_version,
        current_price=_decimal(overview.get("currentPrice")),
        bear_value=_decimal(overview.get("bearValue")),
        base_value=_decimal(overview.get("baseValue")),
        bull_value=_decimal(overview.get("bullValue")),
        selected_model=raw.selected_model,
        material_warnings=list(dict.fromkeys(warnings)),
        scenarios=[
            CompactScenarioObservation(
                scenario_type=scenario.scenario_type,
                selected_model=scenario.selected_model,
                valid=scenario.valid,
                intrinsic_value_per_share=scenario.intrinsic_value_per_share,
                margin_of_safety_price=scenario.margin_of_safety_price,
                warnings=scenario.warnings,
            )
            for scenario in raw.scenarios
        ],
    )


def _decimal(value: object) -> Decimal | None:
    return value if isinstance(value, Decimal) else None
