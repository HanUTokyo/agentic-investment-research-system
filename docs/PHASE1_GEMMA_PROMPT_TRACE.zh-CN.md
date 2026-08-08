# Phase 1 Gemma：最终 Prompt 与逐次模型返回

本文件是针对可重建 mock AAPL 数据的**显式审计复测**。默认生产日志不会保存 prompt 或模型正文；本次由用户明确要求而生成，用于审阅受控 Phase 1 验收中的每一次模型调用。

## 运行边界

- Java 先确定性地计算 AAPL BASE scenario，再将**精简后的证据**提供给模型。
- 未向模型提供原始 portfolio export、交易记录或数据库内容。
- 模型不计算 DCF，也不产生最终数值报告；它只决定是否需要一次额外 scenario，并给出短解释。
- `model: local-router` 是逻辑模型 ID；Router 的当前本地 answer model 为 `gemma4:latest`。
- 两次调用均设置 `temperature=0`，串行执行。

## 第一次模型调用：是否追加 scenario

### System prompt

```text
Return JSON only: run_additional_scenario, scenario_type, reason. If the supplied warning means a material evidence gap, choose true and BEAR. Do not use numbers.
```

### User payload

```json
{
  "model": "FCFF",
  "warnings": [
    "FCFF cross-check is unavailable because D&A, NOPAT, or working-capital change is missing."
  ]
}
```

### 原始模型返回

```json
{
  "run_additional_scenario": true,
  "scenario_type": "BEAR",
  "reason": "The warning indicates a material evidence gap regarding the FCFF calculation due to missing components (D&A, NOPAT, or working-capital change)."
}
```

### Router 元数据

| 字段 | 值 |
|---|---|
| 逻辑模型 | `local-router` |
| Router route 字段 | `null`（当前 OpenAI-compatible response 未返回 route） |
| 调用延迟 | 7472.6 ms |
| Pydantic 解析 | `AdditionalScenarioDecision`，成功 |

### 确定性后续动作

系统检查 `scenario_type` 是否在 allowlist `{BEAR, BULL}` 内。结果为 `BEAR`，因此调用 Java：

```text
POST /api/valuations/AAPL/evaluate
```

Java 返回有效 FCFF BEAR scenario；每股内在价值 `100.7531`。此数字来自 Java，不来自模型。

## 第二次模型调用：短综合

### System prompt

```text
Return JSON only: conclusion and uncertainty. Use supplied evidence only. Do not use digits or make numerical claims.
```

### User payload

```json
{
  "model": "FCFF",
  "warning": [
    "FCFF cross-check is unavailable because D&A, NOPAT, or working-capital change is missing."
  ],
  "additional_scenario": "BEAR"
}
```

### 原始模型返回

```json
{
  "conclusion": "The calculation for Free Cash Flow to Firm cannot be completed due to missing data points.",
  "uncertainty": "High"
}
```

### Router 元数据

| 字段 | 值 |
|---|---|
| 逻辑模型 | `local-router` |
| Router route 字段 | `null` |
| 调用延迟 | 6197.5 ms |
| Pydantic 解析 | `ShortSynthesis`，成功 |

## 质量判断

两次返回均为合法 JSON，并通过 Pydantic 契约。第一次返回正确触发了 allowlist 内的一次 BEAR scenario。

第二次返回的 `uncertainty` 仅为 `High`，语义质量偏弱；这正是后续对 reason 模型进行比较评估的候选指标，而不是系统错误。系统仍将 Java 的完整 warning 原文保留在最终 `ValuationReport.warnings` 中，因此模型的简短回答不会覆盖确定性证据。

## 数据保护说明

这份文档是一次显式审计产物。常规运行保持脱敏：只记录请求结构、工具名、状态码、代码 SHA-256、耗时和结果类别，不记录 prompt、模型正文、认证头或完整金融 payload。
