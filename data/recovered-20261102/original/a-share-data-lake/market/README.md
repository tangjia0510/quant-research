# Tencent public daily A-share price batch

This branch contains **unadjusted daily prices only**, not an investment-ready total-return dataset. Adjustment factors are acquired independently under `../actions/`; joining them requires a separately validated, explicitly named dataset version. Do not silently mix providers or treat an algebraically consistent adjustment as point-in-time certification.

## Scope and progress

Requested dates: 2019-01-01 through 2026-10-30 inclusive. The frozen source master is under `manifests/`; listed securities with any overlap are attempted. Original exchange listings include delisted securities. STAR is included. Beijing coverage depends on verified official code history; a new 920 code is not assumed to recover its former-code history.

`progress.json` is an atomic operational summary. `status/<instrument>.json` is the durable per-security result. The initial bounded pass completes only when every frozen-master security has a terminal record, or a source-access restriction/disk safety stop blocks continuation. Each request uses at most 3 attempts. HTTP 401/403/429/567 stops the entire source immediately, without proxies, challenge solving, or access-control bypass.

States:
- `available`: requested source windows returned and row checks passed. This does **not** mean there are zero missing sessions or that all historical facts are verified.
- `needs_review`: rows were obtained but numeric/unit/overlap checks require review.
- `unavailable`: endpoint returned no usable observations for the requested lifecycle.
- `partial_retry_exhausted` / `retry_exhausted`: bounded request attempts failed; these remain visible rather than being replaced with another stock.
- Global `blocked`: source access or free-disk guard prevents continuation. Pending stocks remain pending, not failed or complete.

## Files and exact units

- `raw/<code>/<window-year>.json.gz`: losslessly compressed response bytes; SHA256 in adjacent receipts applies to the decompressed exact response. The source can return observations outside the requested start; filtering is done only in normalization.
- `normalized/<code>.csv.gz`: raw OHLC, source volume in lots, shares (`lots * 100`), source amount in ten-thousand CNY, CNY (`source amount * 10000`). The per-stock receipt hashes both uncompressed CSV and compressed output.
- `receipts/requests.jsonl`: HTTP attempts and bounded failures, including URL, timestamp, response SHA and byte count.
- `status/<code>.json`: lifecycle, actual dates, row count, missing-session dates, validation findings, source references and normalized hashes.
- `scripts/acquire_tencent_daily.py`: locally authored, standard requests-based serial downloader. It does not execute downloaded JavaScript or third-party repository code.

Normalization does not fill any missing date or price. It checks finite positive OHLC and ordering, nonnegative volume/amount, duplicate dates and cross-window conflicts. For rows with positive amount and volume, amount/volume-derived VWAP must fall within the daily price range with a 2% tolerance for low-value rounding. A failure is recorded and the stock flagged, not silently discarded.

Expected dates use a separately retained observed SSE Composite trading calendar from the earlier same-day verified batch. This is **not independently exchange-certified calendar completeness**. Missing days can reflect suspension or vendor omission. Rows outside the expected calendar are retained and reported. No ST labels, auction observations, historical price limits, intraday bars, or fillability guarantees are inferred.

## Resume

Use the project Python environment containing requests, for example:

    python3 -u a-share-data-lake/market/scripts/acquire_tencent_daily.py --master a-share-data-lake/market/manifests/universe-sharded-with-bse.csv

Do not start a second collector process. The collector uses at most two in-flight requests with one shared start-rate lock: at least 1.05 seconds separates network request starts. Existing verified raw files and terminal records are reused. Resolve an access restriction before restarting a blocked source. Do not rewrite hashes to suppress a validation failure.

The first 30 securities may reuse exact fresh response bytes already downloaded for the independently audited momentum experiment. Their original URL/hash and reuse lineage are recorded. No old withdrawn workbench data are restored.

## Access and rights

Source: Tencent's publicly accessible daily endpoint at `https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get`. Its name contains `proxy`; this is the documented source endpoint itself, not an access-restriction bypass. Initial reachability was HTTP 200; `/robots.txt` returned 404. Neither public availability nor a missing robots file grants redistribution rights. Source licensing/terms remain unspecified in this batch: use for the user's local research, do not publish the raw data publicly or assert an open-data license.

Disk protections: stop new requests if global free space falls below 15 GiB. This market branch has a 15 GiB allocation; monitor branch size in addition to global disk availability.

## Multi-source sharding update

The separate Hugging Face API batch is under `hf_bulk/`, pinned to conversion revision `94d41d1a0f8557682c6acfa829e9fc2c946b4605`. Its 10,946,343 raw rows cover 3,213 main-board codes from 2005-01-04 to 2026-03-03. The normalized price-only view contains 10,943,163 rows after collapsing 3,180 numerically identical duplicates; a securities-name conflict remains in the raw metadata and is not arbitrated in the price view. This partition retains its own source identity and units. HF volume has finer fractional-lot precision than Tencent on many matched rows; it is not altered to mimic Tencent.

For 3,184 securities with sufficient HF start/end coverage, Tencent now requests 2026-03-04 through 2026-10-30 only. For other securities it requests the full 2019 window. Prior Tencent full-history downloads remain unchanged. `requested_start` and `historical_partition` in each status record describe the actual split; do not claim the Tencent partition alone covers every security's full history. No row combines fields from two sources.

The 357 BSE current/inferred identifiers are separate from officially complete historical membership. Missing listing dates and 920-code switch dates remain unknown; vendor-returned pre-2021 observations may reflect earlier NEEQ history. For unknown lifecycles, `missing_sessions` is limited to the observed span and boundary sessions are explicitly unclassified.

To pause cleanly, create `market/PAUSE_REQUESTED`; the collector finishes currently in-flight securities and exits with checkpoint state. Remove this file only before an intentional resume. HTTP 429 is a temporary rate-limit stop, not a failure of all pending securities: respect a supplied Retry-After interval and use one in-flight request on an authorized resumption. Explicit 401/403/567 restrictions remain stopped; never change identity, proxy, or IP to evade them.

## Historical snapshot gaps and exact-row supplements

`hf_bulk/calendar-audit.json` checks the source against the observed SSEComposite calendar for 2019-01-01 through 2026-03-03. The bulk source has **zero rows globally on 2025-05-27 and 2025-11-18**; its maximum date does not establish completeness. Other per-stock gaps can be suspension or provider omission and are not filled synthetically.

`expanded-overlap-audit.json` freezes completed Tencent tail stock statuses and compares the earlier padded Tencent response rows against the normalized HF partition. `historical_supplement/tencent_hf_missing.parquet` contains only real Tencent whole rows whose keys are missing from HF, with source basis and observed-span classification. It is an independent supplementary partition, not a modification of HF. Audit includes input raw hashes and stock-status hashes plus output SHA256. This supplemental output is a partial snapshot until the full download queue and final overlap audit finish; refresh with `scripts/audit_expanded_overlap.py`. Existing complete Tencent histories remain valid independent partitions. Do not sum overlapping source rows as unique coverage or mix OHLC/amount/volume fields across providers. Historical source differences and rights limitations still apply.

### Tencent board-specific volume units (normalizer v4)

STAR securities `sh688*` / `sh689*` report **shares** in the raw K-line volume position; other equity prefixes use **lots**. Normalized `volume_shares = raw * multiplier`, with multiplier 1 for STAR and 100 otherwise; `volume_lots = volume_shares / 100`. Per-stock status records this rule. `star-volume-unit-audit.json` corroborates the distinction across 22 initially retrieved STAR codes / 37,875 dates (VWAP bounds 100% pass using shares and 0% using lots) and compares an independent vendor snapshot; that snapshot has conflicting other fields and is not globally certified. The source API implementation project's [2026-10-07 changelog](https://raw.githubusercontent.com/simonlin1212/a-stock-data/main/CHANGELOG.md) independently documents the same 688/689 rule (not Tencent official documentation). The initial 22 incorrectly scaled normalized outputs are archived under `normalizer_revisions/pre-v4-star-units`; `star-normalization-correction.json` records old/new hashes and correction without network requests. Raw source bytes remain unchanged. Unrelated BSE amount/volume discrepancies remain flagged; the STAR rule is not applied to BSE.

## Completed bounded pass (2026-11-01)

`completion-manifest.json` records final artifact digests. All 5,818 frozen-universe symbols reached a terminal checkpoint: 5,648 available, 168 needs_review, 2 unavailable within requested scope; no active market downloader remains. Tencent normalized partition has 4,130,535 rows. Full CSV/gzip hashes and structural/unit identities passed for all stocks; all 12,419 referenced raw payload hashes passed. This is acquisition/integrity completion, not universal financial-data or tradability certification.

`observed-coverage-union.json/.csv` deduplicates **keys only** across HF raw history, Tencent, and independent exact-row historical supplements, restricted to requested universe and 2019-01-01..2026-10-30: 9,034,591 observed stock-days across 5,816 symbols. 5,571 symbols have an actual 2026-10-30 observation. There are 29,478 absent calendar stock-days within known lifecycle (or observed spans when lifecycle unknown); these include possible suspensions and source omissions, not fabricated prices. Detailed gaps are retained separately. This union is not a materialized blended OHLC price series and includes flagged vendor rows; always consult source and validation state.

Final expanded overlap comparison: 3,041 tail-downloaded stocks, 1,433,296 matched stock-days, no OHLC/amount differences within recorded tolerances. Volume rounding differences remain. Exact Tencent whole-row historical supplement has 6,029 rows across 3,030 symbols for the two globally absent HF dates. Existing full Tencent histories cover other stocks without needing duplicate supplements. HF extends back to 2005 independently, but dates before 2019 are excluded from this union's requested-scope count.

## Bounded latest-date / historical-gap review

`latest-lag-review.json` classifies all 247 symbols lacking an October 30 daily observation: 237 officially delisted with earlier rows; one officially delisted without rows in the requested window (`sh600680`, not proof no historic bars); six active-master symbols with October 30 Tencent quote timestamp, `S` at raw quote index 40 and zero open/volume; two BSE identifiers with earlier rows and unconfirmed lifecycle; one BSE identifier without rows (`bj920085`). Six active-master last dates agree with independent Sina daily API responses. This supports nontrading, but does not itself certify official suspension dates.

After all real Tencent rows and supplements, the two HF-wide missing dates retain 12 absent keys among 3,174 eligible observed-span symbols on 2025-05-27 and five among 3,184 on 2025-11-18. All 17 dates lie within independently retrieved Sina daily spans and are also absent there. These may be legitimate suspensions; no fabricated rows or automatic vendor-error labels were added. A bounded 26-stock independent public API review generated no new missing-target observations and did not modify any price partition. `gap-review-completion-manifest.json` hashes this additional review. Raw response bodies/URLs/SHA/timestamps are retained under `gap_review/raw/`.
