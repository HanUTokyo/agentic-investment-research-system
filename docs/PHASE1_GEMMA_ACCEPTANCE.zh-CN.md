# Phase 1：Gemma 受控验收记录

**目标：** 验证单机、单模型、串行条件下，系统能否完成一个短路径估值闭环：BASE scenario、由模型决定是否运行一次额外 scenario、短 structured synthesis，以及 typed `ValuationReport`。

## 验收约束

- 只使用 Router 中的本地 `gemma4:latest`。
- 一次只运行一个研究任务；没有并行 specialist 或并行 Ollama 请求。
- 最多允许一次额外 scenario，且只允许 `BEAR` 或 `BULL`。
- Java 平台是唯一的 DCF/FCFF/Reverse DCF 计算来源。
- sandbox 只通过 allowlist gateway 访问 Router 和 Java。
- LLM 只能决定是否需要额外 scenario，并生成不含数值的短解释。

## 初次失败轨迹

初次运行在模型决定阶段收到 Router `504/OllamaTimeout`，因此流程在 BASE scenario 后停止。该失败被保留为评估证据，而不是被视作成功：

```text
GET /api/valuations/AAPL                 -> 200
POST /api/valuations/AAPL/evaluate BASE  -> 200
Router typed decision                    -> 504 / OllamaTimeout
```

当时 Router 的历史指标显示成功请求与失败请求都存在较长耗时，因此不能把故障简单归因为多 Agent 并发。

## 控制实验与成功轨迹

控制条件：Router 重启、仅 Gemma 驻留、所有请求串行、Router upstream read timeout 临时调整为 180 秒。

先执行等价的 curl JSON decision：

```text
HTTP 200
total: 8.77 seconds
```

随后 sandbox 内 Phase 1 runner 成功完成：

```text
GET current valuation
  -> BASE scenario via Java engine
  -> Gemma decision: run BEAR because FCFF cross-check warning is material
  -> BEAR scenario via Java engine
  -> Gemma structured synthesis
  -> Pydantic ValuationReport
```

### 已验证输出

| 项目 | 结果 |
|---|---|
| Java selected model | `FCFF` |
| BASE intrinsic value / share | `178.6394` |
| BEAR intrinsic value / share | `100.7531` |
| Reverse DCF | `AVAILABLE` |
| LLM additional-scenario decision | `true`, `BEAR` |
| Typed report | Pydantic `ValuationReport` 已生成 |
| Router post-restart requests | 3 次 HTTP 200，0 次 HTTP 504 |
| Router average upstream latency | 约 7.31 秒 |

## 结论

受控 Phase 1 路径已通过。现有 Gemma 在严格串行、短 prompt、短 JSON 输出、最多一次额外 scenario 的条件下足以完成该验收。

这不代表 Gemma 已适合所有 Agent 工作：复杂 CodeAct、多步异步工具调用、长上下文和更严格的领域综合仍需要继续评估，并与后续 reason/code 模型在相同数据集上比较。

## 复现

```bash
scripts/sandbox/start-gateway.sh
docker build -t agentic-investment-research-sandbox -f Dockerfile.sandbox .
scripts/sandbox/run-codeact.sh -m app.sandbox_phase1_valuation_test
```
