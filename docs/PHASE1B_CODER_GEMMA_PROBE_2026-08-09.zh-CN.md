# Phase 1B：Coder 与 Gemma Router 能力探测

## 目的与边界

本次是受控、串行的能力探测，不是把 Coder 或 Gemma 接入估值报告的生产改动。

```text
Java AAPL compact observation
→ Coder（route_hint=code）生成非金融 Python draft，禁止执行
→ Gemma（route_hint=chat）生成非数值 warning 摘要
```

两个请求都在 Docker sandbox 内通过 Router gateway 发出；不存在并行 inference。Java
仍是数值事实来源，生成代码没有执行，`ValuationReport` 没有被修改。

## 实际结果

运行 ID：`4630e0a4-09af-4674-916e-a30b39086b1e`

Java observation：

```text
symbol: AAPL
selected_model: FCFE
warnings:
- FCFF cross-check is incomplete.
- High ROE may be distorted by buybacks or a small equity base.
```

| Worker | Router HTTP | 延迟 | 合同结果 | 结论 |
|---|---:|---:|---|---|
| DeepSeek-Coder (`code`) | 200 | 30.87s | `CodeDraft` JSON 失败 | 不可接入 typed worker path |
| Gemma (`chat`) | 200 | 13.42s | plain-text 摘要非空 | 可作为不可信摘要候选 |

### Coder 的原始输出

Coder 接收的任务仅要求使用已有 `scenario_types` 变量生成一个排序去重 draft，且禁止
DCF、估值计算、文件、网络、shell、imports 和执行。

它返回的是普通说明文字加 Markdown code fence，而不是要求的 JSON：

````text
Here is a minimal Python draft that creates sorted unique scenario types.

```python
scenario_types = ["Type1", "Type2", "Type3", "Type1"]
unique_scenario_types = sorted(list(set(scenario_types)))
```
...
````

这有两个独立问题：

1. 不满足 `CodeDraft(code, explanation, assumptions)` 的 JSON 合同；现有 runtime 因此以
   `UpstreamProtocolError: router did not return a JSON object` 拒绝它。
2. 它重新定义了题目已提供的 `scenario_types`，因此即使去掉 Markdown，也不是对实际
   deterministic observation 的安全 transformation。

这次拒绝是正确的保护行为：没有 parser repair，没有自动提取 code，也没有执行。

### Gemma 的实际输出

Gemma 收到同一组 Java warnings，并被要求只给出一句、无数字、无交易建议的摘要。它返回：

```text
The analysis notes that the FCFF cross-check is incomplete and high ROE might be
skewed by buybacks or a small equity base.
```

该摘要忠实反映了输入 warnings，未增加数值或投资建议。但它仍是 LLM 生成内容，不能替代
Java evidence，也不能单独驱动 scenario 或最终估值结论。

## 设计结论

- **Gemma**：适合继续作为可选的低风险摘要/抽取 worker 候选；接入前应增加一个小型
  Pydantic `WarningSummary` contract，并用重复运行测试其格式稳定性。
- **Coder**：当前本地 Router Coder 模型不能稳定服从 JSON `CodeDraft` 合同，且本次有
  忽略输入变量的语义漂移。它不应进入 Phase 1B 估值 runtime，更不能执行其代码。
- **多模型能力提升**：本 probe 仅证明连通性与失败隔离；不构成多模型提升估值能力的证据。
