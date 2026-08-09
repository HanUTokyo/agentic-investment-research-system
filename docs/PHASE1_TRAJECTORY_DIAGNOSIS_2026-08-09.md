# Phase 1 AAPL Controller Trajectory Diagnosis

## Scope

This is an opt-in diagnostic replay of the unchanged real AAPL Phase 1
acceptance. It records NOOA turn actions, generated code, tool/validation
observations, and text-only replies. It does not capture Java valuation payloads
or model chain-of-thought.

## Result

Run latency: 340,855 ms. Java `get_compact_valuation` succeeded once. The
Controller failed before native `ValuationReport` return.

| Turn | Controller action | NOOA observation | Classification relevance |
|---:|---|---|---|
| 1 | Called a returned coroutine as a function | `TypeError: 'coroutine' object is not callable` | C |
| 2 | Called a misspelled helper | `NameError` | C |
| 3 | Used prohibited `asyncio.run_coroutine_threadsafe` | `RestrictedCodeError` | C |
| 4 | Successfully fetched and printed compact valuation | execution completed | evidence available |
| 5 | Emitted Markdown/free text containing a draft report instead of a tool call | NOOA routed the text through `return_result`; expected `ValuationReport`, got `str` | D, E |

## Diagnosis against A–F

| Candidate | Finding |
|---|---|
| A. Repeated same action | No — the generated code changed each turn. |
| B. Evidence available but no finalization attempt | No — it did attempt finalization after evidence. |
| C. Illegal Python/tool use | **Yes, primary.** Three of four code cells had deterministic Python/restriction failures. |
| D. Invalid return schema | **Yes, primary terminal failure.** Markdown text became a string `return_result`, not a Pydantic `ValuationReport`. |
| E. Planning/text drift | **Yes, contributing.** Final turn explained a report rather than issuing native structured completion. |
| F. Observation complexity | Not established. The compact Java observation was obtained once; this trace instead shows protocol/control failures. |

## Phase status

```text
Core infrastructure: PASS
Controlled recovery capability: PASS
Real end-to-end ValuationAgent acceptance: FAIL
Primary blocker: Ministral bounded trajectory completion reliability
```

The evidence supports a controller protocol-reliability qualification problem,
not a Java integration, Router connectivity, compact observation, or financial
grounding problem. No prompt, model, Agent, schema, or runtime behavior was
changed by this diagnostic.
