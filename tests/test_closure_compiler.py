import pytest

from app.closure_compiler import ClosureDecision, compile_terminal_action, parse_closure_markers
from app.research_case import IllegalResearchTransition, ResearchCase, ResearchUncertainty


def _case() -> ResearchCase:
    return ResearchCase(
        query="q",
        objective="o",
        tracked_uncertainties=(
            ResearchUncertainty(
                uncertainty_id="nwc", description="NWC caveat", source_evidence_id="forecast"
            ),
        ),
    )


def test_compiler_maps_model_selected_termination_without_selecting_uncertainties() -> None:
    action = compile_terminal_action(
        _case(), ClosureDecision(decision="TERMINATE", remaining_uncertainty_ids=("nwc",))
    )

    assert action is not None
    assert action.action == "FINALIZE"
    assert action.unresolved_uncertainty_ids == ("nwc",)


def test_compiler_never_turns_continue_into_a_terminal_action() -> None:
    assert compile_terminal_action(_case(), ClosureDecision(decision="CONTINUE")) is None


def test_compiler_rejects_unknown_uncertainty() -> None:
    with pytest.raises(IllegalResearchTransition, match="tracked uncertainties"):
        compile_terminal_action(
            _case(), ClosureDecision(decision="TERMINATE", remaining_uncertainty_ids=("unknown",))
        )


def test_marker_parser_requires_an_explicit_unambiguous_semantic_declaration() -> None:
    parsed = parse_closure_markers(
        "analysis\nCLOSURE_DECISION: TERMINATE\nREMAINING_UNCERTAINTIES: nwc"
    )

    assert parsed == ClosureDecision(decision="TERMINATE", remaining_uncertainty_ids=("nwc",))
    assert (
        parse_closure_markers("**CLOSURE_DECISION: TERMINATE**\n**REMAINING_UNCERTAINTIES: nwc**")
        == parsed
    )
    with pytest.raises(ValueError, match="exactly one"):
        parse_closure_markers("CLOSURE_DECISION: TERMINATE")
