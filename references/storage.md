# Storage and study registry

Use this reference when setting up the shared data warehouse, choosing study locations, registering a dataset, finding prior work or moving the library. The skill directory contains executable resources; library data, versioned factors, studies and Python environments live elsewhere. Factor contracts and commands are in [Factor library](factor-library.md).

## Configuration and paths

Configuration lookup follows this order:

1. Explicit `--config FILE`.
2. `QUANT_RESEARCH_CONFIG`.
3. `$QUANT_RESEARCH_HOME/quant-research.json`.
4. `~/quant-research/quant-research.json`.

Place `--config` before the command in examples. Keep the same configuration selected throughout a managed study, including preparation and index updates. `config show` reports the effective configuration and resolved locations. A missing configuration is an instruction to run `config init`, not permission to silently select a different library.

The default configuration is:

```json
{
  "schema_version": 1,
  "warehouse_root": "warehouse",
  "research_root": "studies",
  "factor_root": "factors",
  "sources_root": "sources",
  "runtime_root": "runtime"
}
```

Relative roots resolve against the configuration file's directory, independent of the shell's current directory. Absolute roots are supported for separate disks, but must be reconfigured on a machine where those locations differ. All roots must not overlap and must stay outside the skill directory. `config init` accepts `--warehouse-root`, `--research-root`, `--factor-root`, `--sources-root` and `--runtime-root`; it refuses to overwrite an existing configuration. Existing schema-version-1 configurations without `factor_root` or `sources_root` resolve these as `factors` and `sources` beside the configuration file. Changing a configuration does not move data: copy the corresponding directories first, then point a new configuration at them.

For the first setup, `bootstrap --venv /chosen/runtime/path` can create the Python environment before library configuration exists. Once configured, omitting `--venv` selects `runtime_root/py311`. Run `doctor` with the resulting interpreter before research.

With defaults, the layout is:

```text
quant-research/
├── quant-research.json
├── sources/<source>/<batch-id>/  # Raw acquisition, state, quality and normalized output
├── warehouse/
│   └── <dataset-id>/<version>/
│       ├── manifest.json
│       ├── data.csv | data.parquet | data/
│       └── universe.csv / calendar.txt  # Optional source snapshots
├── factors/
│   ├── index.json / index.md
│   └── <factor-id>/<version>/     # Immutable definition, implementation and provenance
├── studies/
│   ├── index.json
│   ├── index.md
│   └── <study-id>/
│       ├── registry.json
│       ├── protocol.json
│       ├── study.json
│       ├── data/                 # This study's prepared snapshot
│       ├── candidates/
│       ├── runs/discovery/
│       ├── runs/final/
│       ├── freeze.json
│       └── report.md / report.html
└── runtime/                     # Rebuildable Python environments
```

## Dataset identity and versions

`dataset add` copies a supplied CSV, Parquet file or Qlib provider into an immutable warehouse version. Optional `--universe` and `--calendar` inputs travel with it. `--metadata FILE` accepts a JSON object for known source facts; do not infer adjustment basis, historical membership or vendor rights from a filename. This import command does not fetch market data or register unrelated existing directories automatically. Use `data fetch` for the separate download, normalization, validation and registration workflow; see [Market-data preparation](data-preparation.md). Fetch/combine also include immutable quality and provenance evidence in the version.

Registered `region`, `price_basis`, `volume_unit`, `synthetic`, `columns`, currency/frequency, adjustment/volume semantics, universe scope, acquisition identity and limitations are carried into managed protocols. Conflicting protocol values are rejected: a dataset version cannot silently change units or adjustment meaning between studies. Other metadata remains in the source manifest. Register universe/calendar files with the version; a managed protocol cannot add unregistered external membership or calendar files.

Use a descriptive dataset ID such as `cn-daily-adjusted` and an explicit version such as `2026-11-01` or `v1`. IDs and versions use lowercase letters, digits, dots, underscores or hyphens, start with a letter or digit, and are at most 64 characters; trailing dots and Windows reserved names are rejected. Never use a moving `latest` reference inside a frozen study. A changed source gets a new version; an existing ID/version cannot be overwritten.

The warehouse manifest records relative payload filenames and hashes. Its original source location is historical provenance, not the path used after migration. Study creation resolves and verifies the registered version, and records `data.dataset_id`, `data.dataset_version`, `data.manifest_hash` and `data.format` in the protocol. These fields identify the source without embedding a machine-specific warehouse path. Preparation verifies the version and creates the study-local data snapshot. The shared warehouse reduces ambiguity about inputs; each study still owns its prepared evidence.

`dataset list` is a lightweight inventory, with `payload_verified: false`; it does not rehash every market-data file. Full payload checks occur when the version is resolved for a study. Treat error entries as unresolved input problems, not empty datasets.

## Study naming

`study new` creates a unique directory under `research_root` using:

```text
YYYYMMDD-HHMMSSZ-<mode>-<slug>-<6hex>
20261101-083015Z-factor-momentum-20-1a2b3c
```

The timestamp is UTC, `mode` is one of the four research modes, and the suffix prevents collisions. Supply a short lowercase ASCII slug with digits and hyphens, up to 48 characters. Use `--title` for a readable title, including Chinese; titles do not become paths. Preserve the generated study ID when moving a study. Candidate IDs inside a study follow their own contract and do not replace the study ID.

An explicit `init --workspace ...` remains available. Such a study can be indexed when it is a direct child of the configured research root. An arbitrary external workspace is not silently moved into the managed library.

For new managed studies, `--protocol` is optional. Omitting it materializes the [default research plan](contracts.md#default-research-plan) against the selected dataset: 2020–2024 training, 2025 H1 validation, 2025 H2 discovery, 2026 final testing, and 100,000 initial cash. Read the resulting `protocol.json`; available trading dates bound the periods. An explicit protocol overrides this preset and remains the route for different years or assumptions. `init --workspace ... --protocol ...` continues to require the supplied file.

## Global index

Both `index show` and `index refresh` rebuild `research_root/index.json` and `index.md` from study files before returning the current summary. Managed study command completion and failure refresh the index automatically. Entries summarize the study ID, title, mode, dataset/version, state, candidate count, timestamps and report location. Workspace/report paths are relative to the research root so links survive relocation.

The global index also includes a factor-library summary. The detailed factor index lives at `factor_root/index.json` and `index.md`, with an entry for each version, including rejected records and validation failures. It can be rebuilt from the registered packages and validation receipts.

The index is derived, not the authority for experiments. It does not replace `protocol.json`, candidate snapshots, run records or result artifacts. Refresh can recover a missing index. Recognized but malformed studies remain visible as errors, and duplicate registered IDs are errors rather than one entry overwriting another. Unrelated directories and symlinked directories are not traversed. An index state is a summary; `artifact_integrity: not_checked` means it is not a deep verification of every model or data file. Run the study's `status` and relevant verification commands before reusing results.

## Example workflow

Use the validated runtime's Python and replace the input paths with actual files. Inspect `defaults` before using the preset. The CLI binds the materialized research assumptions to the selected registered dataset.

```sh
QR_SKILL="/path/to/quant-research"
QR_PYTHON="/path/to/runtime/bin/python"
QR_CONFIG="$HOME/quant-research/quant-research.json"

"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" config init
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" defaults
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" dataset add \
  --id cn-daily-adjusted --version 2026-11-01 \
  --source /data/daily-equities.parquet --format parquet \
  --metadata /data/source-metadata.json
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" study new \
  --slug momentum-20 --title "20日动量因子研究" --mode factor \
  --dataset cn-daily-adjusted --version 2026-11-01
```

Add `--protocol /research-inputs/protocol.json` to `study new` when explicit settings are needed. Read the returned workspace path and materialized protocol, then use the workspace for `prepare`, `check`, `evaluate`, `freeze`, `finalize`, `status` and `report`. Finish with `index show`. Reuse an existing configuration or dataset version when appropriate; do not rerun their creation commands as if they were overwrite operations.

## Import historical research

Use `study import --source DIR --slug NAME --title TITLE --mode factor|model|joint|report|unknown --historical-status DESCRIPTION --report report.html` for older RD-Agent/Qlib folders. The optional `--datasets`, `--exclude` and `--notes` arguments name JSON files: a list of verified dataset references, a relative-path-to-reason exclusion map, and archival notes. Dataset references contain `id`, `version`, `manifest_hash`, and optionally `source_relative` to identify the original data location. Register shared data before importing its studies.

The command copies retained files under a new `*-archive-*` study's `original/` directory and records their hashes, original source location, source modification times, exclusions and link history in `archive.json`. It never rewrites old protocols or executes saved models. Reports remain original files. Internal file symlinks become same-content local files; external/directory links are recorded rather than followed, so their required data must be mapped to registered snapshots or explicitly accounted for. Environment directories, repository metadata, Python caches, `.env` files and artifact-signing keys are excluded by default. Preserve any required signing material separately with restricted permissions; it is not an ordinary research artifact or a publishable skill asset.

`study verify --workspace PATH` checks the full archived payload. `status` and `report` support archived studies; computation commands reject them. The index shows `archived` plus the recorded `historical_status`, not a newly verified `final_complete`. A new experiment based on old work uses `study new` and its own protocol. Repeating an unchanged import reuses and verifies the existing archive; changed historical content creates a separate record. Do not relabel a rejection, technical recovery or exposed historical period as a successful new experiment.

## Move to another machine

Copy the complete warehouse, factor library, studies and acquisition sources, plus the configuration and this skill version. With the default relative roots, copying the containing library directory preserves their relationship. Select the copied configuration using `--config` or `QUANT_RESEARCH_CONFIG`, rebuild the Python environment under the new runtime root, run `doctor`, then run `index refresh`. The old virtual environment is replaceable and should not be treated as portable executable state.

Do not edit frozen protocols, candidate identities or hashes to make a move appear successful. Managed source identities resolve through the new configuration; stored historical source paths can remain as provenance. Legacy explicit-path protocols retain their original contracts: preserve required locations or create a distinct imported study instead of rewriting the original experiment.

Moving files does not guarantee cache reuse across operating systems, architectures or dependency changes. Preserve the skill version used by existing studies; in particular, a 1.0 study may require its 1.0 runtime/scripts for resumption. New versions are for new studies unless an explicit migration preserves and verifies the old evidence.
