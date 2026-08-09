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

## Phase 1 evidence: seven model shapes

**Phase 1 finding:** More agents or more models are not automatically better. On one frozen public synthetic AAPL case, the fastest grounded success was a direct typed Ministral dispatcher (32.6s). The NOOA + three-worker shape also produced a grounded report, but took 335.7s while R1 returned empty content and Coder returned free-form Markdown under that experiment's then-strict JSON probe. The current worker boundary preserves non-empty raw advisory content for Controller review; it never executes it or treats it as evidence. The result is evidence for bounded orchestration and evaluation, not a claim of multi-agent superiority.

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
"Choose exactly one action from RUN_SCENARIO, DELEGATE_REASON, FINALIZE. Initial Java valuation evidence has already been acquired deterministically. You cannot call tools or write Python. ... Never invent financial numbers or tool names."
```

The full literal per-turn NOOA prompts, including retry/error observations, are intentionally retained in the linked artifacts rather than duplicated inside the README.

### Results at a glance

| # | Form | Final result | Latency | Grounded report? | What the run establishes |
| --- | --- | --- | ---: | --- | --- |
| 1 | Direct Gemma, strict typed dispatcher | No final typed report | >315s | No | `response_format` transport path was not reliable; strict failure is retained. |
| 2 | Direct Ministral, strict typed dispatcher | Success | 32.6s | Yes; unsupported numerical claims = 0 | Small typed decisions can be more reliable than free-form CodeAct. |
| 3 | NOOA Ministral, no Router worker, completion-focused rerun | Success | 115.0s | Yes; unsupported numerical claims = 0 | State-specific legal-action constraints let the controller finish without an unavailable worker. |
| 4 | NOOA Ministral + Router workers | Success | 335.7s | Yes; unsupported numerical claims = 0 | Worker failures were visible and did not corrupt Java-backed numbers. |
| 5 | Direct Gemma, full raw Java snapshot | Complete free-form text | 61.2s | No gate | Readable answer after a larger output budget; qualitative inference remains ungrounded. |
| 6 | Direct Ministral, full raw Java snapshot | Complete free-form text | 31.1s | No gate | Fast readable baseline, but it introduced an unsupported qualitative inference. |
| 7 | GPT-5.6 Terra, full raw Java snapshot | Complete free-form text | Latency unavailable | No gate | Strong concise baseline; one conclusion is still an inference, not a Java field. |

Each row is one serial diagnostic run, not a statistical ranking. Local model load/unload and cache effects are included in latency. The completion-focused #3 is separately labelled because it changes the legal action set (`RUN_SCENARIO | FINALIZE`) and increases the explanation/retry budget; it does **not** overwrite the original strict #3 failure.

### Final outputs for human review

<details>
<summary><strong>1. Direct Gemma strict typed dispatcher — protocol failure</strong></summary>

The strict form has no final `ValuationReport`: it exceeded the 300s client and 315s gateway budgets with the OpenAI-compatible `response_format` request. A later JSON-only transport attempt returned Markdown fences and wrong schema keys; strict `json.loads` and Pydantic correctly rejected it. No parser repair, fallback report, or fabricated success was used.
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
<summary><strong>4. NOOA Ministral + R1 → Coder → Gemma — final grounded conclusion</strong></summary>

> AAPL's current market valuation appears significantly detached from its intrinsic value estimates based on FCFE model projections, indicating a potential overvaluation or mispricing by the market.

Worker inputs were capability-scoped and serial:

```text
R1/reason: "Return one non-numerical evidence gap only. Do not call tools or quote values."
Coder/code: "Create sorted unique scenario type strings only. No imports, files, network, shell, DCF, price, or return calculations."
Gemma/chat: "Return one short non-numerical warning summary only. Do not recommend a trade."
```

Observed worker outputs: R1 returned HTTP 200 with empty `content`; Coder returned Markdown rather than `CodeDraft` JSON and was never executed; Gemma returned “Review financial metrics for completeness and potential distortions.” The controller still produced a valid grounded report after one Java BULL scenario. This is fault containment, not evidence that all workers improved the answer.
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

> AAPL’s market price of 313.33 is above the FCFE base intrinsic value of 84.0 because the valuation’s bull case reaches only 160.81, indicating the market is pricing expectations beyond the supplied scenarios.
>
> The most important uncertainty is model reliability: the FCFF cross-check is incomplete, while high ROE may be distorted by buybacks or a small equity base.

“Market is pricing expectations beyond the supplied scenarios” is a reasonable inference, but not a direct Java source field; a production report should label it as an inference.
</details>

### Why the agent boundary still matters

The raw snapshot baselines are useful for human quality review, but they can introduce plausible-sounding claims that are not source fields. The Phase 1B reports are deliberately different: the LLM decides an allowed next action or qualitative synthesis; deterministic code owns Java HTTP calls, scenario limits, evidence paths, numerical fields, and report validation. No Python DCF/FCFE logic was duplicated, and no model directly accessed the Java database.

For auditability, every literal prompt and raw completion is preserved in [the four-shape artifact](eval/results/phase1b_four_way_synthetic_aapl_2026-08-09.json), [the raw-snapshot artifact](eval/results/raw_java_snapshot_three_model_2026-08-09.json), and [the completion-focused artifact](eval/results/phase1b_relaxed_completion_2026-08-09.json). The Chinese technical reports under `docs/` add the full failure trajectories and methodology.

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
