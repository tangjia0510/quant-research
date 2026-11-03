# Validation and interpretation

## Before performance

Validate unique `(datetime, instrument)` rows, ordered dates, price ranges, nonnegative volume, source fields and split boundaries. Price adjustment and historical membership need provenance beyond a structurally valid table. A third-party provider's hash proves file identity, not correctness of its historical data.

Factor checks verify the output index, numerical values, declared warmup, prefix consistency and invariance of past outputs when future data changes. These are useful falsification tests, not a proof that arbitrary code cannot leak information. Optional scale tests apply only when the candidate promises scale invariance. A factor with physical units must not fail a generic dimensionless-factor rule.

Registered factors have immutable definitions and append-only validation receipts, described in [Factor library](factor-library.md). `factor validate` tests the current code on a deterministic synthetic panel; candidate `check` exercises it on the study's supplied data. Keep current implementation checks distinct from historical evidence and empirical results. A `passed_with_limitations` status retains the stated limits, and rejected entries remain unavailable for candidate execution. In particular, the historical `R2_expand_on_volume` scale sensitivity is retained, and the TREND group's frozen-window rejection is not erased by adapting other factors.

All label offsets are on the shared trading calendar. The training and validation samples whose label end reaches the next segment are excluded. Calendar entry lag and holding horizon are distinct. Preprocessing fits the training segment; validation controls early stopping; discovery supplies research feedback. The optional `preprocessing.clip` controls the absolute normalized-feature bound. `preprocessing.label_transform` is `raw` or `cross_sectional_rank`; transformed targets are used only for learning, while IC and portfolio evaluation retain raw forward returns.

## Interpret three outcomes separately

1. **Execution:** Was the candidate implemented and run, with valid contracts?
2. **Empirical comparison:** What changed on the declared data and costs?
3. **Research validity:** Is this new holdout evidence, historical re-analysis or a synthetic demonstration? What data and execution assumptions remain unresolved?

A pass in one category does not imply a pass in the others. Do not call an unexecuted candidate zero-return. Do not treat an insignificant or unstable increment as proven value. An annualized figure from a short sample is a mathematical transformation, not a forecast.

The daily-bar simulator cannot establish auction availability, order-book queue priority, actual tax treatment for every historical date, market impact or investment capacity. Record costs and trade units actually used. QRBENCH, when generated from supplied bars, is an explicitly synthetic equal-weight price reference; it is not an official market index or a tradable strategy.

The default robustness paths double the configured fees and, separately, use signals one additional trading session old on the same rebalancing calendar (`delayed_signal`). The latter tests stale information, not orders postponed by one day. No predictions before the evaluation segment are supplied: its first scheduled rebalance can have no aged signal and therefore remain in cash until the next scheduled rebalance. Inspect order dates and initial exposure when interpreting that comparison; do not attribute the entire difference to signal decay.

## Final exposure and reproducibility

Freeze code, protocol and dataset identity before final evaluation. Follow [Temporal research design](temporal-design.md) to record whether an evaluation period was unseen, seen only for frozen reproduction, or used to influence research. Final evaluation is not limited to one execution: a faithful frozen rerun can check reproducibility but cannot create new independent evidence. If final results influence another decision, subsequent results on that interval are retrospective research. Existing local reports may already have exposed a period even if this workspace is new. Hashes and directory separation do not create a security boundary against the host agent.

Exact byte-level model equivalence across different hardware is not guaranteed. Record environment versions and seeds, use numerical tolerances for predictions and metrics, and distinguish computational reproduction of frozen code from stochastic generation of new ideas.

For maintenance, run unit tests for data/labels/model persistence and the four-mode smoke test. Test rejected future-dependent factors, invalid data, frozen-code changes, repeated commands and interrupted/resumed work. Preserve evidence of failures while correcting the implementation.
