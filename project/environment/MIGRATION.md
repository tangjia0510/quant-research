# Lightweight historical migration

## Scope
9 research records: 5 native factor studies, 3 literature/strategy reproductions, 1 diagnostic. Original study directories total 5,070,528,017 bytes; 262 selected source/evidence/literature copies total 7,425,907 bytes, plus small new metadata and replay adapter. These figures exclude the Skill snapshot and new BOLL study; they are not the final bundle size.

## Preservation
No original sealed files were changed. Frozen protocols, original code, conclusion/limitations, attempted candidates, failures and small freeze/selection ledgers are retained. No historical candidate is silently promoted to an accepted registry asset. ILLIQ20 alone retains its research bookmark; no live tradability certification. Original code copies preserve bytes for attribution and review; path compatibility is not implied.

## Replay readiness
- `20261102-strategies-v1`: verified offline replay from frozen raw responses after configuring external data root. The adapter reconstructs 2,140 price days and dividend events, reproduces normalization hashes, and matches all six cost/benchmark metric scenarios with tolerance 1e-11. It writes all computed files only under `work/`.
- Other eight historical records: explicit executable adapters are now present. Default dry-run verifies frozen source membership, sizes and SHA, stages scripts under `work/`, compiles them, and records topologically ordered commands. 7 records bind 10,931 data-lake raw/normalized source files (564,731,958 bytes); the 30-stock record binds 157 raw/selection files (7,542,464 bytes). No old intermediate diagnostic panels are required: execute rebuilds the shared diagnostic, then downstream monthly/native inputs. These heavy computations were **not** rerun during migration. Use a fresh work directory and `--execute` only when ready for their resource cost.
- Amplitude replay explicitly rebuilds both native prepared OHLC and the prior ILLIQ monthly base before its calculation. Frozen numeric parquet hashes must match; regenerated provenance receipts are distinguished from the original seals. If serializer/version changes produce different bytes, replay stops for review rather than silently substituting data.
- All paths bind through `local-paths.json`; derived files only under `work/`. The compatibility source code and old conclusions remain immutable. Research-specific `evidence/migration-replay-plan.json` records the validated plan, environment locks and remaining execution boundary.

## External data and derived output
Bulk original public responses and old frozen archives are external bindings under `data-catalog/`. They are not bundled; a destination needs the exact raw snapshots or a verified restoration. Some historic inputs cannot be reacquired exactly, so the external copy must be separately preserved. Prepared Qlib providers, features/labels, factor matrices, trained artifacts, full daily accounts, plots and report renders are excluded and must be recomputed. Do not run copied old packaging/sealing helpers against original roots.

## Map
See `migration-map.json` for every copied source/target/hash and the original frozen anchors. `local-paths.json` is machine-local and excluded from migration. The new lightweight project is a separate organization layer; original archives were not renamed or deleted.
