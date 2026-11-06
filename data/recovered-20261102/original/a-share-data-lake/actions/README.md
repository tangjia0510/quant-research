# Corporate actions, adjustment factors, and security status

This branch acquires public web data interfaces for local research. These are vendor website APIs, not contractual guaranteed SDK feeds. Raw responses, source URLs, retrieval times, hashes, parser code, and gaps are retained. It does not modify the registered momentum study.

## In-progress datasets

- `raw/sina_factors/` and `normalized/factors/`: Sina historical multiplicative HFQ series. JSON is decoded from a JavaScript wrapper; remote JavaScript is never executed. The original decimal text is preserved. A `1900-01-01` row is a vendor base-factor sentinel, **not a genuine listed/traded observation**. Factors are a currently downloaded retrospective series; historical PIT availability or vendor revisions are not certified. The normalization to raw OHLC and share volume is a downstream explicit step, not performed here.
- `raw/eastmoney_sharebonus/` and `normalized/sharebonus-all.csv`: report `RPT_SHAREBONUS_DET`, source report pagination and row counts verified. Contains plans at different stages, not only paid dividends. Original ratios are per 10 shares; plan profile and stage are preserved. Ex-date, record date, proposal/notice dates are distinct. **Cash-payment dates are not supplied by this table and must not be inferred from ex-date.**
- `raw/eastmoney_equity/` and `normalized/equity-all.csv`: report `RPT_F10_EH_EQUITY`, retrospective share-capital event snapshots. Announcement and effective dates remain separate. Future announced changes can occur in the source; they must not be treated effective before END_DATE. No daily forward filling or reconstruction is performed. Vendor universe may include listings outside the official A-share master; consumers must join source security identifiers explicitly.

## Checkpoints and safe use

`catalog/*-status.json` are atomic, per-dataset progress records. `status=running` is not complete. Factor input is frozen in `catalog/universe-input.csv/json`; later STAR/BSE additions require a new explicit frozen batch and do not silently alter an active run. Securities unavailable or unattempted remain explicit gaps. Historical BSE codes and new 920xxx codes must be identity-mapped by the reference branch, not guessed.

Raw receipts include HTTP outcomes and SHA256. Existing successful 30-stock factor payloads are reused only if hashes match their original receipts. There is no result-based stock selection, price filling, or deletion of delisted records.

Sina requests share `../logs/sina-rate.lock` and last-request timestamp with a 1.05-second minimum start interval. Eastmoney requests share `../logs/eastmoney-rate.lock` and timestamp with 1.1 seconds minimum. Individual calls have bounded timeouts and at most three retries with backoff. HTTP 401/403/429/567 stops the affected operation; no proxy, IP override, credential, or challenge bypass is used. No account or paid access is introduced.

Budget: this branch is limited to 8 GiB; stop new acquisitions if filesystem free space falls below 15 GiB. Source and output availability must be inspected before any use in a backtest. Successful transfer and internally consistent parsing do not certify financial accuracy, historic completeness, PIT correctness, or investment suitability.

## Suspension snapshot caveat

`normalized/suspensions-all.csv` is the public vendor response for the documented date query `DATETIME=2019-01-02`. It contains 2,362 distinct securities with one row per security, including events beginning before that query date and future already-announced events. It is therefore catalogued as a **current per-security latest-event snapshot**, not an exhaustive suspension-event history, not 2019 point-in-time knowledge, and not a historical daily tradability mask. Expected resume dates do not prove actual resumption. Historical ST names, suspension histories, price-limit histories, and dividend payment dates remain separate coverage gaps unless another cited dataset explicitly supplies them.

## Additional API event tables

- Rights issues (`rights-all.csv`, RPT_IPO_ALLOTMENT): 982 source records, 640 securities, record dates 1991-05-31–2026-08-12. Rights price, payment subscription window, pre/post issue capital and listing dates are preserved. These payment windows are **rights subscription**, not cash-dividend payment dates.
- Seasoned equity offerings (`seasoned_offerings-all.csv`, RPT_SEO_DETAIL): issue date, shares, offer price, lock-up and listing date as supplied. Source row units are retained; quoted latest prices are not point-in-time features.
- Buybacks (`repurchases-all.csv`, RPTA_WEB_GETHGLIST_NEW): proposed and executed values/statuses retained, including future dated updates. Plans are not completed buybacks.
- Restricted-share unlocks (`unlock_events-all.csv`, RPT_LIFT_STAGE): 2019-01-01–2026-10-30 query. Original vendor amounts/shares are in 10,000-unit fields per the reference documentation; no unlabelled conversion is applied. The table includes post-event returns and current quote fields, which are look-ahead data and must not become historical predictors.

`catalog/event-field-quality.json` audits source fields. Six dividend rows have cash ratios differing from the plan-profile text; both original values are retained and flagged, not silently replaced. `normalized/current-name-risk-flags.csv` only classifies the current name string; it is not a historical ST classification.

## Independent reported price-limit fields

`normalized/hf_price_limits/` is a selected-column projection of the market branch's separately downloaded, fixed-revision Hugging Face snapshot. `normalized/hf_price_limits_unique/` removes 3,180 verified numeric-identical duplicates on 2025-12-18 and adds a quality flag; original input bytes remain intact. Full history: 535,243 null limit pairs and 754 rows with observed close outside provider bounds. Since 2019: 221 null pairs and one out-of-bounds observation (600610.SH, 2020-08-17). These are not exchange-certified execution limits. No limit rule, ST rule, or tradability mask is inferred. All source limitations, licence uncertainty and the 2026-03-03 endpoint remain applicable. Projection and duplicate manifests keep source hashes and row counts.

## Concurrency upgrade

After 383 checkpoints, the single-worker Sina job was stopped cleanly and resumed with `fetch_factors_parallel.py`: two worker threads, **two globally shared host slots maximum**, request starts at least 1.05 seconds apart. Its frozen combined batch has 5,917 identifiers (5,560 official SH/SZ and 357 BSE identifiers from financial/CNINFO reference evidence). Earlier universe batch files remain immutable. All Eastmoney calls also use the shared `catalog/host_gate.py`, globally two slots and 1.1-second start spacing. HTTP 429 signals backpressure and stops this branch's operation; it is not a reason to rotate identities or bypass restrictions.

## Vendor historical status sidecar

`normalized/hf_status/vendor-daily-status.parquet` contains 4,934,625 unique code-days for 5,148 codes, 2021-01-04 through 2025-04-23. Full 9,782,068 input rows were checked: 4,847,443 repeated rows, zero is_st/is_paused conflicts or non-binary values. ST flagged days: 112,630. `catalog/hf-status-audit.json` records original file hashes and derived output hashes. This is only a field-specific structural audit: the full feature dataset stays quarantined, underlying rights remain unverified, and the historical flags are not exchange/PIT certified. All-zero paused values do not prove absence of suspension. No gaps are filled to latest date; current official risk snapshots are separate observations, not historical intervals.

## Completed share-capital history

`equity-all.csv`: all 651 pages, 325,165 exact-unique provider rows (includes non-A instruments). `equity-universe.csv` is an exact `SECUCODE` join to frozen 5,917 identifiers: all 5,917 matched, 174,174 rows, of which 94,886 have effective dates from 2019-01-01 through 2026-10-30. 29 future-effective rows are preserved, not considered applied (latest 2026-11-11). No BSE alias stitching or daily forward filling. `equity-universe.json` contains input/output hashes and exclusions. Source-history availability is not historical-vintage availability; use announcement and effective dates separately.

## First-pass final factor result (2026-11-01)

All frozen 5,917 identifiers attempted: 5,915 successful (SH 2,465; SZ 3,094; BJ 356), two vendor-empty histories (`sh.689009`, `bj.920085`). The 72,357 rows include 5,915 pre-1990 basis sentinels, not real event dates. Do not assign missing factors to 1. All raw and normalized hashes and factor/date values pass `factor-integrity-audit.json`; zero unattempted and zero integrity issues. Maximum effective date is 2026-10-30, last snapshot retrieval 2026-11-01T18:08:15Z. Snapshot freshness is not historical-vintage/PIT certification or price coverage. Both acquisition jobs finished normally.

### Final bounded gap review

`catalog/factor-two-gaps-review.json`: sh.689009 has four implemented cash-dividend records in the independent source, so the empty Sina factor result is not proof of no corporate actions. bj.920085 remains an inferred CNINFO mapping with unknown IPO date and five equity events; absence of dividend/daily rows does not certify factor 1. The documented independent BaoStock factor API is unavailable in this environment according to the normal-endpoint DNS/login evidence; no bypass or repeated probes used.

`catalog/factor-basis-provenance.json` verifies every successful raw JSON: all 5,915 basis rows are exactly source date `1900-01-01` and factor string `1.0000000000000000`. No sentinel or missing-value factor was manufactured. File-level URL/hash evidence is included.

Offline helper commands (run from workspace root):
```
python a-share-data-lake/actions/scripts/audit_factors.py
python a-share-data-lake/actions/scripts/audit_raw_pages.py
python a-share-data-lake/actions/scripts/audit_event_tables.py
python a-share-data-lake/actions/scripts/summarize_actions.py
```
These update audit catalogs; regenerate the artifact manifest afterward if run again.

Final normal-endpoint recovery check at 2026-11-01T18:14:26Z used unmodified BaoStock 00.9.40 default SDK login, bounded by 30 seconds; login still failed 10002007 / Broken pipe. No factor/basic query executed, no endpoint override or fallback IP. Evidence: `catalog/baostock-two-gap-check.json` and `logs/baostock-two-gap-check.log`. No further requests scheduled.
