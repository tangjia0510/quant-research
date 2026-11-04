# Agent-driven experiment trees (no model API)

This experimental adapter adds a persistent **experiment-version tree** above the existing discovery engine. The host agent (Dots, Codex or another tool-using agent) supplies questions, parameters, code and reviews. Python preserves state and runs `batch.py` → native `prepare/check/evaluate`. It never calls a language model, generates an alpha claim, selects a winner, freezes a native study or runs final evaluation.

## First test in Dots

Use a separate checkout of branch `feat/agent-research-tree` and a fresh study. Do not replace the runtime of an existing frozen study: native evidence fingerprints include all Python source files. Keep the original runtime for historical reproduction.

Read this document, `scripts/research_tree.py --help`, and the existing contracts. Use a Python 3.11 environment with this repository's dependencies. The tree bookkeeping needs only the standard library plus `filelock`; actual experiments need the normal research environment. No model API key is required.

Run the engineering smoke before using real data:

```sh
"$QR_PYTHON" tests/smoke_research_tree.py --output /absolute/fresh-tree-smoke
```

It creates explicitly synthetic inputs, runs a root and two sibling experiments through real Qlib, verifies exact-computation dedup and resume, and records a review/prune. These are software checks, not strategy findings. The output must be fresh and outside the repository. The script prints a JSON verification result; logs and state remain in the output directory.

## Initialize a real research tree

First initialize a normal native study using `quant.py init` or `study new`. Data access, protocol design and candidates still use the existing contracts. Prefer a fresh study; one tree owns one native workspace. An existing tree cannot be reset to renew its trial allowance.

Create a specification JSON (replace example paths and budgets):

```json
{
  "schema_version": 1,
  "workspace": "/research/studies/volume-breakout",
  "objective": "Does volume filtering add information to the declared baseline?",
  "evaluation_rule": "Compare discovery IC/ICIR and RankIC/RankICIR, incremental evidence, cost-adjusted outcomes and coverage under the fixed protocol; no final feedback.",
  "max_nodes": 6,
  "max_debug_depth": 2,
  "execution": {
    "worker_threads": 1,
    "max_attempts": 2,
    "timeout_seconds": 1800,
    "memory_budget_mb": 4096,
    "worker_memory_mb": 2048,
    "prepare_memory_mb": 4096
  }
}
```

Resource numbers are examples; inspect the host and dataset first. `max_nodes` must fit the native study's remaining candidate budget. A `debug` code revision is a new node and a new native trial. Unchanged technical retries use `run --resume` and the persisted batch/native repair limits. `max_debug_depth` bounds consecutive debug edges, exactly: depth 0 → 1 → 2 is allowed when the limit is 2; a third debug child is rejected. A successfully repaired node may be reviewed and extended with a normal improvement, which resets consecutive debug depth.

Optional `execution.config` is the absolute managed-library configuration file, forwarded to native commands and bound by hash. The normal configured factor registry is reused. The tree directory must be disjoint from both the study and repository directories.

```sh
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout init --spec /research/tree-spec.json
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout status
```

## Propose, execute, review

Write a normal candidate JSON inside the study and review its Python implementation before executing. Then write a proposal with exactly these fields:

```json
{
  "id": "volume-baseline",
  "parent": null,
  "action": "draft",
  "question": "Does the baseline show a measurable development effect?",
  "change": "Establish the declared baseline candidate",
  "expected_evidence": "Direct factor and model metrics, cost-adjusted portfolio evidence and coverage",
  "decision_rule": "Apply the prespecified study criteria; an inconclusive result is allowed",
  "candidate": "/research/studies/volume-breakout/baseline.json"
}
```

`id` must equal the native candidate ID. `draft` has a null parent. `improve`, `tune` and `ablate` require a complete parent reviewed as `expand`. `debug` requires a failed parent and consumes depth/budget. `question`, `change`, `expected_evidence` and `decision_rule` are required agent-written text; the program checks presence, not scientific correctness.

```sh
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout propose --proposal /research/proposal.json
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout run --node volume-baseline
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout show --node volume-baseline
```

Proposal registration freezes the candidate and local code using the existing native registry. Subsequent edits to the original draft do not change the registered node. A snapshot input JSON under `study/tree-inputs/` feeds the ordinary CLI; do not edit it. Proposal registration and the tree ledger are separate atomic writes: if interrupted between them, repeat the same proposal/ID to reconcile; never delete the registered candidate or reset budgets.

Exact-computation dedup excludes candidate ID/hypothesis text and substitutes content hashes for local code/source paths. Renaming the same code or changing prose does not evade it. It is per-tree, not a proof of mathematical equivalence: differently written equivalent formulas, feature aliases, or external historical experiments require agent review. Factor registry references retain exact IDs/versions/parameters; registry integrity is also checked by native registration.

After execution, read the actual artifacts from `show` and write a review:

```json
{
  "decision": "expand",
  "outcome": "inconclusive",
  "reason": "Explain measured evidence, alternative explanations and remaining uncertainty here",
  "evidence": ["/research/studies/volume-breakout/runs/discovery/volume-baseline/result.json"],
  "next_step": "Propose a matched sibling comparison removing the volume condition"
}
```

```sh
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout decide --node volume-baseline --review /research/review.json
```

Decisions are `expand`, `freeze` (temporarily stop a branch), or `prune` (stop investing in it). Outcomes are `supported`, `refuted`, `inconclusive`, or `invalid`, scoped to the declared question. Failed or unexecuted experiments can only have `invalid` outcomes; they do not refute a scientific hypothesis. Both unsupported and supported *valid* evidence may justify a different child experiment. `expand` requires successful execution and valid evidence, not a positive return.

Evidence paths must belong to that node's discovery, native candidate/check, or batch execution artifacts. Final-period paths are rejected. Completed native artifacts and recorded metrics are verified before review. The agent's interpretation remains separate from machine-produced numbers. The program cannot enforce semantic honesty or stop an unrestricted host from reading other files; never treat a new tree as fresh holdout independence.

## Agent loop and branch control

1. Read `status`; reconcile `recover_first` before doing other execution/reviews.
2. Review completed nodes in `review_next` using evidence, including negative results.
3. Choose a parent based on uncertainty and useful next evidence. Explain why this experiment is worth its cost. Do not simply maximize in-sample return.
4. Propose a new candidate, run it, inspect its results, and record a decision. Create siblings by using the same parent; return to an older reviewed parent if a later improvement fails.
5. Repeat while authorized budget and useful experiments remain. Stop with an explicit conclusion or blocker, saving the exact next action. Do not promise work will continue after the host session ends.

Pruning/freezing a node blocks execution and new proposals anywhere below it; existing descendants and all evidence stay visible. Reopening requires an explicit reason and is recorded as an event:

```sh
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout reopen --node volume-baseline --reason "New evidence warrants revisiting this branch"
```

Reopening sets its review status to pending. Review a complete parent again before expanding it. A reopened descendant remains blocked if an ancestor is still frozen/pruned. Neither reopening nor pause/resume returns spent budget.

## Pause, recovery and execution boundaries

```sh
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout pause --reason "Waiting for data"
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout resume --reason "Data is now available"
"$QR_PYTHON" scripts/research_tree.py --tree /research/trees/volume-breakout run --node volume-baseline --resume
```

Tree resume only re-enables work; it does not start a model or an experiment. `run --resume` resumes the node's original batch plan, verifies successful work and skips it without another attempt. The tree can reconcile a process death after the batch completed but before the tree result was saved. Native batch rules reject still-live prior process groups, changed inputs/runtime and tampered artifacts. Do not delete locks or evidence. A code change requires a new candidate/debug node, never an unchanged-input retry.

One tree mutation/run holds `.tree.lock`; study mutations also use the original `.study.lock`. `status` and `show` are atomic-state reads and remain available during a run. This version serializes experiments in one study; it does not introduce unsafe same-study parallelism. `pause` is a between-experiment operation, not a remote kill command. Interrupt a live run with SIGINT/SIGTERM, let the batch clean up, then resume explicitly. A hard kill may leave workers; preserve the fail-closed live-process check.

The tree binds its runtime, protocol and optional library config. Changing these requires deliberate migration/new research; status remains readable. External source data and full receipts are verified by the underlying batch/native engine during execution. Do not modify the registry/config during execution. Resource settings are admission estimates, not OS-enforced limits.

The native `freeze/finalize/report` workflow remains manual and separate. After native freezing, sealing, archiving or final exposure, tree development is closed; tree status is still readable. Use the same `--worker-threads` setting for native freeze/finalize as the tree used.

## Files and tests

- `state.json`: atomic nodes, immutable proposal details, appended review/event history, decision state and budget.
- `plans/<node>.json`: fixed, hash-bound discovery batch plan.
- `executions/<node>/`: existing batch state, attempt logs, process metadata and verified receipts.
- Native study: immutable candidate snapshots, original check/discovery artifacts and owner marker.

Run `python -m pytest tests/test_research_tree.py tests/test_batch.py tests/test_workflow.py -q` for contract/recovery tests, and the real synthetic smoke above for the complete integration. Tests that replace computation explicitly use fixture-only results and do not demonstrate Qlib or strategy efficacy; the smoke uses actual training and backtests.
