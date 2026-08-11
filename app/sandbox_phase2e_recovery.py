"""One bounded Controller reassessment after Phase 2E no-op semantics are disclosed."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.agents.research_case_controller import ResearchCaseController
from app.clients.stock_platform import StockPlatformClient
from app.config import get_settings
from app.explicit_forecast_executor import ExplicitForecastExecutor
from app.llm.router_adapter import build_nooa_controller_llm
from app.research_case import IllegalResearchTransition, ResearchCase
from app.research_graph import ResearchDispatcher

_PHASE_2E_CASE = (
    Path("artifacts") / "phase2e_acceptance_phase2e-20260811T072324Z-00b386a8"
    / "case_after_nwc_evidence.json"
)


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


async def run() -> Path:
    run_id = f"phase2e-recovery-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_recovery_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    summary: dict[str, Any] = {"run_id": run_id, "started_at": datetime.now(UTC), "status": "RUNNING"}
    _write(directory, "summary.json", summary)
    stock: StockPlatformClient | None = None
    try:
        source = json.loads(_PHASE_2E_CASE.read_text())
        case = ResearchCase.model_validate(source["case"])
        _write(directory, "initial_case.json", {"case": case.model_dump(mode="json")})
        settings = get_settings()
        stock = StockPlatformClient(settings)
        controller = ResearchCaseController(build_nooa_controller_llm(settings))
        decision_started = perf_counter()
        decision = await controller.decide(case)
        _write(
            directory,
            "controller_recovery_decision.json",
            {
                "decision": decision.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in case.evidence],
                "controller_state": "cold",
                "latency_ms": (perf_counter() - decision_started) * 1000,
                "default_preview_semantics": "Template defaults only; new evidence does not alter inputs without a legal assumption-application capability.",
            },
        )
        if decision.action == "REQUEST_VALUATION_ANALYSIS":
            try:
                await ResearchDispatcher(
                    valuation_analysis_executor=ExplicitForecastExecutor(stock)
                ).dispatch(case.select(decision))
            except IllegalResearchTransition as exc:
                _write(
                    directory,
                    "deterministic_action_validation.json",
                    {"accepted": False, "error": str(exc), "error_class": type(exc).__name__},
                )
                summary["status"] = "REJECTED_DUPLICATE_OR_ILLEGAL_ANALYSIS"
            else:
                summary["status"] = "ANALYSIS_ACCEPTED"
        else:
            summary["status"] = "CONTROLLER_CHOSE_NON_NOOP_ACTION"
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        if stock is not None:
            await stock.aclose()
        summary["total_latency_ms"] = (perf_counter() - started) * 1000
        _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
