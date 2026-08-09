# 本地模型真实输出与 NOOA CodeAct 契约对比

## 结论先行

这不是“模型是否聪明”的二元问题，而是三个独立的接口能力：

| 能力 | R1 | DeepSeek-Coder | Gemma | NOOA CodeAct 所需 |
|---|---|---|---|---|
| 短 JSON 判断 | 曾成功；不稳定 | 未作为主路径验证 | 成功 | 合法 JSON + Pydantic 校验 |
| 原生 Ollama tools | 未验证为可用 | 明确不支持 | Phase 1 短路径可用 | `execute_python` / `return_result` tool calls |
| 多轮工具会话 | 未验收 | 失败 | 未完成 NOOA `investigate` 验收 | 持续遵循工具协议并返回最终 typed result |
| 长 reasoning 后最终正文 | 不稳定、常为空 | 不适用 | 未作为 reason 模型测试 | 不能只有 thinking；必须有 final content |

Gemma 已通过的是**受控 Phase 1 短路径**：Python runner 直接调用只读 Java 工具，Gemma 作两次短 JSON 决策，再由 Pydantic 构造报告。它不是 `ValuationAgent.investigate` 的完整 NOOA CodeAct 验收成功。

## 1. R1 的真实输出

### 成功样本：短、固定 JSON 决策

请求要求只返回 `run_additional_scenario`、`scenario_type`、`reason`。经 Router 强制 `route_hint=reason`，`max_tokens=1024`，实际输出：

```json
{
  "run_additional_scenario": true,
  "scenario_type": "BEAR",
  "reason": "The warning indicates a material evidence gap as the FCFF cross-check cannot be performed due to missing key components like D&A, NOPAT, or working-capital change."
}
```

这能通过 `AdditionalScenarioDecision` Pydantic 模型。

### 失败样本：只输出 thinking，未输出 final content

同一类请求在较小预算下，Ollama 返回：

```json
{
  "content": "",
  "thinking": "First, the user has specified that I should respond with JSON only...",
  "done_reason": "length"
}
```

在随后端到端长延迟运行中，即使 `max_tokens=2048`、单并发、约 190 秒、Agent/Router/网关超时为 300/300/315 秒，Router 仍收到 HTTP 200 加空 `content`。这不能通过 JSON 或 Pydantic 边界。

### R1 需要改进的点

1. 必须把 thinking token 与 final-answer token 分配分开，或使用保证保留 final token 预算的模型/服务配置。
2. 需要在真实 Phase 1 prompt 上测量“非空、可解析 JSON”的成功率，而不是只看单次成功样本。
3. 在此之前，R1 只能作为人工触发/可失败的深度 reasoning 辅助，不应承担流程的唯一结构化决策。

## 2. DeepSeek-Coder 的真实输出

### 无 tools 的普通文本请求

请求：计算 `17 * 25 + 8`，并用工具调用表达执行。Coder 返回的是解释加 fenced JSON：

````text
Here's how you can use Python to calculate this expression:
```json
{
  "tool_call": {
    "name": "execute_python",
    "arguments": {
      "code": "result = (17 * 25) + 8\nreturn result"
    }
  }
}
```
````

其中 `return result` 也不是 NOOA Python cell 中所需的 `return_result(result)`；它不能直接完成 CodeAct。

### 原生 tools 请求

Ollama 的实际响应为：

```json
{
  "error": "registry.ollama.ai/library/deepseek-coder:6.7b does not support tools"
}
```

因此不是 prompt 小幅调整可以解决的协议问题。实验性的 Router 文本桥能从单一 JSON 中恢复 tool call，但 Coder 在工具结果后的下一轮会复述上下文，未稳定返回 `return_result` 所需的 typed 参数。

### Coder 需要改进的点

1. 最优解是改用/准备一个 Ollama 原生声明 tools capability 的代码模型，而不是扩展脆弱的文本桥。
2. 若保留桥接，必须在固定数据集上证明：每一轮只产出一个可解析 JSON tool call、参数符合 schema、并能在工具结果后给出 `return_result`。
3. 代码必须由 NOOA 在 Docker 沙盒执行；Router 或模型输出绝不能直接执行。

## 3. Gemma 的真实输出

### 追加情景决策

Gemma 在受控短 prompt 下的实际输出：

```json
{
  "run_additional_scenario": true,
  "scenario_type": "BEAR",
  "reason": "The warning indicates a material evidence gap regarding the FCFF calculation due to missing components (D&A, NOPAT, or working-capital change)."
}
```

它通过 `AdditionalScenarioDecision`，系统随后在 allowlist 检查后调用 Java `POST /api/valuations/AAPL/evaluate`；BEAR 的数值完全来自 Java。

### 短综合

实际输出：

```json
{
  "conclusion": "The calculation for Free Cash Flow to Firm cannot be completed due to missing data points.",
  "uncertainty": "High"
}
```

它通过 `ShortSynthesis`，但 `uncertainty` 过于简略，显示其语义表达质量仍需评估。

### Gemma 需要改进的点

1. 当前可以作为短 JSON 决策/综合基线；不要据此宣称它已经完成复杂 CodeAct。
2. 强化 report schema：把不受约束的 `uncertainty: str` 改为受限严重度与证据字段，减少 `"High"` 这类低信息输出。
3. 单独执行 NOOA `ValuationAgent.investigate` 的原生-tools 验收，记录每一轮工具调用和最终 `ValuationReport`。

## 4. NOOA CodeAct 实际要求 LLM 输出什么

NOOA 的 `CodeActStrategy` 每一回合提供两个 OpenAI 风格工具：

```text
execute_python(code: str)
return_result(result: <目标方法的返回类型>)
```

对于本项目的 `ValuationAgent.investigate(question, symbol) -> ValuationReport`，模型必须做到：

1. 返回 OpenAI/Ollama **原生 tool call**，而不是解释文字、Markdown code fence 或普通 JSON 文本。
2. 用 `execute_python` 调用允许的 `self.get_current_valuation(...)`、`self.run_valuation_scenario(...)` 等只读确定性方法；不得自行算 DCF。
3. 若需要更多证据，可继续产生有限次数的工具调用；系统限制最大迭代和最多一次额外 scenario。
4. 最后调用 `return_result`，其 arguments 必须匹配 `ValuationReport` Pydantic schema，或在 Python cell 中调用 `return_result(report)`。
5. 所有数值主张必须附带可追溯的确定性 `Evidence.source_path`；Pydantic/业务校验会拒绝不符合契约的最终对象。

### 最小成功形状（概念示例）

```json
{
  "tool_calls": [
    {
      "function": {
        "name": "execute_python",
        "arguments": {"code": "current = await self.get_current_valuation(symbol)"}
      }
    }
  ]
}
```

最终不是自由文本结论，而必须是：

```json
{
  "tool_calls": [
    {
      "function": {
        "name": "return_result",
        "arguments": {"result": {"symbol": "AAPL", "...": "ValuationReport-required fields"}}
      }
    }
  ]
}
```

## 5. 真实差距与优先级

| 优先级 | 改进 | 验收标准 |
|---|---|---|
| P0 | 用 Gemma 的原生 tools 跑一次真正的 `ValuationAgent.investigate` | 得到可验证 `ValuationReport`，含 Java evidence 与 tool trace |
| P0 | 为 R1 建立 final-content 成功率指标 | 同一 prompt 集合中非空、schema-valid JSON 的比例与延迟 |
| P1 | 为 Gemma 收紧 synthesis schema | uncertainty/evidence 不再是自由的单词字符串 |
| P1 | 决定 Coder 的替代或原生-tools 版本 | 不再依赖未验证文本桥 |
| P2 | 在 Phase 1 成功后才接入 LangGraph checkpoint | 不能用编排掩盖单 Agent 契约不稳定 |

## 审计边界

本文保存的是用户明确要求审阅的少量真实模型输出。默认运行日志仍不保存 prompts、金融 payload、认证头或模型正文；正式评估应使用显式 opt-in trace 目录和合成数据。
