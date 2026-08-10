from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.valuation_grounding import (
    unsupported_causal_claims,
    unsupported_numerical_text_claims,
)
from app.contracts import NextActionDecision


def test_request_evidence_requires_market_information() -> None:
    decision = NextActionDecision.model_validate(
        {
            "action": "REQUEST_EVIDENCE",
            "evidence_type": "MARKET_INFORMATION",
            "reason": "The valuation gap is established but its cause is not.",
        }
    )

    assert decision.evidence_type == "MARKET_INFORMATION"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "REQUEST_EVIDENCE", "reason": "Need additional evidence."},
        {
            "action": "FINALIZE",
            "evidence_type": "MARKET_INFORMATION",
            "reason": "This is not a request.",
        },
    ],
)
def test_evidence_type_is_valid_only_for_evidence_requests(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        NextActionDecision.model_validate(payload)


def test_causal_evaluator_distinguishes_missing_evidence_from_speculation() -> None:
    assert (
        unsupported_causal_claims(
            "The supplied evidence does not establish market sentiment or future growth expectations."
        )
        == []
    )
    assert unsupported_causal_claims(
        "The price gap reflects market sentiment and future growth expectations."
    ) == ["market sentiment", "future growth expectations"]


def test_numerical_text_evaluator_requires_deterministic_value() -> None:
    allowed = {Decimal("84"), Decimal("120")}

    assert (
        unsupported_numerical_text_claims("The supplied values include 84 and 120.", allowed) == []
    )
    assert unsupported_numerical_text_claims("The fair value is 999.", allowed) == ["999"]
