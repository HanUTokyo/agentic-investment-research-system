# Phase 1B 放宽完成性复跑

本复跑的目的不是改写历史四形态结果，而是为原实验中未得到最终文本的两组提供可人工比较的最终输出。严格实验中的失败仍保留在 [原始四形态报告](/Users/kaihan/Desktop/projects/agentic-investment-research-system/docs/PHASE1B_FOUR_WAY_EVALUATION_2026-08-09.zh-CN.md)。

完整原始 prompt、completion、NOOA trace 与最终报告在 [JSON artifact](/Users/kaihan/Desktop/projects/agentic-investment-research-system/eval/results/phase1b_relaxed_completion_2026-08-09.json)。所有内容来自冻结 synthetic AAPL case。

## 1. Direct Gemma：完整自由文本

严格四形态的 Direct Gemma 使用 JSON schema，并在网关后仍未返回。此前 raw snapshot 的 Gemma 又在 768-token 预算附近截断。此复跑保留相同完整 Java DTO 和问题，但：

- 改为自由文本 baseline；
- `max_tokens` 从 768 提高到 2048；
- 明确要求最多两段、完成每个句子。

Gemma 在 61.2 秒返回，`finish_reason=stop`：

> AAPL's current market price of $313.33 significantly exceeds the base intrinsic value calculated at $84.0, suggesting that the market anticipates substantial future growth not fully captured by the FCFE model. The valuation range spans from a bear case of $57.59 to a bull case of $160.81, indicating considerable disagreement regarding the company's terminal potential.
>
> The most important uncertainty to investigate is the data quality warning that states "FCFF cross-check is incomplete." This suggests fundamental input data gaps could compromise the reliability of all derived intrinsic values. Additionally, analysts should scrutinize whether high Return on Equity (ROE) figures are distorted by aggressive buybacks or a small equity base.

它是完整文本，但仍是没有 grounding gate 的自由输出：例如 “substantial future growth”、“considerable disagreement” 和 “aggressive buybacks” 都不是 DTO 的直接字段。

## 3. NOOA Ministral，无 Router：native typed 完成

严格条件中 controller 可选择 `DELEGATE_REASON`，但这个形态没有 reasoning worker；之后在 600 字符 `reason` 上限的 schema retry 失败。本复跑仅调整 runtime 可用能力与输出预算：

- allowlist 从 `RUN_SCENARIO | DELEGATE_REASON | FINALIZE` 收紧为实际可执行的 `RUN_SCENARIO | FINALIZE`；
- `reason` 上限 600 → 1200；
- NOOA structured-output retry 2 → 3。

模型仍自主选择动作；runtime 没有替它决定 `FINALIZE`，也没有修复模型文本。它在 115.0 秒走 `FINALIZE → ValuationSynthesis → native ValuationReport`，grounding PASS，unsupported numerical claims = 0。

最终报告结论：

> Apple's market valuation appears to be driven by investor expectations of sustained growth and premium placed on its brand, ecosystem dominance, and innovation capabilities, which exceed the base intrinsic value derived from fundamental cash flow projections.

最重要不确定性：

> The reliability of the intrinsic value estimates is compromised by the incomplete free cash flow (FCFF) cross-check process and potential distortions in return on equity (ROE) due to aggressive share buyback programs or a relatively small equity base, which may skew profitability metrics.

数值字段和 evidence paths 仍由 Java-backed compact contract materialize；因此模型上述定性推断不会变成未证据化的报告数值。

## 比较解释

放宽版让三种原本可比较性不足的输出都变为可读文本，但它们不是与严格条件一模一样的实验：Gemma 改了输出格式/预算，NOOA 无 Router 改了合法 action 集合/字段与 retry 上限。最终比较应同时呈现严格结果与这些 completion-focused rerun，而不是只报告成功样本。
