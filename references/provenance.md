# Provenance

This skill adapts the research/development separation used by Microsoft's [RD-Agent](https://github.com/microsoft/RD-Agent): propose a hypothesis, implement it, execute an experiment, inspect feedback and preserve the trace. The design reference was RD-Agent 1.0.0, commit `484776c211e4fbbeef03e0ec00d6bbee7362a4f4`.

The host agent now performs the reasoning steps. This package does not import RD-Agent, duplicate its API client, require its vector retrieval service, or claim to reproduce its exact candidate-selection trajectory.

## Migration map

| RD-Agent entry point | Skill mode | Host agent responsibility | Script responsibility |
|---|---|---|---|
| `fin_factor` (`qlib_rd_loop/factor.py`) | `factor` | Propose a factor, write `compute`, explain matched comparisons and choose the next hypothesis | Check the implementation, build features, train the fixed model and measure discovery/final results |
| `fin_model` (`qlib_rd_loop/model.py`) | `model` | Hold features fixed, choose a preset or write a PyTorch `build_model`, interpret model differences | Fit preprocessing, train with validation, save/reload models, predict and backtest |
| `fin_quant` (`qlib_rd_loop/quant.py`) | `joint` | Choose which component to change, carry forward the other component and record parent/comparison reasoning | Evaluate complete factor-plus-model candidates under the same frozen protocol |
| `fin_factor_report` (`qlib_rd_loop/factor_from_report.py`) | `report` | Read source evidence, resolve formula choices explicitly and write the reproduction factor | Extract text/PDF page text, preserve source hashes, validate and evaluate the implementation |

The original reasoning prompts, hypothesis selection, code development and feedback interpretation become instructions for the host agent in `SKILL.md` and `references/research-modes.md`. They are not hidden model calls in Python. The agent writes candidate code in the study workspace rather than editing the skill.

The deterministic parts become the standalone `scripts/quant.py` interface: `prepare` handles data, `check` handles candidate contracts and checks, `evaluate` handles training/backtesting and numerical feedback, and `freeze`/`finalize` enforce the selected final evaluation. `status` and `report` expose the recorded experiments. The host reads these artifacts, explains the evidence and chooses any next experiment within the budget. This is a migration of the research capabilities, not a line-for-line conversion of every RD-Agent module.

[Qlib](https://github.com/microsoft/qlib) provides quantitative data and backtest facilities. LightGBM, XGBoost, scikit-learn and PyTorch are optional or required numerical libraries according to the selected model. The dependency lock records the actual selected versions. Original library licenses continue to apply to those dependencies.

The bundled example report, example factor, tiny neural model and demo dataset generator are authored functional-verification materials. The generated prices are synthetic, and neither their results nor the example hypothesis is a financial research finding.

Local prior experiments informed validation requirements (date alignment, training-only preprocessing, persisted model prediction checks and retained failed candidates). The factor collection additionally preserves eight historical implementations as portable `compute(frame, params)` adapters alongside five built-in features. Each historical package retains its source code hash, source-study identifiers and relevant evidence. These original files are provenance; ordinary factor execution uses the adapted implementation and never runs an archived study.

The collection preserves `R2_expand_on_volume`'s scale sensitivity and the rejected TREND group record. Adaptation does not promote a historical implementation check into new evidence of investment effectiveness. Private credentials, market-data files, trained models and full historical study payloads do not belong in the skill distribution. See [Factor library](factor-library.md) for package contents, versioning and validation status.
