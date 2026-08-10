# Phase 1 证据充分性延迟诊断

## 问题

原始 evidence-sufficiency 单次运行显示：Ministral only 为 69.8s，而启用 Router advisory 的条件为 19.1s。两次成功轨迹实际上相同：紧凑 Java observation → Ministral → `REQUEST_EVIDENCE(MARKET_INFORMATION)`；Pattern B 没有 Router delegation、worker call 或 scenario call。

本诊断只检查这是否是 serving runtime state（模型加载、驻留或缓存）造成的差异，而不是 Agent architecture 差异。

## 控制与计时范围

两条 sequence 均使用相同的 frozen public AAPL fixture、问题、compact projection、Ministral `ministral-3:8b`、Controller prompt、schema、NOOA retry policy 和受限 sandbox。禁止并发、Web、市场数据、Market Information Agent、scenario 以及主动 Router delegation。

每条 sequence 开始前，直接对远端 Ollama 执行一次 `keep_alive=0` unload 请求；响应为 `done_reason=unload`，紧接着 `/api/ps` 返回空模型列表。该重置动作不计入测试时间。后端 OpenAI-compatible completion 未返回 load duration、prompt evaluation duration、generation duration、token、prefix-cache 或 residency telemetry，因此这些字段明确为 unavailable。

`total_latency_ms` 从 fixture/settings/agent construction 前开始，包含 fixture loading、agent/RouterClient construction、compact projection、Controller request、NOOA structured validation 和 post-validation。最关键的 `controller_call_latency_ms` 只包围 `decide_evidence_sufficiency(...)`，因此包含该次 Controller HTTP/模型调用和 NOOA 对该 typed decision 的必要 validation/retry。

## 运行顺序与结果

| Sequence | 位置 | 条件 | total | Controller call | Router called | 正确性 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| 1: A→B→A→B→A→B | 1 | A | 85.42s | 85.34s | 0 | PASS |
| 1 | 2 | B | 17.84s | 17.83s | 0 | PASS |
| 1 | 3 | A | 17.61s | 17.61s | 0 | PASS |
| 1 | 4 | B | 18.23s | 18.22s | 0 | PASS |
| 1 | 5 | A | 16.97s | 16.96s | 0 | PASS |
| 1 | 6 | B | 17.69s | 17.68s | 0 | PASS |
| 2: B→A→B→A→B→A | 1 | B | 86.52s | 86.44s | 0 | PASS |
| 2 | 2 | A | 18.52s | 18.52s | 0 | PASS |
| 2 | 3 | B | 17.00s | 16.99s | 0 | PASS |
| 2 | 4 | A | 18.64s | 18.63s | 0 | PASS |
| 2 | 5 | B | 18.74s | 18.73s | 0 | PASS |
| 2 | 6 | A | 18.43s | 18.43s | 0 | PASS |

每一行均满足：typed schema valid、`REQUEST_EVIDENCE`、`MARKET_INFORMATION`、unsupported numerical claims = 0、unsupported causal claims = 0、Router delegation = 0、worker calls = 0、scenario calls = 0。所有 Controller context hash 相同，Controller endpoint/model/config 相同；B 仅多构造了一个未被调用的 `RouterClient`。

## 汇总（n 很小，仅作诊断）

| 分组 | n | min | max | mean | median |
| --- | ---: | ---: | ---: | ---: | ---: |
| A — Ministral only | 6 | 16.97s | 85.42s | 29.26s | 18.48s |
| B — Router advisory available | 6 | 17.00s | 86.52s | 29.33s | 18.03s |
| 每条 sequence 的第 1 位 | 2 | 85.42s | 86.52s | 85.97s | 85.97s |
| 位置 2–6 | 10 | 16.97s | 18.74s | 17.97s | 18.03s |

setup、compact projection 和 post-validation 都在毫秒级；几乎全部差异位于 `controller_call_latency_ms`。这与 Ollama 模型首次加载/驻留状态一致，但当前 backend response 没有更细的 load telemetry，因此报告不把它表述为已精确分解的 load time。

## 结论

最支持 **H1 — cold start / model residency effect**。

- Sequence 1 中 A 首先运行时慢；之后 B 与 A 都快速。
- Sequence 2 中 B 首先运行时慢；之后 A 与 B 都快速。
- 没有实际 Router 调用，也没有不同的 Controller prompt、context、schema、endpoint、model alias 或 retry 路径。

因此，早先的 69.8s vs. 19.1s 不应被视为 architecture effect。正确解释是 runtime-state artifact：在没有 delegation 时，两个条件走同一 Controller inference path；首个请求承担了模型非驻留状态的主要成本。

## 复现命令

```bash
# 每组开始前：确认明确卸载（不计入测试计时）
curl -X POST http://<ollama-host>:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"ministral-3:8b","prompt":"","stream":false,"keep_alive":0}'
curl http://<ollama-host>:11434/api/ps

# 严格串行：每次在受控 sandbox 中运行一条 sequence
LATENCY_SEQUENCE_ID=sequence-1 LATENCY_SEQUENCE=A,B,A,B,A,B \
  python -m app.sandbox_evidence_sufficiency_latency_diagnostic

LATENCY_SEQUENCE_ID=sequence-2 LATENCY_SEQUENCE=B,A,B,A,B,A \
  python -m app.sandbox_evidence_sufficiency_latency_diagnostic
```

完整的每轮 stage timing、raw completion、condition/config 与结果位于 [machine-readable artifact](../eval/results/phase1_evidence_sufficiency_latency_diagnostic_2026-08-10.json)。
