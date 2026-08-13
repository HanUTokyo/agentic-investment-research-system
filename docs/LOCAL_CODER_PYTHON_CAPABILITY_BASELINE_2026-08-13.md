# Local Coder Python Capability Baseline

**Date:** 2026-08-13
**Model:** `deepseek-coder:6.7b` via direct remote Ollama
**Condition:** capability-only; this is not a Router or NOOA CodeAct acceptance.

## Method

The model received eleven fixed, non-financial Python implementation or repair tasks. Each task was run three times at temperature zero, producing 33 attempts. A response could include explanatory prose only when it contained exactly one Python fenced block. Each extracted candidate had to pass a static gate (one requested function, no imports, no dunder access, no file/shell/network constructs) before execution.

Candidates ran only in a no-network, read-only, resource-limited Docker container. They never ran on the host. The dataset is `eval/datasets/coder_python_cases.json`; raw response, code hash, static-gate result, and sandbox result are preserved in ignored local `artifacts/coder_python_capability_*` directories.

## Results

| Measure | Result |
| --- | ---: |
| Attempts | 33 |
| Static-valid candidates | 33 / 33 |
| Sandbox-test passes | 27 / 33 (81.8%) |
| Cases passing all three attempts | 9 / 11 |
| Cases with identical code hash across three attempts | 11 / 11 |

The model passed all three attempts for `normalized_tags`, `longest_increasing_run`, `bounded_ratio`, `first_unique`, `parse_positive_ints`, `merge_known_preferences`, `stable_partition`, `invoice_total`, and `window_maximums`.

It failed every attempt for two explicit-contract cases:

- `collapse_balances`: it removed keys whose summed balance was zero, despite an explicit requirement to preserve them.
- `deduplicate_records`: it returned references to original nested dictionaries rather than new dictionaries, so mutating the returned result changed the input.

These failures are semantic contract violations, not parser, sandbox, or protocol failures. Their identical code hashes across all repetitions make them stable failure modes under this prompt and sampling condition.

## Interpretation

This establishes that the model has useful basic Python generation capability, but it is **not yet suitable for CodeAct**.

1. Its 81.8% pass rate is below the provisional 85% minimum proposed for an untrusted code-draft specialist.
2. It reliably generates static-valid code but can miss explicit preservation/aliasing constraints.
3. Previous compatibility evidence establishes that `deepseek-coder:6.7b` does not support native Ollama tools, so this benchmark cannot qualify it for NOOA CodeAct regardless of Python-test performance.
4. This benchmark has no repair turn, repository-edit task, tool call, or multi-turn observation continuation; all are required for a future CodeAct decision.

The Router endpoint was unavailable during this evaluation, so the result isolates direct model capability only. Request scheduling also created remote queueing during the multi-case run; generation latency was captured in artifacts but is not used as a cold/warm or comparative performance claim.

## Next gate

Do not attach this model to a production CodeAct path. If further evaluation is useful, first add a bounded repair-turn suite and repository-local patch tasks; only then test a coder model that has native tool support with NOOA's multi-turn typed tool-return protocol.
