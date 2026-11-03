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

## negative-return-volume-corr20

Strong contemporaneous price/participation coupling may reflect transitory pressure rather than continuation; direction informed by prior reversal results and not independent prior knowledge; expected positive direct orientation, primary model incremental objective assessed separately

### discovery

Status: complete

| Scope | Metric | Value |
|---|---|---|
| signal | ic | 0.015050444781333916 |
| signal | rank_ic | 0.015522150922456183 |
| signal | ic_days | 120 |
| signal | rank_ic_positive_fraction | 0.5083333333333333 |
| portfolio | days | 125 |
| portfolio | total_net_return | -0.10230547460447492 |
| portfolio | net_cagr | -0.19553489518344136 |
| portfolio | max_drawdown | -0.14196760667938335 |
| portfolio | annualized_arithmetic_excess | -0.5429480640014377 |
| portfolio | information_ratio | -2.367183834621225 |
| portfolio | mean_daily_cost | 0.00024341762022889274 |
| portfolio | mean_daily_turnover | 0.24558218116739564 |
| equal_weight | days | 125 |
| equal_weight | total_net_return | 4.984500691684879e-05 |
| equal_weight | net_cagr | 0.0001004900784162821 |
| equal_weight | max_drawdown | -1.9998601375581515e-05 |
| equal_weight | annualized_arithmetic_excess | -0.3609793655083777 |
| equal_weight | information_ratio | -2.315368086959485 |
| equal_weight | mean_daily_cost | 1.2400000129910362e-09 |
| equal_weight | mean_daily_turnover | 2.4800000259820724e-06 |
| increment | days | 120 |
| increment | mean_rank_ic_increment | 0.004131496227178557 |
| increment | hac_lag | 5 |
| increment | hac_ci95 | [-0.0001826232599060314, 0.008445615714263145] |
| increment | interpretation | exploratory paired estimate; not corrected for adaptive search or multiple trials |
| increment | annualized_net_return_difference | 0.014890752130260542 |
| baseline.signal | ic | 0.014952576279706786 |
| baseline.signal | rank_ic | 0.011390654695277624 |
| baseline.signal | ic_days | 120 |
| baseline.signal | rank_ic_positive_fraction | 0.5083333333333333 |
| baseline.portfolio | days | 125 |
| baseline.portfolio | total_net_return | -0.10774171532904575 |
| baseline.portfolio | net_cagr | -0.2053259569316085 |
| baseline.portfolio | max_drawdown | -0.1480504200925561 |
| baseline.portfolio | annualized_arithmetic_excess | -0.557838816131698 |
| baseline.portfolio | information_ratio | -2.5563813127267525 |
| baseline.portfolio | mean_daily_cost | 0.00024593423053294804 |
| baseline.portfolio | mean_daily_turnover | 0.24814277259447576 |
| robustness.double_cost | days | 125 |
| robustness.double_cost | total_net_return | -0.12365991956820721 |
| robustness.double_cost | net_cagr | -0.233648321375309 |
| robustness.double_cost | max_drawdown | -0.1522016291039776 |
| robustness.double_cost | annualized_arithmetic_excess | -0.5904624771930758 |
| robustness.double_cost | information_ratio | -2.5479587522177787 |
| robustness.double_cost | mean_daily_cost | 0.00048546746334518086 |
| robustness.double_cost | mean_daily_turnover | 0.2448244450661685 |
| robustness.delayed_signal | days | 125 |
| robustness.delayed_signal | total_net_return | -0.17586197959001104 |
| robustness.delayed_signal | net_cagr | -0.3228951891295758 |
| robustness.delayed_signal | max_drawdown | -0.2124349962675941 |
| robustness.delayed_signal | annualized_arithmetic_excess | -0.7261569709707508 |
| robustness.delayed_signal | information_ratio | -3.6649602768281864 |
| robustness.delayed_signal | mean_daily_cost | 0.0002345786055459698 |
| robustness.delayed_signal | mean_daily_turnover | 0.23768149785524814 |

[Full numerical evidence: negative-return-volume-corr20/discovery](runs/discovery/negative-return-volume-corr20/result.json)

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
