# Stage 3: Serial R1, Coder, and Gemma Delegation

## Scope

This opt-in synthetic experiment exercised the full Stage 3 control flow in the
Docker sandbox:

```text
Ministral → R1 (reason) → Ministral → Coder (draft) → Ministral
→ Gemma (summary) → Ministral → NOOA native return_result → Pydantic
```

There was no parallel inference, Java-platform access, valuation calculation,
or execution of Coder-generated code.

## Run result

- Run ID: `a85c7a1d-d4d3-435d-8fcb-8e7119bbc793`
- Overall latency: 401,676.41 ms
- Native typed return: successful
- Pydantic validation: successful
- Formal sequence gate: successful (one each of `reason`, `code`, `chat`)

| Worker | HTTP/content state | Latency | Actual output |
|---|---|---:|---|
| R1 (`reason`) | `200`, non-empty, `ok=true` | 98,594.98 ms | `433` |
| Coder (`code`) | `200`, non-empty, `ok=true` | 13,137.44 ms | Correct expression, but text incorrectly claimed `463` |
| Gemma (`chat`) | `200`, non-empty, `ok=true` | 13,784.69 ms | One-sentence summary incorrectly repeated `463` |

The Controller returned:

```json
{
  "reason_answer": "433",
  "untrusted_code_draft": "17 * 25 + 8",
  "code_draft_trusted": false,
  "chat_summary": "Seventeen times twenty-five plus eight results in four hundred sixty-three.",
  "verification_source": "deterministic_expression",
  "final_answer": "433"
}
```

## Important quality finding

The final answer is correct because the Controller independently computed the
fixed expression; Coder output was never executed and was labelled untrusted.
However, the Controller supplied Gemma with `463` after seeing Coder's prose.
Gemma repeated that false premise. The false chat summary did not influence
`final_answer`, but it means this is a **protocol success with an auxiliary
semantic-quality failure**, not evidence that all worker content is reliable.

The gateway also recorded one transient Controller upstream `500` (`invalid
character ... after object key:value pair`) before NOOA's bounded retry
completed successfully. It is retained as Router/Controller failure evidence.

## Next hardening requirement

Before applying Stage 3 to valuation work, downstream prompts and reports must
be constructed from verified evidence only. In particular, a chat/synthesis
worker must receive a verified result reference, not a Coder draft or its
natural-language claims. The evaluator should reject a final report that
contains an unsupported numerical claim even when its primary answer is valid.
