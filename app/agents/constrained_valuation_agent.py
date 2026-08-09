"""Phase 1B: typed controller decisions with deterministic action dispatch.

This module is intentionally separate from the Phase 1A CodeAct agent.  The
controller decides *what* investigation step is useful; the runtime owns every
async invocation, permission, lifecycle transition, and numeric field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

from nooa.config import PredictConfig
from nooa.decorators import strategy
from nooa.strategies import PredictStrategy

from app.agents.valuation_agent import ValuationAgent
from app.agents.valuation_grounding import unsupported_numerical_claim_count
from app.agents.valuation_projection import CompactScenarioObservation, CompactValuationObservation
from app.contracts import (
    Evidence,
    NextActionDecision,
    ReasonResult,
    ReasonTask,
    Uncertainty,
    ValuationReport,
    ValuationScenario,
    ValuationSynthesis,
)

DecisionFailure = Literal[
    "TYPED_DECISION_GENERATION",
    "MODEL_SEMANTIC_DECISION",
    "DISPATCHER_EXECUTION",
    "SPECIALIST_OUTPUT",
    "FINAL_SYNTHESIS",
    "GROUNDING_VALIDATION",
    "BOUNDED_LOOP_EXHAUSTION",
]


class DispatcherError(RuntimeError):
    """An otherwise valid typed decision that is illegal in the current state."""


@dataclass
class Phase1BTrace:
    """Payload-minimized trace: observations are named, never copied verbatim."""

    trajectory: list[dict[str, Any]] = field(default_factory=list)
    typed_decisions_total: int = 0
    typed_decisions_valid: int = 0
    typed_decision_failures: int = 0
    dispatcher_actions_total: int = 0
    dispatcher_failures: int = 0
    r1_calls: int = 0
    scenario_calls: int = 0
    recovery_decisions: int = 0
    finalization_attempts: int = 0
    typed_final_success: bool = False
    grounding_success: bool = False
    failure_classification: DecisionFailure | None = None

    def record(self, **event: Any) -> None:
        self.trajectory.append(event)


_PREDICT = PredictStrategy(
    config=PredictConfig(max_retries=2, max_tokens=768, temperature=0, output_serialization="event")
)


class ConstrainedTypedValuationAgent(ValuationAgent):
    """A ValuationAgent whose normal control flow cannot be arbitrary Python.

    The inherited methods retain the real Java HTTP adapters, compact projection,
    scenario cap, R1 worker boundary, and final grounding checks.  This class
    deliberately does *not* call ``investigate`` (the Phase 1A CodeAct path).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.phase1b_trace = Phase1BTrace()

    @strategy(_PREDICT)
    async def decide_next_action(self, context: str) -> NextActionDecision:
        """Choose exactly one action from RUN_SCENARIO, DELEGATE_REASON, FINALIZE.

        Initial Java valuation evidence has already been acquired deterministically.
        You cannot call tools or write Python.  Select RUN_SCENARIO only when the
        compact observation identifies a material uncertainty not already covered
        by its published scenarios.  Select DELEGATE_REASON only for one bounded,
        non-numerical evidence-gap proposal.  Select FINALIZE when the existing
        Java evidence is enough.  Never invent financial numbers or tool names.

        {context}
        """
        ...

    @strategy(_PREDICT)
    async def synthesize_valuation(self, context: str) -> ValuationSynthesis:
        """Create a qualitative valuation synthesis from the supplied Java facts.

        You cannot call tools or write Python.  Do not include any digits or
        numerical values in conclusion or primary_uncertainty.  Set
        valuation_basis exactly to the supplied selected_model.  State only a
        qualitative conclusion and a material uncertainty already present in the
        deterministic observation.  The runtime, not you, will attach Java-backed
        numerical scenarios and evidence paths.

        {context}
        """
        ...

    async def investigate_constrained(
        self,
        *,
        question: str,
        symbol: str,
        require_initial_reason: bool = False,
    ) -> ValuationReport:
        """Run the bounded Phase 1B decision loop against one tracked symbol.

        ``require_initial_reason`` is evaluation-only: it makes the optional R1
        evidence-gap capability observable for a fair single-vs-multi ablation.
        It is false in the production/default Phase 1B path.
        """

        trace = self.phase1b_trace
        started = perf_counter()
        compact = await self.get_compact_valuation(symbol)
        trace.record(
            state="EVIDENCE_COLLECTED",
            observation_type="CompactValuationObservation",
            decision_schema=None,
            decision=None,
            dispatcher_action="GET_COMPACT_VALUATION",
            tool_result="success",
            validation_result="valid",
            latency_ms=(perf_counter() - started) * 1000,
        )

        reason: ReasonResult | None = None
        if require_initial_reason:
            dispatched_at = perf_counter()
            reason = await self.delegate_reason(
                ReasonTask(
                    prompt=(
                        f"Question: {question}\n"
                        "Given the Java-backed valuation warning set, identify one non-numerical "
                        "assumption or evidence gap worth checking. Do not calculate or quote values. "
                        f"Symbol: {compact.symbol}; model: {compact.selected_model}; "
                        f"warnings: {compact.material_warnings}."
                    )
                )
            )
            trace.r1_calls += 1
            trace.dispatcher_actions_total += 1
            trace.record(
                state="REASON_AVAILABLE" if reason.worker.ok else "REASON_UNAVAILABLE",
                observation_type="ReasonResult",
                decision_schema=None,
                decision=None,
                dispatcher_action="DELEGATE_REASON",
                tool_result="success" if reason.worker.ok else reason.worker.error_type,
                validation_result="valid" if reason.worker.ok else "worker_failure_visible",
                latency_ms=(perf_counter() - dispatched_at) * 1000,
            )
        additional_scenario: CompactScenarioObservation | None = None
        # Three legal decisions: optional worker, optional scenario, then final.
        for _iteration in range(1, 4):
            state = self._state(additional_scenario, reason)
            decision_started = perf_counter()
            trace.typed_decisions_total += 1
            try:
                decision = await self.decide_next_action(
                    self._decision_context(question, compact, additional_scenario, reason, state)
                )
            except Exception as exc:
                trace.typed_decision_failures += 1
                trace.failure_classification = "TYPED_DECISION_GENERATION"
                trace.record(
                    state=state,
                    observation_type="decision_generation",
                    decision_schema="NextActionDecision",
                    decision=None,
                    dispatcher_action=None,
                    tool_result=None,
                    validation_result=type(exc).__name__,
                    latency_ms=(perf_counter() - decision_started) * 1000,
                )
                raise
            trace.typed_decisions_valid += 1
            trace.record(
                state=state,
                observation_type="CompactValuationObservation",
                decision_schema="NextActionDecision",
                decision=decision.model_dump(),
                dispatcher_action=None,
                tool_result=None,
                validation_result="valid",
                latency_ms=(perf_counter() - decision_started) * 1000,
            )

            if decision.action == "FINALIZE":
                trace.finalization_attempts += 1
                return await self._finalize(question, compact, additional_scenario, reason)
            try:
                result = await self._dispatch(
                    decision, symbol, compact, reason, additional_scenario
                )
            except DispatcherError:
                trace.dispatcher_failures += 1
                trace.failure_classification = "MODEL_SEMANTIC_DECISION"
                raise
            except Exception:
                trace.dispatcher_failures += 1
                trace.failure_classification = "DISPATCHER_EXECUTION"
                raise

            trace.dispatcher_actions_total += 1
            if decision.action == "DELEGATE_REASON":
                if not isinstance(result, ReasonResult):
                    raise RuntimeError("dispatcher returned a scenario for DELEGATE_REASON")
                reason = result
                trace.r1_calls += 1
                status = "success" if reason.worker.ok else reason.worker.error_type
                if not reason.worker.ok:
                    trace.failure_classification = "SPECIALIST_OUTPUT"
                observation_type = "ReasonResult"
            else:
                if not isinstance(result, CompactScenarioObservation):
                    raise RuntimeError("dispatcher returned a reason result for RUN_SCENARIO")
                additional_scenario = result
                trace.scenario_calls += 1
                status = "success"
                observation_type = "CompactScenarioObservation"
            trace.record(
                state=self._state(additional_scenario, reason),
                observation_type=observation_type,
                decision_schema="NextActionDecision",
                decision=decision.model_dump(),
                dispatcher_action=decision.action,
                tool_result=status,
                validation_result="valid",
                latency_ms=None,
            )

        trace.failure_classification = "BOUNDED_LOOP_EXHAUSTION"
        raise RuntimeError("Phase 1B bounded decision loop exhausted before FINALIZE")

    async def _dispatch(
        self,
        decision: NextActionDecision,
        symbol: str,
        compact: CompactValuationObservation,
        reason: ReasonResult | None,
        scenario: CompactScenarioObservation | None,
    ) -> ReasonResult | CompactScenarioObservation:
        """Execute only the explicit legal action selected by the typed model."""

        if decision.action == "DELEGATE_REASON":
            if reason is not None:
                raise DispatcherError("DELEGATE_REASON is allowed at most once")
            return await self.delegate_reason(
                ReasonTask(
                    prompt=(
                        f"Question: {symbol} — {decision.reason}\n"
                        "Review this Java-backed compact valuation without calculating or quoting numbers: "
                        f"model={compact.selected_model}; warnings={compact.material_warnings}."
                    )
                )
            )
        if decision.action == "RUN_SCENARIO":
            if scenario is not None:
                raise DispatcherError("RUN_SCENARIO is allowed at most once")
            # The typed action selects a capability, never arbitrary scenario inputs.
            # BULL is the sole Phase-1B legal additional scenario and Java owns its assumptions.
            return await self.run_compact_valuation_scenario(symbol, "BULL")
        raise DispatcherError(f"unsupported dispatcher action: {decision.action}")

    async def _finalize(
        self,
        question: str,
        compact: CompactValuationObservation,
        additional_scenario: CompactScenarioObservation | None,
        reason: ReasonResult | None,
    ) -> ValuationReport:
        trace = self.phase1b_trace
        started = perf_counter()
        try:
            synthesis = await self.synthesize_valuation(
                self._synthesis_context(question, compact, additional_scenario, reason)
            )
            report = self._materialize_report(compact, additional_scenario, synthesis)
            self.validate_final_report(report)
        except Exception as exc:
            trace.failure_classification = (
                "GROUNDING_VALIDATION" if isinstance(exc, ValueError) else "FINAL_SYNTHESIS"
            )
            trace.record(
                state="FINALIZING",
                observation_type="typed_synthesis",
                decision_schema="ValuationSynthesis",
                decision=None,
                dispatcher_action="FINALIZE",
                tool_result=None,
                validation_result=type(exc).__name__,
                latency_ms=(perf_counter() - started) * 1000,
            )
            raise
        trace.typed_final_success = True
        trace.grounding_success = True
        trace.record(
            state="FINALIZED",
            observation_type="typed_synthesis",
            decision_schema="ValuationSynthesis",
            decision=synthesis.model_dump(),
            dispatcher_action="FINALIZE",
            tool_result="ValuationReport",
            validation_result="grounded_valid",
            latency_ms=(perf_counter() - started) * 1000,
        )
        return report

    def _materialize_report(
        self,
        compact: CompactValuationObservation,
        additional_scenario: CompactScenarioObservation | None,
        synthesis: ValuationSynthesis,
    ) -> ValuationReport:
        """Bind typed qualitative synthesis to Java facts; never repair model content."""

        if synthesis.valuation_basis != (compact.selected_model or ""):
            raise ValueError("typed synthesis valuation_basis does not match Java selected_model")
        if unsupported_numerical_claim_count(
            ValuationReport(
                symbol=compact.symbol,
                conclusion=synthesis.conclusion,
                valuation_basis=synthesis.valuation_basis,
                engine_version=compact.engine_version,
                scenario_results=[],
                evidence=[],
                uncertainties=[
                    Uncertainty(
                        description=synthesis.primary_uncertainty,
                        severity=synthesis.uncertainty_severity,
                    )
                ],
                trace_id=self.trace_id,
                generated_at=datetime.now(UTC),
            )
        ):
            raise ValueError("typed synthesis contains unsupported numerical prose")

        scenarios = list(compact.scenarios)
        if additional_scenario is not None:
            scenarios.append(additional_scenario)
        report_scenarios = [self._scenario_to_report(item) for item in scenarios]
        evidence = self._evidence_for(compact, scenarios)
        return ValuationReport(
            symbol=compact.symbol,
            conclusion=synthesis.conclusion,
            valuation_basis=synthesis.valuation_basis,
            engine_version=compact.engine_version,
            scenario_results=report_scenarios,
            evidence=evidence,
            uncertainties=[
                Uncertainty(
                    description=synthesis.primary_uncertainty,
                    severity=synthesis.uncertainty_severity,
                    source_path="java.compact_valuation.material_warnings",
                )
            ],
            warnings=compact.material_warnings,
            tool_calls=list(self.tool_calls),
            trace_id=self.trace_id,
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    def _scenario_to_report(scenario: CompactScenarioObservation) -> ValuationScenario:
        return ValuationScenario(
            scenario_type=scenario.scenario_type,
            selected_model=scenario.selected_model,
            valid=scenario.valid,
            intrinsic_value_per_share=scenario.intrinsic_value_per_share,
            margin_of_safety_price=scenario.margin_of_safety_price,
            warnings=scenario.warnings,
        )

    @staticmethod
    def _evidence_for(
        compact: CompactValuationObservation,
        scenarios: list[CompactScenarioObservation],
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        if compact.current_price is not None:
            evidence.append(
                Evidence(
                    claim="Current market price from Java compact valuation",
                    source_path="java.compact_valuation.overview.current_price",
                    value=compact.current_price,
                    source_field="currentPrice",
                )
            )
        for index, scenario in enumerate(scenarios):
            if scenario.intrinsic_value_per_share is not None:
                evidence.append(
                    Evidence(
                        claim=f"{scenario.scenario_type} intrinsic value from Java scenario",
                        source_path=(
                            f"java.compact_valuation.scenarios[{index}].intrinsic_value_per_share"
                        ),
                        value=scenario.intrinsic_value_per_share,
                        source_field="intrinsicValuePerShare",
                    )
                )
        return evidence

    @staticmethod
    def _state(scenario: CompactScenarioObservation | None, reason: ReasonResult | None) -> str:
        reason_available = reason is not None and reason.worker.ok
        reason_unavailable = reason is not None and not reason.worker.ok
        if scenario is not None and reason_available:
            return "SCENARIO_AND_REASON_AVAILABLE"
        if scenario is not None and reason_unavailable:
            return "SCENARIO_AND_REASON_UNAVAILABLE"
        if scenario is not None:
            return "SCENARIO_AVAILABLE"
        if reason_available:
            return "REASON_AVAILABLE"
        if reason_unavailable:
            return "REASON_UNAVAILABLE"
        return "EVIDENCE_COLLECTED"

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)

    def _decision_context(
        self,
        question: str,
        compact: CompactValuationObservation,
        scenario: CompactScenarioObservation | None,
        reason: ReasonResult | None,
        state: str,
    ) -> str:
        return self._json(
            {
                "question": question,
                "state": state,
                "java_compact_valuation": compact.model_dump(mode="json"),
                "additional_java_scenario": scenario.model_dump(mode="json") if scenario else None,
                "reason_worker": {
                    "available": reason is not None,
                    "ok": reason.worker.ok if reason else None,
                    "proposal": reason.proposal if reason and reason.worker.ok else None,
                },
                "limits": {
                    "r1_calls_remaining": 0 if reason else 1,
                    "scenario_calls_remaining": 0 if scenario else 1,
                },
            }
        )

    def _synthesis_context(
        self,
        question: str,
        compact: CompactValuationObservation,
        scenario: CompactScenarioObservation | None,
        reason: ReasonResult | None,
    ) -> str:
        return self._json(
            {
                "question": question,
                "java_compact_valuation": compact.model_dump(mode="json"),
                "additional_java_scenario": scenario.model_dump(mode="json") if scenario else None,
                "untrusted_reason_proposal": reason.proposal
                if reason and reason.worker.ok
                else None,
                "selected_model_required_verbatim": compact.selected_model,
            }
        )
