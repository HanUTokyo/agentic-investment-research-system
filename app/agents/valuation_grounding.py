"""Small deterministic acceptance checks for the Phase 1 valuation report."""

from __future__ import annotations

import re
from decimal import Decimal

from app.contracts import ValuationReport

_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")


def unsupported_numerical_claim_count(report: ValuationReport) -> int:
    """Count numerical prose claims not represented as deterministic Evidence.

    This deliberately evaluates report prose only. Numeric scenario fields are
    Java objects and are checked separately by ``all_scenario_values_grounded``.
    """

    prose = [report.conclusion, *(item.description for item in report.uncertainties)]
    prose.extend(report.warnings)
    return sum(len(_NUMBER.findall(text)) for text in prose)


def all_scenario_values_grounded(report: ValuationReport) -> bool:
    """Require Java-backed Evidence for every non-null scenario intrinsic value."""

    evidence_values = {
        value
        for item in report.evidence
        if "intrinsic_value_per_share" in item.source_path
        for value in [_as_decimal(item.value)]
        if value is not None
    }
    scenario_values = {
        scenario.intrinsic_value_per_share
        for scenario in report.scenario_results
        if scenario.intrinsic_value_per_share is not None
    }
    return scenario_values <= evidence_values


def _as_decimal(value: object) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    return None
