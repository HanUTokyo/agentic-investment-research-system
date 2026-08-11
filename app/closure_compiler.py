"""Minimal deterministic compilation of a bounded semantic closure decision."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, model_validator

from app.research_case import IllegalResearchTransition, ResearchAction, ResearchCase


class ClosureDecision(BaseModel):
    """Semantic-only conclusion; this is deliberately not a ResearchAction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["CONTINUE", "TERMINATE"]
    remaining_uncertainty_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_uncertainties(self) -> ClosureDecision:
        if len(self.remaining_uncertainty_ids) != len(set(self.remaining_uncertainty_ids)):
            raise ValueError("remaining_uncertainty_ids must be unique")
        return self


def compile_terminal_action(case: ResearchCase, decision: ClosureDecision) -> ResearchAction | None:
    """Compile an already-selected termination semantic into the legal action shape.

    A CONTINUE decision deliberately produces no action.  The compiler never
    upgrades a continuation into termination and never selects uncertainties.
    """
    if decision.decision == "CONTINUE":
        return None
    known = {item.uncertainty_id for item in case.tracked_uncertainties}
    if not set(decision.remaining_uncertainty_ids).issubset(known):
        raise IllegalResearchTransition("closure decision must reference tracked uncertainties")
    return ResearchAction(
        action="FINALIZE",
        reason="Controller semantic closure decision: TERMINATE.",
        unresolved_uncertainty_ids=decision.remaining_uncertainty_ids,
    )


def parse_closure_markers(raw: str) -> ClosureDecision:
    """Accept one explicit semantic declaration; do not repair or infer output.

    Markdown emphasis around an otherwise exact declaration is presentation-only,
    so it is normalized before matching.  No decision value is inferred.
    """
    lines = [line.strip().strip("*").strip() for line in raw.splitlines() if line.strip()]
    decisions = [
        line.removeprefix("CLOSURE_DECISION:").strip()
        for line in lines
        if line.startswith("CLOSURE_DECISION:")
    ]
    uncertainty_values = [
        line.removeprefix("REMAINING_UNCERTAINTIES:").strip()
        for line in lines
        if line.startswith("REMAINING_UNCERTAINTIES:")
    ]
    if len(decisions) != 1 or len(uncertainty_values) != 1:
        raise ValueError(
            "closure response requires exactly one decision and uncertainty declaration"
        )
    if uncertainty_values[0] == "NONE":
        ids: tuple[str, ...] = ()
    else:
        ids = tuple(part.strip() for part in uncertainty_values[0].split(",") if part.strip())
    return ClosureDecision(
        decision=cast(Literal["CONTINUE", "TERMINATE"], decisions[0]),
        remaining_uncertainty_ids=ids,
    )
