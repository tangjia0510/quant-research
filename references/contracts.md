# Input and artifact contracts

Inspect `scripts/quant.py --help` for the installed command interface. All paths supplied to the shell must be quoted; use JSON files for structured input rather than shell-evaluated expressions.

## Default research plan

This installed default is a **legacy compatibility preset**, not a universal research design. Choose dates and roles deliberately using [Temporal research design](temporal-design.md); pass an explicit protocol for a different supported design. This guidance does not change the default policy ID, CLI behavior or existing studies.

Data preparation defaults independently to **2019-01-01 through the latest available completed exchange session**, with 2019 used for feature warmup. Use the [source preparation workflow](data-preparation.md); downloading additional dates does not roll the research split years forward.

`defaults` reports the installed policy without creating a study. A managed `study new` call that omits `--protocol` uses these fixed periods:

| Period | Internal split | Role |
|---|---|---|
| 2020–2024 | `train` | Fit the model and preprocessing |
| January–June 2025 | `valid` | Model validation and, where applicable, early stopping |
| July–December 2025 | `discovery` | Compare factors and freeze the research selection |
| 2026 | `final` | Evaluate the frozen selection |

The two 2025 segments together implement the validation year. This is a fixed split, not annual rolling retraining; the years do not advance with the wall clock. Date endpoints are selected from the registered source's available trading dates within each period. In particular, the 2026 end is the available source end, not an assumed December 31. Missing required periods are an input error; do not silently shift the study to another era. `prepare` still verifies usable market-data coverage and records limitations.

Initial cash defaults to **100,000** in the simulation's currency, intended as RMB for China-equity research. The account starts with cash and no stock holdings. Other portfolio defaults are 10 target holdings, 95% stock exposure, equal target weights, five-session rebalancing, 100-share trade units, buy cost `0.0005`, sell cost `0.0015`, and zero minimum fee. The default model is Ridge with `alpha=1.0`; the label remains next-open entry and a five-session horizon. These are declared research assumptions, not certified brokerage charges or fills.

Supplying `--protocol FILE` preserves that protocol's explicit dates and values; omitted portfolio fields receive their documented defaults. The explicit-workspace `init` command still requires a protocol. Existing studies retain their frozen dates, cash and other settings when the skill is upgraded. Inspect the generated `protocol.json` before preparation, and use a new explicit protocol when the user requests different settings.

## Protocol

A protocol JSON records these fields before research starts:

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `mode` | `factor`, `model`, `joint`, or `report` |
| `objective` | The question and comparison being tested |
| `data.path` | Source CSV/Parquet file or Qlib provider directory for explicit-workspace studies |
| `data.dataset_id`, `data.dataset_version`, `data.manifest_hash` | Immutable registered source identity for managed studies; populated by `study new` |
| `data.format` | `csv`, `parquet`, or `qlib` |
| `data.region` | Qlib region, initially `cn` |
| `splits` | Ordered `train`, `valid`, `discovery`, `final` inclusive date pairs |
| `label` | `price`, `entry_lag`, `horizon` measured in trading sessions |
| `model` | `kind` and `params` for the default model |
| `preprocessing` | Optional `clip` and `label_transform` |
| `portfolio` | `top_k`, `rebalance`, `initial_cash`, `position`, `buy_cost`, `sell_cost`, `min_cost`, `trade_unit` |
| `budget` | `max_trials`, `max_repairs`, `timeout_seconds` |
| `seed` | Reproducibility seed |

State `data.price_basis` (`raw`, `adjusted`, or `unspecified`), `data.volume_unit` (`shares` or `units`), data limitations and whether the source is synthetic in `data`. Examples are preset choices, not universal market defaults. The label is future price at `entry_lag + horizon` divided by price at `entry_lag`, minus one. A five-session horizon with next-open entry therefore requires six future sessions for label maturity.

For configured warehouse roots, dataset registration, study naming and the global index, read [Storage and study registry](storage.md). Managed studies resolve their source identity through that configuration; they do not store a replacement absolute `data.path` in the frozen protocol.

Use observed trading-calendar dates and sufficient warmup; do not invent arbitrary date cutoffs or use the future end of a supplied calendar as proof that prices exist. Every segment must have enough observations after purging. The generated synthetic protocol is executable but is not a template for selecting live-market research dates.

For fixed splits, training and validation samples remain identical across discovery and final evaluation: validation purging uses the earliest declared evaluation start after validation; each rolling fold instead uses its own predeclared boundaries.

Optional `folds` provides rolling windows. Each fold supplies `train`, `valid`, and the evaluation phase (`discovery` or `final`) date pairs, directly or under `splits`. Evaluation windows must be disjoint and stay within the corresponding overall phase date range: both the lower and upper bounds are checked. Each fold separately fits preprocessing and model weights. Include both phase definitions when using the same protocol for discovery and finalization.

## Preprocessing and learning targets

Features use training-only median/IQR scaling. `preprocessing.clip` is a positive finite absolute clipping bound, default `10`; transformed missing feature values are filled with zero (the training median). The engine rejects a feature with no finite training observations.

`preprocessing.label_transform` is either `raw` (default) or `cross_sectional_rank`. The rank transform uses each date's eligible securities and computes `(percentile_rank - 0.5) * 3.46`, matching Qlib CSRankNorm semantics. It changes learning/validation targets only. Prediction evaluation retains the original forward-return labels. Record the transform before comparing candidates; an error metric on transformed labels cannot be directly compared with an error metric on raw returns.

## Bars and universe

CSV/Parquet input uses `datetime`, `instrument`, `open`, `high`, `low`, `close`, `volume`; `factor` is optional. Prepared data has a sorted, unique `(datetime, instrument)` index. Price fields must share an explicitly described adjustment basis; volume must use a stated unit.

Optional `data.calendar` names a newline-separated ISO trading-date file. Qlib providers retain their own trading calendar; CSV/Parquet without one infer dates from observed rows and cannot detect a whole-market missing session. An optional `data.universe` CSV contains `instrument,start,end` membership intervals. Membership affects eligibility while past price rows can still provide lookback history. A static list is not a historical index-membership claim. Missing prices, newly listed securities and delistings remain data-quality concerns.

`prepare` snapshots inputs into the workspace and writes a data manifest. A generated Qlib provider supports the daily simulator. The current implementation provides `QRBENCH`, a synthetic equal-weight close-price reference constructed from available bars, with no transaction costs and cash on dates without a valid basket. Identify it as synthetic in reports; an external official-index benchmark input is not implemented.

## Candidates

Candidate JSON contains:

- `id`: a stable filename-safe identifier; use letters, numbers, hyphens or underscores.
- `kind`: `factor`, `model`, `joint`, or `report`.
- `hypothesis`: the mechanism, intended comparison and what changes from the baseline.
- `features`: built-in baseline columns: `return_5`, `volatility_20`, `momentum_20`, `range_position_20`, `volume_ratio_5`.
- `factor_refs`: optional list of exact registry references, for example `[{"id":"deltab5","version":"1.0.0"}]`; see [Factor library](factor-library.md).
- `factor_file`: workspace-relative factor implementation. Factor, joint and report modes require this field or a nonempty `factor_refs` list; both may be supplied when their output columns differ.
- `factor_params`: parameters passed to the factor function.
- `max_lookback`: price observations needed by the generated function, including observations needed to form returns.
- `scale_invariant`: optional boolean; set `true` only when the factor's mathematical definition is invariant to uniform price scaling. This enables the corresponding check, not a requirement that all factors be scale invariant.
- `model`: override of the protocol model, required in model and joint modes. Custom models additionally require `file`.
- `source`: for report mode, `{path, locator, formula}`; `path` is workspace-relative and points to the preserved source.

All candidate files must stay under the workspace. Registered factors are resolved through the selected library configuration and copied into the candidate snapshot with their definitions, provenance and manifest hashes. The registered definition supplies each factor's lookback and scale contract; the candidate-level fields describe only `factor_file`. Evaluated candidate identities are frozen so reusing an ID with different content cannot overwrite an earlier result. A new research idea or code repair gets a new ID and, when shared, a new registered factor version.

### Factor implementation

Expose `compute(frame, params)`. The input is a DataFrame indexed by `(datetime, instrument)` with bar fields and no labels. Return one Series or a DataFrame of numeric factor columns with exactly the supplied index. Preserve warmup rows as missing values. Do not filter by hardcoded calendar dates or read hidden input files.

Built-in feature names, registered-factor columns and generated column names must not collide. Declare scale invariance only when the mathematics supports it. Factor code runs in a separate Python worker with limited environment and timeout, but neither this subprocess nor AST lint is a hostile-code sandbox.

### Model implementation

Presets are `ridge`, `lightgbm`, and `xgboost`. For a custom PyTorch network, set `model.kind` to `custom` and `model.file` to a workspace-relative Python module. Define `build_model(num_features)` returning `torch.nn.Module`. Forward input shape is `(rows, features)`; output is `(rows,)` or `(rows, 1)`. The engine owns loss, optimization, early stopping and serialization.

Common custom training parameters include `epochs`, `patience`, `batch_size`, `lr`, and `seed`. Keep the example network small when verifying installation. More complex research architectures need their own meaningful checks and compute budget.

## Command results

The CLI writes JSON to stdout with `{ok, command, result}` on success and `{ok: false, error: {type, message}}` on failure. Operational logs can go to stderr. Inspect `ok` and the process exit code; the presence of an old artifact is not evidence of a successful new run.

Managed study commands also return `library_index` refresh information. An index error does not replace the experiment's own success or failure: inspect both and repair the index with the correct configuration before presenting the library as current.

The workspace keeps the protocol, source manifest, candidate snapshots, discovery runs, frozen selection and final runs. Model files, predictions, portfolio paths and metrics are evidence. Never edit generated metrics to match a narrative. An independent report or interpretation can cite those artifacts without changing them.
