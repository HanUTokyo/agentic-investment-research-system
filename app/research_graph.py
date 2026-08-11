"""Phase 2A LangGraph skeleton: Controller choice, deterministic dispatch, reassessment."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.research_case import (
    EvidenceRequestOutcome,
    ExecutedResearchAction,
    GroundingFailure,
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)


class ResearchController(Protocol):
    async def decide(self, case: ResearchCase) -> ResearchAction: ...


class EvidenceExecutor(Protocol):
    async def __call__(
        self, case: ResearchCase, action: ResearchAction
    ) -> Sequence[ResearchEvidence] | EvidenceExecutionResult: ...


class EvidenceExecutionResult:
    """Deterministic evidence execution may instead persist an availability outcome."""

    def __init__(
        self,
        evidence: Sequence[ResearchEvidence] = (),
        evidence_request_outcome: EvidenceRequestOutcome | None = None,
    ) -> None:
        self.evidence = tuple(evidence)
        self.evidence_request_outcome = evidence_request_outcome


class ScenarioExecutor(Protocol):
    async def __call__(
        self, case: ResearchCase, action: ResearchAction
    ) -> Sequence[ResearchEvidence]: ...


class ValuationAnalysisExecutor(Protocol):
    async def __call__(
        self, case: ResearchCase, action: ResearchAction
    ) -> Sequence[ResearchEvidence]: ...


class ResearchDispatcher:
    """Known operation execution and all state integrity remain deterministic."""

    def __init__(
        self,
        evidence_executor: EvidenceExecutor | None = None,
        scenario_executor: ScenarioExecutor | None = None,
        valuation_analysis_executor: ValuationAnalysisExecutor | None = None,
    ) -> None:
        self._evidence_executor = evidence_executor
        self._scenario_executor = scenario_executor
        self._valuation_analysis_executor = valuation_analysis_executor

    async def dispatch(self, case: ResearchCase) -> ResearchCase:
        action = case.pending_action
        if action is None:
            raise IllegalResearchTransition("dispatcher requires pending action")
        started = datetime.now(UTC)
        if action.action == "REQUEST_EVIDENCE":
            if self._evidence_executor is None:
                raise IllegalResearchTransition("REQUEST_EVIDENCE executor is not configured")
            execution_result = await self._evidence_executor(case, action)
            if isinstance(execution_result, EvidenceExecutionResult):
                evidence = execution_result.evidence
                outcome = execution_result.evidence_request_outcome
            else:
                evidence = tuple(execution_result)
                outcome = None
            return case.record_execution(
                self._execution(action, started, evidence), evidence, outcome
            )
        if action.action == "RUN_SCENARIO":
            if self._scenario_executor is None:
                raise IllegalResearchTransition("RUN_SCENARIO executor is not configured")
            evidence = tuple(await self._scenario_executor(case, action))
            if any(item.source_type != "deterministic_valuation" for item in evidence):
                raise IllegalResearchTransition(
                    "scenario executor must return deterministic valuation evidence"
                )
            return case.record_execution(self._execution(action, started, evidence), evidence)
        if action.action == "REQUEST_VALUATION_ANALYSIS":
            if self._valuation_analysis_executor is None:
                raise IllegalResearchTransition(
                    "REQUEST_VALUATION_ANALYSIS executor is not configured"
                )
            evidence = tuple(await self._valuation_analysis_executor(case, action))
            if not evidence or any(
                item.source_type != "deterministic_valuation"
                or item.numerical_authority != "deterministic_valuation"
                for item in evidence
            ):
                raise IllegalResearchTransition(
                    "valuation analysis executor must return deterministic valuation evidence"
                )
            return case.record_execution(
                self._execution(action, started, evidence),
                evidence,
            )
        if action.action == "DELEGATE_SPECIALIST":
            raise IllegalResearchTransition("no specialist is registered in Phase 2A")
        if action.action == "FINALIZE":
            if action.unresolved_uncertainty_ids:
                known = {item.uncertainty_id for item in case.tracked_uncertainties}
                if not set(action.unresolved_uncertainty_ids).issubset(known):
                    raise IllegalResearchTransition(
                        "FINALIZE limitations must reference tracked uncertainties"
                    )
                executed = case.record_execution(
                    ExecutedResearchAction(
                        action=action, started_at=started, completed_at=datetime.now(UTC)
                    )
                )
                return executed.model_copy(update={"status": "FINALIZED_WITH_LIMITATIONS"})
            report = case.final_report
            if (
                report is None
                or unsupported_numerical_claim_count(report)
                or not all_scenario_values_grounded(report)
            ):
                raise GroundingFailure(
                    "FINALIZE requires a grounded ValuationReport attached by deterministic code"
                )
            executed = case.record_execution(
                ExecutedResearchAction(
                    action=action, started_at=started, completed_at=datetime.now(UTC)
                )
            )
            return executed.model_copy(update={"status": "FINALIZED"})
        raise IllegalResearchTransition(f"unsupported action {action.action}")

    @staticmethod
    def _execution(
        action: ResearchAction, started: datetime, evidence: Sequence[ResearchEvidence]
    ) -> ExecutedResearchAction:
        fingerprints = {
            item.provenance.get("effective_input_fingerprint")
            for item in evidence
            if item.provenance.get("effective_input_fingerprint")
        }
        return ExecutedResearchAction(
            action=action,
            started_at=started,
            completed_at=datetime.now(UTC),
            produced_evidence_ids=tuple(item.evidence_id for item in evidence),
            effective_input_fingerprint=next(iter(fingerprints))
            if len(fingerprints) == 1
            else None,
        )


class GraphState(TypedDict):
    case: ResearchCase


def build_research_graph(
    controller: ResearchController,
    dispatcher: ResearchDispatcher,
    *,
    checkpointer: MemorySaver | None = None,
):
    async def controller_node(state: GraphState) -> dict[str, ResearchCase]:
        return {"case": state["case"].select(await controller.decide(state["case"]))}

    async def dispatch_node(state: GraphState) -> dict[str, ResearchCase]:
        return {"case": await dispatcher.dispatch(state["case"])}

    def next_node(state: GraphState) -> str:
        return (
            END
            if state["case"].status in {"FINALIZED", "FINALIZED_WITH_LIMITATIONS"}
            else "controller"
        )

    graph = StateGraph(GraphState)
    graph.add_node("controller", controller_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_edge(START, "controller")
    graph.add_edge("controller", "dispatch")
    graph.add_conditional_edges("dispatch", next_node, {END: END, "controller": "controller"})
    return graph.compile(checkpointer=checkpointer or MemorySaver())
