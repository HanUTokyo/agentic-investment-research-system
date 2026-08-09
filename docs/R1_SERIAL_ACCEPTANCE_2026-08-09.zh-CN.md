# R1 串行长延迟 Phase 1 验收记录

## 目的

验证 Mac mini M1 上的 `deepseek-r1:8b` 是否仅因等待时间不足而无法完成 Phase 1 的结构化证据缺口判断。

## 运行设计

- 并发：1；未启动其它 Agent 或模型请求。
- Java 平台：Mac mini `192.168.31.216:8080`，仅经 Docker allowlist 网关访问。
- Router：本机 `127.0.0.1:8000`，强制 `route_hint=reason`。
- R1：`max_tokens=2048`。
- 超时：Agent 300 秒、Router 上游 300 秒、Docker 网关上游 315 秒。
- 先读取 AAPL 当前估值，再运行只读 BASE scenario，随后要求 R1 返回 `AdditionalScenarioDecision` JSON。

## 实测结果

- Java `GET /api/valuations/AAPL`：200。
- Java `POST /api/valuations/AAPL/evaluate`：200。
- R1 请求：HTTP 200；Router 与网关在约 190 秒内一直保持连接。
- R1 completion：空 `content`，因此 Pydantic JSON 边界正确拒绝该结果。

## 结论

增加等待时间解决了此前 Docker 网关 30 秒提前断开的实现缺陷，但没有使 R1 稳定生成结构化最终答案。该实验不能通过 Phase 1 验收。

Phase 1 尚缺少一次真正由 NOOA `ValuationAgent.investigate` 完成的、可验证 typed `ValuationReport` 真实成功轨迹。R1 应保留为可选长时 reasoning 模型；主 CodeAct/typed-output 路径必须使用一个具备原生 tools 且已测得稳定完成 JSON 的本地模型。
