import json

from eval.runners.controller_worker_benchmark import benchmark


def test_benchmark_compares_recorded_architectures(tmp_path) -> None:
    outcome = {
        "completed_investigate": True,
        "native_tool_calls_valid": True,
        "execute_python_success": True,
        "return_result_success": True,
        "pydantic_valid": True,
        "unsupported_numerical_claim": False,
        "code_worker_invoked": False,
        "worker_materially_contributed": False,
        "code_syntax_valid": None,
        "code_policy_violation": None,
        "empty_final_result": False,
        "timed_out": False,
        "nooa_iterations": 2,
        "latency_ms": 10,
    }
    controller = tmp_path / "controller.jsonl"
    worker = tmp_path / "worker.jsonl"
    controller.write_text(json.dumps(outcome) + "\n")
    worker.write_text(json.dumps({**outcome, "code_worker_invoked": True}) + "\n")

    report = benchmark(controller, worker)

    assert report["controller_only"]["runs"] == 1
    assert report["controller_plus_worker"]["code_worker_calls"] == 1
