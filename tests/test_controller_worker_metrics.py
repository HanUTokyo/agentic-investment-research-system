from eval.metrics.controller_worker import RunOutcome, summarize


def test_worker_utility_uses_worker_invocations_as_denominator() -> None:
    results = summarize(
        [
            RunOutcome(
                True, True, True, True, True, False, False, False, None, None, False, False, 2, 10
            ),
            RunOutcome(
                True, True, True, True, True, False, True, True, True, False, False, False, 3, 20
            ),
            RunOutcome(
                False,
                True,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                True,
                False,
                False,
                2,
                30,
            ),
        ]
    )
    assert results["complete_investigate_success_rate"] == 2 / 3
    assert results["code_worker_calls"] == 2
    assert results["code_worker_utility_rate"] == 0.5
