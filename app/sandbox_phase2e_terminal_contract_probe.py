"""Phase 2E contract recovery probe: typed closure only, no execution."""

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
from app.research_case import ResearchCase

_SOURCE_CASE = (
    Path("artifacts")
    / "phase2e_availability_recovery_phase2e-availability-20260811T074656Z-7af3e793"
    / "initial_case.json"
)
_EXPECTED_HASH = "30bf6809466c67c87073299bb5dd720272c7ca2e27494e1b2cda35fda254fb49"
_EXPECTED_UNCERTAINTY = "explicit-forecast-nwc-caveat"
_ATTEMPTS = 3


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _case_hash(case: ResearchCase) -> str:
    payload = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def run() -> Path:
    run_id = f"phase2e-terminal-contract-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_terminal_contract_probe_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    source = json.loads(_SOURCE_CASE.read_text())
    case = ResearchCase.model_validate(source["case"])
    frozen_hash = _case_hash(case)
    if frozen_hash != _EXPECTED_HASH:
        raise RuntimeError(f"unexpected frozen case hash: {frozen_hash}")
    _write(
        directory,
        "frozen_case.json",
        {"source": str(_SOURCE_CASE), "sha256": frozen_hash, "case": case.model_dump(mode="json")},
    )
    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "RUNNING",
        "model": "ministral-3:8b",
        "frozen_case_sha256": frozen_hash,
        "attempts": _ATTEMPTS,
    }
    _write(directory, "summary.json", summary)
    controller = ResearchCaseController(build_nooa_controller_llm(get_settings()))
    results: list[dict[str, Any]] = []
    for attempt in range(1, _ATTEMPTS + 1):
        started = perf_counter()
        record: dict[str, Any] = {
            "attempt": attempt,
            "started_at": datetime.now(UTC),
            "frozen_case_sha256": frozen_hash,
        }
        try:
            # Deliberately no case.select/dispatcher call: protocol reliability only.
            decision = await controller.decide(case)
            record["decision"] = decision.model_dump(mode="json")
            record["matches_contract"] = decision.action == "FINALIZE" and tuple(
                decision.unresolved_uncertainty_ids
            ) == (_EXPECTED_UNCERTAINTY,)
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            record["error"] = str(exc)
            record["matches_contract"] = False
        record["latency_ms"] = (perf_counter() - started) * 1000
        results.append(record)
        _write(directory, f"attempt_{attempt}.json", record)
        summary["results"] = results
        _write(directory, "summary.json", summary)
    summary["matching_decisions"] = sum(item["matches_contract"] for item in results)
    summary["status"] = "COMPLETED"
    _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
