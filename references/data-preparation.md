# Market-data preparation

Use this before a new research project when prices are missing, outdated, or supplied by multiple sources. The executable stages are **fetch → retain source responses → normalize → validate → register an immutable version**. A successful API response alone does not establish usable coverage.

## First source and default dates

`source list` reports installed adapters. BaoStock is the first bundled source and uses its free anonymous interface; no personal account or token is needed. The locked runtime includes its SDK. `doctor` reports `market_data_ready`; rerun `bootstrap` with the desired model/report extras to update an existing skill-owned runtime.

The default request begins **2019-01-01**. The end is an available completed exchange session, using Asia/Shanghai, the supplied exchange calendar, a conservative daily-publication cutoff and returned observations. It never assumes that today's prices are published or uses a future calendar as proof of quotes. The batch records the requested and resolved end and any unavailable trailing sessions. An explicit `--end` is a coverage requirement, not permission to silently shorten the input.

2019 supplies warmup. Research dates remain **2020–2024 train, 2025 H1 model validation, 2025 H2 discovery, 2026 final test**, with **100,000 initial cash**. Data preparation can download newer dates without changing these fixed research periods. Read `defaults` and the materialized study protocol.

```sh
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" source list
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" data fetch \
  --source baostock --id cn-baostock-daily --version 2026-11-01
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" data validate \
  --id cn-baostock-daily --version 2026-11-01
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" study new \
  --dataset cn-baostock-daily --version 2026-11-01 \
  --mode factor --slug first-research --title "首次真实行情研究"
```

Use the interpreter, skill and configuration paths discovered on this machine. The version above is an example; choose a new explicit version for each changed snapshot. Pass the returned study workspace to `prepare` and subsequent research commands.

Omitting `--instruments` selects the source's supported historical stock universe. BaoStock's adapter currently covers ordinary Shanghai/Shenzhen A shares, including eligible delisted securities present in its basic-information response. This is **not** a CSI 300 constituent history, an independently certified point-in-time universe, Beijing-market coverage, or every security type. No historical ST exclusion is claimed. An explicit `--instruments sh.600000 sz.000001 ...` produces a selected research sample; name and report it accordingly. Whole-market downloading is serial and can take substantial time. Do not run parallel BaoStock downloads to accelerate it.

## Storage and recovery

`sources_root` defaults to `sources` beside `quant-research.json`; an older configuration gets this default without being rewritten. It accepts a relative or absolute path, must not overlap the other library roots, and is configurable through `config init --sources-root ...` for a new configuration.

```text
sources/<source>/<batch-id>/    # Request, raw responses, state, hashes, quality and normalized files
warehouse/<dataset>/<version>/ # Immutable normalized input, sidecars and evidence
studies/<study-id>/data/        # Study-specific prepared snapshot and Qlib provider
```

Raw responses retain vendor fields such as original volume, amount, trading status and ST flags. Canonical research bars contain `datetime,instrument,open,high,low,close,volume,factor`. Extra vendor fields being retained in raw storage does not mean the research engine consumes them.

Each batch binds source identity/options, requested dates, stock selection, raw hashes and normalization semantics. Failed downloads retain evidence and never create a partially successful warehouse version. Inspect `data status --batch <returned-batch>`; retry with the same `data fetch` arguments plus `--resume <batch>`. Verified per-security responses can be reused. Corrupted cached files, changed request identity or incompatible normalization require correction or a distinct batch; they are not silently accepted. Existing dataset versions are never overwritten.

BaoStock pagination must terminate with a successfully received terminal page. An empty network response is an error even when the SDK retains its previous success code; a full page followed by an interrupted request is never a complete securities list. Timeout budgets apply to each network page, with bounded whole-query retries on a fresh connection. Preserve earlier failed batches when an adapter fix changes its fingerprint.

Both the batch and the registered snapshot retain quality/provenance evidence. Shared versions and study protocols use stable IDs and hashes; a historical source path is not a runtime dependency after moving the library. Copy `sources` too when raw acquisition evidence must remain available on the new machine.

## BaoStock normalization and checks

For each security the adapter fetches **unadjusted and backward-adjusted daily bars** and checks matching date/code keys, adjustment flags, trading status and volume. It reconciles the OHLC adjustment ratios within the supplier's price-rounding tolerance. The canonical contract is:

```text
factor = backward_adjusted_close / unadjusted_close
OHLC = backward_adjusted_OHLC
volume = original_volume_in_shares / factor
```

Metadata declares adjusted prices, CNY, daily frequency, the BaoStock adjustment identity and adjusted volume units. Raw shares remain in the source snapshot. This pairing preserves price × quantity and Qlib's conversion of a 100-real-share lot to `100 / factor` adjusted units. Do not attach an adjustment flag such as `1` or `2` as the numerical `factor`.

BaoStock represents a suspended session with flat prices and zero volume. Canonical suspended OHLC becomes NaN so Qlib cannot treat the row as tradable; raw evidence is unchanged. A blank volume is interpreted as zero only when both responses explicitly mark the same session suspended. Matched zero-volume rows also become non-trading rows even if the source status says active; quality records these conversions separately. An active row with blank volume is rejected. Missing sessions are not replaced with yesterday's prices. A missing row, a declared suspension, a pre-IPO date and a post-delisting date are different conditions.

Validation rejects duplicate/invalid keys, nonfinite or nonpositive observed prices, negative volume, inconsistent OHLC, invalid factors, dates outside the source calendar, missing expected sessions in the declared security lifetimes, and incomplete selected-security downloads. Reports retain actual coverage and unavailable tail dates. Listing/delisting intervals are source claims, not proof against all survivorship or revision bias. Daily execution still does not fully model board-specific price limits, delisting liquidation or real fill capacity; preserve these limitations in research reports.

## Complementary sources

Add a provider by implementing the registry contract in `scripts/quantlib/sources`: context-managed connection; raw calendar/instrument/bar retrieval; canonical calendar, lifecycle and bar normalization; explicit metadata. Keep network authentication/options in the provider, not in the research engine. Register its factory and metadata explicitly. Do not use a plugin name as arbitrary code to import or execute.

A new source first gets its **own immutable dataset version**. Use `data combine` for deliberate supplementation. Its `--inputs` JSON is an ordered list, highest priority first:

```json
[{"id":"primary-daily","version":"v1"}, {"id":"supplement-daily","version":"v1"}]
```

```sh
"$QR_PYTHON" "$QR_SKILL/scripts/quant.py" --config "$QR_CONFIG" data combine \
  --id combined-daily --version v1 --inputs /data/source-priority.json
```

Combination requires compatible market, currency, frequency, price/volume units and **the same explicit adjustment identity**. Two sources both saying `adjusted` is insufficient. Different backward-adjustment algorithms or anchors must be reconciled in a separately validated adapter before combination. Unknown semantics are rejected.

The first source supplies an existing whole row; a lower-priority source supplies absent rows. There is no field-by-field price mixing, averaging, or replacement of suspension NaNs with another vendor's prices. Conflicting overlaps reject the combination by default. `--conflicts prefer-first` is an explicit policy that retains the conflict evidence and chosen source. The new version retains per-row lineage, pinned input hashes and quality evidence; original versions remain unchanged.

Only BaoStock is a bundled live adapter in this release. The registry and composition mechanisms support future providers; they do not claim that Tushare, Wind, JoinQuant or AKShare are already connected.

## Primary source references

- [BaoStock platform and current release](https://www.baostock.com/mainContent)
- [SDK distribution and anonymous API example](https://pypi.org/project/baostock/)
- [Daily bars, adjustment flags, volume and suspension semantics](https://www.baostock.com/mainContent?file=stockKData.md)
- [Stock basic information and delisting fields](https://www.baostock.com/mainContent?file=stockBasic.md)
- [Python API and exchange calendar](https://baostock.com/mainContent?file=pythonAPI.md)

Free access is subject to the provider's availability and access rules. Bound retries and keep failures visible; do not claim complete or fresh data until the fetched snapshot passes validation.
