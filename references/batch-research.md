# Bounded parallel discovery batches

`scripts/batch.py` is a bundled coordinator for the existing `quant.py` CLI. It schedules **prepare → check → evaluate** tasks, never arbitrary shell commands, candidate generation, selection, freezing or final evaluation. Read [Factor optimization](factor-optimization.md) for experimental design. Parallel execution does not validate a factor or reduce multiple-testing risk.

## Setup and interface

Initialize fresh studies and write reviewed candidate files before running a batch. Use distinct study directories for concurrent work; each must be nonarchived, unfrozen and unsealed. A `freeze.json`, `archive.json`, or `supplementary/final-artifact-manifest.json` marker prevents development writes. Do not point a new batch at a completed historical study merely because it has no native freeze file.

Run with the same separately installed research Python used for ordinary CLI commands:

```sh
"$QR_PYTHON" scripts/batch.py --plan /absolute/batch-plan.json --output /absolute/batch-evidence
"$QR_PYTHON" scripts/batch.py --plan /absolute/batch-plan.json --output /absolute/batch-evidence --resume
```

The output directory must be outside the skill and all study directories, and must not contain those studies. Preserve it between attempts. No runtime installation or data download is performed by this command. This scheduler currently requires a POSIX host for process-group cancellation; Windows is rejected rather than claiming equivalent tree cleanup.

The plan is a **batch-specific schema**, not additional fields in `protocol.json`. Unknown keys/commands are rejected. Example (replace paths and resource estimates before use):

```json
{
  "schema_version": 1,
  "config": "/absolute/library-config.json",
  "max_workers": 2,
  "worker_threads": 1,
  "cpu_budget": 2,
  "memory_budget_mb": 4096,
  "worker_memory_mb": 1024,
  "prepare_memory_mb": 4096,
  "global_candidate_budget": 2,
  "max_attempts": 2,
  "timeout_seconds": 3600,
  "tasks": [
    {"id": "a-prepare", "command": "prepare", "workspace": "/research/a"},
    {"id": "b-prepare", "command": "prepare", "workspace": "/research/b"},
    {"id": "a-check", "command": "check", "workspace": "/research/a", "candidate": "/research/a/candidate.json", "depends_on": ["a-prepare", "b-prepare"]},
    {"id": "b-check", "command": "check", "workspace": "/research/b", "candidate": "/research/b/candidate.json", "depends_on": ["a-prepare", "b-prepare"]},
    {"id": "a-evaluate", "command": "evaluate", "workspace": "/research/a", "candidate": "/research/a/candidate.json", "depends_on": ["a-check"]},
    {"id": "b-evaluate", "command": "evaluate", "workspace": "/research/b", "candidate": "/research/b/candidate.json", "depends_on": ["b-check"]}
  ]
}
```

The numerical memory values illustrate small synthetic jobs, not a recommendation for whole-market data. Measure representative peak usage first. All check tasks depending on all prepare tasks gives a clear preparation barrier; cross-study dependencies are supported.

| Field | Contract |
|---|---|
| `schema_version` | Required, `1` |
| `tasks` | Nonempty list of unique safe IDs; only `prepare`, `check`, `evaluate` |
| `workspace` | Existing initialized study path; no initialization inside scheduler |
| `candidate` | Required for check/evaluate; existing candidate JSON inside its study; absent for prepare |
| `depends_on` | Task IDs, defaults to `[]`; acyclic. Evaluate requires an ancestor check for the same candidate and study |
| `config` | Optional existing library config path, forwarded to every quant command; specify for managed libraries |
| `global_candidate_budget` | Required positive cap on distinct `(study, candidate ID)` in the fixed plan, including unsuccessful candidates |
| `max_workers` | Default `2`; one active command per study, always |
| `worker_threads` | Default `1`, range 1–64; passed explicitly to native worker |
| `cpu_budget` | Defaults to process CPU affinity count; `max_workers × worker_threads` must fit, and declared budget cannot exceed observed affinity |
| `memory_budget_mb` | Defaults to 80% of observed available/physical/cgroup remaining memory, whichever is smallest |
| `worker_memory_mb` | Per check/evaluate reservation, default `2048`; tune from evidence |
| `prepare_memory_mb` | Default entire memory budget. Prepare is globally exclusive even if a smaller reservation is declared |
| `max_attempts` | Default `2` total attempts per task across all resumes; no automatic retry loop |
| `timeout_seconds` | Default `3600` per task, not per entire batch |

An already prepared study may omit its prepare task; its snapshot is verified. Otherwise each check needs a prepare ancestor. A study may have only one prepare task. Independent studies must have matched protocol, data-content hashes and sampling assumptions; different source paths are permitted only with matched content. Candidate registration is coordinated under the native study lock and also consumes each study's original candidate budget.

## Isolation and resource limits

The coordinator holds an exclusive batch-output lock and schedules no two tasks in the same study at once. Every child still goes through the native `.study.lock`; another batch or direct CLI can cause a fail-closed lock-contention error rather than unsafe overlap. Shared library index updates retain their own lock; inspect per-command index errors separately from experiment success.

Prepare is globally exclusive with all other compute in this batch because full-market preparation can consume most memory. Across studies, prepare/provider trees are **not** automatically shared, copied, symlinked or hard-linked. There is no cross-candidate fitted-baseline cache. Reuse immutable source versions and existing verified preparations, not mutable generated files. Hash agreement is necessary for comparison, not permission to inject another study's results.

Reservations and pre-launch memory checks are **not OS-enforced RAM/CPU limits**. The scheduler defers a task if current memory headroom is below its reservation; if no active task can free resources, it records a failed admission rather than hanging or launching unsafely. It samples Linux process-group RSS and records an observed peak; shared pages may be counted more than once and short spikes may be missed. Monitor real workloads and use conservative estimates; a machine's current memory size is not a fixed skill default.

Native `quant.py --worker-threads N` is a global option placed before the subcommand, defaults to `4` for standalone CLI compatibility, and controls worker OpenMP/OpenBLAS/MKL/NumExpr settings. Batch explicitly selects its configured value, default `1`. Subsequent native cache verification, `freeze` and `finalize` must use the same explicit `--worker-threads` value because it is part of the research fingerprint. Known model thread parameters must fit this budget; factor workers already use one thread. Custom code is not a hostile-code sandbox and can allocate beyond estimates. These controls are not a guarantee against every library's independent worker pool.

## Evidence, cancellation and recovery

`state.json` is atomically published. It contains the normalized plan, input/runtime binding, task states, append-only attempt records, commands, dedicated stdout/stderr paths, timestamps, process identifiers, resource observations and audited receipts. Task states include `pending`, `launching`, `running`, `success`, `failed`, `blocked`, `cancelled`, `interrupted`; these are scheduler states, not additions to native run-file schema. Every attempt gets its own directory. A failed dependency blocks its descendants; independent tasks can finish. The batch exits nonzero if any task fails/blocks, and returns `130` on handled cancellation.

The plan includes all proposed candidates before launch; failures remain counted. Selection waits for the declared batch checkpoint, not whichever candidate finishes first. Changing a candidate or hypothesis is a new trial, not a technical retry. A new batch directory does not reset the overall research budget or exposure history; the coordinator's cap is local to this fixed batch, not a global cross-library search accountant.

On SIGINT/SIGTERM or task timeout, the coordinator terminates only the task's dedicated process group, including native check/evaluation and factor descendants. In batch mode native workers remain in that group; standalone CLI isolation remains unchanged. A start gate opens only after the process identity is persisted, limiting the spawn/persistence crash gap. No existing study locks are removed.

Use `--resume` with the same plan/output after addressing a technical failure. Unspecified resource defaults reuse the original resolved values; explicit plan changes, source/candidate/runtime changes and altered successful artifacts fail closed. Successful tasks are verified and skipped without a new attempt. Failed/cancelled/interrupted tasks can retry only within the persisted attempt limit and native repair budget. A previously running process group still present causes refusal: establish that the original task has terminated before resuming, rather than launching a duplicate or deleting evidence. A hard-killed coordinator cannot guarantee immediate descendant cleanup. Do not automatically kill a group of uncertain ownership.

Frozen snapshots, registered candidate identities, source-content hashes, runtime source, package versions and worker-thread settings bind evidence. Runtime changes can invalidate older native fingerprints; old research artifacts are preserved, not overwritten or relabeled corrupted because a newer implementation differs. This release does not migrate prior caches. Continue prior frozen reproduction only with its matching runtime/environment, and use new studies for the updated engine.

## Verification

`tests/test_batch.py` exercises validation, resource admission, dependency failures, attempts, real lightweight child-process overlap, serialization, cache checks and live-group refusal using the standard library test runner. `tests/smoke_batch.py` uses two isolated synthetic Qlib studies, demonstrates actual training/evaluation overlap, verifies no same-study/prepare overlap, checks idempotent resume, and cancels a live native worker tree. Synthetic smoke validates engineering behavior only, never investment value.
