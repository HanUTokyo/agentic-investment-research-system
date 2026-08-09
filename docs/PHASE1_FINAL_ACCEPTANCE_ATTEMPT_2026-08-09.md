# Phase 1 Final Acceptance Attempt — AAPL

## Target

This real sandbox run exercised the existing bounded Phase 1 path:

```text
AAPL question -> Java compact valuation -> Ministral CodeAct investigation
-> optional R1 / optional one scenario -> native ValuationReport -> grounding
```

The acceptance script permits one R1 delegation, one scenario, no Coder/Gemma,
and requires native typed return plus zero unsupported numerical claims.

## Result

Run ID: `3f2743eb-ead9-4875-ae61-6b8459a98395`

| Field | Observed value |
|---|---|
| Total latency | 560,589 ms |
| Java compact valuation | success (2,905 ms) |
| R1 calls | 0 |
| Scenario calls | 0 |
| Coder / Gemma calls | 0 / 0 |
| Native `ValuationReport` | not returned |
| Grounding gate | not reached |
| Failure | `GenerationError`: six CodeAct iterations exhausted |

The exact NOOA error was:

```text
Generation failed after 6 iterations (max_iterations=6).
Unable to complete `investigate`.
```

## Decision

**Phase 1 — Single NOOA Valuation Agent is not yet accepted.** The deterministic
Java boundary was respected and no unsupported report was emitted, but the
Controller did not complete the required native typed-return contract within
the bounded iteration budget. No fallback report, parser repair, or non-native
construction was used to conceal this failure.
