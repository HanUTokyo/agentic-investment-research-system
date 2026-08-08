# Live valuation research trace — AAPL

**Run time:** 2026-08-08T08:42:04Z  
**Research ID:** `a7f1f691-5df0-48b5-86aa-03751ebc3f4f`  
**Mode:** Local, sequential, read-only Agent tools; Java platform and local AI Router running on the developer machine.

This is a reproducible integration trace against the disposable mock PostgreSQL
database. It is not investment advice and it does not contain portfolio account,
transaction, or holding-size data.

## Research question

> Does the current deterministic valuation support allocating incremental capital to AAPL? Identify the decisive valuation evidence and the material evidence gap.

## Execution boundary

- The Python service did not calculate DCF values.
- Java `valuation-java-2.0.0` selected and evaluated the FCFF model.
- The Agent used only read-only HTTP tools.
- The local Router selected the locally configured answer model. The LLM received
  a small evidence summary and was prohibited from adding numerical claims.
- NOOA CodeAct was intentionally disabled because the Docker execution sandbox
  has not been started for this run.

## State timeline

| State | Input | Output / transition |
|---|---|---|
| `PLANNED` | Question above; symbol `AAPL` | Sequential read-only workflow selected; CodeAct disabled. |
| `SNAPSHOT_RETRIEVED` | `get_company_snapshot("AAPL")` | Java engine `valuation-java-2.0.0`; model `FCFF`; applicability `AVAILABLE`; no missing fields. |
| `FUNDAMENTALS_RETRIEVED` | `get_financial_history("AAPL")` | 48 quarterly fundamental records; capital-allocation history present. |
| `CURRENT_VALUATION_RETRIEVED` | `get_current_valuation("AAPL")` | Model `FCFF`; three persisted scenario slots; no missing fields. |
| `SCENARIO_EVALUATED` | BASE assumptions below | Valid FCFF result; one data-quality warning. |
| `SCENARIO_EVALUATED` | BEAR assumptions below | Valid FCFF result; one data-quality warning. |
| `SCENARIO_EVALUATED` | BULL assumptions below | Valid FCFF result; one data-quality warning. |
| `REVERSE_DCF_RETRIEVED` | `solve_market_implied_assumptions("AAPL")` | Reverse DCF available. |
| `SYNTHESIS_VALIDATED` | Deterministic evidence summary only | Pydantic-validated local-model response; unsupported numerical claims: zero. |
| `COMPLETED` | All steps successful | End-to-end elapsed time: 14.6 seconds. |

## Deterministic tool inputs and outputs

### Scenario inputs

All values were passed to `POST /api/valuations/AAPL/evaluate`. The endpoint
evaluates without persisting a scenario.

| Scenario | Base cash flow | Initial growth | Discount rate | Terminal growth | Years | Margin of safety |
|---|---:|---:|---:|---:|---:|---:|
| BASE | 128,000,000,000 | 7.0% | 8.5% | 2.5% | 10 | 20.0% |
| BEAR | 110,000,000,000 | 2.0% | 9.5% | 2.0% | 10 | 30.0% |
| BULL | 140,000,000,000 | 10.0% | 8.0% | 3.0% | 10 | 10.0% |

Each scenario used `baseCashFlowMode=MANUAL`, `growthMode=CUSTOM_LINEAR`, and
`discountRateMode=MANUAL_RATE`. Java resolved the common market inputs as
risk-free rate 4.65%, beta 1.086, and equity risk premium 5.0%.

### Scenario outputs from Java

| Scenario | Selected model | Valid | Intrinsic value / share | Margin-of-safety price | Warnings |
|---|---|---:|---:|---:|---|
| BASE | FCFF | Yes | 178.6394 | 142.9115 | FCFF cross-check unavailable because D&A, NOPAT, or working-capital change is missing. |
| BEAR | FCFF | Yes | 100.7531 | 70.5271 | Same warning. |
| BULL | FCFF | Yes | 263.0358 | 236.7322 | Same warning. |

### Reverse DCF output from Java

| Field | Value |
|---|---:|
| Status | `AVAILABLE` |
| Implied initial growth rate | 19.7832% |
| Implied discount rate | 6.1154% |

## Agent tool-call trace

| Tool | Result | Duration |
|---|---|---:|
| `get_company_snapshot` | Success | 477.0 ms |
| `get_financial_history` | Success | 35.8 ms |
| `get_current_valuation` | Success | 107.1 ms |
| `run_valuation_scenario(BASE)` | Success | 113.6 ms |
| `run_valuation_scenario(BEAR)` | Success | 104.2 ms |
| `run_valuation_scenario(BULL)` | Success | 113.0 ms |
| `solve_market_implied_assumptions` | Success | 295.7 ms |

## Local-model synthesis trace

### Exact model input

The Router received this evidence summary (not the raw portfolio export or
fundamental payload):

```json
{
  "selected_model": "FCFF",
  "scenario_values": {
    "BASE": "178.6394",
    "BEAR": "100.7531",
    "BULL": "263.0358"
  },
  "reverse_dcf_status": "AVAILABLE",
  "warning": [
    "FCFF cross-check is unavailable because D&A, NOPAT, or working-capital change is missing."
  ]
}
```

System constraint: return exactly a JSON object with `assessment`,
`primary_uncertainty`, and `next_step`; use supplied facts only; do not use
digits or introduce numerical claims. `max_tokens` was 200.

### Validated model output

```json
{
  "assessment": "The Free Cash Flow to Firm (FCFF) valuation model has scenario values available for BASE, BEAR, and BULL cases. However, a warning indicates that the FCFF cross-check is unavailable due to missing data points such as Depreciation and Amortization, Net Operating Profit After Tax, or working capital change.",
  "primary_uncertainty": "The inability to perform an FCFF cross-check due to missing underlying financial inputs (D&A, NOPAT, or working-capital change).",
  "next_step": "Obtain the necessary detailed financial data points—specifically Depreciation and Amortization, Net Operating Profit After Tax, and working capital changes—to complete the FCFF cross-check."
}
```

The response was decoded by `RouterClient.complete_structured`, which permits
only a complete single JSON fence (or bare JSON) and validates the parsed object
with Pydantic. It passed the run's no-new-numerical-claims check.

## Interpretation and limitations

The deterministic valuation range is wide, so this trace does **not** authorize
an allocation decision. The model's most useful contribution was to surface the
same evidence gap returned by the Java engine, rather than replacing the engine
or inventing a conclusion.

The next deterministic integration improvement is to obtain or review the
missing D&A, NOPAT, and working-capital-change inputs so Java can perform its
FCFF cross-check. Until then, the reported valuation scenarios are usable but
carry the warning shown above.

## Verification

Run from the repository root after starting Java on port 8080 and Router on port
8000:

```bash
$HOME/.local/bin/uv run ruff check app tests
$HOME/.local/bin/uv run ruff format --check app tests
$HOME/.local/bin/uv run pyright
$HOME/.local/bin/uv run pytest -q
```

The test suite at the time of this trace passed with 19 tests and one opt-in live
Router compatibility test skipped.
