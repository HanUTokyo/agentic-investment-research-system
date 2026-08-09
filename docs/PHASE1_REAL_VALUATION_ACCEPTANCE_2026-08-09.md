# Phase 1 Real ValuationAgent Acceptance — 2026-08-09

## Objective

Run the real, sandboxed AAPL valuation path with only:

```text
Ministral Controller → Java valuation API → optional R1 proposal →
optional Java scenario → NOOA native return_result(ValuationReport)
```

Coder and Gemma were excluded by design.

## Implementation completed

- `ValuationAgent.investigate()` remains the NOOA CodeAct entrypoint.
- `delegate_reason(ReasonTask)` was added as a one-call R1 capability. It returns
  `ReasonResult`, keeps `http_success`, `content_empty`, latency, route, and
  model fields, and marks all output untrusted for numerical claims.
- `run_valuation_scenario()` allows one Java evaluation per research run and
  rejects a second attempt before it reaches Java.
- The valuation tool returns only report-relevant authoritative Java fields to
  the Controller. It removes per-year projection rows that `ValuationReport`
  does not consume; it does not calculate or alter any Java value.
- The acceptance runner rejects reports with numeric prose claims and requires
  Java-backed Evidence for every included scenario intrinsic value.

## Real runs

### Attempt 1

- Result: failed before Java/R1 invocation.
- Failure: `GenerationError` — NOOA `return_result` validation expected
  `ValuationReport`.
- Meaning: Controller CodeAct attempted an invalid final return rather than
  executing the required valuation tool. No financial result was emitted.

### Attempt 2 (temporary public-AAPL protocol trace)

- Java `GET /api/valuations/AAPL`: HTTP 200 confirmed.
- Controller then had repeated upstream `500` responses and slow continuation
  after receiving the large raw valuation observation.
- R1 and scenario calls: zero before termination.
- This identified observation size as a contributing controller-context issue.

### Attempt 3 (report-relevant Java adapter, normal payload-free logging)

- Java `GET /api/valuations/AAPL`: HTTP 200 confirmed.
- Controller had a recoverable upstream `500`, then resumed multiple CodeAct
  turns after the Java observation.
- R1 calls: zero; scenario calls: zero; Coder calls: zero; Gemma calls: zero.
- The Controller did not reach `delegate_reason` or native typed return within
  the bounded practical run window and was terminated explicitly. No report was
  constructed, parsed, or repaired outside NOOA.

## Current acceptance status

**Not passed.** The real Java integration and bounded capability layer are in
place, but the full criterion cannot be declared until Ministral reliably moves
from Java observation to its next CodeAct tool call and returns a valid native
`ValuationReport`.

The current breakpoint is **Controller CodeAct observation continuation**. It is
not a Java valuation API failure, Router/R1 failure, scenario-execution failure,
or evidence-validator failure.

## Verified safeguards

- Java remains the sole valuation/numerical authority.
- No Python valuation calculation was added.
- Coder and Gemma were never called in all three real attempts.
- No scenario was persisted or run in the final two attempts.
- No Markdown parser, JSON repair, or manual `ValuationReport` construction was
  used to hide failure.
- Normal gateway logging was restored to payload-free mode after temporary
  public-AAPL protocol debugging.

## Next evidence-driven step

Keep the production `ValuationReport` unchanged. Investigate the NOOA/
Ministral tool-call serialization failures and reduce the Controller's initial
CodeAct task into one explicit Java-fetch cell before adding R1/scenario
decisions. A successful run must still use native `return_result` and satisfy
the grounding gate; no fallback result is acceptable.
