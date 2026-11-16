# External data catalog

`lake-*` entries organize the existing six data-lake branches without moving their files. Branch-level entries are inventories, not immutable dataset versions: their SHA is intentionally null. Research must bind exact file hashes or a verified manifest.

`legacy-*` entries bind original frozen study archives or exact old input manifests. They preserve provenance and historical evidence, not a promise that all their computed outputs belong in a portable bundle.

The latest gap and acceptance references are explicitly round-scoped. Previous source maps may have older counts. Prefer the latest gap ledger for completeness, and the original endpoint receipts for provenance.

Machine-local root paths are in `local-paths.json` and excluded from export. Raw data stays external; no bulk lake files, normalized caches, factor matrices or runtime environments are copied by migration.

`mip-daily-qfq-20261116-v1` and `mip-daily-none-20261116-v1` identify two components of the same hash-pinned archive, retained as a repository Release attachment. Resolve either against the `mip_backup` root after downloading the archive. See [MIP data reference](../../references/mip-daily-data.md) for restoration, schema and research limitations; successful archive resolution does not register a Qlib dataset or certify price coverage.
