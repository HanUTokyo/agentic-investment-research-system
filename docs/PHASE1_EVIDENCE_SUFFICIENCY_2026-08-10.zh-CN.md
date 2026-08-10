# Phase 1 收尾实验：证据充分性与信息缺口升级

## 实验问题

冻结的 synthetic AAPL 估值输入能证明市场价高于 FCFE bear/base/bull 区间，并能指出 FCFF cross-check 不完整、ROE 可能受回购或较小权益基数扭曲。它不能证明市场为何给出该价格：没有增长预期、市场情绪、品牌溢价、生态系统、创新溢价、风险溢价或错误定价的数据来源。

本实验测试 Controller 能否把这一区分表达为一个受类型约束的证据请求，而不是把推理伪装成事实。原则是：**额外推理不能制造缺失的信息。**

## 受控条件

两个条件使用完全相同的冻结 fixture、问题、Ministral Controller、紧凑 Java 投影、温度与有界重试策略；没有私有数据、Web、市场数据或 Market Information Agent。

| 条件 | 可用能力 | 不可用能力 |
| --- | --- | --- |
| Pattern A — Ministral only | Java-derived compact observation、typed decision | Router、worker、市场信息 |
| Pattern B — Ministral + Router | 与 A 相同，另有现有 Router advisory pool | worker 的市场数据访问、将 advisory 升级为事实或数值证据 |

Pattern B 的 Router worker 仍是可选且不可信的 advisory。Controller 可以选择委派，但没有义务为了使用多模型而委派。

## 新的类型化边界

`NextActionDecision` 新增以下合法终态：

```json
{
  "action": "REQUEST_EVIDENCE",
  "evidence_type": "MARKET_INFORMATION",
  "reason": "The supplied valuation evidence establishes the price-to-model gap but does not establish its cause."
}
```

该 schema 强制 `REQUEST_EVIDENCE` 带 `evidence_type`，并拒绝其他动作携带该字段。它没有实现 Phase 2 的市场信息 agent；Phase 1 在请求处停止。

评估器增加可审计的因果术语分类，检测该 fixture 不能支持的解释（例如 `future growth expectations`、`market sentiment`、`brand premium`、`ecosystem dominance`、`innovation premium`、`risk premium`、`mispricing`）。明确表示“现有证据不能证明该术语”的否定句不计为违规。数值文本仍只允许来自紧凑 Java observation 中的确定性值。

## 原始输入与输出

问题保持为：

> Why is AAPL's current market price above the base intrinsic value, and what is the most important valuation uncertainty to investigate?

完整 synthetic prompt、紧凑 observation、两次原始 completion 与决策记录在 [machine-readable artifact](../eval/results/phase1_evidence_sufficiency_synthetic_aapl_2026-08-10.json)。这是公开 fixture，不包含持仓、真实投资记录、token 或本机路径。

两个实际 completion 相同，均为严格合法 JSON：

```json
{
  "action": "REQUEST_EVIDENCE",
  "reason": "The Java valuation shows AAPL's current market price of $313.33 is significantly above its base intrinsic value of $84.00, but the deterministic evidence does not explain why the market assigns this premium. The material warnings (e.g., incomplete FCFF cross-check and potential ROE distortion) highlight data-quality uncertainties, but they do not address the causal reason for the price-to-value gap.",
  "evidence_type": "MARKET_INFORMATION"
}
```

## 实际轨迹与结果

| 指标 | Pattern A — Ministral only | Pattern B — Ministral + Router |
| --- | ---: | ---: |
| Controller decision 次数 | 1 | 1 |
| typed schema validation | PASS | PASS |
| 最终 lifecycle | `REQUESTED_MARKET_INFORMATION` | `REQUESTED_MARKET_INFORMATION` |
| Router delegation | 0 | 0 |
| scenario calls | 0 | 0 |
| unsupported numerical claims | 0 | 0 |
| unsupported causal claims | 0 | 0 |
| 总延迟 | 69.8s | 19.1s |
| 结论 | PASS | PASS |

Pattern B 中 Router 是可达、可供 Controller 选择的，但 Controller 在第一轮就识别出信息缺口并请求市场信息，因此没有发生 Router request、selected worker 或 advisory completion。这不是 Router 路径故障；在没有新增 market-data capability 的条件下，避免无必要 delegation 正是预期行为。单次延迟受本地模型加载/卸载、缓存和并发环境影响，不能视为性能排名。

## 保留的失败轨迹

首次 Pattern A 诊断运行在 NOOA 的 structured-output validation 阶段失败：Ministral 输出的 `reason` 超过既有 600 字符上限，NOOA 两次重试后报告 `GenerationError`。没有解析、截断、JSON repair 或伪造结果。

为使“证据充分性”而非冗长文本成为被测变量，Controller prompt 随后明确限制 `reason` 为一到两句且少于 300 字符；schema 未放宽，模型在下一次真实运行中自行输出合法 JSON。该失败和调整均保留在 artifact 的 `diagnostic_pre_run` 中。

## 结论与 Phase 2 交接

本实验满足 Phase 1 收尾条件：Controller 能区分“估值差距已由 Java 证据建立”与“市场价格原因缺少证据”，并明确返回 `REQUEST_EVIDENCE(MARKET_INFORMATION)`，没有制造因果或数值主张。

因此，多模型推理本身不是解决信息缺口的理由；agent 只应在新增缺失的信息或执行能力时才被引入。Phase 2 的起点应是一个具备来源保留能力的 Market Information Agent：它消费此请求，返回带 provenance 的 evidence packets，再由 Controller 做后续综合；本次实验没有实现该 agent。

## 复现与校验

```bash
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/pyright
.venv/bin/pytest -q

# 每个条件单独以 sandbox 运行，严格串行：
EVIDENCE_SUFFICIENCY_CONDITION=ministral_only \
  python -m app.sandbox_evidence_sufficiency_evaluation

EVIDENCE_SUFFICIENCY_CONDITION=ministral_router_advisory \
  python -m app.sandbox_evidence_sufficiency_evaluation
```

实际验收通过 Docker sandbox 和受控 Controller/Router proxy 执行；本地单元测试只使用冻结 fixture，不需要 Java、Router、Ollama、数据库或私有数据。
