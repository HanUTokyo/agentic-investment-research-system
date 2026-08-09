"""Small reproducible metrics for Controller-only versus Controller+Worker runs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunOutcome:
    completed_investigate: bool
    native_tool_calls_valid: bool
    execute_python_success: bool
    return_result_success: bool
    pydantic_valid: bool
    unsupported_numerical_claim: bool
    code_worker_invoked: bool
    worker_materially_contributed: bool
    code_syntax_valid: bool | None
    code_policy_violation: bool | None
    empty_final_result: bool
    timed_out: bool
    nooa_iterations: int
    latency_ms: float


def summarize(outcomes: list[RunOutcome]) -> dict[str, float | int]:
    total = len(outcomes)
    worker_runs = [outcome for outcome in outcomes if outcome.code_worker_invoked]
    return {
        "runs": total,
        "complete_investigate_success_rate": _rate(
            outcomes, lambda item: item.completed_investigate
        ),
        "native_tool_call_correctness": _rate(outcomes, lambda item: item.native_tool_calls_valid),
        "execute_python_success_rate": _rate(outcomes, lambda item: item.execute_python_success),
        "return_result_success_rate": _rate(outcomes, lambda item: item.return_result_success),
        "pydantic_valid_result_rate": _rate(outcomes, lambda item: item.pydantic_valid),
        "unsupported_numerical_claim_rate": _rate(
            outcomes, lambda item: item.unsupported_numerical_claim
        ),
        "empty_final_result_rate": _rate(outcomes, lambda item: item.empty_final_result),
        "timeout_rate": _rate(outcomes, lambda item: item.timed_out),
        "code_worker_calls": len(worker_runs),
        "code_worker_utility_rate": _rate(
            worker_runs, lambda item: item.worker_materially_contributed
        ),
        "mean_latency_ms": sum(item.latency_ms for item in outcomes) / total if total else 0.0,
    }


def _rate(outcomes: list[RunOutcome], predicate) -> float:
    return sum(predicate(outcome) for outcome in outcomes) / len(outcomes) if outcomes else 0.0
