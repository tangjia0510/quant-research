# Lightweight portable research projects

Use this layout for agent-neutral handoff, research catalogues and migration without recomputable bulk artifacts. The adapter is `scripts/project.py`; it is separate from the existing `quant.py` managed-study engine. It does not rename, modify or silently resume old sealed studies.

## Three storage classes

```text
project/
  project.json
  skill/                         # Controlled, hash-bound copy of this Skill
  research/<id>/
    research.yaml                # JSON encoding (valid YAML); schema below
    src/                         # Research-specific code, not dependencies
    protocol.json                # Frozen rules/parameters/time design
    attempts.jsonl               # Small trial/failure/exposure/selection ledger
    conclusion.md                # Measured summary, limitations, key audit conclusion
  registry/factors/<id>/asset.json
  registry/strategies/<id>/asset.json
  literature/                    # Deduplicated original evidence and source cards
  data-catalog/<id>.json          # External input identities; no bulk input copies
  environment/                   # Dependency locks and skill snapshot hashes
  local-paths.json                # Machine-specific bindings; NEVER exported
  work/<id>/                     # Rebuildable outputs; NEVER exported
external-data-store/             # Raw inputs, separate retention/access policy
```

Research is the complete attempt history, including negative findings. Registry is a versioned subset with explicit admission evidence, not a synonym for a bookmarked candidate. Keep a bookmark as research metadata. Admission must name the evaluated rules, costs, evidence range and limitations; historical association is not live-trading approval. Failed or untested strategies do not enter registry merely to fill it. Retired assets retain history.

Keep raw data that cannot be reacquired independently of the lightweight bundle. A file being large is not a reason to destroy it. Refer to immutable versions and hashes, not moving `latest` aliases. Derived prices, feature matrices, labels, prepared Qlib providers, fitted models, account-day ledgers, images/reports and runtime environments are rebuilt under `work/`. Preserve small key results and the original trial/failure/freeze/exposure history: recomputing can reproduce arithmetic, but cannot reconstruct the order of human selection decisions.

## Contract v1

`project.json` is created by `init`. `research.yaml` uses **JSON encoding**, which is valid YAML and needs only Python's standard library. The adapter does not parse arbitrary YAML syntax.

```json
{"schema_version":1,"id":"20261103-example","title":"Example research","type":"strategy","status":"draft","data_refs":["bars-v1"],"entrypoint":"src/run.py","favorite":false}
```

Types: `factor`, `strategy`, `diagnostic`, `mixed`. Status: `draft`, `running`, `completed`, `rejected`, `inconclusive`, `archived`. `entrypoint` is a relative existing `src/` file, or null when replay is not implemented. An optional `legacy_ref: {"root":"legacy_library","path":"studies/<id>"}` points to external old artifacts; it is provenance, **not proof of runnable portability**. Record `replay_status` and limitations for legacy code that still needs adaptation. Do not claim all studies replay if only one adapter has been tested.

Research runner convention: accept `--project-root PATH --work-dir PATH`, resolve the data catalogue, verify raw inputs, generate outputs only in the selected work directory. Treat a changed protocol/code/input as a new run identity, not permission to replace frozen evidence. Existing native engine studies retain their own study layout, signing/lock semantics and runtime. A wrapper may reconstruct a fresh workspace under `work/`, but must not patch old hashes to make resumption pass.

A catalogue entry for a single immutable file:

```json
{"schema_version":1,"id":"bars-v1","version":"2026-10-30","kind":"file","sha256":"<64 lowercase hex>","locator":{"root":"raw_store","path":"source/bars.csv"},"limitations":["Latest-vintage data, not authenticated PIT"]}
```

For a directory, use `kind: directory`, `sha256: null` and optional `manifest: {"path":"manifest.json","sha256":"<64 lowercase hex>"}`. Directory resolution checks manifest bytes only; downstream acquisition/replay must verify its payload members. Unhashed references require explicit `limitations` and are unresolved evidence, not certified inputs. Add columns, units, acquisition method, licensing/provenance and temporal availability as metadata. Null hashes cannot silently become verified.

`local-paths.json` is a simple mapping, e.g. `{"raw_store":"../data-store","legacy_library":"../old-library"}`. Relative locations are resolved against the project, not the shell. On another machine recreate this file using authorized available inputs; missing roots, missing files and hash drift fail clearly. A portable bundle does not contain those external data bytes or grant access rights.

Registry asset records require `status: admitted|retired`, `version`, `research_ids`, nonempty `admission`, and nonempty `limitations`. These fields are evidence declarations, not an automatic economic-quality score. Review the linked protocols/results before admission; the structural validator cannot certify investment validity.

## Commands

```sh
python /path/to/skill/scripts/project.py --project /path/to/project init
python /path/to/skill/scripts/project.py --project /path/to/project new --id example-v1 --title Example --type strategy
python /path/to/skill/scripts/project.py --project /path/to/project resolve --id bars-v1
python /path/to/skill/scripts/project.py --project /path/to/project snapshot-skill --source /path/to/skill
python /path/to/skill/scripts/project.py --project /path/to/project validate
python /path/to/skill/scripts/project.py --project /path/to/project index
python /path/to/skill/scripts/project.py --project /path/to/project export --output /elsewhere/research.zip --dry-run
python /path/to/skill/scripts/project.py --project /path/to/project export --output /elsewhere/research.zip
python /path/to/skill/scripts/project.py --project /new/location/project import --source /elsewhere/research.zip
```

`init` is idempotent. `new` and `import` reject existing destinations. Export refuses overwrite, runs validation and binds every included file by SHA/size. Import rejects duplicate paths, escapes, symlinks, mismatched hashes and excessive sizes, validates in a temporary directory and only then installs the project. Import does not execute research or install dependencies. Index is derived and written under `work/index.json`, not a portable authority.

Export is allowlisted to `skill`, `research`, `registry`, `literature`, `data-catalog`, `environment`, `project.json` and `README.md`; `work`, runtimes, caches and `local-paths.json` are excluded. Supported text/source formats and original PDF evidence are bounded to 16 MiB per file, 64 MiB total; CSV is bounded to 256 KiB of compact evidence. Large original literature can be externalized by hash rather than changing the limit to transport datasets. Do not hide bulk tables in text files to bypass the contract. The limits are a guardrail, not semantic proof that every allowed file is essential.

`skill/` is an explicit controlled snapshot, with hashes under `environment/skill-snapshot.json`. Modify the source Skill then refresh the snapshot; do not edit the two copies independently. Validation detects changed bound files. Hashes establish integrity, not a sandbox or trust in downloaded code.

## Migration acceptance

Preserve old sealed roots byte-for-byte. Create light records referencing them; mark omissions and replay limitations. Verify selected retained files, source manifests and old freeze anchors. Dry-run and inspect export membership/size; import under a different root with no local bindings; verify that absent inputs fail explicitly. Rebind inputs and replay at least one representative research from raw inputs, comparing metrics without copying its computed outputs. New research uses this layout from its first frozen protocol. Passing these checks is a lightweight handoff, not a full raw-data backup or proof that all legacy code is portable.


## Single-source repository mode
A `project/` directory may set `skill_source` to exactly `..`. The parent must contain `SKILL.md` and `scripts/project.py`. The parent Skill is the source of truth; project/ has no Skill duplicate. Validation checks the controlled manifest against parent Skill files. Export stages an independent portable copy with a generated Skill snapshot and removes the repository reference. Only declared root Skill files and scripts/references/assets/agents/tests are selected, never nested project content. Update environment/skill-snapshot.json when intentionally changing source. Standalone imports retain their own controlled snapshot.
