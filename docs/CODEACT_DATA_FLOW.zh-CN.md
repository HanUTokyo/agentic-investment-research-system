# CodeAct 与投资研究系统：端到端数据流（中文版）

本文说明 Agentic Investment Research System 在本地运行时，数据如何在用户、Java 确定性金融平台、FastAPI Agent、NOOA、AI Router、Docker sandbox 与 Ollama 之间流动；同时区分已通过实际测试的路径和当前限制。

## 一句话原则

LLM 不计算 DCF、不读取数据库、不直接访问 Ollama；它只在受限环境内决定何时调用确定性工具，并基于工具证据解释结果。

## 完整数据流

```text
研究问题 / UI
        |
        v
FastAPI Agent Service
        |  Pydantic contracts + research_id + trace metadata
        v
NOOA Valuation Agent / CodeAct Strategy
        |                              |
        | LLM generation               | generated Python (untrusted)
        v                              v
AI Router <---- allowlist gateway ---- Docker CodeAct sandbox
        |                                      |
        v                                      | only approved HTTP aliases
Local Ollama                                Java REST API
                                               |
                                               v
                                      PostgreSQL mock data
                                      + Java valuation engine
```

## 组件职责与允许的数据

| 组件 | 接收的数据 | 输出的数据 | 明确禁止 |
|---|---|---|---|
| Java 平台 | REST 参数、mock PostgreSQL 数据 | holdings、fundamentals、FCFF/FCFE、scenario、reverse DCF | LLM 推理、Python DCF、直接暴露数据库 |
| FastAPI Agent | 研究问题、symbol | Pydantic tool contracts、结构化报告 | 直连 PostgreSQL、重算估值 |
| NOOA | 方法签名、工具结果、任务状态 | tool call、CodeAct 代码、typed result | 任意递归 agent、未 allowlist 的工具 |
| AI Router | OpenAI-compatible chat/tool 请求 | 本地模型选择与回答 | 由 Agent 复制路由规则、云模型 |
| Docker sandbox | 生成的 Python、批准的环境变量 | 仅临时执行结果 | 宿主文件、Docker socket、外网、直连 Ollama |
| Gateway | HTTP 请求的 method/path/结构元数据 | 只允许的 HTTP 转发 | `/metrics`、任意 URL、未批准 Java 路径 |

## 已验证的 AAPL 确定性研究路径

以下实际测试使用可重建 mock 数据库中的 AAPL 数据。详细 scenario、工具耗时与模型输出见 [AAPL 中文研究轨迹](TEST_RUN_AAPL_2026-08-08.zh-CN.md)。

### 1. 输入与状态初始化

输入问题：

> 当前确定性估值是否支持向 AAPL 增量配置资金？请识别决定性估值证据和最重要的证据缺口。

Agent 为请求生成 `research_id` / `trace_id`，初始状态为 `PLANNED`。Phase 1 使用串行执行，最大并发为一。

### 2. Agent 到 Java REST 的只读工具调用

| Agent 工具 | Java endpoint | 返回的确定性数据 |
|---|---|---|
| `get_company_snapshot` | `GET /api/valuations/{symbol}` + `GET /api/portfolio/export/v2` | engine version、适用性、估值 snapshot、可选 holding context |
| `get_financial_history` | `GET /api/portfolio/history/fundamentals` + `GET /api/portfolio/history/capital-allocation` | 季度基本面与资本配置历史 |
| `get_current_valuation` | `GET /api/valuations/{symbol}` | 模型选择、warnings、field sources、scenario |
| `run_valuation_scenario` | `POST /api/valuations/{symbol}/evaluate` | Java 计算的未保存 scenario、sensitivity、reverse DCF |
| `solve_market_implied_assumptions` | 读取 BASE snapshot 后调用同一 evaluate endpoint | Java reverse DCF |

实际 AAPL 测试中，Java 选择 `FCFF`，三种 scenario 都有效：

| Scenario | 每股内在价值 | 安全边际价格 |
|---|---:|---:|
| BASE | 178.6394 | 142.9115 |
| BEAR | 100.7531 | 70.5271 |
| BULL | 263.0358 | 236.7322 |

逆向 DCF 返回的隐含初始增长率为 19.7832%。这些数值全部由 Java `valuation-java-2.0.0` 计算，不由 LLM 或 Python 计算。

### 3. 结构化 Agent 边界

Java JSON 进入 `StockPlatformClient` 后立刻解析为 Pydantic contracts，例如：

- `ValuationSnapshot`
- `ValuationEvaluation`
- `CompanySnapshot`
- `FinancialHistory`

因此上游 404、超时、无效 JSON、契约不匹配都会变为明确的安全错误类型，而不是被 LLM 猜测。

### 4. Router 与本地模型

NOOA 通过 LiteLLM 使用逻辑模型 ID `local-router` 调用：

```text
POST /v1/chat/completions
```

Router 根据自己的配置选择本地 Ollama 模型。Agent 不包含、也不复制 `code | reason | chat` 分类规则。模型的 Markdown JSON fence 会由 `RouterClient.complete_structured` 严格解包，然后用 Pydantic 验证；无效或截断 JSON 会被拒绝。

默认日志不记录 prompt、金融 payload、token 或认证头。

## CodeAct sandbox 实际路径

### 1. 镜像与进程约束

运行器 `scripts/sandbox/run-codeact.sh` 以如下安全策略运行容器：

- 非 root UID `10001`
- 只读 root filesystem 与 `/sandbox`
- 无宿主目录挂载、无 Docker socket、无凭据挂载
- `--cap-drop ALL` 与 `no-new-privileges`
- CPU 1、内存 1 GiB、PID 128 的资源限制
- 唯一临时可写区域：容器 `/tmp`；容器退出后删除
- `agent-restricted` internal Docker network

实际验证结果：根目录不可写、`/sandbox` 不可写、宿主 home 目录不可见、连接外网返回 `Network is unreachable`。

### 2. Allowlist gateway

gateway 有两张网络接口：一侧连接 internal sandbox network，另一侧才可访问 macOS host。sandbox 只能通过两个 alias 访问它：

| Alias | 目标 | 允许路径 |
|---|---|---|
| `router-proxy:8080` | host Router:8000 | `GET /health/ready`、`POST /v1/chat/completions` |
| `stock-proxy:8080` | host Java:8080 | OpenAPI、只读 valuation/history/export、仅 `POST .../evaluate` |

例如 sandbox 请求 `router-proxy/metrics` 被实际验证为 HTTP 403。它不能解析或访问 `host.docker.internal`、Ollama、任意网页或数据库。

### 3. NOOA 与 Ollama tool-history 兼容修复

NOOA 使用多轮工具历史；其中 assistant tool call 原本是 OpenAI 格式：

```text
id + type + function.arguments (JSON string) + tool_call_id
```

Ollama 要求不同格式：

```text
function.name + function.arguments (JSON object)
```

curl 已证明单轮双工具请求成功、带原始 OpenAI tool-history 的请求失败。Router 现在只对历史工具消息做最小规范化：把 JSON string arguments 解析为 object，并移除 `tool_call_id`。修复后 NOOA 的多轮 CodeAct 请求由 502 变为 HTTP 200。

## CodeAct 执行审计

审计只应用于 sandbox smoke test。它不记录代码正文，而输出：方法名、迭代次数、代码 SHA-256、字节长度、执行状态和返回值类型。

最近一次实际输出：

```json
{
  "event": "sandbox_codeact_execution",
  "method": "solve",
  "iteration": 0,
  "code_sha256": "8b8243247cab21ebc07a2493c7106781cd139786005a9fb8eac39f0ca1ed5982",
  "code_bytes": 156,
  "status": "complete",
  "returned_value_type": "object"
}
```

这证明模型生成的 Python 已在 sandbox 中被 NOOA 执行。代码没有写入宿主机，也没有以明文保存在审计日志中。

## 可观察性数据流

```text
Agent tool invocation
  -> research_id / agent / stage / success / duration
  -> sanitized gateway request shape
     (path, status, JSON keys, tool names, message roles)
  -> CodeAct execution metadata
     (SHA-256, byte length, iteration, status, return type)
```

不得记录：prompt 正文、Java financial payload、认证 header、token、生成代码正文、任何真实 portfolio 数据。

## 当前限制与下一步

1. 小模型已经完成隔离 CodeAct 的生成与执行 smoke test，但对复杂 typed return（尤其是多个异步工具步骤）尚不稳定。
2. `ValuationAgent.investigate` 的生产级 CodeAct 仍应在单独的 opt-in integration gate 下启用，而不是默认 FastAPI 请求路径。
3. 现有 FCFF 输出仍带数据质量警告：D&A、NOPAT 或营运资本变动不足以完成 cross-check。
4. Phase 2 才引入 LangGraph state、SQLite checkpoint、暂停/恢复与多 Agent 路由。

## 复现命令

```bash
# 启动 gateway（Java 8080 与 Router 8000 已运行）
scripts/sandbox/start-gateway.sh

# 构建隔离镜像
docker build -t agentic-investment-research-sandbox -f Dockerfile.sandbox .

# 运行不具副作用的 CodeAct 审计 smoke test
scripts/sandbox/run-codeact.sh -m app.sandbox_codeact_arithmetic
```
