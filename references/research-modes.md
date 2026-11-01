# Research modes

Read the relevant mode before choosing candidates. The same numerical engine supports all modes; the difference is what the agent changes, records and compares.

Unless the user supplies an explicit protocol, all modes use the [default research plan](contracts.md#default-research-plan): 2020–2024 training, 2025 validation split internally into H1 model validation and H2 discovery, then 2026 testing, with 100,000 initial cash. This fixed plan does not imply rolling retraining. Inspect its materialized date endpoints before starting research.

## Factor research

1. Define the economic or statistical mechanism and measurable expectation. State available fields and when each is known.
2. Specify baseline features, initially `return_5` and `volatility_20`. The engine evaluates a fixed baseline alongside the candidate. These two features are examples, not a required strategy.
3. Select a version from the [factor library](factor-library.md), or write a pure `compute(frame, params)` implementation and state the actual number of observations required. A standard deviation over 20 one-session returns needs 21 prices.
4. Use the same model, label, dates and portfolio settings for baseline and added-factor candidates. Do not change the model at the same time and attribute all improvement to the factor.
5. Inspect coverage, prediction IC/RankIC, costs, drawdown and the comparison's consistency. A generated explanation is a hypothesis, not evidence.

A candidate uses `kind: factor` and `features` for baseline feature names. Supply a nonempty `factor_refs` list or a workspace-relative `factor_file` with `factor_params` and `max_lookback`; referenced versions carry their own contracts. These factor columns are added to the baseline columns. Candidate IDs are immutable after evaluation; use a new ID for each correction.

## Model research

Hold features and the research protocol fixed. This includes the exact versions of any `factor_refs`; the baseline uses the same referenced factors as the model candidate. Start with a supported preset (`ridge`, `lightgbm`, `xgboost`) before testing a custom model, unless the user requests a particular architecture.

For custom PyTorch models, provide a workspace-relative file through `model.file`, set `model.kind: custom`, and define `build_model(num_features)` returning a `torch.nn.Module`. Its forward method takes a two-dimensional feature tensor and returns one prediction per row. The script controls optimization, early stopping, prediction and persistence. Read the actual model parameters in the candidate; do not assume every preset accepts the same keys.

Use an explicitly justified, small change. Compare validation diagnostics as well as discovery performance. The final segment does not choose epochs or architecture. Test save/reload consistency so a reported model is an executable artifact, not only a score.

## Joint factor/model optimization

A joint study alternates changes to the factor and model. Every candidate must keep `kind: joint`, include `model`, and supply a `factor_file` or nonempty `factor_refs`. To test one component, copy the unchanged component's definition into the new candidate and change only the other. Do not switch candidate kinds within a joint study. Each iteration must identify its parent and changed component in its hypothesis or metadata; this recorded parent does not automatically copy code or choose the next experiment.

Use this sequence unless the question requires another controlled design:

1. Inspect the fixed-feature baseline model evaluated automatically alongside each candidate.
2. Factor change under that model.
3. Model change using the chosen development features.
4. Optional interaction comparison if the remaining budget permits.

Keep the baseline and failed candidates visible. The host agent chooses the next research action; this package does not reproduce RD-Agent's original stochastic action-selection policy. Matching frozen computations is the reproducibility target, not generating identical research ideas with different agents.

## Report reproduction

Accept a user-provided Markdown/text report or readable PDF. `extract-report --input ... --output ...` creates a text representation with source location information; inspect it before coding. If a scanned PDF or corrupted formula cannot be reliably extracted, ask for an accessible equation or use the host's existing document/vision tools. Do not claim automatic OCR support.

For each candidate record:

- The source file, title or URL and its page/section.
- The exact formula or a faithful mathematical transcription.
- Field meaning, units, publication lag, window definition and missing-value treatment.
- Explicit implementation choices where the source is ambiguous.

Copy the source into the workspace so its hash can travel with the experiment. Use `kind: report`, source evidence, and a `factor_file` or exact `factor_refs` that implement the cited formula. A registry reference does not remove the requirement to reconcile the report's formula and assumptions. Compare both formula correctness and quantitative results. If the source's data, fees or dates are unavailable, describe the result as an adapted reproduction and list differences. Never replace an unreadable equation with a plausible-looking formula without saying so.

The bundled report is a synthetic method note, clearly marked as such; it only verifies this path.
