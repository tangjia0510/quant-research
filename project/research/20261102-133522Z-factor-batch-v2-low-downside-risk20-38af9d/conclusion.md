# 迁移后研究入口

本目录是轻量研究记录。下方保留历史结论原文，但原文提及的 outputs/、report/、admission.json 等路径属于旧归档，并不表示这些大产物已搬到本目录。

- 当前元信息与数据引用：`research.yaml`、`protocol.json`。
- 尝试/失败历史：`attempts.jsonl`。
- 当前可用关键证据：`evidence/`。
- 原文按字节保存在 `evidence/legacy-conclusion.md`，旧路径应通过 `research.yaml` 的 `legacy_ref` 解析。
- 回放入口：`src/replay.py --project-root PROJECT --work-dir PROJECT/work/NEW_ATTEMPT`。
- 此入口默认只做 dry-run。加 `--execute` 才计算；本轮只验证输入哈希、依赖和输出路径，未重算大规模历史结果。见 `evidence/migration-replay-plan.json`。
- 曲线、矩阵、账本和新运行报告写入指定 `work/`，不属于迁移包。

## 历史结论（保留当时措辞和路径）

# Quantitative research report

Historical research; numerical checks do not establish investment validity.

Mode: factor

Question: Three fixed price-volume mechanisms; primary paired model RankIC increment vs fixed Ridge baseline; retrospective development and globally bounded parallel batch

| Segment | Start | End |
|---|---|---|
| train | 2020-01-02 | 2024-12-31 |
| valid | 2025-01-02 | 2025-06-30 |
| discovery | 2025-07-01 | 2025-12-31 |
| final | 2026-01-05 | 2026-10-30 |

Final results exposed: False

## low-downside-risk20

Lower downside-specific risk may add information beyond total volatility; incremental Ridge baseline explicitly includes volatility20; expected positive direct orientation, primary model incremental objective assessed separately

### discovery

Status: complete

| Scope | Metric | Value |
|---|---|---|
| signal | ic | 0.014761448631640035 |
| signal | rank_ic | 0.017611945242427287 |
| signal | ic_days | 120 |
| signal | rank_ic_positive_fraction | 0.5333333333333333 |
| portfolio | days | 125 |
| portfolio | total_net_return | -0.29503308926273264 |
| portfolio | net_cagr | -0.5057938273848226 |
| portfolio | max_drawdown | -0.32989472779121487 |
| portfolio | annualized_arithmetic_excess | -1.0421135355749422 |
| portfolio | information_ratio | -5.521990599294478 |
| portfolio | mean_daily_cost | 0.0002029269434509303 |
| portfolio | mean_daily_turnover | 0.206319898585166 |
| equal_weight | days | 125 |
| equal_weight | total_net_return | 4.984500691684879e-05 |
| equal_weight | net_cagr | 0.0001004900784162821 |
| equal_weight | max_drawdown | -1.9998601375581515e-05 |
| equal_weight | annualized_arithmetic_excess | -0.3609793655083777 |
| equal_weight | information_ratio | -2.315368086959485 |
| equal_weight | mean_daily_cost | 1.2400000129910362e-09 |
| equal_weight | mean_daily_turnover | 2.4800000259820724e-06 |
| increment | days | 120 |
| increment | mean_rank_ic_increment | 0.006221290547149662 |
| increment | hac_lag | 5 |
| increment | hac_ci95 | [-0.007694787636425836, 0.02013736873072516] |
| increment | interpretation | exploratory paired estimate; not corrected for adaptive search or multiple trials |
| increment | annualized_net_return_difference | -0.48427471944324463 |
| baseline.signal | ic | 0.014952576279706786 |
| baseline.signal | rank_ic | 0.011390654695277624 |
| baseline.signal | ic_days | 120 |
| baseline.signal | rank_ic_positive_fraction | 0.5083333333333333 |
| baseline.portfolio | days | 125 |
| baseline.portfolio | total_net_return | -0.10774171532904564 |
| baseline.portfolio | net_cagr | -0.20532595693160827 |
| baseline.portfolio | max_drawdown | -0.14805042009255542 |
| baseline.portfolio | annualized_arithmetic_excess | -0.5578388161316977 |
| baseline.portfolio | information_ratio | -2.5563813127267534 |
| baseline.portfolio | mean_daily_cost | 0.00024593423053294804 |
| baseline.portfolio | mean_daily_turnover | 0.24814277259447576 |
| robustness.double_cost | days | 125 |
| robustness.double_cost | total_net_return | -0.3205430504337492 |
| robustness.double_cost | net_cagr | -0.5411840773530998 |
| robustness.double_cost | max_drawdown | -0.3384540544853397 |
| robustness.double_cost | annualized_arithmetic_excess | -1.1167878645660219 |
| robustness.double_cost | information_ratio | -5.969632971481077 |
| robustness.double_cost | mean_daily_cost | 0.0004006957194510302 |
| robustness.double_cost | mean_daily_turnover | 0.20342809856455854 |
| robustness.delayed_signal | days | 125 |
| robustness.delayed_signal | total_net_return | -0.34565225565254465 |
| robustness.delayed_signal | net_cagr | -0.5747247024823982 |
| robustness.delayed_signal | max_drawdown | -0.34565225565254465 |
| robustness.delayed_signal | annualized_arithmetic_excess | -1.1934030502916613 |
| robustness.delayed_signal | information_ratio | -6.19852834476953 |
| robustness.delayed_signal | mean_daily_cost | 0.00020348118950063744 |
| robustness.delayed_signal | mean_daily_turnover | 0.20685410085558542 |

[Full numerical evidence: low-downside-risk20/discovery](runs/discovery/low-downside-risk20/result.json)

## Data provenance

Snapshot: 6e5753d6add722daf7bae55c51a2ed5722c826d49fab8bb31ccef434226c1c5d

Rows: 8777908; instruments: 5435

All input snapshots retrospective, not independently certified PIT/vintage

No future-label condition used in source eligibility; missing current bars remain NaN

Native train-median factor imputation differs from supplementary matched61 complete history sample

Historical ST/board-specific limits/suspensions not fully available

No complete terminal delisting returns or forced liquidation

302132 pre-switch mapped history excluded; old300114 not independently covered

sh689009 excluded for missing factor; sh600680 no period bars

Calendar observed SSE composite, not exchange certified

2026 previously exposed; final means retrospective robustness not untouched holdout

Daily simulator not calibrated slippage/capacity and benchmark synthetic

QRBENCH is a synthetic equal-weight close-price reference; cash on dates without a valid basket; no transaction costs

Daily-bar simulation does not certify real fills, capacity or point-in-time data quality

[Full data manifest](data/manifest.json)

[Frozen protocol](protocol.json)
