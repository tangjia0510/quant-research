# BOLL ETF study

Two fixed local BOLL hypotheses on the traded 510300 ETF, not an original-author return replication. Research budget: 2 strategies, no parameter search. Read `protocol.json`, `amendments.json`, `conclusion.md`, `attempts.jsonl`.

## Rebuild and run

Use the project's locked Python environment and bind `legacy_library` in local-only `local-paths.json` to the existing external archive. Original provider responses are SHA-checked. Derived normalized input CSV files are rebuilt under `work/` and their bytes verified; the portable package does not carry data matrices or historical price rows.

- Preparation only (no strategy results): `python research/20261103-boll-etf-v1/src/run.py --project-root . --prepare-only`
- Tests: `python -m unittest discover -s research/20261103-boll-etf-v1/src -p test_boll.py -v`
- After layout/migration and protocol audit approval: `python research/20261103-boll-etf-v1/src/run.py --project-root . --authorization work/20261103-boll-etf-v1/authorization.json`
- Independent replay: use the same code and authorization with `--work-dir work/20261103-boll-etf-v1-replay` (relative to shell cwd, must remain within this project's work).

The authorization JSON must identify this research, `migration_accepted: true`, and the frozen protocol SHA. The file is an explicit local workflow gate, not cryptographic proof of independent auditing. Existing result files cannot be silently overwritten.

All daily indicators, forward labels, curves, account ledgers, trades, reports and raw-input normalization caches belong to `work/`, excluded from portable exports. Keep only code, frozen protocol, compact conclusions and attempt history here. Data absence after migration is a required explicit prerequisite, not permission to replace with synthetic data or change source vintages.

## Rebuild the optional presentation

After the frozen calculation is complete, `python research/20261103-boll-etf-v1/src/report.py --project-root . --work-dir work/20261103-boll-etf-v1` regenerates DOCX, HTML and plots under work/report. Use the separately pinned optional dependencies in environment/report-requirements.txt plus a CJK font (`--font-file`). Presentation dependencies are separate from numeric-research dependencies. The report labels audit status from retained validation metadata; regenerating a presentation does not create a fresh independent audit.
