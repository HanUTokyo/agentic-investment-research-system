"""Phase 2F: compare closure decisions from one frozen Phase 2E ResearchCase.

This is evaluation-only.  It deliberately makes no dispatcher, tool, executor,
or ResearchCase mutation call: each model receives the identical frozen state
and emits at most one typed semantic decision.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.agents.research_case_controller import ResearchCaseController
from app.config import get_settings
from app.llm.router_adapter import build_nooa_controller_llm
from app.research_case import ResearchAction, ResearchCase

_SOURCE_CASE = (
    Path("artifacts")
    / "phase2e_availability_recovery_phase2e-availability-20260811T074656Z-7af3e793"
    / "initial_case.json"
)
_CONDITIONS = ("ministral-3:8b", "deepseek-r1:8b")
_RUNS_PER_CONDITION = 3
_EXPECTED_ACTION = "FINALIZE"
_EXPECTED_UNCERTAINTY = "explicit-forecast-nwc-caveat"


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _case_hash(case: ResearchCase) -> str:
    payload = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _assessment(action: ResearchAction) -> dict[str, Any]:
    correct_uncertainty = tuple(action.unresolved_uncertainty_ids) == (_EXPECTED_UNCERTAINTY,)
    return {
        "schema_valid": True,
        "action": action.action,
        "matches_expected_action": action.action == _EXPECTED_ACTION,
        "correct_nwc_uncertainty": correct_uncertainty,
        "continues_research": action.action
        in {
            "REQUEST_EVIDENCE",
            "REQUEST_VALUATION_ANALYSIS",
            "RUN_SCENARIO",
            "DELEGATE_SPECIALIST",
        },
        "oracle_match": action.action == _EXPECTED_ACTION and correct_uncertainty,
    }


async def run() -> Path:
    run_id = f"phase2f-closure-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2f_closure_comparison_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    source = json.loads(_SOURCE_CASE.read_text())
    case = ResearchCase.model_validate(source["case"])
    frozen_hash = _case_hash(case)
    _write(
        directory,
        "frozen_case.json",
        {"source": str(_SOURCE_CASE), "sha256": frozen_hash, "case": case.model_dump(mode="json")},
    )
    _write(
        directory,
        "evaluation_oracle.json",
        {
            "expected_action": _EXPECTED_ACTION,
            "unresolved_uncertainty_ids": [_EXPECTED_UNCERTAINTY],
            "reason": (
                "Targeted NWC evidence is already present; repeating the default preview is a deterministic no-op; "
                "latest reported revenue is FY2026 Q3 and later reported actuals are unavailable; no legal capability "
                "consumes the NWC observations into an assumption. Close while disclosing the remaining NWC bridge uncertainty."
            ),
        },
    )
    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "RUNNING",
        "frozen_case_sha256": frozen_hash,
        "runs_per_condition": _RUNS_PER_CONDITION,
        "conditions": list(_CONDITIONS),
    }
    _write(directory, "summary.json", summary)
    settings = get_settings()
    results: dict[str, list[dict[str, Any]]] = {model: [] for model in _CONDITIONS}
    for model in _CONDITIONS:
        model_settings = settings.model_copy(update={"ministral_controller_model": model})
        controller = ResearchCaseController(build_nooa_controller_llm(model_settings))
        for attempt in range(1, _RUNS_PER_CONDITION + 1):
            call_started = perf_counter()
            record: dict[str, Any] = {
                "model": model,
                "attempt": attempt,
                "frozen_case_sha256": frozen_hash,
                "started_at": datetime.now(UTC),
            }
            try:
                # No dispatch: this is the isolated closure-decision measurement.
                decision = await controller.decide(case)
                record["decision"] = decision.model_dump(mode="json")
                record["assessment"] = _assessment(decision)
            except Exception as exc:
                record["assessment"] = {
                    "schema_valid": False,
                    "oracle_match": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            record["latency_ms"] = (perf_counter() - call_started) * 1000
            results[model].append(record)
            _write(directory, f"{model.replace(':', '_')}_attempt_{attempt}.json", record)
            summary["results"] = results
            _write(directory, "summary.json", summary)
    for model, records in results.items():
        summary.setdefault("condition_summary", {})[model] = {
            "valid": sum(item["assessment"]["schema_valid"] for item in records),
            "oracle_matches": sum(
                item["assessment"].get("oracle_match", False) for item in records
            ),
            "actions": [item.get("assessment", {}).get("action") for item in records],
        }
    summary["status"] = "COMPLETED"
    summary["total_latency_ms"] = (perf_counter() - started) * 1000
    _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
