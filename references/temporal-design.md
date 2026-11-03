# Temporal research design

Use this reference before selecting dates, comparing research variants, or interpreting a final evaluation. Choose roles from the research question, data availability and prior exposure, not from the current calendar year alone. This reference changes guidance only: it adds no CLI command, protocol field, native factor-only mode or automatic exposure enforcement.

## Choose roles by research type

| Research type | Development design | Independent evaluation claim |
|---|---|---|
| Prespecified fixed factor, no learned predictor | A development interval with prespecified chronological folds for direct factor diagnostics; disclose all sign, horizon, parameter and universe choices | A later, genuinely unexposed interval after the definition and diagnostic plan are frozen |
| Learned prediction model, including native `factor` mode | Training fits weights/transforms; model validation controls hyperparameters/early stopping; discovery compares hypotheses; final evaluates the frozen selection | New evidence only if the relevant final observations were not previously used to guide that selection |
| Joint factor/model search | The same four roles, with a recorded parent and controlled changes | Preserve the same selection/exposure boundary; changing both components does not create another holdout |

A fixed formula needs no model-training segment merely to compute direct IC. If thresholds, normalizers or other components are learned, declare the historical fitting window and fit only on permitted past data. Choosing the best development fold, sign or horizon is selection; development-fold results are not untouched final evidence.

The current native engine always trains a predictor, including `factor` mode. Pure factor diagnostics remain supplementary study-local analysis. Do not remove `train`/`valid` from a native protocol or claim that this table implements a new runtime mode.

## Keep the installed preset compatible

The installed policy `calendar-2020-2026-v1` retains 2020–2024 train, 2025 H1 model validation, 2025 H2 discovery and the available 2026 observations for final evaluation. Call it a legacy compatibility preset, not a universal best split. Its dates do not advance with today's date. Its policy ID, default resolution and missing-coverage errors remain unchanged.

For a different supported design, use an explicit protocol with the existing ordered `splits` and optional `folds`; inspect actual coverage before preparation. Do not rewrite an existing study's frozen protocol. No user-facing preset selector, automatic date planner, or alternative default is introduced by this reference.

## Prespecify temporal folds

- Split by whole trading date, keeping each date's security cross-section together. Do not randomly split stock-day rows and call it temporal validation.
- For model research, each fold has ordered, disjoint train, valid and evaluation intervals. Fit imputation/scaling, learned exposure transforms and model weights only on permitted historical training data; validation may control the declared fitting choices, never future evaluation data.
- Purge boundary-crossing labels using each sample's actual label end on the shared trading calendar, including entry lag and holding horizon. Do not substitute a fixed calendar-day gap. The native engine already purges training/validation at their boundaries and excludes evaluation labels maturing after the evaluation end; supplementary diagnostics must apply equivalent maturity checks.
- The existing native `folds` accepts phase-specific train/valid/evaluation date pairs. Evaluation windows must stay inside the parent discovery/final range, be non-overlapping, and produce continuous evaluation-calendar coverage. Each fold fits its own preprocessing and model. Supplementary non-contiguous diagnostic windows must not be presented as supported native evaluation folds.
- Development folds used for selecting features, models or settings belong to research feedback, even when each prediction is locally out of training sample. A final rolling evaluation can retrain on earlier observations according to a frozen schedule; report those information sets and distinguish predeclared updating from outcome-driven method changes.
- Predeclare fold dates, aggregation/weighting, exclusions, selection rule and stopping budget. Preserve weak folds and failed variants. More folds do not correct adaptive-search or multiple-testing bias.

## Record exposure, not a one-run rule

Use a study-local research note/ledger with date ranges, universe, source of exposure, what was inspected, when, whether it influenced a choice, and the relevant frozen artifact identities. This is a documentation convention, not new protocol JSON. Carry earlier reports and cross-workspace exposure forward.

| Evidence state | Interpretation |
|---|---|
| Unseen before selection was frozen | Potential new holdout evidence, subject to provenance and other validity checks |
| Seen only while rerunning/reproducing the same frozen selection | Reproduction of the original evaluation; no new independent confirmation from another execution |
| Seen and used to choose a sign, horizon, candidate, universe, model or reporting rule | Exposed research history; later results for those observations are retrospective, even in a new workspace |
| Prior exposure or its influence is uncertain | Do not label the period an untouched holdout; disclose uncertainty |

A frozen final calculation may be rerun for recovery or reproducibility. Looking twice is not itself a statistical violation; using the result to change the next selection and then claiming independence is. Existing `final_exposed` records that native final evaluation was initiated; it does not distinguish these states or discover external exposure. Preserve it and supplement it with the note rather than pretending the Boolean proves an untouched test.

For any study whose 2026 results already informed research decisions, record the relevant 2026 observations as exposed. Do not infer that every future 2026 observation is already known, or that changing the study directory resets exposure. If no genuinely new interval is available, report retrospective robustness and defer independent confirmation rather than manufacture a holdout.

## Implementation boundary

These decisions, supplementary fixed-factor plans, explicit supported protocols and exposure notes can be adopted through documentation after approval. A native factor-only evaluation path, automatic role/date planning, cross-study exposure registry, or machine-enforced multi-state exposure classification would require separately approved code/schema changes and tests. None is implemented by this reference. Existing studies and currently running experiments remain unchanged.
