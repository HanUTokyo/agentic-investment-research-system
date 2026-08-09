# Phase 1B 四形态模型能力对比（synthetic AAPL）

结论：这轮单次诊断实验没有证明“三 worker 多模型”比 Direct Ministral 的最终质量或可靠性更高。Direct Ministral 以约 32.6 秒完成了严格 typed decision、typed synthesis 与 grounding；NOOA + 三 worker 也完成，但耗时约 335.7 秒，且 R1 空响应、Coder 非 JSON。它证明了受控 worker 失败不会破坏数值 grounding，而不是证明多模型带来能力提升。

完整机器可读原始轨迹（包括 synthetic prompt、raw completion、worker 状态和 schema 结果）在 [phase1b_four_way_synthetic_aapl_2026-08-09.json](/Users/kaihan/Desktop/projects/agentic-investment-research-system/eval/results/phase1b_four_way_synthetic_aapl_2026-08-09.json)。其中没有真实持仓、Java 数据库、密钥或个人路径。

## 方法

- 冻结输入：`synthetic-aapl-phase1b-v1`，包含 synthetic Java-derived compact AAPL observation 与预定义 BULL scenario；不调用实时 Java API。
- 同一问题、同一 `NextActionDecision` / `ValuationSynthesis`、同一 deterministic dispatcher、同一 `ValuationReport` grounding gate；最多一个 scenario。
- 调用顺序固定为 Gemma direct → Ministral direct → Ministral NOOA（无 Router worker）→ Ministral NOOA + Router worker。
- 第四组 worker 强制严格串行 `R1(reason) → Coder(code) → Gemma(chat) → Ministral`；Coder 文本仅作为未执行草稿，任何 worker 都不能写入数值、evidence 或报告字段。
- 每组仅运行一次。模型装载/卸载、缓存和推理时间在本机上不可可靠拆分，下面 latency 均为完整请求/运行耗时，不能视为统计性能排名。

历史上单独运行的 Gemma 结果不参与这次排名；本报告只使用本次冻结 case 的四次运行。

## 结果

| 条件 | 最终 typed report | Grounding | 耗时 | 关键轨迹 / 失败 |
| --- | --- | --- | ---: | --- |
| Direct Gemma | 失败 | 不适用 | >315s（约 349s 后人工停止） | 没有 completion；超过 300s client 与 315s gateway 预算后仍未返回。|
| Direct Ministral | 成功 | PASS，unsupported numerical claims = 0 | 32.6s | `FINALIZE → typed synthesis`；0 scenario。|
| Ministral NOOA，无 Router worker | 失败 | 不适用 | 142.4s | `DELEGATE_REASON → unavailable → RUN_SCENARIO`；下一 typed decision 的 `reason` 超过 schema 600 字符上限，NOOA retry 后失败。|
| Ministral NOOA + R1/Coder/Gemma | 成功 | PASS，unsupported numerical claims = 0 | 335.7s | worker 串行完成；controller 运行一个 BULL scenario 后 `FINALIZE → typed synthesis`。|

第四组的 raw trace 中 `RUN_SCENARIO` 出现两次，是同一个 decision 在 dispatcher 前与 dispatcher 后各记录一次；`scenario_calls = 1`，实际没有突破最多一次 scenario 的约束。controller 文字称 “BEAR”，但 typed action 并不允许模型指定 scenario 参数；dispatcher 只执行预定义、Java-backed BULL capability。这正是“LLM 决定 WHAT，runtime 保证 HOW”的边界。

## Worker 观察（仅第四组）

| Worker / route hint | HTTP | 结果 | latency |
| --- | --- | --- | ---: |
| DeepSeek R1 / `reason` | 200 | `content=""`，标记 `empty_content`，不作为有效建议 | 58.1s |
| DeepSeek-Coder / `code` | 200 | 返回 Markdown/Python prose，严格 JSON `CodeDraft` 校验失败；代码未执行 | 28.4s |
| Gemma / `chat` | 200 | 有效短摘要：审查完整性与可能的指标扭曲 | 11.3s |

因此第四组的通过不能归因于 R1 或 Coder 的有效贡献。Gemma 的短摘要与原有 Java warnings 基本同义；它也没有向报告中引入数值。

## 人工审阅栏

| 条件 | warning 覆盖 | 结论相关性 | 不受支持的事实 |
| --- | --- | --- | --- |
| Direct Gemma | 无输出 | 无法评审 | 无报告 |
| Direct Ministral | 覆盖 FCFF cross-check 和 ROE/buyback warning | 直接回答价格与 base value 的差异及主要不确定性 | grounding gate = 0 |
| NOOA，无 Router | 未形成最终报告 | 未完成 | 无报告 |
| NOOA + 三 worker | 覆盖同一 warning 集合 | 有关，但没有明显超过 Direct Ministral 的新增洞见 | grounding gate = 0 |

最终质量仍应由人类审阅 raw trace 判断；自动 gate 只验证 typed contracts、确定性 evidence paths 和数字来源。

## 设计结论

1. Direct Ministral 是本 case 下最小、最快且合规的成功形态。
2. NOOA 的 typed runtime 能隔离 Router worker 的空响应和非结构化 Coder 输出：最终没有 fake tool call、parser repair、代码执行或 fabricated numerical claim。
3. 目前没有证据要求生产 Phase 1B 默认强制调用三 worker。保留其为 evaluation/ablation 模式，直到多 case 结果显示 warning coverage、结论质量或可靠性有可重复改善。
4. Direct Gemma 的无界等待暴露了端到端 timeout 失效风险；评估 harness 已改为独立可终止条件运行。后续应单独诊断该 direct endpoint/model 的连接与 generation lifecycle，而非把 timeout 解释为能力差。

## 可复现性与限制

实现位于 `app/evaluation/four_way.py` 和 `app/sandbox_phase1b_four_way_evaluation.py`，fixture 位于 `fixtures/eval/phase1b_aapl.json`。CI 使用 fake Router / direct model contract tests，不需要 Java、Router、Ollama、数据库或私有数据。原始 trace 只有在 `EVAL_CAPTURE_RAW=1` 且输入为 synthetic fixture 时才保存。

本实验不是统计显著性评估：每个条件只运行一次，模型的装载、卸载、缓存和本机资源竞争可能显著影响 latency 与成功率。多模型仅在其有效 worker contribution 能在不违反 grounding 的前提下，稳定提升最终质量、覆盖度或可靠性时，才应称为“提升”。
