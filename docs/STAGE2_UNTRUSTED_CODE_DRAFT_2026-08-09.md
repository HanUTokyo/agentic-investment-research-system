# Stage 2: Untrusted Coder Draft Verification

## Purpose

This synthetic, opt-in run verifies the Stage 2 trust boundary:

```text
Ministral Controller → R1 reason worker → Coder draft worker
→ Ministral Controller → NOOA native return_result → Pydantic
```

The Coder response is evidence of a proposed expression only.  It is not
executed and neither its prose nor any numerical claim determines the final
answer.  The Controller independently computes the fixed expression inside its
NOOA CodeAct cell.

## Run

- Run ID: `f16c8f38-895a-4739-b5ec-c4783c6d536c`
- Command: `scripts/sandbox/run-codeact.sh -m app.sandbox_reason_code_delegation_experiment`
- Controller: `ministral-3:8b`, through the sandbox's controller proxy
- Reason worker: Router `route_hint=reason` → `deepseek-r1:8b`
- Code worker: Router `route_hint=code` → `deepseek-coder:6.7b`
- Total wall-clock latency: 198,577.86 ms
- Execution: strictly serial; no Coder output was executed.

## Observed worker outputs

| Worker | HTTP / content status | Latency | Output |
|---|---|---:|---|
| R1 reason | `200`, non-empty, `ok=true` | 115,329.39 ms | `433` |
| Coder draft | `200`, non-empty, `ok=true` | 18,379.42 ms | `print(17 * 25 + 8)` with prose incorrectly claiming the result is `463` |

This is a deliberately useful failure signal: the Coder produced the correct
expression and a contradictory, incorrect natural-language conclusion.

## Controller outcome

Ministral's native `execute_python` cell retained the Coder text only as
`untrusted_code_draft`, calculated `str(17 * 25 + 8)` itself, and called NOOA
native `return_result`.  Pydantic validated:

```json
{
  "reason_answer": "433",
  "untrusted_code_draft": "...which is 463.",
  "code_draft_trusted": false,
  "verification_source": "deterministic_expression",
  "final_answer": "433"
}
```

The run passed its strict acceptance gate: exactly one reason and one code
delegation, both non-empty; no chat worker; `code_draft_trusted=false`; a
declared deterministic verification source; and final answer `433`.

## Implication

This validates the policy needed before using Coder for future CodeAct work:
generated code and accompanying text remain untrusted until an independently
defined deterministic verifier accepts them.  For this arithmetic probe the
verifier is a direct expression; for valuation work it must be the Java
platform's authoritative API/engine, not Python or an LLM.
