# Environment and portability

The skill is a directory of instructions and Python source. Keep the Python environment, data and experimental artifacts outside that directory. Copying the skill to a different host must not require modifying its source files.

## Install for Codex and Claude Code

Keep one extracted copy of the complete `quant-research` directory at a stable path. Both hosts use its `SKILL.md`, `references`, `scripts` and `assets`; `agents/openai.yaml` supplies optional Codex display metadata. No host-specific tools are named in the research workflow.

For user-level discovery, link that directory into each host's skills directory. Replace the source placeholder below with the actual extracted directory. These commands assume the destination does not already exist; preserve an existing installation and inspect it before deciding to replace it.

```sh
QR_SKILL_SOURCE="/absolute/path/to/quant-research"
mkdir -p "$HOME/.codex/skills" "$HOME/.claude/skills"
ln -s "$QR_SKILL_SOURCE" "$HOME/.codex/skills/quant-research"
ln -s "$QR_SKILL_SOURCE" "$HOME/.claude/skills/quant-research"
```

Copy the complete folder instead if symlinks are unavailable. Open a new host session so skill discovery sees the installation. A host that can read files and execute Python can follow the same workflow; installing a skill does not install its numerical runtime.

## First run

1. Locate this skill and inspect `python3 scripts/quant.py --help`.
2. Run `doctor` with the intended Python interpreter.
3. If needed, invoke `bootstrap --venv /chosen/runtime/path` using the exact options reported by `bootstrap --help`. Prefer a subdirectory of the library's runtime root, default `~/quant-research/runtime`. The installer uses the bundled dependency definitions; do not borrow another study's site-packages with `.pth` or `PYTHONPATH`.
4. Use the resulting environment's Python to run every research command.
5. Use `--extras models reports` for the optional PyTorch and PDF dependencies. Plain-text sources do not require the reports extra.
6. Initialize or select the library configuration, inspect `factor list`, and use `factor seed --validate` to install and verify the bundled factor collection when it is absent. Registered factors live outside the skill under `factor_root`; see [Factor library](factor-library.md).
7. Run `defaults` to inspect the fixed research dates and initial cash. A managed `study new` without `--protocol` uses this policy and resolves its endpoints from the selected dataset.

CPU execution is the baseline. No Docker daemon, Conda, MongoDB, RD-Agent, embedding service, Magpie configuration or model API key is required by these scripts. Access to the host coding agent's own model is supplied by that agent. For missing real inputs, use the bundled free BaoStock adapter through `data fetch`; the [data-preparation guide](data-preparation.md) describes source coverage, the default 2019-to-latest window, quality checks and source extensions. Network availability and market completeness must be measured, not assumed. External vendor accounts remain optional and are not configured automatically.

Python 3.11 and locked numerical dependencies are the initial supported environment. Native wheels and platform libraries still matter, especially for OpenMP and neural models. An installation check on one operating system is not a validation of every OS/architecture. Use `doctor` and the smoke tests on each target machine.

## Moving a study

Use the configured library in [Storage and study registry](storage.md) for new research. That reference defines relative roots, registered dataset identities and index rebuilding after a move. Copy the full study evidence, required warehouse versions and factor library including validation receipts; rebuild the runtime on the new machine. Candidate snapshots already contain their referenced factor packages, while the shared library is needed to register new references. Keep the matching skill version, since changing executable code or dependencies can invalidate cached runs.

For an older explicit-path workspace, ensure its source snapshot remains available and hashes match. Create a distinct imported study if its immutable source path must change; do not overwrite an old protocol and claim it is the original experiment.

## First study using real data

When the user has no data file or account, first run `data fetch --source baostock --id cn-baostock-daily --version <new-version>`, inspect quality and limitations, and use its registered ID/version in `study new`. Dates default to 2019 through the latest available completed session. `--instruments` can explicitly select a small onboarding sample; label it as a sample. See [Market-data preparation](data-preparation.md) for full commands and resume/combination behavior.

Replace the example data path below with an existing daily-equity dataset, then send this request to either host:

> 请使用 quant-research skill 做一次因子研究。真实日线数据是 `/data/daily-equities.csv`，使用已配置的数据仓库和研究根目录。先检查已有数据版本和研究索引，再核对数据字段、复权口径、交易日历和实际覆盖日期，登记明确的数据版本。采用默认的 2020–2024 训练、2025 验证、2026 测试和 10 万元初始资金，核对生成协议中的实际交易日期。以 return_5、volatility_20 和 Ridge 为基线，提出并实现有明确假设的因子，最多 6 个候选、每个最多 2 次失败重试。先跑检查和发现集比较，冻结候选后只做一次最终评估，给出可追溯报告并更新索引。不要用演示数据替代真实数据。

For a Qlib provider, give the provider directory and identify its format as `qlib`; for Parquet use the file and `parquet`. The [default plan](contracts.md#default-research-plan) supplies declared dates, model and portfolio assumptions unless the user supplies an explicit protocol. Historical membership, data units and adjustment basis still need source evidence. Data must cover the required periods; the default plan cannot manufacture missing 2026 observations or automatically substitute other years. The agent registers or reuses the dataset version, runs `study new`/`prepare`, and then follows the shared check/evaluate/freeze/finalize/report workflow. Model, joint and report studies use the corresponding mode and contracts; report reproduction also requires the supplied report source.

## Engineering demo

Run `assets/make_demo.py --output /new/demo-directory` to create synthetic bars and a complete protocol. Run `tests/smoke_modes.py --help` for the four-mode execution test. These assets establish functional portability, not financial validity or compatibility with every market's trading conventions.
