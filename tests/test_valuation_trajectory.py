from app.experiments.valuation_trajectory import ValuationTrajectoryRecorder


def test_trajectory_classifier_separates_protocol_and_text_drift() -> None:
    recorder = ValuationTrajectoryRecorder()
    recorder.turns = [
        {
            "turn": 1,
            "actions": [{"tool": "execute_python", "code": "bad()", "result_status": "error"}],
            "python_observations": [{"error": "RestrictedCodeError"}],
            "text_only": [],
        },
        {
            "turn": 2,
            "actions": [
                {
                    "tool": "return_result",
                    "code": None,
                    "result_status": "error",
                    "result_preview": "Invalid result: expected ValuationReport",
                }
            ],
            "python_observations": [],
            "text_only": [{"content": "markdown report"}],
        },
    ]

    diagnosis = recorder._classify()["candidate_categories"]

    assert diagnosis["C_illegal_python_or_tool"] is True
    assert diagnosis["D_invalid_return_schema"] is True
    assert diagnosis["E_text_or_planning_drift"] is True
    assert diagnosis["B_no_finalize_after_evidence"] is False
