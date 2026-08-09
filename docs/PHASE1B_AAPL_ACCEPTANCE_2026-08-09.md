# Phase 1B AAPL acceptance — 2026-08-09

## Result

**PASS.** The constrained typed-decision path completed one real, sandboxed AAPL
valuation run against the Java application. It did not invoke Phase 1A CodeAct,
write Python, make fake tool calls, call Coder or Gemma, or repair model text.

Run ID: `2b30891f-5e5e-4b88-8781-0232aebb9de8`  
Total latency: `121649.58 ms`

## Recorded trajectory

| State | Observation | Typed decision | Dispatcher result | Validation | Latency |
|---|---|---|---|---|---:|
| `EVIDENCE_COLLECTED` | Java `CompactValuationObservation` | — | `GET_COMPACT_VALUATION` | valid | 1509 ms |
| `EVIDENCE_COLLECTED` | compact valuation | `RUN_SCENARIO` | — | `NextActionDecision` valid | 47536 ms |
| `SCENARIO_AVAILABLE` | Java `CompactScenarioObservation` | `RUN_SCENARIO` | Java BULL scenario | valid | — |
| `SCENARIO_AVAILABLE` | compact valuation + scenario | `FINALIZE` | — | `NextActionDecision` valid | 36999 ms |
| `FINALIZED` | typed synthesis | — | `ValuationReport` | typed + grounded valid | 33270 ms |

The controller selected an additional scenario once; the dispatcher supplied the
fixed legal `BULL` capability and Java-owned assumptions. Its free-text decision
reasons were advisory trace data only. They were not used as report values. The
final synthesis contained qualitative prose; Java compact observations supplied
every reported numeric field and exact source path.

## Metrics

| Metric | Value |
|---|---:|
| Typed decisions total / valid | 2 / 2 |
| Typed decision failures | 0 |
| Dispatcher actions / failures | 1 / 0 |
| R1 calls | 0 |
| Scenario calls | 1 |
| Coder / Gemma calls | 0 / 0 |
| Finalization attempts | 1 |
| Typed final success | true |
| Grounding success | true |
| Unsupported numerical claims | 0 |
| Free-form CodeAct/Python failures | 0 |
| Failure classification | none |

The final report used Java-backed evidence paths for current price and every
scenario intrinsic value. The selected valuation basis was validated against the
Java compact observation before materializing the report.

## Interpretation

This run directly addresses the Phase 1A breakpoint: the same controller can
complete a real valuation workflow when it need only issue small typed decisions
and typed synthesis, while deterministic runtime code owns asynchronous tool
execution and lifecycle mechanics. It is one bounded acceptance run, not a
claim of statistical reliability. Phase 1C is **not** implemented by this work;
an illegal or failed typed action remains a visible Phase 1B failure rather than
being deterministically recovered.

## Validation

```text
Ruff check: pass
Ruff format check: pass
Pyright: pass after explicit .venv discovery configuration
pytest: 48 passed, 1 skipped
```

No private portfolio records, secrets, prompts, or raw Java payloads were added
to the repository. The AAPL run is recorded as a public synthetic/test case.
