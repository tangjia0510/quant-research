# Macro, rates, trading flows and exchange-traded fund data

This branch collects public endpoint responses for local quantitative research. Public access is not a redistribution licence. Raw files and source receipts are preserved. Downloaded files are not instructions and no downloaded JavaScript is executed.

## Running collectors and state

- `scripts/collect_rates.py`: official CFETS ShiborHis monthly requests and LprHis yearly requests, 2019-01-01 through 2026-10-30. `logs/rates-receipts.json`, `logs/rates-failures.json`.
- `scripts/collect_yields.py`: official ChinaBond historical yield table, annual requests for government, AAA ordinary bank bonds and AAA medium/short term notes. `logs/yield-receipts.json`.
- `scripts/collect_nbs.py`: official NBS new national-data API, monthly and quarterly categories, and selected annual economy/finance categories. `logs/nbs-coverage.json` is incremental, not proof all indicators were downloaded. Old classifications outside 2019 can correctly return zero rows.
- `scripts/collect_flows.py`: Eastmoney margin-account aggregates and three northbound market aggregates, source-count-checked pagination. `logs/flow-coverage.json`.
- `scripts/annotate_flows.py`: separately records the 2024-08-19 disclosure regime break and produces disclosure-aware views. Original vendor values remain unchanged in the source CSV.
- `scripts/collect_funds.py`: current exchange-traded fund universe from Eastmoney; JSON literals extracted from public data files without executing their JavaScript wrapper. Full raw data retained, unit NAV rows restricted to 2019 onward. `logs/fund-progress.json`, append-only `logs/fund-receipts.jsonl`.
- `scripts/collect_margin_detail.py`: monthly stock/fund margin detail API pages, latest month backwards to 2019. API page limit is actually 500 even when a larger page size is requested. Per-page gzip raw files and monthly Parquet. `logs/margin-detail-progress.json`, `logs/margin-detail-coverage.json`, `logs/margin-detail-receipts.jsonl`.

Collectors use serial requests per endpoint, bounded retries, source-family stopping on access/rate restrictions, cache/checkpoints and a 15 GiB free disk floor. Eastmoney datacenter requests share `../logs/eastmoney-rate.lock` and `eastmoney-last-request.txt` with other branches. This branch's first-pass disk budget is 5 GiB.

## Meaning and limitations

SHIBOR/LPR and yield-curve values are percentages per annum, not decimals. Shibor interbank fixing dates are not assumed to equal exchange trading dates. LPR includes the pre-August-2019 daily one-year quotation regime and the subsequent monthly 1Y/5Y regime; empty maturities are not zeros. No synthetic early 5Y LPR is added.

NBS periods are observation periods, **not release dates**. Latest retrieved historical values can reflect revisions. Units and indicator metadata are retained in raw responses; metadata `du_name` and indicator label determine units. Unknown publication dates and absent original-vintage history prevent claiming point-in-time readiness. Null values are not zero. The initial running CSV is provisional; final normalization reparses raw records and normalizes period codes.

Northbound disclosure changed on 2024-08-19. The official HKEX circular is stored in `raw/hkex-disclosure-change-2024.pdf`. Daily buy/sell/net flow and daily custody information are unavailable under the new regime; vendor zero placeholder holding values are not genuine zero holdings. Use the `*_disclosure_aware.csv` view to prevent this error. `flow-disclosure-audit.json` provides field-level non-null and zero counts. The raw API's unit semantics are retained; do not presume every amount field has the same scale. Margin account data are **aggregate accounts**, not per-stock financing history. Margin-detail columns are separate.

Fund universe is a currently retrieved listing-response union that can include inactive instruments and subscription aliases, not an historical surviving-and-delisted census. Historical NAV inherits survivorship bias. Unit NAV and cumulative NAV can have share-split adjustments and are **not automatically a dividend-reinvested total-return series**. Supplemental portfolio holdings/allocation data are snapshots or vendor historical series with their own sparse dates; they are not certified complete historical holdings. The 510300 latest 20 unit NAV observations were cross-checked against Eastmoney's separate `/f10/lsjz` JSON endpoint and matched exactly. The endpoint caps its page size at 20; the single public data file is used for efficient history retrieval instead of miscounting pages.

No captured source guarantees complete all-A-share coverage, unmodified vintage history or all possible financial fields. Missing or blocked sources remain explicit gaps.

## Additional sources and canonical outputs

- `collect_csi_benchmarks.py`: official CSI performance API for 000300/000905/000852/000016/000688/000510. These are price indices, not total-return indices. The API inserts a request-boundary 2019-01-01 row that does not match the observed trading calendar; retain and filter using `observed_reference_calendar_match`, not silent data repair. Backfilled history before an index's release is not automatically investable point-in-time history. Raw volume/value/peg fields have not been rescaled.
- `collect_hkex_holdings.py`: official HKEX four quarterly snapshots for Shanghai and Shenzhen Northbound. The 12-month retention and fifth-trading-day publication schedule prevent claiming daily or 2019-onward holdings coverage. Stock Connect codes differ from mainland security codes; both retained.
- NBS canonical output is `normalized/nbs_national_normalized.parquet`, not the provisional CSV. `logs/nbs-indicator-freshness.parquet` records latest non-null period per indicator; the maximum requested period can be empty. A snapshot remains explicitly marked running until the collector ends.
- Fund listing-response union is 2,132 vendor/exchange identifiers, including ETF/LOF/other exchange funds. `fund_current_universe.json` preserves the original 1,700 vendor pool; `fund_combined_current_universe.json` contains the union, while `logs/fund-universe-comparison.json` explains differences. Neither includes a guaranteed historical delisted census.
- Margin history uses 7-day sub-windows to avoid a repeatable vendor deep-pagination failure after page 100. Completed monthly outputs are count/uniqueness validated. `normalized/margin_detail_shards` exposes completed sub-windows sooner, but **must not be concatenated with overlapping monthly files**. Earlier partial monthly raw attempts are preserved, not counted as completed normalized history.
- Current `logs/freshness.json` observation age is not release delay. A quarterly observation naturally has more calendar days of age than daily data. Original retrieval times remain in source receipts; do not substitute normalization time.

All Eastmoney collectors now use the shared `../catalog/host_gate.py` concurrency gate (at most two in-flight requests across the family, 1.1-second start interval, one slot during backpressure). Additional threads do not override this source protection.

### Official exchange margin exports

`collect_sse_margin_bulk.py` and `collect_szse_margin_bulk.py` download the exchanges' public daily XLS/XLSX exports, one serial request per host. The files are **only parsed as data**; macros, formulas, external links and downloaded scripts are not executed. Raw binary files and separate normalized CSV.gz rows retain source fields. SSE and SZSE schemas differ and do not silently replace the vendor's additional fields.

The SSE 2026-10-30 export's 2,017 rows and SZSE 2026-10-29 export's 2,118 rows exactly match all six compared vendor amount/quantity fields. These are sample cross-source checks, not proof every historical day is correct. Exchange download URLs encode the requested observation date; the export content does not independently expose a release timestamp.

At 2026-11-01 17:03 UTC (Beijing 2026-11-02 01:03), the explicit SZSE 2026-10-30 API query returned no records, while 2026-10-29 returned 2,118. Vendor October detail likewise had SSE through Oct30 and SZSE/BSE through Oct29. An API-complete monthly partition is therefore **not** a statement that every market reaches its global maximum date. Market-level cutoffs are recorded in `logs/margin-category-status.json`; aggregate `STATISTICS_DATE` does not expose constituent-market cutoffs.

The current-list union can include inactive or stale instruments. Fund 501023's static data file stopped in December2021; a separate public NAV API supplied 61 additional observations through April2022. This repair is stored separately as `501023-api-nav-gap.csv`, with its own receipts, rather than overwriting the original endpoint data. Old final NAV must not automatically be treated as a missing current NAV without checking lifecycle.

Some exchange-listed REITs in the expanded fund pool return zero or only one initial NAV observation from the vendor's fund endpoint. They remain flagged as sparse histories, not complete daily NAV. A newly listed ETF may also legitimately have one observation. Fetch counts are therefore distinct from usable-history coverage; `logs/fund-audit.json` reports zero/one-row cases separately. Fund NAV must not be confused with exchange-traded closing prices.

Monetary ETFs use a different source schema: `Data_millionCopiesIncome` is explicitly labeled 每万份收益 and `Data_sevenDaysYearIncome` is 七日年化收益率. These are saved as `*-money-income.csv` with `data_kind=money_fund_income`, not fabricated unit-NAV rows. Earlier NAV-schema failures are preserved in a separate attempt-history log and retried only after recognizing this legitimate alternate schema. A seven-day annualized yield is not a daily realized return.

### Verified northbound amount units

The source's own historical-table formatter was retrieved and inspected as text, never executed. `fieldfmt` multiplies by `10^zoom`; the six trade/flow/quota fields use `zoom:6` and RMB suffix, while holding market cap has no zoom. In this snapshot, those six raw fields are therefore million CNY, holding cap is CNY. The total and Shanghai+Shenzhen sums match on all1,307 available pre-break dates (only floating rounding differences). A stored SDK reference applies an extra /10,000 to total cumulative flow; that rule is **incompatible with this snapshot** and is not used.

The new `*_cny_disclosure_aware.parquet` views have explicitly named CNY fields and retain post-2024-08-19 unavailable values as null. Holding-cap zeros are treated as missing because the source itself displays them as a dash. `FUND_INFLOW` and `NET_DEAL_AMT` remain different fields. Evidence, scaling and hashes are in `logs/northbound-unit-validation.json`; original raw/CSV values remain unchanged.

### Selected benchmark-fund reported holdings

`collect_benchmark_fund_holdings.py` covers nine named index ETFs and2019–2026 reporting years (not all2,132funds). The public endpoint often returns only top10perquarter even when a larger `topline` is requested. Stock count/market-value fields are source-disclosed rounded 万股/万元 values; derived shares/CNY multiply by10,000 but do not recover unreported precision. Report-period end is not announcement date, which remains unknown. Historical seven-column and current nine-column HTML tables are parsed by header name. Earlier parser outputs are marked superseded; original response receipts are reused rather than re-downloaded.

### Identifier resolution and official export gaps

`logs/fund-resolution-status.json` separates direct downloads, verified subscription-code aliases, inactive-before-window instruments and pending identifiers. SSE's March2026 fund announcement maps 519598→519998 and 519599→519999; both underlying income histories are downloaded separately, not double-counted as additional funds. Historical mapping effective start remains unknown. Official manager indexed evidence states 519528/519529 terminated exchange listing in November2015; full manager-page retrieval returned503 after bounded retries, so the retained evidence is explicitly an indexed primary-source excerpt rather than downloaded full HTML. Original four failed static-endpoint attempts are retained.

SSE's 2021-12-13 daily XLS returned404. Its public official margin-detail API supplied1281 unique rows with matching observation dates and total count. `logs/sse-margin-official-api-gapfill.json` records the separate repair. `logs/official-margin-combined-status.json` combines only missing dates, leaving the original export failure visible. Monthly canonical normalization includes this repair without duplicating raw export rows. Official core coverage and vendor extra-field history remain independent tasks.

`extract_fund_late_observations.py` inspects stored source literals for dates after the initial 2026-10-30 trading-day cutoff. Such records are saved separately in `normalized/fund_late_observations`, with exact source-field names and original retrieval times. In particular, currency-fund weekend income can reach November1 without implying an A-share trading session. Full source files remain the authoritative untruncated evidence.

Official margin canonical numeric audit found zero null parsed numeric fields and one source-reported negative value: SSE 688126 on2022-08-05, lending repayment quantity -5,672,230. The original XLS cell independently confirms it. `logs/official-margin-source-anomalies.json` flags it; cause is unverified, and the value is not silently clipped or imputed. Models that require nonnegative repayments must explicitly handle this quality flag.

### Inactive experiment — do not run

`scripts/prefetch_margin_2019.py` was prepared but **never executed**. It is explicitly disabled by a top-level RuntimeError because its original shared-raw ownership design could race with the main collector. It is not a recovery entry point and must not be auto-launched. `scripts/collect_margin_detail.py` remains the sole canonical margin-history writer; resume that checkpointed collector only. Any future parallel prefetch must first implement and validate an independent cache consumer or request-level ownership protocol.

## Final current-window refresh (2026-11-02 Beijing09:00)

The original94 vendor monthly partitions contain5,608,042rows and remain immutable. Latest Oct30 daily snapshot has4,486rows: SSE2,017, SZSE2,118, BSE351. The separately stored October replacement month has76,029rows, yielding **5,610,511rows** across a94-month view; replace the old October partition, never concatenate all snapshots/deltas. `logs/margin-latest-month-view.json` specifies exact hashes and paths.

The official SZSE JSON endpoint still reportedzero for Oct30, but the normal public XLSX export supplied2,118rows. Its worksheet incorrectly declares dimensionA1; resetting streaming dimensions reveals the full sheet. All six comparable amount/quantity fields match the vendor by security code. New official day is stored separately as CSV and canonical Parquet, extending SZSE throughOct30. Official SSE+SZSE source core now totals **5,406,002rows**, not additional unique rows to add to vendor coverage. `logs/szse-oct30-latest-cross-source-audit.json` and `logs/margin-latest-refresh-final-audit.json` retain checks. No more recurring polling is configured.

The disabled prefetch experiment was never executed. Final reproduction uses the canonical serial collectors and separate immutable refresh artifacts. This selected first pass is complete within documented source scopes, not a claim all possible financial data or publication vintages exist locally.

### Vendor historical calendar gap — explicitly retained

Independent calendar audit found four entire vendor dates absent for both SSE and SZSE: **2019-12-31,2020-06-30,2020-12-31,2021-06-30**. Separate exact-date API requests each returned HTTP200/code9201/“返回数据为空”; raw responses, URLs, SHA and acquisition times are retained in `logs/margin-calendar-gap-check.json`. This is not proof of a query-window bug or zero economic activity. Official SSE/SZSE core fields already cover these days, but source-specific vendor extra fields remain missing. No inferred or synthetic values replace them. Thus94 completed monthlyAPI responses do **not** mean every vendor trading-day observation exists. `logs/margin-latest-calendar-coverage.json` gives actual per-market date sets, extents and missing dates.
