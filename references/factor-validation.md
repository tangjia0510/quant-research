# Factor validation and admission

Use this reference when assessing a factor's empirical value, selecting factors for a model, or reviewing a factor research report. It complements [implementation validation](validation.md) and [factor research mode](research-modes.md); a valid implementation is not evidence of a useful signal.

For a controlled sequence of improvements based on these diagnostics, use [Factor optimization research loop](factor-optimization.md).

For proposing the original claim or adapting a literature formula, use [Factor discovery](factor-discovery.md), then return here to distinguish implementation, association and investment evidence.

The intended starting point is daily China-equity research. Declare the actual market, calendar, security universe, currency and execution rules. Do not transfer A-share assumptions to another market without revising them.

## What is executable today

This checklist distinguishes implemented diagnostics from additional research; it does not add protocol keys. The current engine fits a model to baseline features plus candidate factors, evaluates **model prediction** IC/RankIC, and compares the model with a fixed baseline. It saves daily prediction IC/RankIC, their separate non-annualized ICIR/RankICIR, raw single-factor metrics for every feature column, RankIC positive fraction, paired RankIC increments with a HAC interval, portfolio costs/turnover, and optional double-cost and one-session-old-signal backtests. Configured folds support rolling evaluation windows.

Quantile portfolios, multi-horizon decay curves, industry/size neutralization and multiple-testing correction are **additional diagnostics**, not existing automatic outputs. They need separately reviewed study-local analysis and appropriate data. Label any such script and output as supplementary; do not attribute a one-off diagnostic to the bundled engine. Do not add unsupported keys to the protocol or invent CLI commands. Inspect [contracts](contracts.md) and the installed CLI before execution.

## 1. Specify the claim before measuring it

Record the factor definition/version, economic or statistical hypothesis, expected sign, lookback, information timestamp, target horizon, comparison baseline and intended use. A negative IC can support a prespecified inverse signal; choosing its sign after inspecting results is another research choice, not independent confirmation. Set a finite candidate/variant budget and decision criteria before comparing results; there is no universal IC or ICIR admission threshold.

Check these inputs before performance:

- **Point-in-time availability:** distinguish observation date, publication date, revisions and the earliest usable trading session. Factor code must not receive labels or future information. Prefix/future-perturbation checks can falsify leakage but cannot prove arbitrary code safe.
- **Universe:** preserve historical membership and listing/delisting intervals. Report selected-stock versus whole-market coverage, exclusions and liquidity filters. A present-day constituent list or surviving-stock sample cannot establish historical investability.
- **Missingness:** report daily eligible count, factor/label availability, warmup and exclusions separately. Do not replace missing raw prices with fabricated observations. For direct diagnostics, state whether unavailable factors are excluded; the engine's train-median feature imputation is a different estimand. Compare candidates on matched observations and disclose coverage differences.
- **Corporate actions and units:** reconcile adjusted/raw prices, adjustment factors, volume units, splits and dividends with the return definition. A price-return label is not automatically a total shareholder return.
- **Terminal observations:** inspect delistings, suspensions and unavailable exits. A missing terminal price must not silently become a zero return or a harmless dropped loser. If terminal returns or liquidation assumptions are unavailable, report the affected securities/dates and resulting survivorship or outcome-selection uncertainty. Do not claim it was resolved by structural data validation.

## 2. Separate factor diagnostics from model diagnostics

For each date, direct factor IC correlates the **factor value** with the declared future return across eligible securities. Pearson IC measures linear association; RankIC uses Spearman ranks. Record the actual sample count, tie handling, minimum cross-section and dates rejected for constant values or insufficient observations. Preserve the daily series, not just its mean.

The bundled engine also correlates **trained model predictions** with raw forward returns, even in `factor` mode or when rank-transformed labels are used for training. A model can invert or combine a factor; its prediction IC is not the factor's standalone IC. Name the two series distinctly and never substitute one for the other.

For every direct-factor or prediction series, report mean Pearson IC with ICIR and mean RankIC with RankICIR, each with its own sample dispersion and valid-date count. Follow the [signal metric contract](contracts.md#signal-metrics-and-icir): ddof=1, signed, non-annualized ratios, sampling frequency, label horizon, missingness and undefined reasons. Undefined/zero-dispersion cases are not infinite evidence. State any annualization separately; multiplying by the square root of trading days assumes dependence properties that overlapping labels commonly violate. The engine's portfolio `information_ratio` is a return-based excess-performance measure, **not ICIR**.

Assess uncertainty over dates, not by treating every stock-day as independent. Overlapping forward returns and persistent signals induce serial dependence: use a justified HAC lag or time-block resampling and disclose the choice. The existing HAC interval concerns the **paired model RankIC increment**, not direct factor ICIR. Its nominal 95% interval is exploratory and is not corrected for adaptive search or multiple trials. Preserve the tested family, failed variants and sign/horizon choices; use a declared multiplicity procedure or explicitly label the evidence exploratory. Neither a trial budget nor a nominal interval removes selection bias.

## 3. Check ordering, horizon and stability

- **Quantile ordering:** choose bins and ranking direction before evaluation; handle ties and small cross-sections explicitly. Show group counts and mean forward returns, top-minus-bottom spread and whether ordering is persistent or driven by a single extreme group. Monotonicity is evidence to inspect, not a rule that every valid nonlinear signal must satisfy.
- **Return accounting:** daily overlapping five-session forward returns cannot be compounded as daily tradable returns. Label group-return tables as predictive diagnostics. For an investable equity curve, specify staggered holdings or non-overlapping rebalances, capital allocation, entry/exit timing and costs. A theoretical long-short spread is not proof that short positions are available or affordable.
- **Decay and multiple horizons:** predeclare a small set of label horizons and signal ages. Distinguish changing the holding horizon from aging a signal and from delaying an order. Recompute labels, maturity exclusions and matched samples for each horizon; show observation counts as well as IC/spread. Do not select the best horizon and call it an untouched result.
- **Time robustness:** inspect prespecified yearly/subperiod or rolling summaries and relevant market regimes, including weak periods; disclose small samples. Configured rolling folds are available, but automatic multi-horizon analysis is not. Keep training, validation and evaluation boundaries intact for every fold and label horizon.

The native `delayed_signal` backtest uses signals one additional session old on the same rebalance calendar. Its first scheduled rebalance may lack an aged signal and remain in cash. Inspect order dates and exposure; the performance difference is not a pure decay estimate. It does not replace a decay curve.

## 4. Identify exposures and incremental value

Compare raw factor diagnostics with industry/size-controlled diagnostics only when historical, as-of-available classifications and market capitalization are available. State industry taxonomy, size definition (for example, log market capitalization), exposure timestamp, regression/within-group method, weighting, outlier treatment and eligible sample. Report coverage and both raw and adjusted results. Current classifications, future capitalization or silent substitutions are not valid historical controls. With missing historical exposure data, mark **not performed: required point-in-time data unavailable**, not neutralized or passed.

Distinguish three questions: standalone factor association; association conditional on chosen risk/style exposures; and incremental value when added to an existing predictor. Check redundancy with baseline signals and use matched dates, universe, model, training procedure and costs for an ablation. Correlation screening alone does not prove an independent contribution. The bundled baseline comparison answers the third question for the declared model; it does not automatically control industry/size or establish causality. A joint factor/model change cannot be attributed entirely to the factor.

## 5. Test whether the signal survives implementation

Report gross versus net results, actual turnover convention, fees, trade units, rebalance frequency and initial exposure. Match the intended execution price and signal availability. Stress plausible cost assumptions and inspect concentration, liquidity and tradability rather than reporting only annualized returns.

The daily Qlib simulator applies configured costs and trading assumptions; the engine also reports average daily cost/turnover and can double configured fees. These do not constitute a calibrated slippage, market-impact or capacity model. A capacity claim needs suitable liquidity data, participation and order-size assumptions, fill constraints and an impact model with sensitivity analysis. Without them, mark capacity/slippage **unassessed**. Board-specific limits, suspensions, short-sale access and delisting liquidation also need market- and date-appropriate treatment. Do not certify real fills from daily bars.

## 6. Preserve an honest holdout

Choose model-based or supplementary fixed-factor time roles using [Temporal research design](temporal-design.md). Development folds used for selection are not independent final evidence; rerunning frozen final computations is allowed but does not renew the holdout.

Use the protocol's training and validation segments for their declared roles and discovery for research feedback. Fit learned transforms only on permitted data; purge labels that mature across split boundaries. Freeze selected candidates, code, data and assumptions before final evaluation using the existing workflow. Include supplementary analysis definitions in the research record before revealing their final results; the engine does not automatically freeze arbitrary supplementary files.

Keep prior tests, rejected attempts and exposed periods visible across workspaces. Once a final-period diagnostic influences a sign, horizon, universe, threshold or factor choice, that interval is exposed research history, not a fresh holdout for the next selection. A new directory, immutable hash or rerun cannot restore independence. The skill's freeze checks do not prove that an unrestricted host never inspected held-out data. If no untouched data remains, conclude retrospective evidence and state what new evidence would be needed.

## 7. Record the decision and reproducible evidence

Keep supplementary files inside the study, outside the installed skill and separate from engine-generated artifacts. File names and formats below are a reporting convention, **not required CLI artifacts or new schema fields**. Preserve:

- A diagnostic plan with hypotheses, sign, horizons/ages, universe, costs, tested family and prespecified decision criteria.
- Data/version identities, factor and analysis source hashes, commands, environment, seeds, exposure-data provenance and the observation/exclusion audit.
- Daily factor IC/RankIC with counts, group-return tables, horizon/time summaries and raw versus controlled results where performed; separately link native prediction IC, baseline increments, orders and portfolio paths.
- A complete attempt ledger and an admission record identifying the evidence available at selection, frozen candidate, exposure status, measured results, missing checks and decision rationale. Do not overwrite engine metrics or past failed results.

Use a compact conclusion such as:

> **Claim and scope:** [factor/version, market/universe, dates, sign/horizon, direct factor or model-prediction evidence]. **Measured evidence:** [IC/RankIC stability and uncertainty, group ordering, horizon/time robustness, baseline increment and net costs, with artifact links]. **Unperformed or unresolved:** [historical exposures, terminal returns, multiplicity, fills/capacity, and why]. **Holdout status:** [discovery, genuinely untouched frozen final, exposed retrospective, or synthetic]. **Decision:** [retain for further research, admit provisionally for the declared use, reject, or inconclusive], against [prespecified criteria]; [next evidence needed].

Factor-library registration/implementation validation and empirical admission are separate decisions. An implementation may be valid while investment value is negative, inconclusive or untested. Do not convert a diagnostic checklist into a universal pass score or an investment recommendation.
