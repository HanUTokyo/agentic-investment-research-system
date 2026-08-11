# Phase 2 Stateful Research Milestone

**Status: CLOSED — PASS**
**Date:** 2026-08-11

## Final phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| 2A — persistent ResearchCase and semantic-neutral orchestration | PASS | Typed persistent state, legal transitions, and `controller → dispatch → controller / END` LangGraph skeleton. |
| 2B — evidence-conditioned replanning | PASS | A real Controller requested external market evidence; provenance-complete evidence persisted and was available for the next decision. |
| 2C — deterministic valuation capability selection | PASS | SEC operating evidence led to Controller-selected `EXPLICIT_FORECAST`; Java forecast evidence persisted and exposed a further NWC uncertainty. |
| 2D — evidence-grounded assumption translation | DEFERRED | The deterministic adapter and Java temporal contract are ready, but canonical AAPL has no real first-party FY2027 revenue guidance meeting the strict metric, period, and provenance contract. This is not an architecture failure and has no real acceptance run. |
| 2E — uncertainty-driven bounded closure | PASS | The Controller semantically chose closure with the NWC caveat; deterministic compilation produced and executed the legal terminal action. |

**Phase 2 overall: PASS.**

## Frozen architectural conclusion

> LLM owns semantic intent; deterministic software compiles and executes that intent as legal control operations.

The Controller/LLM owns:

- what information is missing;
- what to investigate next;
- which existing valuation capability is relevant;
- whether to continue or terminate; and
- which uncertainties remain.

Deterministic software owns:

- protocol compilation;
- tool execution;
- legal state transitions and bounded iteration mechanics;
- schema, grounding, provenance, and evidence-availability validation;
- duplicate/no-op protection;
- numerical extraction/transformation and bounded override construction;
- financial calculation; and
- terminal lifecycle execution.

The Java Stock Platform is the authority for valuation and forecast numerical outputs. External sources are authorities only for their reported facts. LLM interpretation is semantic reasoning, not numerical evidence.

## Graph and control-plane audit

The LangGraph topology remains exactly:

```text
controller → dispatch → controller / END
```

It contains no edge or runtime rule equivalent to “market evidence implies forecast,” “NWC caveat implies retrieval,” or “guidance implies override.” The Controller selects a legal semantic action; the dispatcher validates and executes it. The Phase 2D revenue-guidance adapter is only reachable from an explicit typed Controller request and was not automatically enabled for the deferred AAPL case.

Phase 2E clarified an important boundary: Ministral can make the semantic closure judgement, but it is unreliable at emitting the strict terminal-control protocol directly. The successful pattern is **semantic closure plus deterministic compiler**: the model selects `TERMINATE` and names existing uncertainties; deterministic code validates and compiles that already-selected intent into `FINALIZE(unresolved_uncertainty_ids=...)`. The compiler does not decide whether research ends or which uncertainty is acceptable.

## Canonical acceptance artifacts

Artifacts are durable JSON records under the ignored local `artifacts/` directory. They are preserved locally and intentionally not committed.

| Phase | Canonical path | Purpose |
| --- | --- | --- |
| 2B | `artifacts/phase2b_acceptance_phase2b-20260811T045803Z-cbfa568a/` | Real AAPL evidence-conditioned replanning: two Controller decisions, real evidence, and persisted state. |
| 2C | `artifacts/phase2c_acceptance_phase2c-20260811T054700Z-0cab79b3/` | SEC operating evidence → Controller-selected explicit forecast → Java deterministic forecast evidence → reassessment. |
| 2D | `tests/test_revenue_guidance_forecast_executor.py` and `app/revenue_guidance_forecast_executor.py` | Deferred/readiness record: deterministic evidence-validation, fiscal-alignment, and bounded-override contract. The Java temporal-contract focused tests were completed in the companion Stock Platform repository; no Phase 2D real-acceptance artifact exists by design. |
| 2E | `artifacts/phase2e_closure_acceptance_phase2e-closure-acceptance-20260811T104413Z-da87db0e/` | Frozen state `30bf6809466c67c87073299bb5dd720272c7ca2e27494e1b2cda35fda254fb49` → semantic closure → compiled terminal action → `FINALIZED_WITH_LIMITATIONS` with `explicit-forecast-nwc-caveat`. |

The retained `sandbox_phase2*` modules are evaluation harnesses, not production orchestration. Earlier `phase2e_*` recovery and `phase2f_*` artifacts are diagnostic/failed-experiment history; they are not canonical acceptance evidence.

## Verification record

The repository’s Python verification command set is:

```text
pytest
ruff
pyright
```

The final results for this closing commit are recorded in the commit handoff. Java temporal-contract focused tests were previously completed in the companion Stock Platform repository. Its full Maven integration-test run has an existing forked-JVM hang caveat and was not made artificially green through unrelated changes; the temporal metadata change did not alter valuation mathematics.

## Deferred work

Phase 2D remains deferred, not failed. It should only resume when a symbol has a real first-party revenue-guidance fact whose metric, unit, and issuer fiscal period can be deterministically aligned to Java forecast Year-1. No Phase 3 work is started by this milestone.
