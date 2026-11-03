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

## volume-weighted-close-location20

Persistent closes near the high, weighted by observed participation, proxy buying pressure; not signed order flow or market-cap turnover; expected positive direct orientation, primary model incremental objective assessed separately

### discovery

Status: complete

| Scope | Metric | Value |
|---|---|---|
| signal | ic | 0.014881576667878567 |
| signal | rank_ic | 0.011873156342705669 |
| signal | ic_days | 120 |
| signal | rank_ic_positive_fraction | 0.5083333333333333 |
| portfolio | days | 125 |
| portfolio | total_net_return | -0.11413768807295299 |
| portfolio | net_cagr | -0.2167682024886468 |
| portfolio | max_drawdown | -0.149014694905101 |
| portfolio | annualized_arithmetic_excess | -0.5723631100931285 |
| portfolio | information_ratio | -2.633289055117417 |
| portfolio | mean_daily_cost | 0.0002490994862257492 |
| portfolio | mean_daily_turnover | 0.2513410420408176 |
| equal_weight | days | 125 |
| equal_weight | total_net_return | 4.984500691684879e-05 |
| equal_weight | net_cagr | 0.0001004900784162821 |
| equal_weight | max_drawdown | -1.9998601375581515e-05 |
| equal_weight | annualized_arithmetic_excess | -0.3609793655083777 |
| equal_weight | information_ratio | -2.315368086959485 |
| equal_weight | mean_daily_cost | 1.2400000129910362e-09 |
| equal_weight | mean_daily_turnover | 2.4800000259820724e-06 |
| increment | days | 120 |
| increment | mean_rank_ic_increment | 0.00048250164742804345 |
| increment | hac_lag | 5 |
| increment | hac_ci95 | [-0.0016291526198680265, 0.002594155914724113] |
| increment | interpretation | exploratory paired estimate; not corrected for adaptive search or multiple trials |
| increment | annualized_net_return_difference | -0.014524293961430651 |
| baseline.signal | ic | 0.014952576279706786 |
| baseline.signal | rank_ic | 0.011390654695277624 |
| baseline.signal | ic_days | 120 |
| baseline.signal | rank_ic_positive_fraction | 0.5083333333333333 |
| baseline.portfolio | days | 125 |
| baseline.portfolio | total_net_return | -0.10774171532904486 |
| baseline.portfolio | net_cagr | -0.20532595693160682 |
| baseline.portfolio | max_drawdown | -0.1480504200925553 |
| baseline.portfolio | annualized_arithmetic_excess | -0.5578388161316976 |
| baseline.portfolio | information_ratio | -2.556381312726751 |
| baseline.portfolio | mean_daily_cost | 0.00024593423053294804 |
| baseline.portfolio | mean_daily_turnover | 0.24814277259447576 |
| robustness.double_cost | days | 125 |
| robustness.double_cost | total_net_return | -0.13696471413239375 |
| robustness.double_cost | net_cagr | -0.25692343995817735 |
| robustness.double_cost | max_drawdown | -0.16280541661716474 |
| robustness.double_cost | annualized_arithmetic_excess | -0.6245832303559904 |
| robustness.double_cost | information_ratio | -2.8671080554691963 |
| robustness.double_cost | mean_daily_cost | 0.0004963156677848015 |
| robustness.double_cost | mean_daily_turnover | 0.2503188987564304 |
| robustness.delayed_signal | days | 125 |
| robustness.delayed_signal | total_net_return | -0.2290431721206443 |
| robustness.delayed_signal | net_cagr | -0.40809419524127133 |
| robustness.delayed_signal | max_drawdown | -0.2572438805071764 |
| robustness.delayed_signal | annualized_arithmetic_excess | -0.8589518651824812 |
| robustness.delayed_signal | information_ratio | -4.086027377292668 |
| robustness.delayed_signal | mean_daily_cost | 0.0002358613833910551 |
| robustness.delayed_signal | mean_daily_turnover | 0.23894004713357725 |

[Full numerical evidence: volume-weighted-close-location20/discovery](runs/discovery/volume-weighted-close-location20/result.json)

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
