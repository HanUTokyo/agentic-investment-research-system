# Agentic Investment Research System

A local-first AI research service that investigates a deterministic investment platform instead of replacing it with an LLM.

## The idea in two minutes

Financial facts, portfolio accounting, FCFF/FCFE valuation, sensitivity analysis, and reverse DCF remain in the Java Investment Platform. This independent FastAPI service gives a bounded NOOA valuation specialist typed, read-only HTTP tools. The existing AI Router selects among local Ollama models; the agent service never embeds classifier rules or directly calls Ollama.

```text
Java Investment Platform -> FastAPI typed adapters -> Ministral / NOOA controller
                                      ^                         |
                              deterministic evidence             +-> AI Router -> selected local worker
```

### Relationship to the companion repositories

- [Investment Research Portfolio Platform](https://github.com/HanUTokyo/Investment-Research-Portfolio-Platform) is the separate Java/Spring Boot deterministic source system. It owns portfolio accounting, fundamentals, FCFF/FCFE valuation, scenario evaluation, and business rules. This repository calls it only through read-only HTTP contracts; it never imports its code or opens its database.
- [AI Router Classifier](https://github.com/HanUTokyo/ai-router-classifier) is the separate local model-routing service. It owns task classification and Ollama model selection. This repository uses its HTTP API and does not copy routing rules or classifier logic.

This repository is therefore independently deployable and is not a nested extension of either companion repository.

Why these components: LangGraph (Phase 2) owns durable stateful research workflows; NOOA owns specialist autonomy and iterative CodeAct; the Router owns local model selection; Java owns every financial calculation. LangChain, cloud models, RAG, direct database access, and trade execution are intentionally out of scope.

## Current capability

Phase 0/1 provides a typed read-only integration layer, synthetic mock platform, health endpoints, a bounded `ValuationAgent`, and a Docker containment runner for future CodeAct execution. It supports tracked Java-platform symbols only and makes no persistent valuation or portfolio writes.

## Phase 2 milestone (closed)

Phase 2 established persistent, evidence-grounded stateful research while preserving deterministic execution authority. The final status is **PASS**: Phase 2A, 2B, 2C, and 2E passed; Phase 2D is deliberately deferred because canonical AAPL lacks qualifying first-party FY2027 guidance, not because of an architectural failure. See [the Phase 2 milestone record](docs/PHASE2_STATEFUL_RESEARCH_MILESTONE_2026-08-11.md) for authority boundaries, canonical acceptance artifacts, and verification notes.

## Phase 1 evidence: seven model shapes

**Phase 1 finding:** More agents or more models are not automatically better. On the latest frozen public synthetic AAPL rerun, direct typed Ministral was the fastest grounded success (49.0s); the NOOA Controller plus Router auto-selected advisory also produced a grounded report, but took 313.5s. The Controller selected one advisory capability; Router returned non-empty raw content without an explicit route hint. The current worker boundary preserves non-empty raw advisory content for Controller review, but never executes it or treats it as evidence. The result is evidence for bounded orchestration and evaluation, not a claim of multi-agent superiority.

The comparison uses a single question and no private data:

> Why is AAPL's current market price above the base intrinsic value, and what is the most important valuation uncertainty to investigate?

### Literal deterministic source input

All seven forms use this frozen public synthetic Java case. The raw-snapshot baselines receive it verbatim; typed-agent conditions receive the deterministic compact projection shown next. Real Java remains the numerical authority in the live system.

```json
{
  "GET /api/valuations/AAPL": {
    "symbol": "AAPL",
    "engineVersion": "synthetic-java-valuation-1.0.0",
    "selectedModel": "FCFE",
    "overview": {
      "currentPrice": 313.33,
      "bearValue": 57.59,
      "baseValue": 84.0,
      "bullValue": 160.81
    },
    "dataQuality": {
      "reasons": [
        "FCFF cross-check is incomplete.",
        "High ROE may be distorted by buybacks or a small equity base."
      ]
    },
    "scenarios": [
      {"scenarioType": "BEAR", "selectedModel": "FCFE", "valid": true, "intrinsicValuePerShare": 57.59, "warnings": []},
      {"scenarioType": "BASE", "selectedModel": "FCFE", "valid": true, "intrinsicValuePerShare": 84.0, "warnings": []},
      {"scenarioType": "BULL", "selectedModel": "FCFE", "valid": true, "intrinsicValuePerShare": 160.81, "warnings": []}
    ],
    "fieldSources": {"currentPrice": {"source": "SYNTHETIC_PRICE", "field": "closePrice"}}
  },
  "POST /api/valuations/AAPL/evaluate (predefined BULL scenario)": {
    "symbol": "AAPL",
    "engineVersion": "synthetic-java-valuation-1.0.0",
    "scenario": {"scenarioType": "BULL", "selectedModel": "FCFE", "valid": true, "intrinsicValuePerShare": 160.81, "warnings": []}
  }
}
```

### Deterministic agent-facing input

The Phase 1B agent never receives the full application DTO. Its adapter deterministically projects it to this smaller contract; no LLM summarizes, calculates, or changes it.

```json
{
  "question": "Why is AAPL's current market price above the base intrinsic value, and what is the most important valuation uncertainty to investigate?",
  "java_compact_valuation": {
    "symbol": "AAPL",
    "selected_model": "FCFE",
    "engine_version": "synthetic-java-valuation-1.0.0",
    "current_price": 313.33,
    "bear_value": 57.59,
    "base_value": 84.0,
    "bull_value": 160.81,
    "material_warnings": [
      "FCFF cross-check is incomplete.",
      "High ROE may be distorted by buybacks or a small equity base."
    ]
  },
  "limits": {"scenario_calls_remaining": 1, "r1_calls_remaining": 1}
}
```

The literal system inputs used with these payloads were also fixed:

```text
Raw snapshot baseline:
"You are an investment research analyst. The user message contains a question and complete deterministic Java valuation API outputs. Answer directly in concise prose. Do not calculate, alter, or invent financial numbers. Every numerical claim must be present in the supplied Java JSON. Identify the most important uncertainty."

Direct typed dispatcher decision:
"Return only a JSON object matching NextActionDecision. Choose RUN_SCENARIO, DELEGATE_REASON, or FINALIZE. Java observations are authoritative. Do not invent numbers, tools, or Python. Prefer FINALIZE when evidence is sufficient."

Direct typed dispatcher synthesis:
"Return only a JSON object matching ValuationSynthesis. Do not use digits or make numerical claims. Copy selected_model exactly as valuation_basis. Use only supplied Java warnings and observations."

NOOA typed decision:
"Choose exactly one action from RUN_SCENARIO, DELEGATE_REASON, DELEGATE_CODE, DELEGATE_CHAT, or FINALIZE. Initial Java valuation evidence has already been acquired deterministically. You cannot call tools or write Python. ... Never invent financial numbers or tool names."
```

The full literal per-turn NOOA prompts, including retry/error observations, are intentionally retained in the linked artifacts rather than duplicated inside the README.

### Results at a glance

| # | Form | Final result | Latency | Grounded report? | What the run establishes |
| --- | --- | --- | ---: | --- | --- |
| 1 | Direct Gemma, strict typed dispatcher | Success | 99.3s | Yes; unsupported numerical claims = 0 | The same bounded contract now completed without repair. |
| 2 | Direct Ministral, strict typed dispatcher | Success | 49.0s | Yes; unsupported numerical claims = 0 | Typed decisions and synthesis completed with the same fixture. |
| 3 | NOOA Ministral, no Router worker, completion-focused rerun | Success | 112.5s | Yes; unsupported numerical claims = 0 | The controller completed through the constrained legal-action path. |
| 4 | NOOA Ministral + Router auto-selected advisory | Success | 313.5s | Yes; unsupported numerical claims = 0 | One non-empty raw advisory was returned to the controller; no hint was supplied to Router. |
| 5 | Direct Gemma, full raw Java snapshot | Complete free-form text | 71.1s | No gate | Readable baseline; qualitative interpretation remains outside the typed grounding gate. |
| 6 | Direct Ministral, full raw Java snapshot | Complete free-form text | 29.7s | No gate | Fast readable baseline; it still adds qualitative causal interpretation beyond Java fields. |
| 7 | GPT-5.6 Terra, full raw Java snapshot | Complete free-form text | Latency unavailable | No gate | Native-model comparison only; not a timed local HTTP measurement. |

Each row is one serial diagnostic run, not a statistical ranking. Local model load/unload and cache effects are included in latency. The completion-focused #3 is separately labelled because it changes the legal action set (`RUN_SCENARIO | FINALIZE`) and increases the explanation/retry budget; it does **not** overwrite the original strict #3 failure.

### Final outputs for human review

<details>
<summary><strong>1. Direct Gemma strict typed dispatcher — final grounded conclusion</strong></summary>

> The current market price significantly exceeds the base intrinsic value derived from the FCFE model. This discrepancy suggests that the valuation may be influenced by factors not captured in the standard financial models, such as future growth expectations or market sentiment.

Its typed uncertainty identified potentially buyback-distorted ROE. The runtime attached Java-derived scenarios and evidence paths; grounding passed.
</details>

<details>
<summary><strong>2. Direct Ministral typed dispatcher — final grounded conclusion</strong></summary>

> The current market price exceeds the base intrinsic value as per FCFE model, potentially reflecting investor expectations of future growth or risk premiums not fully captured in the valuation framework. The most critical uncertainty stems from the **high ROE distortion**, likely influenced by aggressive buybacks or a narrow equity base, which may skew profitability metrics and intrinsic value estimates.

The runtime attached all scenario values and evidence paths from the deterministic contract.
</details>

<details>
<summary><strong>3. NOOA Ministral without Router — final grounded conclusion (completion-focused rerun)</strong></summary>

> Apple's market valuation appears to be driven by investor expectations of sustained growth and premium placed on its brand, ecosystem dominance, and innovation capabilities, which exceed the base intrinsic value derived from fundamental cash flow projections.

Its typed uncertainty was the incomplete FCFF cross-check and potentially buyback-distorted ROE. The report passed native typed-return, lifecycle, and grounding validation.
</details>

<details>
<summary><strong>4. NOOA Ministral + Router auto-selected advisory — final grounded conclusion</strong></summary>

> AAPL's current market valuation appears significantly detached from its intrinsic value estimates based on FCFE model projections, indicating a potential overvaluation or mispricing by the market.

Ministral selected one capability-scoped advisory after receiving deterministic evidence:

```text
reason: "Return one non-numerical evidence gap only. Do not call tools or quote values."
```

The Router request contained no `route_hint`; its response returned non-empty advisory text and the logical model identifier `local-router` (the current Router response does not expose the underlying selected model). The raw advisory was passed to Ministral as untrusted context, never executed or used as numerical evidence. The controller then ran one Java BULL scenario and produced a grounded report. This does not establish that the advisory improved final quality.
</details>

<details>
<summary><strong>5. Direct Gemma with full raw Java snapshot — free-form result</strong></summary>

> AAPL's current market price of $313.33 significantly exceeds the base intrinsic value calculated at $84.0, suggesting that the market anticipates substantial future growth not fully captured by the FCFE model. The valuation range spans from a bear case of $57.59 to a bull case of $160.81, indicating considerable disagreement regarding the company's terminal potential.
>
> The most important uncertainty to investigate is the data quality warning that states "FCFF cross-check is incomplete." This suggests fundamental input data gaps could compromise the reliability of all derived intrinsic values. Additionally, analysts should scrutinize whether high Return on Equity (ROE) figures are distorted by aggressive buybacks or a small equity base.

This is complete (`finish_reason=stop`) but has no evidence-path or claim-grounding gate.
</details>

<details>
<summary><strong>6. Direct Ministral with full raw Java snapshot — free-form result</strong></summary>

> AAPL’s current market price (**$313.33**) exceeds its **base intrinsic value ($84.00)** due to a **bullish scenario projection** (FCFE model) of **$160.81**, which is closer to the market’s valuation than the base case.
>
> The **most important uncertainty** stems from **data quality issues**: high ROE may be distorted by buybacks or a small equity base, and the incomplete FCFF cross-check weakens confidence in the valuation framework. Investigate whether AAPL’s ROE is artificially inflated by aggressive share repurchases or an overly leveraged balance sheet.

“Overly leveraged balance sheet” is not present in Java data. This is an intentional example of why raw prompt output is a baseline, not a production report.
</details>

<details>
<summary><strong>7. GPT-5.6 Terra with full raw Java snapshot — free-form result</strong></summary>

> AAPL’s market price of 313.33 is above the FCFE base intrinsic value of 84.0 and also above the supplied bull value of 160.81. The deterministic data establishes that gap, but does not by itself establish its cause.
>
> The most important uncertainty is model reliability: the FCFF cross-check is incomplete, while high ROE may be distorted by buybacks or a small equity base.

“Market is pricing expectations beyond the supplied scenarios” is a reasonable inference, but not a direct Java source field; a production report should label it as an inference.
</details>

### Why the agent boundary still matters

The raw snapshot baselines are useful for human quality review, but they can introduce plausible-sounding claims that are not source fields. The Phase 1B reports are deliberately different: the LLM decides an allowed next action or qualitative synthesis; deterministic code owns Java HTTP calls, scenario limits, evidence paths, numerical fields, and report validation. No Python DCF/FCFE logic was duplicated, and no model directly accessed the Java database.

For auditability, every literal prompt and raw completion is preserved in [the four-shape artifact](eval/results/phase1b_four_way_synthetic_aapl_2026-08-09.json), [the raw-snapshot artifact](eval/results/raw_java_snapshot_three_model_2026-08-09.json), and [the completion-focused artifact](eval/results/phase1b_relaxed_completion_2026-08-09.json). The Chinese technical reports under `docs/` add the full failure trajectories and methodology.

### Phase 1 close-out: evidence sufficiency

The valuation fixture can establish a price-to-model gap, but it has no market-information source that could establish *why* the market assigns that price. This is a different control from numerical grounding: more reasoning cannot create missing facts.

Two real, strictly serial sandbox runs used the same frozen AAPL compact valuation and the same Ministral Controller. Pattern A exposed no Router workers. Pattern B made the existing Router advisory pool available, but did not grant it market-data access. Both produced the same valid typed decision on their first Controller turn:

```json
{
  "action": "REQUEST_EVIDENCE",
  "evidence_type": "MARKET_INFORMATION",
  "reason": "The valuation gap is established, but its cause is not established by the supplied deterministic evidence."
}
```

| Pattern | Latency | Router delegations | Unsupported numerical claims | Unsupported causal claims | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Ministral only | 69.8s | 0 | 0 | 0 | `REQUEST_EVIDENCE(MARKET_INFORMATION)` |
| Ministral + Router advisory pool | 19.1s | 0 | 0 | 0 | `REQUEST_EVIDENCE(MARKET_INFORMATION)` |

In Pattern B the Controller correctly chose not to delegate: the worker pool had no new information capability, so no Router request or advisory was produced. A follow-up order-reversal diagnostic confirmed that the initial 69.8s vs. 19.1s readings were runtime-state artifacts: after an explicit Ollama unload, whichever condition ran first took about 85–87s, while all subsequent runs clustered near 17–19s. They are not an architecture speed ranking. The key result is epistemic rather than speed: additional reasoning diversity did not remove the information deficit. Full synthetic prompts, raw completions, decisions, and validation results are in [the evidence-sufficiency artifact](eval/results/phase1_evidence_sufficiency_synthetic_aapl_2026-08-10.json), [the latency diagnostic artifact](eval/results/phase1_evidence_sufficiency_latency_diagnostic_2026-08-10.json), and [the Chinese technical report](docs/PHASE1_EVIDENCE_SUFFICIENCY_2026-08-10.zh-CN.md).

## Run

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run fastapi dev app/main.py
```

Copy `.env.example` to `.env` for local dependencies. CI and unit tests use only synthetic fixtures. See [architecture](docs/ARCHITECTURE.md), [API integration](docs/API_INTEGRATION.md), [security](docs/SECURITY.md), and [design decisions](docs/DESIGN_DECISIONS.md).

## Current limitations

- The live OpenAPI capture is pending a running Java server; the checked-in contract is schema-only.
- Router/NOOA CodeAct compatibility is an opt-in live test before real execution is enabled.
- LangGraph persistence, multi-agent research, dynamic specialists, and evaluation arrive in later phases.
- Licensing is intentionally undecided; no license is granted by this repository.
