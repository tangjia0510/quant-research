# Recent 1-minute API observations

Public source: Sina `CN_MarketDataService.getKLineData`, the unadjusted route documented by AKShare's official source `akshare/stock/quote/stock_zh_a_sina.py`. The reviewed reference is text only in `probes/akshare-source-reference.txt`; none of that downloaded code is executed. JSONP is parsed as JSON, never evaluated.

Frozen query: `scale=1`, `ma=no`, `datalen=1970`, one normal request per instrument (up to three bounded technical attempts), 5,818 identifiers from the existing reference price universe. Source may return fewer records or stale historical records. This is a recent-window collection, **not** full 2019–2026 minute history, tick data, or order books. No derived intervals are generated.

The expected latest complete exchange day is 2026-10-30. Returned timestamps are preserved as exchange-local `Asia/Shanghai`; source strings carry no explicit offset. Actual first/last timestamp and target-day presence are in each status record. More recent observations, if any, are retained but flagged, not silently accepted as complete-day data.

Minute `volume` is normalized as shares for the sampled SH/SZ/STAR/ChiNext/BJ instruments, unlike Tencent daily's board-dependent volume units. Evidence is `catalog/probe-unit-audit.json`: amount/volume tests plus independently normalized daily-volume and OHLC comparisons. This is evidence-based unit interpretation, not a vendor contractual unit guarantee. Residual price/amount mismatches (especially BJ) retain original values and `needs_review`; no guessed multiplier correction is applied. Amount is CNY. Prices are unadjusted according to the documented route and sampled daily-price comparison.

No-trade/auction intervals may be absent. Many active names return 238 rows on a trading day, and sparse securities fewer. There is no imposed 240-bar completeness assumption or filling of absent minutes. First day is usually truncated by the source window. Minute sums can differ from daily source totals; observations do not prove complete transaction coverage.

`raw/` contains gzip-compressed exact response bytes with per-attempt receipts: URL, UTC retrieval time, HTTP status, original/compressed SHA256 and sizes. `normalized/` contains gzipped CSV. `catalog/status/` stores source outcome, quality flags, normalized SHA and observed dates. Empty responses are unavailable, not zero-price series. Source failures stay separate from numerical warnings.

The collector uses the shared global Sina gate, at most two in-flight requests and a minimum 1.05-second start interval across workers. Access-denial responses stop the source. HTTP429 would signal shared reduced concurrency and pause the affected worker; this completed pass encountered no HTTP429. Checkpoints are per instrument. It leaves at least 15 GiB globally free and bounds this branch to 3 GiB; it does not alter research results or use proxies, login, paid feeds or private credentials.

Run/resume with the prepared Python interpreter:
`python3 a-share-data-lake/intraday/scripts/collect.py`

Scope and run identity: `catalog/run-contract.json`; live progress: `catalog/progress.json`. Retired/unknown-lifecycle securities remain in the frozen universe. A successful response does not certify exchange completeness, PIT provenance or trading usability.

Access to a public API is not a grant of redistribution or commercial-data rights. No explicit dataset license was established from the API; retain source attribution and check rights before external redistribution or production use. The repository reference's software license does not license the returned market data.

## Final bounded pass

Completed 2026-11-01 22:13 UTC: 5,818 terminal instruments; 5,809 nonempty series with 11,436,565 observed rows. Internal bar sanity checks classify 5,327 available and 482 needs_review; 9 delisted identifiers returned empty. 5,571 instruments have observations on 2026-10-30. The 238 older nonempty series comprise 229 delisted, 6 master-active, and 3 disclosure-mapped identifiers. Older windows are preserved, not relabeled current. `available` means these local checks passed, not guaranteed fit for trading or complete vendor coverage.

Final integrity and cached-daily comparison: `catalog/audit.json`; per-day diagnostics: `catalog/daily-reconciliation.csv.gz`; payload checksums: `catalog/file-manifest.json`. Re-run local audit without network: `python3 a-share-data-lake/intraday/scripts/audit.py`.
