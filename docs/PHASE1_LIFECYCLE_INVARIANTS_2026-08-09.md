# Phase 1 Lifecycle Invariants — 2026-08-09

## Design

`ValuationAgent.investigate()` now uses NOOA `CodeActConfig.postconditions` for
deterministic business invariants. `InvariantError` is a model-correctable
validation error in NOOA: it is emitted as an observation and does not create
a fallback report.

```text
START
  → get_compact_valuation() succeeds
  → EVIDENCE_COLLECTED
  → optional bounded R1 / Java scenario
  → READY_TO_FINALIZE
  → native return_result(ValuationReport)
```

The enforced rules are:

1. `return_result` is rejected before initial Java compact valuation evidence.
2. A typed report is rejected when it contains numerical prose unsupported by
   deterministic Evidence.
3. A typed report is rejected when an included scenario intrinsic value has no
   correctly named Java evidence path/value.

## Real run 1: lifecycle invariant enabled

- Java `get_compact_valuation`: succeeded, 3,304.24 ms.
- Native `ValuationReport` Pydantic return: succeeded.
- R1/scenario/Coder/Gemma: 0 calls.
- Controller had one recoverable upstream 500.
- The report was not accepted because the external grounding gate detected two
  numerical prose claims and a Bear source-path typo.

This proves the lifecycle invariant prevented the prior no-evidence path and
allowed Ministral to progress to Java evidence and typed return.

## Real run 2: lifecycle plus grounding postcondition enabled

- The Controller generated multiple early finalization / recovery turns.
- No Java, R1, scenario, Coder, or Gemma call occurred.
- Gateway observed controller 200 responses and recoverable 500 responses.
- The run was terminated during a bounded practical window while the Controller
  still had not used the invariant feedback to call `get_compact_valuation()`.

## Status

The runtime behavior is correct: illegal state cannot finalize, and a typed but
ungrounded report cannot escape the agent. The current remaining failure is
model-specific recovery behavior under the larger real `ValuationReport`
contract, not Java integration or deterministic lifecycle enforcement.

No Markdown parsing, report repair, alternate finalizer, Python valuation logic,
or unbounded retries were introduced.
