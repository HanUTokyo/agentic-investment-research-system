from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: "".join(
            [value.split("_")[0], *[part.capitalize() for part in value.split("_")[1:]]]
        ),
        populate_by_name=True,
        extra="allow",
    )


class FieldSource(ContractModel):
    source: str | None = None
    field: str | None = None
    as_of_date: date | None = None


class ValuationScenario(ContractModel):
    scenario_type: str
    selected_model: str | None = None
    valid: bool
    intrinsic_value_per_share: Decimal | None = None
    margin_of_safety_price: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)
    resolved_assumptions: dict[str, Any] | None = None


class ValuationSnapshot(ContractModel):
    symbol: str
    engine_version: str
    selected_model: str | None = None
    calculation_date: date | None = None
    data_quality: dict[str, Any] | None = None
    overview: dict[str, Decimal | None] | None = None
    scenarios: list[ValuationScenario] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)


class ValuationEvaluation(ContractModel):
    symbol: str
    engine_version: str
    scenario: ValuationScenario
    sensitivity: dict[str, Any] | None = None
    reverse_dcf: dict[str, Decimal | str | None] | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class FinancialHistory(ContractModel):
    symbol: str
    quarterly_fundamentals: list[dict[str, Any]] = Field(default_factory=list)
    capital_allocation: dict[str, Any] | None = None


class CompanySnapshot(ContractModel):
    symbol: str
    valuation: ValuationSnapshot
    holding: dict[str, Any] | None = None


class Evidence(ContractModel):
    claim: str
    source_path: str
    value: Decimal | str | bool | None = None
    source_field: str | None = None


class Uncertainty(ContractModel):
    description: str
    severity: Literal["low", "medium", "high"]
    source_path: str | None = None


class ToolCallSummary(ContractModel):
    tool_name: str
    success: bool
    duration_ms: float | None = None


class MethodSpec(ContractModel):
    """A bounded method signature visible to the code-generation worker."""

    name: str
    signature: str
    description: str


class CodeTask(ContractModel):
    """A small, non-financial computation delegated to the code worker."""

    objective: str
    available_methods: list[MethodSpec] = Field(default_factory=list)
    known_variables: dict[str, str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    expected_result: str


class CodeDraft(ContractModel):
    """Untrusted code: it is validated before NOOA may execute it."""

    code: str = Field(min_length=1, max_length=4_000)
    explanation: str | None = Field(default=None, max_length=1_000)
    assumptions: list[str] = Field(default_factory=list, max_length=10)


class CodeDraftTrace(ContractModel):
    research_id: str
    agent: str = "valuation"
    stage: str = "code_worker"
    worker_invoked: bool = True
    router_route: str = "code"
    model: str | None = None
    latency_ms: float | None = None
    code_length: int | None = None
    validation_status: Literal["accepted", "rejected"]
    execution_status: Literal["not_executed", "executed", "failed"] = "not_executed"
    iteration: int | None = None


class ReasonTask(ContractModel):
    prompt: str = Field(min_length=1, max_length=1_000)


class CodeTaskText(ContractModel):
    prompt: str = Field(min_length=1, max_length=1_000)


class ChatTask(ContractModel):
    prompt: str = Field(min_length=1, max_length=1_000)


class WorkerResult(ContractModel):
    ok: bool
    http_success: bool
    content_empty: bool
    content: str | None = None
    error_type: str | None = None
    latency_ms: float | None = None
    # ``auto`` is the production default: the Router's existing rule +
    # classifier policy selects the model.  The named values remain only for
    # historical compatibility probes that explicitly tested route hints.
    route_hint: Literal["auto", "reason", "code", "chat"] = "auto"
    requested_capability: Literal["reason", "code", "chat"] | None = None
    model: str | None = None


class ReasonResult(ContractModel):
    """An untrusted, non-numerical proposal from the bounded R1 worker."""

    worker: WorkerResult
    proposal: str | None = None
    trusted_for_numerical_claims: bool = False


class NextActionDecision(ContractModel):
    """A deliberately small controller decision for the Phase 1B dispatcher."""

    action: Literal[
        "RUN_SCENARIO",
        "DELEGATE_REASON",
        "DELEGATE_CODE",
        "DELEGATE_CHAT",
        "FINALIZE",
    ]
    reason: str = Field(min_length=1, max_length=600)


class NoRouterNextActionDecision(ContractModel):
    """Evaluation-only decision contract when the reasoning capability is disabled."""

    action: Literal["RUN_SCENARIO", "FINALIZE"]
    reason: str = Field(min_length=1, max_length=1_200)


class RecoveryDecision(ContractModel):
    """Bounded recovery choice; retained for a later probe, not auto-dispatched."""

    action: Literal[
        "REFETCH_EVIDENCE",
        "RERUN_SCENARIO",
        "RETRY_FINALIZATION",
        "DELEGATE_REASON",
    ]
    reason: str = Field(min_length=1, max_length=600)


class ValuationSynthesis(ContractModel):
    """Qualitative controller output materialized against deterministic Java facts.

    It intentionally contains no valuation figures.  The runtime attaches all
    numerical fields and their evidence paths directly from Java observations.
    """

    conclusion: str = Field(min_length=1, max_length=1_200)
    valuation_basis: str = Field(min_length=1, max_length=120)
    primary_uncertainty: str = Field(min_length=1, max_length=800)
    uncertainty_severity: Literal["low", "medium", "high"]


class RecoveryPlan(ContractModel):
    """Bounded R1 proposal for a Controller-owned invariant recovery action."""

    error_type: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    required_tool: str | None = None
    expected_evidence: str | None = None


class DelegationResult(ContractModel):
    reason_summary: str = Field(min_length=1)
    code_answer: str = Field(min_length=1)
    chat_summary: str = Field(min_length=1)
    final_answer: str = Field(min_length=1)


class ReasonDelegationResult(ContractModel):
    worker_answer: str = Field(min_length=1)
    final_answer: str = Field(min_length=1)


class ReasonCodeDelegationResult(ContractModel):
    reason_answer: str = Field(min_length=1)
    untrusted_code_draft: str = Field(min_length=1)
    code_draft_trusted: bool = False
    verification_source: Literal["deterministic_expression"]
    final_answer: str = Field(min_length=1)


class SerialDelegationResult(ContractModel):
    """Stage 3 result with an explicit trust boundary for the Coder draft."""

    reason_answer: str = Field(min_length=1)
    untrusted_code_draft: str = Field(min_length=1)
    code_draft_trusted: bool = False
    chat_summary: str = Field(min_length=1)
    verification_source: Literal["deterministic_expression"]
    final_answer: str = Field(min_length=1)


class ValuationReport(ContractModel):
    symbol: str
    conclusion: str
    valuation_basis: str
    engine_version: str
    scenario_results: list[ValuationScenario]
    market_implied_assumptions: dict[str, Decimal | str | None] | None = None
    evidence: list[Evidence]
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    trace_id: str
    generated_at: datetime
