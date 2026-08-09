# Phase 1B — Constrained Typed-Decision Valuation Agent

## Purpose

Phase 1A proved the integration boundary, compact Java observation, lifecycle
invariants, grounding validation, and sandbox were functional. Its real AAPL
acceptance failed because the Ministral controller used free-form CodeAct Python
for routine control flow: it made coroutine/protocol errors, then produced text
instead of a native typed result after fetching evidence.

Phase 1B tests a narrower proposition: use the same controller for small typed
decisions and synthesis while the runtime owns invocation mechanics.

## Design

```text
Java full valuation DTO
  -> deterministic CompactValuationObservation
  -> Ministral NextActionDecision (Pydantic / NOOA PredictStrategy)
  -> deterministic allowlisted dispatcher
  -> optional compact scenario or R1 advisory result
  -> Ministral ValuationSynthesis (Pydantic / NOOA PredictStrategy)
  -> Java-backed evidence materialization + grounding validation
  -> ValuationReport
```

The decision allowlist is `RUN_SCENARIO`, `DELEGATE_REASON`, and `FINALIZE`.
Initial valuation retrieval is mandatory and happens before the first decision.
The dispatcher has the only legal implementation of HTTP/async calls, permits
one R1 request and one additional Java BULL scenario, and never executes model
generated Python. R1 is optional, serial, and untrusted for numerical claims.

`ValuationSynthesis` contains qualitative prose only. The runtime does not
repair model output: it rejects a wrong Java model label or numerical prose. It
then binds an already-valid synthesis to Java values and deterministic evidence
paths. This is a typed integration boundary, not a replacement valuation engine.

## Acceptance command

With the restricted gateway and local controller proxy running:

```sh
AI_ROUTER_API_KEY=local-demo-key scripts/sandbox/run-codeact.sh \
  -m app.sandbox_phase1b_acceptance
```

The JSON output records the compact trajectory, decision and dispatcher metrics,
R1/scenario counts, final typed/grounding status, and failure classification.
No portfolio payload, prompts, or credentials are emitted.

## Scope and decision boundary

This is not Phase 1C. On illegal, repeated, or failed model action, Phase 1B
records a precise failure; it does not choose a recovery action on the model's
behalf. A result showing reliable typed decisions but unreliable recovery choice
would be evidence to evaluate deterministic recovery orchestration separately.
