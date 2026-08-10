"""Small deterministic acceptance checks for the Phase 1 valuation report."""

from __future__ import annotations

import re
from decimal import Decimal

from app.contracts import ValuationReport

_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
_UNSUPPORTED_CAUSAL = re.compile(
    r"\b(?:future growth expectations?|future growth|growth expectations?|investor expectations?|market sentiment|"
    r"brand premium|brand loyalty|ecosystem(?: dominance| lock-?in)?|innovation(?: premium| momentum)?|"
    r"risk premium|mispricing|overvalu(?:ed|ation)|undervalu(?:ed|ation)|speculative demand|"
    r"margin expansion)\b",
    re.IGNORECASE,
)
_NEGATED_CAUSAL = re.compile(
    r"\b(?:no|not|cannot|can't|does not|do not|did not|insufficient|missing|unknown|"
    r"unestablished|not established|doesn't establish)\b",
    re.IGNORECASE,
)


def unsupported_numerical_claim_count(report: ValuationReport) -> int:
    """Count numerical prose claims not represented as deterministic Evidence.

    This deliberately evaluates report prose only. Numeric scenario fields are
    Java objects and are checked separately by ``all_scenario_values_grounded``.
    """

    prose = [report.conclusion, *(item.description for item in report.uncertainties)]
    prose.extend(report.warnings)
    return sum(len(_NUMBER.findall(text)) for text in prose)


def unsupported_causal_claims(text: str) -> list[str]:
    """Return ungrounded market-cause terms, while permitting explicit negation.

    The frozen Phase-1 fixture deliberately has no market-information source.
    This compact, auditable taxonomy detects the causal explanations that the
    fixture cannot establish. A nearby negation is accepted because recognising
    the absence of evidence is the intended decision in this experiment.
    """

    findings: list[str] = []
    for match in _UNSUPPORTED_CAUSAL.finditer(text):
        preceding = text[max(0, match.start() - 96) : match.start()]
        if not _NEGATED_CAUSAL.search(preceding):
            findings.append(match.group(0))
    return findings


def unsupported_numerical_text_claims(text: str, allowed_values: set[Decimal]) -> list[str]:
    """Return numerical prose tokens that are absent from deterministic evidence."""

    findings: list[str] = []
    for token in _NUMBER.findall(text):
        try:
            value = Decimal(token)
        except Exception:
            findings.append(token)
            continue
        if value not in allowed_values:
            findings.append(token)
    return findings


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
