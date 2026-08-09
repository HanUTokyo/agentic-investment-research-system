# Invariant Recovery Probe — 2026-08-09

## Objective

Test whether the real Ministral NOOA Controller can use concise deterministic
`InvariantError` observations to recover and native-return a grounded
`ValuationReport`. Every probe used Java-backed compact valuation data only.
R1, Coder, Gemma, scenarios, LangGraph, and valuation calculations were absent.

## Structured feedback contract

The runtime emits small agent-facing fields rather than stack traces:

```text
ERROR_TYPE
FIELD
INVALID_VALUE
EXPECTED_SOURCE
REQUIRED_ACTION
```

Examples include `MISSING_INITIAL_EVIDENCE`, `UNSUPPORTED_NUMERIC_CLAIM`, and
`INVALID_EVIDENCE_PATH`.

## Real execution results

| Case | Latency | Java calls | Feedback delivered | Controller action after feedback | Native valid return | Outcome |
|---|---:|---:|---|---|---|---|
| `missing_initial_evidence` | 286,073.45 ms | 2 | No | Requested valid Java-backed candidate directly | Yes | Probe failed: no invalid finalization/recovery observed |
| `unsupported_numeric_claim` | 313,024.53 ms | 1 | No | None | No | Controller ended with text instead of `return_result(ValuationReport)` |
| `invalid_evidence_path` | 167,721.12 ms | 1 | Yes, once | Explained the error in text; did not request valid candidate | No | Recovery failed after two typed-return attempts |

The final case provides the cleanest result: the deterministic feedback was
actually delivered and Ministral correctly described the mismatch, but did not
translate that understanding into the required tool action and native retry.

## Conclusion

Structured feedback improves error *interpretability*, but this Ministral setup
did not reliably perform recovery actions under the full `ValuationReport`
contract. No probe reached a successful invalid-finalization → feedback →
corrective-action → valid-native-return loop.

This is not a Java, compact-contract, R1, scenario, or evidence fabrication
failure. It is a Controller CodeAct action-selection failure after receiving
feedback.

## Recommendation

Ministral alone is not sufficient for reliable invariant recovery in this
contract. A next bounded experiment may delegate only **recovery planning** to
R1 after an invariant error, while Ministral remains the sole NOOA protocol
owner and tool executor. That experiment must verify that a plan becomes an
actual Controller tool call; R1 prose alone must not be considered recovery.
