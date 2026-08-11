"""Phase 2A persistent, provenance-bound ResearchCase state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts import Evidence, ValuationReport


class ResearchEvidence(BaseModel):
    """Adds inspectable provenance to the existing Phase 1 evidence contract."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    evidence: Evidence
    source: str
    source_type: Literal["deterministic_valuation", "external", "specialist"]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claim_scope: tuple[str, ...] = ()
    provenance: dict[str, str] = Field(default_factory=dict)
    numerical_authority: Literal["deterministic_valuation", "external_source", "none"] = "none"

    @model_validator(mode="after")
    def validate_authority(self) -> ResearchEvidence:
        if self.numerical_authority == "deterministic_valuation" and self.source_type != "deterministic_valuation":
            raise ValueError("deterministic numerical authority requires deterministic valuation evidence")
        if self.source_type == "specialist" and self.numerical_authority != "none":
            raise ValueError("specialist output cannot be numerical authority")
        return self


class ResearchAction(BaseModel):
    """Typed semantic decision; it deliberately contains no executable protocol."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action: Literal["REQUEST_EVIDENCE", "RUN_SCENARIO", "DELEGATE_SPECIALIST", "FINALIZE"]
    reason: str = Field(min_length=1, max_length=600)
    request: str | None = None
    selected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def evidence_request_requires_information_need(self) -> ResearchAction:
        if self.action == "REQUEST_EVIDENCE" and not self.request:
            raise ValueError("REQUEST_EVIDENCE requires a bounded information need")
        return self


class ExecutedResearchAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: ResearchAction
    started_at: datetime
    completed_at: datetime
    produced_evidence_ids: tuple[str, ...] = ()


class SpecialistResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    specialist: str
    summary: str
    evidence_ids: tuple[str, ...] = ()
    started_at: datetime
    completed_at: datetime


class ResearchCase(BaseModel):
    """Canonical state whose history reconstructs each Controller-to-runtime step."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    valuation_context: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[ResearchEvidence, ...] = ()
    findings: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    executed_actions: tuple[ExecutedResearchAction, ...] = ()
    specialist_results: tuple[SpecialistResult, ...] = ()
    current_hypothesis: str | None = None
    pending_action: ResearchAction | None = None
    status: Literal["OPEN", "FINALIZED"] = "OPEN"
    iteration_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=8, ge=1)
    final_report: ValuationReport | None = None

    @model_validator(mode="after")
    def validate_state(self) -> ResearchCase:
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("ResearchCase evidence ids must be unique")
        if self.status == "FINALIZED" and self.final_report is None:
            raise ValueError("finalized ResearchCase requires final_report")
        return self

    def select(self, action: ResearchAction) -> ResearchCase:
        if self.status != "OPEN" or self.pending_action is not None:
            raise IllegalResearchTransition("case cannot select an action in its current state")
        if self.iteration_count >= self.max_iterations:
            raise ResearchIterationLimit("research iteration bound reached")
        return self.model_copy(update={"pending_action": action, "iteration_count": self.iteration_count + 1})

    def record_execution(self, execution: ExecutedResearchAction, evidence: tuple[ResearchEvidence, ...] = ()) -> ResearchCase:
        if self.pending_action is None or execution.action.action_id != self.pending_action.action_id:
            raise IllegalResearchTransition("execution must match pending action")
        old = {item.evidence_id for item in self.evidence}
        new = {item.evidence_id for item in evidence}
        if old & new or len(new) != len(evidence):
            raise IllegalResearchTransition("evidence provenance may not be overwritten")
        return self.model_copy(update={"evidence": self.evidence + evidence, "executed_actions": self.executed_actions + (execution,), "pending_action": None})


class IllegalResearchTransition(ValueError):
    pass


class ResearchIterationLimit(ValueError):
    pass


class GroundingFailure(ValueError):
    pass
