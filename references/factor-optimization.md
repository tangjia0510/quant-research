# Factor optimization research loop

Use this guide when improving a factor, not merely checking one implementation. Read [Factor validation and admission](factor-validation.md) for measurement and [Temporal research design](temporal-design.md) for data roles and exposure. The outcome is a justified research decision, including a negative or inconclusive result, not a promise to find a profitable factor.

When the hypothesis itself is not yet defined, start with [Factor discovery](factor-discovery.md); a post-hoc mechanism story must not be relabeled a prespecified reason for optimization.

This is an agent research recipe, not an automated optimizer, new CLI command or protocol schema. Direct-factor diagnostics remain supplementary study-local analysis; native `factor` mode evaluates a trained predictor with additional factors. Keep those evidence streams separate. Do not retrospectively replace an ongoing or frozen study's objective, selection rule or protocol with this guide. Record later changes as new trials where permitted, or a new study when frozen inputs must change, carrying exposed history forward.

## 1. Diagnose and predeclare

Start from the exact current formula, its baseline and saved diagnostic artifacts. Identify a specific failure hypothesis: noisy short-term returns, stale information, volatility exposure, illiquidity, excessive turnover, concentration, weak ordering, unstable periods or redundant predictive content. Do not infer a mechanism from the best backtest alone.

Before new results are inspected, preserve a study-local plan containing:

- Claim and intended use: standalone momentum association, a tradable strategy, or incremental model information; market, universe and point-in-time fields available.
- Primary metric and direction: choose direct IC **or** RankIC, or an explicit model-increment objective, before selection. Retain both IC and RankIC in reporting; do not switch to whichever is positive. Record supporting net performance, coverage, stability and uncertainty criteria without a universal numeric threshold.
- Label horizon, entry timing, costs, development dates/folds and exposure status; the untouched final interval if one actually exists.
- A finite family of candidate mechanisms/parameters and budget, including sign/horizon/conditional variants, repairs and failed attempts. Specify aggregation across folds and the tie-break/selection rule. State the multiplicity treatment, or explicitly designate exploratory screening.
- A stopping rule: budget exhausted, inadequate data/coverage, no convincing improvement, implementation failure, or criteria met and ready to freeze. A request to find an effective factor does not authorize searching until a positive number appears.

Use the existing protocol budget for native studies and a supplementary ledger for diagnostics it does not count. A plan note is not a new supported JSON field. Obtain additional scope/budget if needed rather than silently continuing.

## 2. Change a mechanism, not just the score

Choose a small, justified subset of these possibilities; none is guaranteed to help:

| Candidate mechanism | Hypothesis to test | Control or failure risk |
|---|---|---|
| Change lookback or skip the most recent sessions | Separate a persistent trend from short-lived reversal/noise | More windows are more trials; state exact endpoints and warmup |
| Scale momentum by past volatility or another risk measure | Reduce domination by high-risk stocks | Use only available past estimates; bound/handle near-zero denominators; compare unscaled parent |
| Add a volume or liquidity condition | Trend strength may depend on participation/tradability | Volume is not capitalization-based turnover; conditions change coverage/exposure and need a matched-universe comparison |
| Smooth the signal | Reduce noise and turnover | Smoothing may add lag and weaken timeliness; compare costs and decay |
| Robust normalization or clipping | Reduce outlier sensitivity | Predeclare cross-sectional versus historical transform, fit learned parameters only on permitted history; preserve raw diagnostics |

Industry/size adjustments require real point-in-time exposure fields, not proxy labels or present-day classifications. If unavailable, state not performed; do not call OHLCV-only normalization industry neutralization.

Negating momentum is an inverse/reversal orientation, not discovery of a new independent alpha. Changing sign after viewing results consumes selection freedom and must be recorded. With a symmetric linear Ridge model and consistent preprocessing, negating a feature is a coefficient reparameterization and normally produces equivalent predictions; tiny numerical differences are not independent information. Do not count both orientations as independent confirmations or claim that Ridge's learned negative coefficient proves positive standalone momentum.

Change one material aspect relative to a recorded parent. For a combined recipe, retain component ablations so gains cannot be attributed to the wrong mechanism. Keep model, label, costs and universe unchanged for a factor-only comparison; record unavoidable deviations explicitly.

## 3. Implement and screen on development data

Review generated code, verify its declared lookback and factor contract, then use the existing `check` and `evaluate` workflow described in [SKILL](../SKILL.md) and [contracts](contracts.md). Inspect the installed `scripts/quant.py --help` for arguments. Reuse exact registered versions or workspace-local files; repairs receive new candidate IDs and shared factor versions. Preserve failed checks and rejected trials rather than replacing them.

For native incremental testing, keep `kind: factor`, keep `features` as the intended baseline columns, and add the candidate through `factor_file` or `factor_refs`. The engine removes the extra factor inputs to construct its fixed baseline. Putting the candidate signal into `features` instead can defeat the intended added-factor comparison; inspect recorded baseline feature names and predictions. Hold the model fixed. Native prediction IC and paired baseline increments are not direct factor IC.

For supplementary direct diagnostics:

1. Form the eligible universe and factor ranks/groups using information available at signal time, before observing future-label availability. Preserve those memberships and counts.
2. Attach forward labels and audit missing outcomes, including immature tails, suspensions and delistings. A uniformly immature end-of-sample tail may be excluded by a declared maturity rule; security-specific missing exits are a potential outcome-selection bias, not an innocuous filter.
3. Evaluate available labels without silently re-ranking the remaining securities. If a complete-case regrouping is also shown, label it as conditional on observed outcomes, not an ex-ante portfolio. Report missing-label shares by group/date and unresolved terminal returns. Do not fill missing outcomes with zero or favorable assumptions.
4. Compare parent/candidate on matched dates and securities, while also reporting each one's full coverage and the size/reason for the common-sample restriction. A common sample can itself be selected; it does not cure missing-outcome bias.

Save daily series, group counts/returns, time/horizon summaries, commands and source/data hashes, with separate native and supplementary artifact labels. Overlapping forward returns are diagnostic outcomes, not directly compoundable daily portfolio returns.

## 4. Select on evidence, not a convenient exception

Apply the predeclared primary objective and supporting criteria across all planned development folds, retaining weak periods and failures. Inspect uncertainty using justified HAC or time-block methods for serial dependence. Native HAC intervals concern paired **prediction RankIC increments** and are not multiple-testing-adjusted; they do not establish direct-factor significance. Use a declared correction for the tested family when making a confirmatory claim, or retain exploratory language and require new evidence. A finite budget alone does not eliminate adaptive-search bias.

Check group ordering, concentration, sign consistency and horizon sensitivity. Non-monotonic groups are a warning against a simple “higher momentum means higher return” interpretation; if a nonlinear hypothesis is proposed, record a new trial rather than rewriting the original success criterion. RankIC alone does not prove usable tail portfolios. A result driven by a few dates, reduced coverage, favorable costs or an extreme group needs disclosure, not a post-hoc exclusion.

Do not change metric, direction, horizon, sample, cost assumptions or period after seeing results merely to declare effectiveness. Legitimate revisions are new documented hypotheses tested under the remaining approved budget and exposure constraints. Report whether a result is standalone, model incremental, cost-surviving, conditional, or merely implementation-valid; these are different claims.

## 5. Run multiple candidates in parallel without changing the experiment

Parallelism reduces elapsed time, not the number of hypotheses tested. Fix the candidate batch, global trial/repair budget, comparison rules and selection checkpoint before launch. Wait for every planned candidate to reach an audited terminal outcome, or apply a predeclared timeout/failure rule; do not select the first completed winner, silently drop failed jobs or give slower candidates a different sample. Adaptive next batches need a recorded decision and remaining budget. Parallelism does not weaken multiplicity correction, exposure tracking or final-holdout discipline.

### Current execution boundary

Use the bundled [batch scheduler](batch-research.md) for a fixed discovery-task DAG across isolated studies; it does not choose candidates or implement an autonomous optimizer. Study commands including `check` and `evaluate` hold a study-wide `.study.lock` with zero wait timeout; concurrent calls on the **same study** can fail immediately rather than queue or run together. Do not bypass the CLI lock by calling internal functions/workers directly. Candidate registration/budget counting, protocol/preparation state, event history, run summaries and freeze/finalize decisions require coordinated ownership. Initialization and other registry operations are not covered by a blanket concurrency guarantee.

Use one coordinator to serialize all commands for a shared study. Parallelize only independent, isolated studies or reviewed supplementary diagnostic jobs with separate output paths. Create/configure those workspaces under the coordinator before launching their compute. Separate studies must use the same frozen data, dates/folds, label, universe, model/baseline and costs for a controlled comparison; retain a global candidate ledger and budget so each study's local budget does not multiply the search allowance. Native outputs do not automatically aggregate cross-study comparisons. Do not merge results into another study's run directories or fabricate a completed native candidate. If a selected candidate is evaluated again in the destination study, preserve its earlier exposure and provenance.

The shared library index has its own lock and atomic file publication, but it is not a transaction covering every study. Expect independent refresh contention; let the coordinator inspect reported index errors and refresh after the batch when needed. Do not concurrently mutate a dataset version, factor registry entry or shared configuration while workers consume it.

### Candidate dependency graph and reuse

For each candidate, preserve this dependency order: **registered immutable definition → implementation check → training/evaluation → artifact/coverage audit → terminal result → batch selection**. Different candidates may advance independently only where the isolation above permits. Do not launch a downstream step before its prerequisite succeeds. Design/code review can proceed concurrently without writing shared study state.

Treat prepared data, labels and baseline conditions as read-only reusable inputs only when their identities match: source/prepared-content hashes, calendar and universe/eligibility, price basis, label price/lag/horizon and maturity rules, split/fold boundaries, preprocessing/model configuration, seed/runtime and evaluation sample. A changed horizon or eligibility mask invalidates label/sample reuse. Reusing a fitted baseline additionally requires identical training inputs and numerical/runtime assumptions, not merely the same model name. The native engine computes its own baseline; cross-candidate label/baseline caching is not a new supported feature of this guide. Do not inject supplementary caches into native outputs or use writable shared links to bypass snapshots.

### Resource and failure control

- Measure available CPU, memory limits and per-job peak memory with a representative run before choosing worker count. Leave headroom for data copies, model fitting and the coordinator; reduce concurrency if memory pressure, swapping or worker failures appear. A memory figure observed on one machine is not a portable skill default.
- Budget **outer jobs × inner threads**, including BLAS/OpenMP and model-library threads. The native global `--worker-threads` option defaults to four threads, while the batch scheduler explicitly defaults to one; a parent-shell override alone is not reliably inherited. LightGBM/XGBoost defaults and custom-model threading have separate settings; inspect actual model parameters/runtime. Use the implemented thread option and fewer outer jobs when needed; inspect the [batch resource contract](batch-research.md) rather than assuming reservations are hard OS limits. Supplementary workers can set reviewed inner-thread limits before imports.
- Keep a coordinator-owned ledger with planned, pending, running, successful and failed attempts, timestamps, input hashes, artifact paths, errors and retry reasons. These are descriptive ledger states, **not new native schema values**; native run files use `running`, `complete` and `failed`. Preserve every attempt, including lock-contention and resource failures, while distinguishing orchestration failures from statistical results.
- Give supplementary attempts unique output directories, publish an audited completion manifest atomically, and never treat an existing partial file as success. Atomic replacement of one file is not a multi-file transaction or a substitute for locks. Native evaluation already preserves attempt directories, validates completed artifacts and uses hash-based reuse; its guarantees depend on the normal serialized CLI path.
- After interruption, establish that no worker still owns the task before restarting. Inspect native `status` and logs, then rerun the same supported command for unchanged inputs within its repair budget. Do not delete locks or evidence to force a rerun, reuse a candidate ID for changed code, or start two retries for one task. A changed hypothesis is a new trial, not an idempotent technical retry. Finish by auditing all artifacts and reconciling the ledger before selection or freeze.

## 6. Freeze, evaluate and stop

When the selection rule is satisfied, use the existing `freeze`, `finalize` and `report` workflow for native candidates. Preserve the supplementary plan/code identities before final results are revealed; arbitrary supplementary files are not automatically frozen by the engine. Do not keep optimizing on final feedback under the same holdout claim.

On genuinely unseen data, evaluate the frozen choice and report both support and contradictions. On an already exposed period, including observed 2026 data that informed earlier choices, call the result retrospective robustness; a new study directory does not renew independence. Frozen reruns may establish computational reproduction, not another independent test.

Stop with one of: **promising development candidate awaiting new evidence**, **provisionally supported for the declared scope**, **rejected**, or **inconclusive**. Include the formula/version, parent and change, primary and secondary outcomes, full attempt count, exposure status, costs/coverage, unperformed controls, artifact links and next evidence required. Stop rather than declaring success when data quality or capacity assumptions remain decisive blockers. Continue only for a new justified hypothesis within the authorized budget and with honest disclosure of all accumulated exposure.
