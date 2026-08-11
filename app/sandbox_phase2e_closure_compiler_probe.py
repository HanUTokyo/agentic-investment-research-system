"""Final Phase 2E recovery: semantic closure declaration then deterministic compilation."""

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


def _prompt(case: ResearchCase) -> str:
    projection = {
        "query": case.query,
        "objective": case.objective,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "claim": item.evidence.claim,
                "scope": item.claim_scope,
                "provenance": item.provenance,
            }
            for item in case.evidence
        ],
        "evidence_availability": [
            item.model_dump(mode="json") for item in case.evidence_availability
        ],
        "executed_actions": [item.action.model_dump(mode="json") for item in case.executed_actions],
        "tracked_uncertainties": [
            item.model_dump(mode="json") for item in case.tracked_uncertainties
        ],
        "capability_semantics": {
            "default_preview": "Uses Java template defaults only; equivalent repeats are deterministic no-op actions.",
            "nwc": "No legal capability currently consumes historical NWC observations into a forecast assumption.",
            "availability": "Later SEC reported revenue than the latest recorded period is not currently available.",
        },
    }
    return """Make one semantic research-closure decision. Do not generate a ResearchAction, JSON, tools, code, HTTP, or numerical assumptions.

Choose TERMINATE if the current research should end, including where remaining uncertainty should be disclosed. Choose CONTINUE only if a genuinely available, non-no-op research action remains.

At the END of your response, declare exactly:
CLOSURE_DECISION: TERMINATE or CONTINUE
REMAINING_UNCERTAINTIES: comma-separated existing uncertainty IDs, or NONE

ResearchCase projection:
""" + json.dumps(projection, sort_keys=True)


async def run() -> Path:
    run_id = f"phase2e-closure-compiler-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_closure_compiler_probe_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    source = json.loads(_SOURCE_CASE.read_text())
    case = ResearchCase.model_validate(source["case"])
    frozen_hash = _case_hash(case)
    if frozen_hash != _EXPECTED_HASH:
        raise RuntimeError(f"unexpected frozen case hash: {frozen_hash}")
    prompt = _prompt(case)
    _write(
        directory,
        "frozen_case.json",
        {"source": str(_SOURCE_CASE), "sha256": frozen_hash, "case": case.model_dump(mode="json")},
    )
    _write(directory, "semantic_prompt.json", {"prompt": prompt})
    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "RUNNING",
        "frozen_case_sha256": frozen_hash,
        "attempts": _ATTEMPTS,
    }
    _write(directory, "summary.json", summary)
    base_url = os.environ["MINISTRAL_CONTROLLER_BASE_URL"].rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=360.0) as client:
        results: list[dict[str, Any]] = []
        for attempt in range(1, _ATTEMPTS + 1):
            started = perf_counter()
            record: dict[str, Any] = {
                "attempt": attempt,
                "frozen_case_sha256": frozen_hash,
                "started_at": datetime.now(UTC),
            }
            try:
                response = await client.post(
                    "/chat/completions",
                    json={
                        "model": "ministral-3:8b",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 1_024,
                    },
                )
                response.raise_for_status()
                raw = str(response.json()["choices"][0]["message"]["content"])
                # Preserve the model output before validation so a declaration
                # failure remains auditable rather than being inferred from an exception.
                record["raw_response"] = raw
                semantic = parse_closure_markers(raw)
                compiled = compile_terminal_action(case, semantic)
                record.update(
                    {
                        "raw_response": raw,
                        "semantic_decision": semantic.model_dump(mode="json"),
                        "compiled_action": compiled.model_dump(mode="json") if compiled else None,
                        "matches_expected_terminal": (
                            compiled is not None
                            and compiled.action == "FINALIZE"
                            and compiled.unresolved_uncertainty_ids == (_EXPECTED_UNCERTAINTY,)
                        ),
                    }
                )
            except Exception as exc:
                record.update(
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "matches_expected_terminal": False,
                    }
                )
            record["latency_ms"] = (perf_counter() - started) * 1000
            results.append(record)
            _write(directory, f"attempt_{attempt}.json", record)
            summary["results"] = results
            _write(directory, "summary.json", summary)
    summary["matching_terminals"] = sum(item["matches_expected_terminal"] for item in results)
    summary["status"] = "COMPLETED"
    _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
