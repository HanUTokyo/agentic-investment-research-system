# 完整 Java Snapshot 直接提示词：Gemma、Ministral、GPT-5.6 Terra

结论：在同一份完整 synthetic Java valuation DTO 与同一问题下，三者都没有产生新的确定性数值；但自由文本基线没有 `ValuationReport`、evidence-path 校验或 unsupported-numerical-claim gate。它适合人类比较模型回答质量，不应替代 Phase 1B 的受控 Agent 路径。

完整输入和逐字输出见 [machine-readable artifact](/Users/kaihan/Desktop/projects/agentic-investment-research-system/eval/results/raw_java_snapshot_three_model_2026-08-09.json)。输入是公开 synthetic AAPL fixture，不含任何真实持仓或私有 Java 数据。

## 完全相同的输入形式

每个模型接收：

1. 初始问题：为什么 AAPL 市价高于 base intrinsic value，以及最重要的估值不确定性是什么？
2. 完整 `GET /api/valuations/AAPL` synthetic Java DTO。
3. 完整预定义 BULL `POST /api/valuations/AAPL/evaluate` synthetic Java DTO。

没有 compact projection、NOOA、Router、Agent、schema repair 或 grounding gate。Gemma 与 Ministral 通过本地 controller endpoint 串行调用；Terra 通过内部受控模型调用。Terra 的 endpoint latency 在该环境不可见，故不参与 latency 比较。

## 真实最终文本

### Gemma — 61.8s，输出截断

> AAPL's current market price of $313.33 is significantly above the base intrinsic value calculated by the FCFE model, which is $84.0. The supplied valuation outputs confirm this discrepancy but do not provide a qualitative reason for the difference between the market pricing and the modeled intrinsic value.
>
> The most important uncertainty to investigate is the potential distortion of profitability metrics. Specifically, the data quality report warns

Gemma 在 token budget 边界停止于半句；没有被续写或修复。

### Ministral — 31.1s

> AAPL’s current market price (**$313.33**) exceeds its **base intrinsic value ($84.00)** due to a **bullish scenario projection** (FCFE model) of **$160.81**, which is closer to the market’s valuation than the base case.
>
> The **most important uncertainty** stems from **data quality issues**:
> - **"High ROE may be distorted by buybacks or a small equity base"**—this suggests potential overstatement of profitability metrics, undermining the FCFE model’s reliability.
> - The **incomplete FCFF cross-check** further weakens confidence in the valuation framework.
>
> Investigate whether AAPL’s ROE is artificially inflated by aggressive share repurchases or an overly leveraged balance sheet.

人工审阅注意：最后一句中的 “aggressive” 和 “overly leveraged balance sheet” 不是 Java DTO 明示事实；这正是自由文本基线不具备 agent grounding gate 的例子。

### GPT-5.6 Terra — endpoint latency 未暴露

> AAPL’s market price of 313.33 is above the FCFE base intrinsic value of 84.0 because the valuation’s bull case reaches only 160.81, indicating the market is pricing expectations beyond the supplied scenarios.
>
> The most important uncertainty is model reliability: the FCFF cross-check is incomplete, while high ROE may be distorted by buybacks or a small equity base.

人工审阅注意： “market is pricing expectations beyond the supplied scenarios” 是合理推断，但不是 Java DTO 的直接字段，应在生产报告中标记为 inference 或要求 evidence-path 支持。

## 与此前 Phase 1B Agent 的对比

此前的 [四形态 Agent 对比](/Users/kaihan/Desktop/projects/agentic-investment-research-system/docs/PHASE1B_FOUR_WAY_EVALUATION_2026-08-09.zh-CN.md) 使用 compact typed observation、受限 action dispatcher、typed synthesis 和 grounding。其 Direct Ministral 成功用时 32.6s；NOOA + 三 worker 成功用时 335.7s；两者均为 `unsupported numerical claims = 0`。

这轮 raw-snapshot 的 Direct Ministral 用时相近（31.1s），但输出直接把 BULL scenario 当作市价溢价的原因，且加入了没有在 DTO 明示的杠杆猜测。由此单一 case 能支持的结论是：完整 DTO 直接提示可生成可读回答，但不提供足够的数值事实边界、结论可审计性和 action control；不能据此取代 Agent-facing typed contract。

本次同样不是统计排名：每个模型仅一轮，本地模型装载/缓存影响延迟。最终文字质量仍应由人类审阅 artifact 决定。
