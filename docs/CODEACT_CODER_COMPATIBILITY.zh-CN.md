# DeepSeek-Coder 与 NOOA CodeAct 兼容性记录

日期：2026-08-08（本地实验）

## 结论

`deepseek-coder:6.7b` 已通过现有 AI Router 的 `route_hint=code` 被选中，且请求始终从 Docker CodeAct 沙盒经由受控 Router 网关转发；没有直接连接 Ollama，也没有扩大沙盒网络或文件系统权限。

但该 Ollama 模型当前明确不支持原生 `tools`。NOOA CodeAct 需要 `execute_python` 与 `return_result` 工具调用，因此它不能作为 Phase 1 中可靠的 CodeAct 执行模型。

## 证据

- 直连 Ollama 的无工具聊天请求：HTTP 200，模型返回 `ok`。
- 直连 Ollama 的带 `execute_python` tools 请求：HTTP 400，错误为 `deepseek-coder:6.7b does not support tools`。
- Router 指标将 CodeAct 请求记录为 `model=deepseek-coder:6.7b`，网关结构化日志记录 `route_hint=code`；因此不是自动分类误路由。
- Docker 审计事件记录 Python 单元在非 root、只读、默认拒绝网络的容器内执行。审计仅记录代码 SHA-256、字节数与状态，默认不记录生成的代码、prompt 或金融载荷。
- 为实验实现的 Router JSON 工具协议桥可以将 Coder 的单一 JSON 工具调用还原为 OpenAI tool call；然而在第二回合 Coder 会复述上下文而非稳定地产生符合 `return_result` schema 的 JSON。NOOA/Pydantic 正确拒绝了该字符串结果。

## 影响与决定

1. `build_nooa_router_llm(..., route_hint="code")` 保留。它只声明任务意图，实际模型选择仍属于 Router。
2. 对具备原生 Ollama tools 支持的模型，继续使用原生协议；这是 Phase 1 CodeAct 验收的默认路径。
3. Coder 文本协议桥是隔离的 Router 兼容实验，不应在没有成功率评估前作为生产能力宣称。
4. 在单机硬件上，NOOA LLM 客户端的重试设为零，避免客户端超时后形成多个排队的本地模型请求。

## 后续验收条件

只有在受控数据集上同时满足以下条件时，才可启用 Coder CodeAct：原生 tools 支持，或文本桥的结构化 tool-call 有可量化的成功率、无不受控重试、并且能通过沙盒与类型验证的完整工具轨迹。
