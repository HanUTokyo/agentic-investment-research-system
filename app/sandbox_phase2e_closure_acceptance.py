"""Bounded real Phase 2E closure acceptance from persisted AAPL NWC state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from app.closure_compiler import compile_terminal_action, parse_closure_markers
from app.research_case import ResearchCase
from app.research_graph import ResearchDispatcher

_SOURCE_CASE = (
    Path("artifacts")
    / "phase2e_availability_recovery_phase2e-availability-20260811T074656Z-7af3e793"
    / "initial_case.json"
)
_EXPECTED_HASH = "30bf6809466c67c87073299bb5dd720272c7ca2e27494e1b2cda35fda254fb49"


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _case_hash(case: ResearchCase) -> str:
    payload = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _prompt(case: ResearchCase) -> str:
    return """Make one semantic research-closure decision. Do not generate a ResearchAction, JSON, tools, code, HTTP, or numerical assumptions.

Choose TERMINATE if the research should end, including where remaining uncertainty should be disclosed. Choose CONTINUE only if a genuinely available, non-no-op research action remains.

At the END of your response, declare exactly:
CLOSURE_DECISION: TERMINATE or CONTINUE
REMAINING_UNCERTAINTIES: comma-separated existing uncertainty IDs, or NONE

ResearchCase projection:
""" + json.dumps(
        {
            "query": case.query,
            "objective": case.objective,
            "evidence": [
                {"evidence_id": item.evidence_id, "claim": item.evidence.claim, "scope": item.claim_scope, "provenance": item.provenance}
                for item in case.evidence
            ],
            "evidence_availability": [item.model_dump(mode="json") for item in case.evidence_availability],
            "executed_actions": [item.action.model_dump(mode="json") for item in case.executed_actions],
            "tracked_uncertainties": [item.model_dump(mode="json") for item in case.tracked_uncertainties],
            "capability_semantics": {
                "default_preview": "Uses Java template defaults only; equivalent repeats are deterministic no-op actions.",
                "nwc": "No legal capability currently consumes historical NWC observations into a forecast assumption.",
                "availability": "Later SEC reported revenue than the latest recorded period is not currently available.",
            },
        },
        sort_keys=True,
    )


async def run() -> Path:
    run_id = f"phase2e-closure-acceptance-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_closure_acceptance_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    source = json.loads(_SOURCE_CASE.read_text())
    case = ResearchCase.model_validate(source["case"])
    frozen_hash = _case_hash(case)
    if frozen_hash != _EXPECTED_HASH:
        raise RuntimeError(f"unexpected frozen case hash: {frozen_hash}")
    _write(directory, "initial_case.json", {"source": str(_SOURCE_CASE), "sha256": frozen_hash, "case": case.model_dump(mode="json")})
    summary: dict[str, Any] = {"run_id": run_id, "status": "RUNNING", "frozen_case_sha256": frozen_hash}
    _write(directory, "summary.json", summary)
    started = perf_counter()
    try:
        async with httpx.AsyncClient(base_url=os.environ["MINISTRAL_CONTROLLER_BASE_URL"].rstrip("/"), timeout=360.0) as client:
            decision_started = perf_counter()
            response = await client.post(
                "/chat/completions",
                json={"model": "ministral-3:8b", "messages": [{"role": "user", "content": _prompt(case)}], "temperature": 0, "max_tokens": 1_024},
            )
            response.raise_for_status()
            raw = str(response.json()["choices"][0]["message"]["content"])
        semantic = parse_closure_markers(raw)
        _write(directory, "semantic_closure_decision.json", {"raw_response": raw, "decision": semantic.model_dump(mode="json"), "latency_ms": (perf_counter() - decision_started) * 1000})
        action = compile_terminal_action(case, semantic)
        _write(directory, "compiled_terminal_action.json", {"action": action.model_dump(mode="json") if action else None})
        if action is None:
            summary["status"] = "CONTINUED"
            return directory
        dispatched = await ResearchDispatcher().dispatch(case.select(action))
        _write(directory, "final_case.json", {"case": dispatched.model_dump(mode="json")})
        summary.update({"status": "CLOSED", "final_status": dispatched.status, "final_uncertainty_ids": list(action.unresolved_uncertainty_ids)})
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        summary["total_latency_ms"] = (perf_counter() - started) * 1000
        _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
