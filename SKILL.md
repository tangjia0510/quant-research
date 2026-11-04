---
name: quant-research
description: "Prepare versioned daily-equity market data and conduct reproducible quantitative research with Qlib: test factors, develop prediction models, alternate factor/model improvements, or reproduce research formulas. Use for market-data preparation, research, historical experiments, backtests and evidence reports; not live order execution or personal portfolio bookkeeping."
metadata:
  version: "1.5.2"
---

# Quantitative research

You are the research agent. Form hypotheses, write candidate implementations, interpret measured results and decide what to test next. The scripts perform computation and preserve evidence; they do not call another language model.

## Start with the research question

Identify the objective, supplied data, intended market, prediction horizon, comparison baseline and resource budget. Infer what is already explicit in the request or workspace. Ask only for missing information that changes the experiment. If the user supplies an existing study, run `status` before doing new work; otherwise inspect `config show`, `dataset list`, `factor list` and `index show` before creating a new one.

Read [Factor discovery](references/factor-discovery.md) when proposing a hypothesis or transferring a published factor. It turns a mechanism into a measurable, falsifiable research plan and uses ILLIQ as an adapted-replication case, not a guaranteed strategy.

Choose the mode and read its section in [Research modes](references/research-modes.md):

- `factor`: hold the prediction model fixed and test additional signals.
- `model`: hold the features fixed and compare model parameters or architectures.
- `joint`: alternate factor and model changes with an explicit parent candidate.
- `report`: extract a source formula, record its location, then implement and test it.

Read [Contracts](references/contracts.md) before creating the protocol or first candidate. The scope is daily-equity research. Different asset classes need their own calendars, labels and execution assumptions; do not quietly reuse equity defaults.

Choose the temporal design by the research question using [Temporal research design](references/temporal-design.md). The installed CLI retains this fixed legacy compatibility preset when no explicit protocol is supplied: **2020–2024 training, 2025 validation, 2026 testing, and 100,000 initial cash (RMB for the intended China-equity studies)**. Internally, 2025 H1 is model validation and H2 is discovery for factor selection. Run `defaults` to inspect the policy; `study new` without `--protocol` resolves these periods against the registered data's actual coverage. The years do not roll forward automatically. Defaults for new studies do not rewrite existing protocols.

## Run the workflow

Resolve this skill's actual directory; never assume an installation path. Use `scripts/quant.py --help` to inspect the installed interface. Python environments, source data and study outputs belong outside this skill directory.

For installation in Codex or Claude Code and a first request using real data, see [Portability](references/portability.md). The [migration map](references/provenance.md) explains which RD-Agent responsibilities moved to the host agent and which are executable scripts.

For lightweight migration and a unified factor/strategy catalogue, read [Portable research projects](references/portable-project.md) and use `scripts/project.py`. Keep code, protocols, small decision/evidence ledgers and conclusions portable; keep raw inputs externally referenced and recomputable bulk outputs under `work/`. This adapter preserves the native study engine rather than changing its directory contract.

Read [Storage and study registry](references/storage.md) when establishing the library, registering data, naming a study or moving to another machine. Use the configured warehouse and study root for new research; keep explicit-workspace `init` for an existing workflow that requires it.

Read [Market-data preparation](references/data-preparation.md) when real inputs are missing or need updating. The first bundled adapter is free, account-free BaoStock; inspect `source list` and `doctor`. `data fetch` defaults to 2019-01-01 through the latest available completed exchange session. Downloading, standardizing, checking and registering real data are one preparation stage. Keep raw batches under `sources_root`, separate from immutable warehouse versions. Other providers can implement the same adapter contract; combine only semantically compatible versions with recorded source priority and conflicts. Never substitute the current constituent list for a historical stock universe.

Read [Factor library](references/factor-library.md) to reuse or publish a factor. Shared implementations belong under configured `factor_root`, default `~/quant-research/factors`, as immutable ID/version packages. Use exact `factor_refs` in candidates; inspect their source, validation and limitations before reuse. Draft new code inside a study and register a version with `factor add` when it is ready to share. Never overwrite a registered version or edit bundled seed assets during research.

Read [Factor validation and admission](references/factor-validation.md) when assessing a factor's empirical value or selecting it for a model. It separates direct factor diagnostics from model-prediction metrics and identifies additional checks that are not implemented by the current CLI.

Read [Factor optimization research loop](references/factor-optimization.md) when improving a factor: diagnose a mechanism, predeclare a finite selection plan, compare controlled variants on development data, then freeze and evaluate without relabeling exposed evidence. Its parallel-candidate guidance distinguishes isolated work from same-study CLI operations that must remain serialized. Read [Batch research](references/batch-research.md) before using the bundled `scripts/batch.py` discovery scheduler; it preserves study locks and does not select or finalize candidates.

For prior RD-Agent/Qlib artifacts, use the historical import workflow in that reference. Preserve original protocols, rejected attempts and reports inside an archive; historical records must not masquerade as newly executed studies.

For adaptive branches, sibling comparisons, pruning or resuming a multi-experiment investigation, read [Agent-driven research trees](references/research-tree.md) and use `scripts/research_tree.py`. You generate each proposal and evidence-based review; the script does not call a model. Start with `status`, reconcile interrupted executions, then propose → run → inspect artifacts → decide within the fixed budget. Preserve failed branches and never equate successful execution with a supported hypothesis. Tree state belongs outside the skill and study; this adapter serializes native discovery commands and never automates final evaluation. Use a fresh study when testing this experimental runtime, preserving older runtime versions for existing frozen evidence.

1. Run `doctor`. If dependencies are missing, use `bootstrap` to create a separate environment under the configured runtime root or another user-selected location. Reuse that environment's Python for every command. Initialize missing library configuration with `config init`; do not replace an existing configuration to change its paths.
2. Reuse a verified dataset version, run `data fetch --source baostock --id ... --version ...` to prepare new real inputs, or register supplied files with `dataset add`. State the source's actual stock coverage and inspect its quality report; a selected small sample verifies the pipeline, not a whole-market result. Use `study new --slug ... --title ... --dataset ... --version ...` for the default plan, or add `--protocol ...` for explicitly supplied splits and assumptions. Inspect the materialized protocol, then use the returned workspace path for `prepare` and all subsequent commands. Inspect the prepared manifest, coverage and limitations before continuing. The bundled demo is synthetic and cannot replace unavailable real data.
3. Set the baseline features and fixed protocol model. The engine evaluates a baseline alongside each candidate. Reuse registered factors through `factor_refs`, or write a workspace-local factor. Write a candidate JSON and use `check --workspace ... --candidate ...`, then `evaluate --workspace ... --candidate ...`. Evaluate only on the discovery segment during research.
4. Propose a specific mechanism or reproduce an explicit source formula. Record the registered factor versions or workspace-local factor/model file in a new candidate JSON. Include the intended lookback and comparison. Repeat check/evaluate within the budget; retain rejected and failed attempts. Correct implementation mistakes using a new candidate ID and, for shared factors, a new factor version so the original remains reviewable.
5. Compare candidates on matched dates and assumptions, using metrics saved by the scripts. Every standalone factor and combined model score must report Pearson IC with ICIR, and RankIC with RankICIR, separately by horizon and evaluation segment. Read the [signal metric contract](references/contracts.md#signal-metrics-and-icir) for sample counts, non-annualized ratios and undefined cases. Numerical results come from artifacts, not from mental arithmetic or a language-model judgement. Record your interpretation separately from the measured facts.
6. Freeze the selected candidate IDs with `freeze --workspace ... --candidates ...` before running `finalize --workspace ...`. Final evaluation uses the frozen inputs. Changing a frozen candidate requires a new study or new protocol; it is not a repair to the old result.
7. Run `report --workspace ...`. Explain the question, data/splits, candidate provenance, baselines, outcomes, rejected attempts and remaining limitations. Link the generated report and its underlying artifacts. Check the library index entry; use `index refresh` to rebuild it after a move or external file changes. An inconclusive or negative result is a valid outcome.

For interruptions, use `status` and rerun the same command. Content hashes determine reuse; an old file's existence alone does not establish a cache hit. Do not delete old evidence to obtain a clean-looking run.

## Research boundaries that matter

- Training preprocessing and early stopping may only see their declared training/validation data. Split isolation is derived from the actual label horizon, not a fixed number copied from another experiment.
- Candidate code receives bars, never labels. Run future-perturbation and output-contract checks. See [Validation and interpretation](references/validation.md) for what these checks prove.
- Preserve data snapshots and report missing/filtered observations. Do not backfill raw prices, use current constituents as historical members, or silently change the universe to improve results.
- Research feedback uses discovery results. Once final results influence another choice, record that data as exposed history. A skill cannot prove that a host with unrestricted file access never read a dataset.
- Preserve the user's finite research budget. Do not continue searching until a positive result appears. Do not invent an API-call count for the host model; the scripts count experiments, not private host usage.
- Check factor units and scale behaviour according to its declared definition. Not all valid factors are dimensionless and not all need a sixty-session window.
- The code worker and static checks are execution aids, not a hostile-code sandbox. Review generated Python before executing it in the host's permitted environment.

## Examples and verification

`assets/make_demo.py --output ...` creates a clearly labelled synthetic dataset and protocol. `assets/example_factor.py`, `assets/tiny_model.py` and `assets/example_report.md` illustrate the supported contracts. Copy examples into a workspace before editing; do not alter this skill during an ordinary study.

`tests/smoke_modes.py` exercises all four modes with actual model training and Qlib backtests. Its synthetic results verify software execution only. Source and adaptation notes are in [Provenance](references/provenance.md).
