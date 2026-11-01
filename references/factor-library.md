# Versioned factor library

Use this reference to find, reuse, validate or register a factor. `config show` reports the effective `factor_root`. Its default is `~/quant-research/factors`; with a custom configuration, the default `factors` directory is relative to that configuration file. Set `--factor-root` during `config init`, or edit the existing configuration deliberately after copying the library to its new location.

## Identity, files and evidence

Every shared factor has a lowercase portable ID and an explicit semantic version such as `1.0.0`. Preserve legacy names in `display_name` and `aliases`; aliases are descriptive and do not replace exact ID/version references. Do not use `latest` in a candidate.

```text
<factor_root>/
├── index.json
├── index.md
├── <factor-id>/<version>/
│   ├── definition.json       # Formula, contract, origin, limitations and admission decision
│   ├── factor.py             # compute(frame, params); absent for rejected records
│   ├── provenance/           # Original code and retained historical evidence, when available
│   └── manifest.json         # Relative payload paths and SHA-256 hashes
└── validations/<factor-id>/<version>/
    └── <timestamp>-<unique-id>.json
```

`factor add` copies the package, creates its manifest and refuses changed content under an existing ID/version. Validation receipts are append-only outside the immutable package. A later failed validation does not delete an earlier pass, and a later pass does not erase a failure. The index is derived and can be rebuilt; the package and receipts are the evidence. Resolving a factor verifies its complete payload, including unexpected or missing files.

## Initialize and inspect

Use the same interpreter and configuration as the study:

```sh
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" factor seed --validate
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" factor list
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" factor show \
  --id deltab5 --version 1.0.0
```

`factor seed` installs the bundled packages into the configured library. Repeating it reuses identical packages; it never overwrites local changes. `--validate` executes the registered implementations through the current factor contract and saves receipts. An ordinary study reuses the existing library; it does not repeatedly seed or validate every package.

The initial collection contains five built-in features and eight adapted historical factors, all at version `1.0.0`, plus a rejected historical record:

| Origin | Registered IDs |
|---|---|
| Built-in features | `return_5`, `volatility_20`, `momentum_20`, `range_position_20`, `volume_ratio_5` |
| Bollinger study | `deltab5`, `squeeze20_40` |
| Bollinger/XGBoost study | `r1_band_volume_trend`, `r1_range_pos20`, `r2_band_dir_persist`, `r2_expand_on_volume` |
| Strategy-discovery study | `rev_r1_vol_dryup5`, `rev_r1_range_pos20` |
| Rejected strategy-discovery record | `trend_r1_trend_range_pos55` |

The eight historical adapters preserve original output names, original source hashes and source-study identifiers. Original archived files remain unchanged. Inspect `output_columns` before combining them: an ID such as `r1_band_volume_trend` produces the legacy column `band_volume_trend`. Formula-equivalence notes identify the three range-position records and the two volume-ratio records without merging their separate provenance. These are 13 reusable records, not a claim of 13 independent signals.

## Use a registered factor in a study

For an existing prepared factor study, a candidate can be:

```json
{
  "id": "deltab5-v1",
  "kind": "factor",
  "hypothesis": "Test whether the five-session change in Bollinger position adds information to the fixed baseline.",
  "features": ["return_5", "volatility_20"],
  "factor_refs": [{"id": "deltab5", "version": "1.0.0"}]
}
```

Save the candidate JSON inside the workspace and pass its absolute filename to `check`, then `evaluate`, for example `--candidate "$WORKSPACE/inputs/deltab5.json"`. The CLI resolves a relative candidate filename from the current working directory; paths inside the JSON (`factor_file`, `model.file`, `source.path`) are workspace-relative. Factor, joint and report candidates require `factor_file` or a nonempty `factor_refs` list. Report mode still requires its source evidence, and joint mode still requires its model definition. Registry definitions supply each referenced factor's lookback and scale contract. The bundled factors have fixed formulas and accept no parameter overrides; revise the package version to change a formula.

At registration, the study snapshots the selected packages and pins their manifest hashes and validation summaries. Subsequent computation uses those snapshots, so moving or removing the shared library does not redirect an existing candidate to different code. A new candidate must resolve the exact versions again. Keep factor columns unique across `features`, references and a custom `factor_file`.

In factor, joint and report modes, referenced factor outputs are candidate additions. The comparison removes these additions and uses the declared baseline features and protocol model. In model mode, references are fixed inputs shared by the candidate and its baseline. Existing built-in `features` and workspace-local `factor_file` workflows remain supported.

## Register new factors

Write drafts under the study workspace, for example `drafts/my_factor/`, with `factor.py` and `definition.json`. `factor.py` follows [the factor contract](contracts.md#factor-implementation). A minimal reusable definition is:

```json
{
  "schema_version": 1,
  "factor_id": "my_factor",
  "version": "1.0.0",
  "display_name": "My factor",
  "aliases": [],
  "description": "State the intended mechanism and observable input fields.",
  "formula": "Write the exact mathematical definition, including missing-value rules.",
  "output_columns": ["my_factor"],
  "parameters": {},
  "max_lookback": 21,
  "scale_invariant": true,
  "status": "accepted",
  "limitations": [],
  "source": {"kind": "study", "study_id": "the-source-study-id"},
  "validation_context": {"research_effectiveness": "not established"}
}
```

Choose actual lookback and scale behaviour for the formula; the numbers above are examples. Include source passages, original code or review evidence under `provenance/` when available. Keep credentials, raw market data and unrelated study artifacts out of the package.

```sh
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" factor add \
  --source "$QR_WORKSPACE/drafts/my_factor"
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" factor validate \
  --id my_factor --version 1.0.0
```

The shared result is `<factor_root>/my_factor/1.0.0/`. Later studies reference that exact ID/version. Keep experimental results in their originating studies and identify them in provenance; a factor package is not a replacement for a study. A code, formula, contract or provenance change gets a new version. An implementation awaiting review should not be presented as validated merely because `factor add` accepted its package structure.

## Validation and historical restrictions

The displayed validation status is `unvalidated`, `passed`, `passed_with_limitations`, `failed` or `rejected`. Current receipts apply to a specific manifest hash; a receipt for other bytes cannot validate this version. Historical checks remain historical provenance. `factor validate` uses a deterministic synthetic panel to test the implementation, row contract, causality and declared lookback/scale properties. `check` also exercises the selected factor on the study's real inputs. Neither test establishes a profitable or robust investment signal.

`R2_expand_on_volume` retains its recorded scale sensitivity: `scale_invariant` is false and the limitation stays visible even when implementation checks pass. Do not infer from a skipped scale test that the factor is invariant.

The TREND rejection is retained and cannot be selected as an executable accepted factor. The historical group was rejected because its sibling `TREND_PATH_QUAL55` needed 61 price observations, exceeding that study's frozen 60-observation limit. This is a group-level historical rejection, not a claim that `TREND_R1_TREND_RANGE_POS55` itself necessarily requires 61 observations or is mathematically invalid. Preserve the rejection and original diagnostics; a different research protocol must create a separately reviewed version rather than rewriting the historical decision.

Relevant provenance also retains earlier proposal rejections, the date-filter repair and the REV failure/recovery record. They describe the original research history and are not relabelled as current adapter failures or successes.

Move the complete factor directory, including validation receipts, alongside the warehouse and studies. No original RD-Agent checkout, HDF5 file or old absolute source path is required to execute an adapted registered factor. Rebuild the runtime on the new machine and inspect `factor list` and `index refresh` before further research.
