# Phase 1B model ablation — 2026-08-09

## Question

Does adding the local DeepSeek R1 evidence-gap worker improve the constrained
typed-decision AAPL valuation path, compared with a single Ministral controller?

## Protocol

Both current conditions used the same real Java AAPL endpoint, compact
agent-facing observation, typed `NextActionDecision`, deterministic dispatcher,
one-scenario cap, typed `ValuationSynthesis`, sandbox, and grounding gate. They
ran serially. The only variable was whether R1 was required once immediately
after Java evidence collection. R1 was advisory only and could not contribute
numerical claims or execute tools.

The older Gemma result is historical context, not a fair head-to-head result: it
used the earlier short Phase 1 protocol and a different Java valuation snapshot.

## Results

| Condition | Result | Typed decisions | R1 | Scenario | Grounding | Total latency |
|---|---|---:|---|---:|---|---:|
| Historical Gemma-only Phase 1 | pass | 2 JSON responses | none | 1 BEAR | pass | ~13.67 s model time |
| Single Ministral Phase 1B | **pass** | 2 / 2 valid | disabled | 1 BULL | pass | **170.59 s** |
| Ministral + forced R1 Phase 1B | **pass** | 2 / 2 valid | HTTP 200, `empty_content` | 1 BULL | pass | **233.85 s** |

### Single Ministral baseline

Run ID: `f4fc1e2d-336e-43bb-a919-1e65b949142a`

- R1 was physically disabled through `PHASE1B_REASONING_ENABLED=0`.
- Java compact valuation, one BULL scenario, typed final synthesis, and
  `ValuationReport` grounding all passed.
- No CodeAct Python, Coder, Gemma, fake tool calls, or unsupported numerical
  claims occurred.

### Multi-model condition

Run ID: `db827898-7c7d-4543-b138-37388bbb6a19`

- The evaluation-only policy required exactly one R1 evidence-gap review after
  Java evidence. This is not the default Phase 1B production flow.
- Router returned R1 HTTP 200 in `52696.67 ms`, but its final `content` was
  empty. The trace recorded `REASON_UNAVAILABLE`; this failure was not hidden.
- Ministral still selected the same legal BULL scenario and produced a valid
  grounded report. It did not treat R1 thinking or empty output as evidence.
- The worker added `63266.44 ms` of total latency versus the single-Ministral
  baseline, without changing completion, grounding, scenario count, or the
  qualitative final conclusion.

## Decision

**Do not claim multi-model capability improvement from this case.** The
single-Ministral baseline already completed the bounded workflow, while R1 did
not yield usable final content and increased latency by about 37%. The system's
failure containment is valuable—the worker fault remained visible and Java facts
stayed authoritative—but that is reliability isolation, not analytical utility.

The next valid claim needs a curated multi-case dataset with the same protocol,
repeated runs, an explicit worker-content validity rate, and human-scored
evidence-gap usefulness. Until then R1 remains optional, not mandatory, in the
Phase 1B production path.

## Historical Gemma caveat

[The earlier Gemma trace](PHASE1_GEMMA_PROMPT_TRACE.zh-CN.md) passed its older
short-contract acceptance but its final uncertainty response was only `High`.
That motivates evaluation, but it cannot establish a model ranking because the
protocol and Java snapshot differed. A fair Gemma-versus-Ministral test should
run the current Phase 1B typed-decision harness with the controller model
swapped, using the same frozen synthetic fixture or a stable Java snapshot.
