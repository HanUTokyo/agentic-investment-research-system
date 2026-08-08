# AAPL 实际估值研究轨迹（中文版）

**运行时间：** 2026-08-08T08:42:04Z  
**研究 ID：** `a7f1f691-5df0-48b5-86aa-03751ebc3f4f`  
**运行模式：** 本地、串行、只读 Agent 工具；Java 平台与本地 AI Router 均在开发机运行。

这是一次针对可重建 mock PostgreSQL 数据库的端到端集成测试。它不是投资建议；本文不包含账户、交易或持仓规模数据。

## 研究问题

> 当前确定性估值是否支持向 AAPL 增量配置资金？请识别决定性估值证据和最重要的证据缺口。

## 执行边界

- Python Agent 服务没有计算任何 DCF 数值。
- Java `valuation-java-2.0.0` 负责选择并计算 FCFF 模型。
- Agent 只调用只读 HTTP 工具。
- 本地 Router 选择已配置的本地回答模型；LLM 仅接收精简证据摘要，且不得新增数值主张。
- 此次运行没有启动 Docker 执行 sandbox，因此 NOOA CodeAct 被刻意禁用。

## 状态时间线

| 状态 | 输入 | 输出 / 状态迁移 |
|---|---|---|
| `PLANNED` | 上述问题；标的 `AAPL` | 选择串行只读流程；CodeAct 禁用。 |
| `SNAPSHOT_RETRIEVED` | `get_company_snapshot("AAPL")` | Java engine 为 `valuation-java-2.0.0`；模型 `FCFF`；适用性 `AVAILABLE`；没有缺失字段。 |
| `FUNDAMENTALS_RETRIEVED` | `get_financial_history("AAPL")` | 获得 48 条季度基本面记录；资本配置历史存在。 |
| `CURRENT_VALUATION_RETRIEVED` | `get_current_valuation("AAPL")` | 模型 `FCFF`；存在三个已保存的 scenario 槽位；没有缺失字段。 |
| `SCENARIO_EVALUATED` | 下文 BASE 假设 | FCFF 结果有效；存在一条数据质量警告。 |
| `SCENARIO_EVALUATED` | 下文 BEAR 假设 | FCFF 结果有效；存在一条数据质量警告。 |
| `SCENARIO_EVALUATED` | 下文 BULL 假设 | FCFF 结果有效；存在一条数据质量警告。 |
| `REVERSE_DCF_RETRIEVED` | `solve_market_implied_assumptions("AAPL")` | Reverse DCF 可用。 |
| `SYNTHESIS_VALIDATED` | 仅确定性证据摘要 | 本地模型输出经 Pydantic 验证；不受支持的数值主张数量为零。 |
| `COMPLETED` | 所有步骤成功 | 端到端耗时 14.6 秒。 |

## 确定性工具输入与输出

### Scenario 输入

以下数据被传给 `POST /api/valuations/AAPL/evaluate`。该端点只评估，不会持久化 scenario。

| Scenario | 基础现金流 | 初始增长率 | 折现率 | 永续增长率 | 年数 | 安全边际 |
|---|---:|---:|---:|---:|---:|---:|
| BASE | 128,000,000,000 | 7.0% | 8.5% | 2.5% | 10 | 20.0% |
| BEAR | 110,000,000,000 | 2.0% | 9.5% | 2.0% | 10 | 30.0% |
| BULL | 140,000,000,000 | 10.0% | 8.0% | 3.0% | 10 | 10.0% |

所有 scenario 共同使用：`baseCashFlowMode=MANUAL`、`growthMode=CUSTOM_LINEAR`、`discountRateMode=MANUAL_RATE`。Java 解析得到的共同市场输入为：无风险利率 4.65%、beta 1.086、股权风险溢价 5.0%。

### Java Scenario 输出

| Scenario | 选定模型 | 有效 | 每股内在价值 | 安全边际价格 | 警告 |
|---|---|---:|---:|---:|---|
| BASE | FCFF | 是 | 178.6394 | 142.9115 | 因 D&A、NOPAT 或营运资本变动缺失，无法完成 FCFF cross-check。 |
| BEAR | FCFF | 是 | 100.7531 | 70.5271 | 同上。 |
| BULL | FCFF | 是 | 263.0358 | 236.7322 | 同上。 |

### Java Reverse DCF 输出

| 字段 | 值 |
|---|---:|
| 状态 | `AVAILABLE` |
| 隐含初始增长率 | 19.7832% |
| 隐含折现率 | 6.1154% |

## Agent 工具调用轨迹

| 工具 | 结果 | 耗时 |
|---|---|---:|
| `get_company_snapshot` | 成功 | 477.0 ms |
| `get_financial_history` | 成功 | 35.8 ms |
| `get_current_valuation` | 成功 | 107.1 ms |
| `run_valuation_scenario(BASE)` | 成功 | 113.6 ms |
| `run_valuation_scenario(BEAR)` | 成功 | 104.2 ms |
| `run_valuation_scenario(BULL)` | 成功 | 113.0 ms |
| `solve_market_implied_assumptions` | 成功 | 295.7 ms |

## 本地模型综合轨迹

### 精确模型输入

Router 接收的是下列证据摘要，而非原始 portfolio export 或完整基本面 payload：

```json
{
  "selected_model": "FCFF",
  "scenario_values": {
    "BASE": "178.6394",
    "BEAR": "100.7531",
    "BULL": "263.0358"
  },
  "reverse_dcf_status": "AVAILABLE",
  "warning": [
    "FCFF cross-check is unavailable because D&A, NOPAT, or working-capital change is missing."
  ]
}
```

系统约束：仅返回一个含 `assessment`、`primary_uncertainty` 与 `next_step` 的 JSON 对象；只能使用给定事实；不得使用数字或新增数值主张。`max_tokens` 为 200。

### 已验证的模型输出

```json
{
  "assessment": "The Free Cash Flow to Firm (FCFF) valuation model has scenario values available for BASE, BEAR, and BULL cases. However, a warning indicates that the FCFF cross-check is unavailable due to missing data points such as Depreciation and Amortization, Net Operating Profit After Tax, or working capital change.",
  "primary_uncertainty": "The inability to perform an FCFF cross-check due to missing underlying financial inputs (D&A, NOPAT, or working-capital change).",
  "next_step": "Obtain the necessary detailed financial data points—specifically Depreciation and Amortization, Net Operating Profit After Tax, and working capital changes—to complete the FCFF cross-check."
}
```

输出由 `RouterClient.complete_structured` 解码：它只接受完整的单个 JSON code fence 或裸 JSON，之后再由 Pydantic 验证。该输出通过了本次运行的“不得新增数值主张”检查。

## 结论与限制

确定性估值区间很宽，因此本次轨迹**不构成**增配授权。模型最有价值的作用是指出与 Java engine 相同的证据缺口，而不是替代 Java engine 或虚构结论。

下一项确定性集成改进，是获取或审核缺失的 D&A、NOPAT 与营运资本变动输入，使 Java 能完成 FCFF cross-check。在此之前，以上估值 scenario 可以使用，但必须携带表中所示警告。

## 验证方法

在仓库根目录启动 Java（8080）和 Router（8000）后执行：

```bash
$HOME/.local/bin/uv run ruff check app tests
$HOME/.local/bin/uv run ruff format --check app tests
$HOME/.local/bin/uv run pyright
$HOME/.local/bin/uv run pytest -q
```

本报告对应的测试状态为：19 个测试通过，1 个 opt-in live Router compatibility 测试跳过。
