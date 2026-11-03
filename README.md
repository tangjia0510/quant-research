# Quant Research

Single-source quantitative research Skill and lightweight research records.

- `SKILL.md`, `scripts/`, `references/`: the only maintained Skill source.
- `project/research/`: nine historical studies and BOLL research, including negative results.
- `project/data-catalog/`: references and hashes, not raw market data.
- `project/literature/`: source links; third-party PDFs are omitted.
- `project/work/`: regenerated output, excluded from Git and migration.

```sh
python scripts/project.py --project project validate
python scripts/project.py --project project export --output /tmp/quant-research.zip
python scripts/project.py --project /tmp/imported-quant import --source /tmp/quant-research.zip
```

Repository mode references the parent Skill through `skill_source: ".."`. Export creates a controlled Skill snapshot in the portable bundle, without storing a second copy in Git. External raw input locations must be configured in ignored `project/local-paths.json`. Absence of raw data is reported, never replaced with invented observations.

See `project/environment/MIGRATION.md` for research replay and `project/environment/PUBLICATION.md` if present for publication changes. Only Faber and BOLL have full replay evidence; other historical studies have dependency/dry-run checks, not a fresh full recomputation. Historical evidence hashes refer to the original research code; repository adapter changes are recorded separately. Public availability does not assign a new blanket open-source license. Existing third-party notices are preserved.
