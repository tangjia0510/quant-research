# 迁移后研究入口

本目录是轻量研究记录。下方保留历史结论原文，但原文提及的 outputs/、report/、admission.json 等路径属于旧归档，并不表示这些大产物已搬到本目录。

- 当前元信息与数据引用：`research.yaml`、`protocol.json`。
- 尝试/失败历史：`attempts.jsonl`。
- 当前可用关键证据：`evidence/research-decision.json`。
- 原文按字节保存在 `evidence/legacy-conclusion.md`，旧路径应通过 `research.yaml` 的 `legacy_ref` 解析。
- 回放入口：`src/replay.py --project-root PROJECT --work-dir PROJECT/work/NEW_ATTEMPT`。
- 此入口默认只做 dry-run。加 `--execute` 才计算；本轮只验证输入哈希、依赖和输出路径，未重算大规模历史结果。见 `evidence/migration-replay-plan.json`。
- 曲线、矩阵、账本和新运行报告写入指定 `work/`，不属于迁移包。

## 历史结论（保留当时措辞和路径）

# Quantitative research report

Historical research; numerical checks do not establish investment validity.

Mode: factor

Question: 在预注册30只代码分层A股样本中，检验20日动量对return_5与volatility_20固定Ridge基线的增量；非全市场、非盲测结论

| Segment | Start | End |
|---|---|---|
| train | 2020-01-02 | 2024-12-31 |
| valid | 2025-01-02 | 2025-06-30 |
| discovery | 2025-07-01 | 2025-12-31 |
| final | 2026-01-05 | 2026-10-30 |

Final results exposed: False

## momentum20-ridge-v1

固定Ridge(alpha=1)和return_5、volatility_20基线，仅增加20交易日收益率；预期提高开发期逐日RankIC与扣费净收益且不增加最大回撤。只检验此一候选，不追逐结果调参。

### discovery

Status: complete

| Scope | Metric | Value |
|---|---|---|
| signal | ic | 0.044041845567642936 |
| signal | rank_ic | -0.005476586734695621 |
| signal | ic_days | 120 |
| signal | rank_ic_positive_fraction | 0.5 |
| portfolio | days | 125 |
| portfolio | total_net_return | 0.16366879078424112 |
| portfolio | net_cagr | 0.3574131242045824 |
| portfolio | max_drawdown | -0.13239887183299637 |
| portfolio | annualized_arithmetic_excess | 0.08495213532076787 |
| portfolio | information_ratio | 0.7513372661590277 |
| portfolio | mean_daily_cost | 0.0001443379546925571 |
| portfolio | mean_daily_turnover | 0.1479251495577816 |
| equal_weight | days | 125 |
| equal_weight | total_net_return | 0.09048501725621749 |
| equal_weight | net_cagr | 0.19080684161629313 |
| equal_weight | max_drawdown | -0.06425840298875818 |
| equal_weight | annualized_arithmetic_excess | -0.06145387607615141 |
| equal_weight | information_ratio | -2.042225060906058 |
| equal_weight | mean_daily_cost | 4.546863645276932e-06 |
| equal_weight | mean_daily_turnover | 0.007910137128165344 |
| increment | days | 120 |
| increment | mean_rank_ic_increment | -0.002309331041848453 |
| increment | hac_lag | 5 |
| increment | hac_ci95 | [-0.00948209380761214, 0.004863431723915235] |
| increment | interpretation | exploratory paired estimate; not corrected for adaptive search or multiple trials |
| increment | annualized_net_return_difference | -0.010966254727193404 |
| baseline.signal | ic | 0.047454193435367456 |
| baseline.signal | rank_ic | -0.0031672556928471632 |
| baseline.signal | ic_days | 120 |
| baseline.signal | rank_ic_positive_fraction | 0.49166666666666664 |
| baseline.portfolio | days | 125 |
| baseline.portfolio | total_net_return | 0.17040935230815846 |
| baseline.portfolio | net_cagr | 0.37331122979413545 |
| baseline.portfolio | max_drawdown | -0.1254759188958623 |
| baseline.portfolio | annualized_arithmetic_excess | 0.09591839004796131 |
| baseline.portfolio | information_ratio | 0.8804341843147185 |
| baseline.portfolio | mean_daily_cost | 0.0001475211135326824 |
| baseline.portfolio | mean_daily_turnover | 0.15110529898180813 |
| robustness.double_cost | days | 125 |
| robustness.double_cost | total_net_return | 0.14377301668768538 |
| robustness.double_cost | net_cagr | 0.31103151310744215 |
| robustness.double_cost | max_drawdown | -0.1374336047434559 |
| robustness.double_cost | annualized_arithmetic_excess | 0.05037242136140347 |
| robustness.double_cost | information_ratio | 0.44068004668780747 |
| robustness.double_cost | mean_daily_cost | 0.0002893675851980401 |
| robustness.double_cost | mean_daily_turnover | 0.1481689399917864 |
| robustness.delayed_signal | days | 125 |
| robustness.delayed_signal | total_net_return | 0.098301410039769 |
| robustness.delayed_signal | net_cagr | 0.20807703034074954 |
| robustness.delayed_signal | max_drawdown | -0.12667417100088496 |
| robustness.delayed_signal | annualized_arithmetic_excess | -0.032325822814815615 |
| robustness.delayed_signal | information_ratio | -0.2746736098085943 |
| robustness.delayed_signal | mean_daily_cost | 0.00013343299833199886 |
| robustness.delayed_signal | mean_daily_turnover | 0.13700038695727884 |

[Full numerical evidence: momentum20-ridge-v1/discovery](runs/discovery/momentum20-ridge-v1/result.json)

## Data provenance

Snapshot: f7c7e80937d8fd4bde81097793b9406101e0a869bbfabfe0af34d94c88b0befb

Rows: 56194; instruments: 30

Unknown missing-session cause is preserved, not called verified suspension

Factors retrospectively obtained; no independently certified event-time/PIT correctness

Delisting liquidation not fully modeled by engine

Unified price-limit proxy does not implement historical ST and board limits

Small code-stratified sample not market-representative

Vendor data may be revised; snapshot not point-in-time certified

Calendar is observed SSE Composite sessions, not official holiday calendar

QRBENCH is a synthetic equal-weight close-price reference; cash on dates without a valid basket; no transaction costs

Daily-bar simulation does not certify real fills, capacity or point-in-time data quality

[Full data manifest](data/manifest.json)

[Frozen protocol](protocol.json)
