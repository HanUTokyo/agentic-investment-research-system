from datetime import UTC, datetime

import pytest

from app.contracts import Evidence
from app.research_case import (
    ExecutedResearchAction,
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
    ResearchIterationLimit,
)
from app.research_graph import GroundingFailure, ResearchDispatcher


def test_research_case_serializes_and_preserves_evidence_provenance() -> None:
    evidence = ResearchEvidence(evidence_id="java-base", evidence=Evidence(claim="Base", source_path="java.x", value="1"), source="Java valuation engine", source_type="deterministic_valuation", provenance={"engine_version": "java-1"}, numerical_authority="deterministic_valuation")
    case = ResearchCase(query="Assess ACME", objective="Assess value", evidence=(evidence,))
    restored = ResearchCase.model_validate_json(case.model_dump_json())
    assert restored.evidence[0].provenance == {"engine_version": "java-1"}


def test_state_update_never_overwrites_existing_evidence() -> None:
    evidence = ResearchEvidence(evidence_id="same", evidence=Evidence(claim="x", source_path="java.x"), source="Java", source_type="deterministic_valuation", numerical_authority="deterministic_valuation")
    case = ResearchCase(query="q", objective="o", evidence=(evidence,)).select(ResearchAction(action="REQUEST_EVIDENCE", reason="need source", request="market context"))
    with pytest.raises(IllegalResearchTransition, match="overwritten"):
        case.record_execution(
            ExecutedResearchAction(
                action=case.pending_action,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            ),
            (evidence,),
        )


@pytest.mark.asyncio
async def test_finalization_requires_grounded_report_and_iteration_is_bounded() -> None:
    finalizing = ResearchCase(query="q", objective="o").select(
        ResearchAction(action="FINALIZE", reason="try to bypass grounding")
    )
    with pytest.raises(GroundingFailure, match="grounded ValuationReport"):
        await ResearchDispatcher().dispatch(finalizing)

    progressed = ResearchCase(query="q", objective="o", max_iterations=1).select(
        ResearchAction(action="REQUEST_EVIDENCE", reason="need evidence", request="market context")
    )
    completed = progressed.record_execution(
        ExecutedResearchAction(
            action=progressed.pending_action,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
    )
    assert completed.iteration_count == 1
    with pytest.raises(ResearchIterationLimit):
        completed.select(ResearchAction(action="REQUEST_EVIDENCE", reason="repeat", request="market context"))
