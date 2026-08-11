"""Phase 2A persistent, provenance-bound ResearchCase state."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts import Evidence, ValuationReport


class RevenueGuidance(BaseModel):
    """Single accepted Phase 2D external evidence representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    metric: Literal["REVENUE"]
    representation: Literal["ABSOLUTE_FY_RANGE"]
    low: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    currency: Literal["USD"]
    target_fiscal_year: int = Field(ge=2000, le=3000)
    raw_fact: str = Field(min_length=1, max_length=2_000)
    published_at: datetime
    source_url: str = Field(min_length=1, max_length=2_000)
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_range(self) -> RevenueGuidance:
        if self.high < self.low:
            raise ValueError("revenue guidance high must be greater than or equal to low")
        return self


class EvidenceAvailability(BaseModel):
    """Deterministic statement of whether a bounded fiscal fact exists as of the case date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    availability_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str = Field(min_length=1, max_length=16)
    evidence_type: Literal["SEC_REPORTED_REVENUE"]
    as_of_date: datetime
    latest_fiscal_year: int
    latest_fiscal_period: Literal["Q1", "Q2", "Q3", "Q4", "FY"]
    latest_period_end: str = Field(min_length=1)
    source: str = Field(min_length=1)
    provenance: dict[str, str] = Field(default_factory=dict)


class EvidenceRequestTarget(BaseModel):
    """Bounded fiscal evidence target selected semantically by the Controller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_type: Literal["SEC_REPORTED_REVENUE"]
    symbol: str = Field(min_length=1, max_length=16)
    fiscal_year: int = Field(ge=2000, le=3000)
    fiscal_period: Literal["Q1", "Q2", "Q3", "Q4", "FY"]


class EvidenceRequestOutcome(BaseModel):
    """Persistent deterministic result when a requested fact is not presently available."""

    model_config = ConfigDict(frozen=True)

    outcome_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str
    target: EvidenceRequestTarget
    status: Literal["NOT_YET_AVAILABLE"]
    availability_id: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = Field(min_length=1, max_length=1_000)


class ResearchUncertainty(BaseModel):
    """A provenance-bound uncertainty the Controller may explicitly retain at closure."""

    model_config = ConfigDict(frozen=True)

    uncertainty_id: str = Field(default_factory=lambda: str(uuid4()))
    description: str = Field(min_length=1, max_length=1_000)
    source_evidence_id: str = Field(min_length=1)


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
    originating_evidence_ids: tuple[str, ...] = ()
    revenue_guidance: RevenueGuidance | None = None

    @model_validator(mode="after")
    def validate_authority(self) -> ResearchEvidence:
        if (
            self.numerical_authority == "deterministic_valuation"
            and self.source_type != "deterministic_valuation"
        ):
            raise ValueError(
                "deterministic numerical authority requires deterministic valuation evidence"
            )
        if self.source_type == "specialist" and self.numerical_authority != "none":
            raise ValueError("specialist output cannot be numerical authority")
        if self.revenue_guidance is not None:
            if self.source_type != "external" or self.numerical_authority != "external_source":
                raise ValueError("revenue guidance requires external-source authority")
        return self


class ValuationAnalysisRequest(BaseModel):
    """The only Phase 2C valuation-analysis request exposed to the Controller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: Literal["EXPLICIT_FORECAST"]
    symbol: str = Field(min_length=1, max_length=16)
    rationale: str = Field(min_length=1, max_length=600)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    analysis_mode: Literal["DEFAULT_TEMPLATE_PREVIEW", "EVIDENCE_GROUNDED_OVERRIDE"]
    assumption_application: Literal["YEAR_1_REVENUE_GUIDANCE"] | None = None

    @model_validator(mode="after")
    def distinct_evidence_ids(self) -> ValuationAnalysisRequest:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("valuation analysis evidence_ids must be unique")
        if (
            self.analysis_mode == "DEFAULT_TEMPLATE_PREVIEW"
            and self.assumption_application is not None
        ):
            raise ValueError("default template preview cannot apply an assumption")
        if (
            self.analysis_mode == "EVIDENCE_GROUNDED_OVERRIDE"
            and self.assumption_application != "YEAR_1_REVENUE_GUIDANCE"
        ):
            raise ValueError("evidence-grounded override requires YEAR_1_REVENUE_GUIDANCE")
        return self


class ResearchAction(BaseModel):
    """Typed semantic decision; it deliberately contains no executable protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action: Literal[
        "REQUEST_EVIDENCE",
        "REQUEST_VALUATION_ANALYSIS",
        "RUN_SCENARIO",
        "DELEGATE_SPECIALIST",
        "FINALIZE",
    ]
    reason: str = Field(min_length=1, max_length=600)
    request: str | None = None
    evidence_target: EvidenceRequestTarget | None = None
    valuation_analysis: ValuationAnalysisRequest | None = None
    unresolved_uncertainty_ids: tuple[str, ...] = ()
    selected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def evidence_request_requires_information_need(self) -> ResearchAction:
        if self.action == "REQUEST_EVIDENCE" and not self.request:
            raise ValueError("REQUEST_EVIDENCE requires a bounded information need")
        if self.action != "REQUEST_EVIDENCE" and self.request is not None:
            raise ValueError("request is only valid for REQUEST_EVIDENCE")
        if self.evidence_target is not None and self.action != "REQUEST_EVIDENCE":
            raise ValueError("evidence_target is only valid for REQUEST_EVIDENCE")
        if self.action == "REQUEST_VALUATION_ANALYSIS" and self.valuation_analysis is None:
            raise ValueError("REQUEST_VALUATION_ANALYSIS requires valuation_analysis")
        if self.action != "REQUEST_VALUATION_ANALYSIS" and self.valuation_analysis is not None:
            raise ValueError("valuation_analysis is only valid for REQUEST_VALUATION_ANALYSIS")
        if self.action != "FINALIZE" and self.unresolved_uncertainty_ids:
            raise ValueError("unresolved_uncertainty_ids are only valid for FINALIZE")
        if len(self.unresolved_uncertainty_ids) != len(set(self.unresolved_uncertainty_ids)):
            raise ValueError("unresolved_uncertainty_ids must be unique")
        return self


class ExecutedResearchAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: ResearchAction
    started_at: datetime
    completed_at: datetime
    produced_evidence_ids: tuple[str, ...] = ()
    effective_input_fingerprint: str | None = None


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
    tracked_uncertainties: tuple[ResearchUncertainty, ...] = ()
    evidence_availability: tuple[EvidenceAvailability, ...] = ()
    evidence_request_outcomes: tuple[EvidenceRequestOutcome, ...] = ()
    executed_actions: tuple[ExecutedResearchAction, ...] = ()
    specialist_results: tuple[SpecialistResult, ...] = ()
    current_hypothesis: str | None = None
    pending_action: ResearchAction | None = None
    status: Literal["OPEN", "FINALIZED", "FINALIZED_WITH_LIMITATIONS"] = "OPEN"
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
        uncertainty_ids = [item.uncertainty_id for item in self.tracked_uncertainties]
        if len(uncertainty_ids) != len(set(uncertainty_ids)):
            raise ValueError("ResearchCase uncertainty ids must be unique")
        return self

    def select(self, action: ResearchAction) -> ResearchCase:
        if self.status != "OPEN" or self.pending_action is not None:
            raise IllegalResearchTransition("case cannot select an action in its current state")
        if self.iteration_count >= self.max_iterations:
            raise ResearchIterationLimit("research iteration bound reached")
        return self.model_copy(
            update={"pending_action": action, "iteration_count": self.iteration_count + 1}
        )

    def record_execution(
        self,
        execution: ExecutedResearchAction,
        evidence: tuple[ResearchEvidence, ...] = (),
        evidence_request_outcome: EvidenceRequestOutcome | None = None,
    ) -> ResearchCase:
        if (
            self.pending_action is None
            or execution.action.action_id != self.pending_action.action_id
        ):
            raise IllegalResearchTransition("execution must match pending action")
        old = {item.evidence_id for item in self.evidence}
        new = {item.evidence_id for item in evidence}
        if old & new or len(new) != len(evidence):
            raise IllegalResearchTransition("evidence provenance may not be overwritten")
        if (
            evidence_request_outcome is not None
            and evidence_request_outcome.action_id != execution.action.action_id
        ):
            raise IllegalResearchTransition("evidence request outcome must match pending action")
        return self.model_copy(
            update={
                "evidence": self.evidence + evidence,
                "executed_actions": self.executed_actions + (execution,),
                "evidence_request_outcomes": (
                    self.evidence_request_outcomes + (evidence_request_outcome,)
                    if evidence_request_outcome is not None
                    else self.evidence_request_outcomes
                ),
                "pending_action": None,
            }
        )


class IllegalResearchTransition(ValueError):
    pass


class ResearchIterationLimit(ValueError):
    pass


class GroundingFailure(ValueError):
    pass
