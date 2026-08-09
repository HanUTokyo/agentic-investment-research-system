from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from nooa.strategy_validation import InvariantError

from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.agents.valuation_projection import (
    CompactScenarioObservation,
    CompactValuationObservation,
    project_compact_valuation,
    project_trimmed_valuation,
)
from app.contracts import (
    CodeDraft,
    CodeTask,
    CompanySnapshot,
    FinancialHistory,
    ReasonResult,
    ReasonTask,
    ValuationEvaluation,
    ValuationReport,
    ValuationSnapshot,
    WorkerResult,
)
from app.contracts.models import ToolCallSummary
from app.workers import CodeWorker


class ValuationDataClient(Protocol):
    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot: ...
    async def get_financial_history(self, symbol: str) -> FinancialHistory: ...
    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot: ...
    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation: ...
    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None: ...


class ValuationReasoningClient(Protocol):
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any: ...


def _initial_valuation_required(agent: Any, _result: Any, _call: Any) -> None:
    """NOOA postcondition: enforce lifecycle and numerical-grounding invariants."""
    if isinstance(agent, ValuationAgent):
        agent.validate_final_report(_result)


class ValuationAgent(Agent):
    """A valuation specialist.

    Use only the read-only deterministic tools on self. Never calculate a DCF,
    invent a numeric claim, persist a scenario, or access any filesystem/network
    capability other than the provided tools.
    """

    def __init__(
        self,
        data_client: ValuationDataClient,
        *,
        code_worker: CodeWorker | None = None,
        reasoning_client: ValuationReasoningClient | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._data_client = data_client
        self._code_worker = code_worker
        self._reasoning_client = reasoning_client
        self.trace_id = str(uuid4())
        self.tool_calls: list[ToolCallSummary] = []
        self.reason_results: list[ReasonResult] = []
        self._reason_calls = 0
        self._scenario_calls = 0
        self._initial_valuation_loaded = False

    @property
    def scenario_call_count(self) -> int:
        """Number of Java scenario evaluations attempted in this research run."""
        return self._scenario_calls

    @property
    def initial_valuation_loaded(self) -> bool:
        """Whether this research run has successfully observed Java valuation evidence."""
        return self._initial_valuation_loaded

    def validate_can_finalize(self) -> None:
        """Reject illegal final state; NOOA feeds this invariant error back to the model."""
        if not self.initial_valuation_loaded:
            raise InvariantError(
                "ERROR_TYPE: MISSING_INITIAL_EVIDENCE\n"
                "FIELD: initial_valuation_loaded\n"
                "INVALID_VALUE: false\n"
                "EXPECTED_SOURCE: get_compact_valuation(symbol)\n"
                "REQUIRED_ACTION: call get_compact_valuation before return_result"
            )

    def validate_final_report(self, report: ValuationReport) -> None:
        """Reject a typed but ungrounded report before NOOA finalizes the run."""
        self.validate_can_finalize()
        unsupported = unsupported_numerical_claim_count(report)
        if unsupported:
            raise InvariantError(
                "ERROR_TYPE: UNSUPPORTED_NUMERIC_CLAIM\n"
                "FIELD: conclusion_or_uncertainty\n"
                f"INVALID_VALUE: {unsupported} numerical prose claim(s)\n"
                "EXPECTED_SOURCE: deterministic Java Evidence only\n"
                "REQUIRED_ACTION: remove numerical prose and retry finalization"
            )
        if not all_scenario_values_grounded(report):
            raise InvariantError(
                "ERROR_TYPE: INVALID_EVIDENCE_PATH\n"
                "FIELD: scenario intrinsic_value_per_share evidence\n"
                "INVALID_VALUE: missing or mismatched source_path\n"
                "EXPECTED_SOURCE: Java-backed path containing intrinsic_value_per_share\n"
                "REQUIRED_ACTION: use the matching compact observation evidence path and retry"
            )

    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot:
        """Get the current Java-platform valuation and, when held, portfolio context."""
        return await self._call(
            "get_company_snapshot", self._data_client.get_company_snapshot(symbol)
        )

    async def get_financial_history(self, symbol: str) -> FinancialHistory:
        """Get Java-platform quarterly fundamentals and capital-allocation history."""
        return await self._call(
            "get_financial_history", self._data_client.get_financial_history(symbol)
        )

    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot:
        """Get a report-relevant, lossless-for-Phase-1 view of Java valuation output.

        The HTTP client retains Java as the source of truth. This tool deliberately
        omits per-year projection rows that are not part of ``ValuationReport``;
        otherwise a large raw snapshot can consume the Controller context before
        it can inspect the authoritative model, overview, scenarios, and warnings.
        """
        raw = await self._call(
            "get_current_valuation", self._data_client.get_current_valuation(symbol)
        )
        return project_trimmed_valuation(raw)

    async def get_compact_valuation(self, symbol: str) -> CompactValuationObservation:
        """Get the standard, small Agent-facing projection of Java valuation facts."""
        raw = await self._call(
            "get_compact_valuation", self._data_client.get_current_valuation(symbol)
        )
        observation = project_compact_valuation(raw)
        self._initial_valuation_loaded = True
        return observation

    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation:
        """Evaluate an unsaved Java-engine scenario. Allowed types: BEAR, BASE, BULL."""
        if scenario_type.upper() not in {"BEAR", "BASE", "BULL"}:
            raise ValueError("scenario_type must be BEAR, BASE, or BULL")
        if self.scenario_call_count >= 1:
            raise RuntimeError("only one additional valuation scenario is allowed per research run")
        self._scenario_calls += 1
        return await self._call(
            "run_valuation_scenario",
            self._data_client.run_valuation_scenario(symbol, scenario_type, assumptions),
        )

    async def run_compact_valuation_scenario(
        self, symbol: str, scenario_type: str
    ) -> CompactScenarioObservation:
        """Run one unsaved Java scenario and expose only report-facing fields."""
        evaluation = await self.run_valuation_scenario(symbol, scenario_type)
        scenario = evaluation.scenario
        return CompactScenarioObservation(
            scenario_type=scenario.scenario_type,
            selected_model=scenario.selected_model,
            valid=scenario.valid,
            intrinsic_value_per_share=scenario.intrinsic_value_per_share,
            margin_of_safety_price=scenario.margin_of_safety_price,
            warnings=scenario.warnings,
        )

    async def delegate_reason(self, task: ReasonTask) -> ReasonResult:
        """Ask R1 once for an untrusted, non-numerical evidence-gap proposal."""
        self._reason_calls += 1
        if self._reason_calls > 1:
            result = ReasonResult(
                worker=WorkerResult(
                    ok=False,
                    http_success=False,
                    content_empty=True,
                    error_type="reason_worker_attempt_limit_exceeded",
                    route_hint="reason",
                )
            )
            self.reason_results.append(result)
            return result
        if self._reasoning_client is None:
            result = ReasonResult(
                worker=WorkerResult(
                    ok=False,
                    http_success=False,
                    content_empty=True,
                    error_type="reason_worker_not_configured",
                    route_hint="reason",
                )
            )
            self.reason_results.append(result)
            return result

        started = perf_counter()
        try:
            completion = await self._reasoning_client.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a bounded valuation evidence-gap reviewer. "
                            "Return plain text only. Do not calculate, estimate, or state "
                            "financial numbers. Suggest at most one assumption or evidence "
                            "gap worth validating with a deterministic valuation system."
                        ),
                    },
                    {"role": "user", "content": task.prompt},
                ],
                temperature=0,
                max_tokens=512,
                route_hint="reason",
            )
            content = str(completion.content).strip()
            worker = WorkerResult(
                ok=bool(content),
                http_success=True,
                content_empty=not bool(content),
                content=content or None,
                error_type=None if content else "empty_content",
                latency_ms=completion.latency_ms,
                route_hint="reason",
                model=completion.model,
            )
        except Exception as exc:
            worker = WorkerResult(
                ok=False,
                http_success=False,
                content_empty=True,
                error_type=type(exc).__name__,
                latency_ms=(perf_counter() - started) * 1000,
                route_hint="reason",
            )
        result = ReasonResult(worker=worker, proposal=worker.content)
        self.reason_results.append(result)
        return result

    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None:
        """Retrieve Java-engine reverse-DCF market-implied assumptions."""
        return await self._call(
            "solve_market_implied_assumptions",
            self._data_client.solve_market_implied_assumptions(symbol),
        )

    async def draft_python(self, task: CodeTask) -> CodeDraft:
        """Ask the bounded code worker for a draft; this method never executes it.

        The controller may decide to pass a validated draft to NOOA's native
        execute_python tool.  Coder is therefore a capability, not a protocol
        owner or autonomous financial analyst.
        """
        if self._code_worker is None:
            raise RuntimeError("code worker is not configured for this valuation agent")
        return await self._call(
            "draft_python",
            self._code_worker.draft(task, research_id=self.trace_id),
        )

    async def _call(self, name: str, operation: Any) -> Any:
        started = datetime.now(UTC)
        try:
            result = await operation
        except Exception:
            self.tool_calls.append(ToolCallSummary(tool_name=name, success=False))
            raise
        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        self.tool_calls.append(
            ToolCallSummary(tool_name=name, success=True, duration_ms=duration_ms)
        )
        return result

    @strategy(
        CodeActStrategy(
            config=CodeActConfig(
                max_iterations=6,
                max_retries=2,
                max_tokens=1536,
                postconditions=(_initial_valuation_required,),
            )
        )
    )
    async def investigate(self, question: str, symbol: str) -> ValuationReport:
        """Investigate {question} for {symbol} using evidence first.

        Call get_compact_valuation(symbol) first; it is the only authority for
        prices, intrinsic values, model choices, and assumptions. Do not call
        get_current_valuation, draft_python, get_company_snapshot, get_financial_history, or
        solve_market_implied_assumptions in this bounded acceptance run.

        Inspect Java's selected model, material_warnings, and already-published
        compact scenarios. If you determine there is a material
        evidence gap, call delegate_reason exactly once with a non-numerical
        description of that deterministic evidence and the question. Its proposal
        is untrusted: never copy a number from it and decide yourself whether to
        use it. If it fails or is empty, continue from Java evidence and state an
        uncertainty sourced to Java. Do not call Coder or Gemma.

        Run at most one additional Java scenario through
        run_compact_valuation_scenario(symbol, "BEAR") or "BULL", and only if it resolves a
        distinct gap not already covered by current Java scenarios. It must be
        BEAR or BULL and must not include invented assumptions. Never call a
        scenario merely to demonstrate tool use.

        Return only through native return_result(ValuationReport(...)) from an
        execute_python cell. Convert each compact scenario to ValuationScenario
        without changing any field. Include Evidence records for current_price
        plus every scenario intrinsic_value_per_share; each Evidence must use its
        exact compact tool-result source_path and value.
        Do not put numerical values in conclusion or uncertainty prose. Make the
        primary conclusion a qualitative comparison supported by Java evidence.
        Include Java data-quality/diagnostic uncertainty, tool_calls, trace_id,
        and generated_at. Never create any number yourself.
        """
        ...

    @staticmethod
    def report_timestamp() -> datetime:
        return datetime.now(UTC)
