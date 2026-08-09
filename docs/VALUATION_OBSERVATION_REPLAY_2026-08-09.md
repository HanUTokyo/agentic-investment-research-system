# Valuation Observation Replay — 2026-08-09

## Question

Does the real valuation acceptance failure come primarily from the size or
complexity of the Java valuation observation, rather than Java HTTP, R1, or
NOOA itself?

## Method

Each replay used the same direct, tool-capable `ministral-3:8b` Controller in
the Docker sandbox. The Controller received one deterministic observation via
one `get_observation()` tool call and then had to finish through NOOA native
`return_result(ObservationAcknowledgement)`. No R1, Coder, Gemma, scenario, or
LLM-generated summary was available.

`CompactValuationObservation` is a deterministic Python mapping of authoritative
Java fields: symbol, current price, bear/base/bull values, selected model, and
Java-derived material warnings. It performs no financial calculation.

## Results

| Variant | Input source | Bytes / depth | Observation tool | Controller continuation / typed return | Latency | Errors |
|---|---|---:|---|---|---:|---|
| A | tiny fixed `{symbol}` | 31 / 1 | 1 | success / success | 40,747.76 ms | 0 |
| B | fixed compact AAPL facts | 278 / 2 | 1 | failed / failed | 32,704.97 ms | 1 `GenerationError` |
| C | Java GET → current trimmed DTO | 5,289 / 4 | 1 | success / success | 13,558.34 ms | 0 |
| D | Java GET → compact projection | 277 / 2 | 1 | success / success | 9,087.43 ms | 0 |

For D, the Java tool call itself took 1,133.16 ms. For C it took 1,192.63 ms.
The retained D gateway trace contained one Controller HTTP 200 and zero HTTP
500 responses. The B failure was a NOOA `GenerationError`: Ministral emitted a
free-text recovery message where native `ObservationAcknowledgement` was
required. It was not an HTTP, Java, or projection failure.

## Interpretation

The hypothesis that observation size/complexity is the *primary* blocker is
**not supported**:

- C succeeded with a 5.3 KB, depth-4 live trimmed observation.
- D succeeded with the live Java-to-compact path and had the lowest total
  latency.
- B failed despite being almost identical in size to D. This demonstrates an
  intermittent Controller/NOOA protocol-continuation failure independent of
  Java payload size.

The experiments do support an Agent-facing deterministic contract: D is small,
fast, traceable to Java, and successful. It should be introduced as a focused
tool contract for the Controller, while preserving Java's full DTO at the HTTP
boundary and keeping the full `ValuationReport` schema unchanged.

## Scope and limitations

This replay proves simple typed continuation only. It does not prove the full
`ValuationReport` return path, R1 delegation, or scenario decision flow. The
next experiment should retain D's compact Java projection and separately test
one explicit Java-fetch CodeAct cell before reintroducing the full valuation
report contract.
