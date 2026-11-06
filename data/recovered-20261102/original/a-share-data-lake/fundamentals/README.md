# A-share financial statements acquisition

Initial finite pass: report quarters 2019-03-31 through 2026-09-30, Eastmoney public market-wide balance sheet, income, cash flow and earnings tables. Queries intentionally do not restrict to today's surviving securities; compare returned symbols with the independently downloaded reference master before forming a historical universe.

## Structure

- `raw/<table>/<period>/page-N.json.gz`: losslessly compressed complete vendor JSON responses.
- `receipts/`: full source URL, retrieval UTC time, original/compressed SHA256, row pagination and attempt receipts.
- `normalized/<table>/<period>.parquet`: original field names and values plus lineage fields.
- `catalog/<table>/<period>.json`: observed counts, duplicate-key checks, date bounds, schemas and file hashes.
- `catalog/progress.json`: success/failure/unattempted overview (only completed task pages count as success).
- `source-review/`: saved public interface documentation and robots response. Third-party source scripts are read as documentation, never executed.

## Financial/PIT caveats

These are **current vendor snapshots of historical report periods**, not a complete revision history. Keep fiscal `REPORT_DATE`, vendor `NOTICE_DATE`, optional other timestamp fields and acquisition time separate. A notice timestamp may be attached to subsequently revised financial values. All normalized rows have `_pit_ready=false`; using `NOTICE_DATE` alone does not make them point-in-time safe. Announcement URLs and original filings may be incomplete. Null values are preserved, not zero-filled. Some bank, broker and insurance line items differ. Ratios are retained in original vendor units and must be mapped field-by-field, not inferred from column names.

Summary statements are not equivalent to every field of a full filing. Rows of other security categories returned by the endpoint remain in the raw corpus; universe eligibility belongs to a documented downstream filter. Report coverage does not prove every eligible issuer filed in that quarter.

## Access and recovery

`acquire_statements.py` is locally authored, uses a shared host lock at `../logs/eastmoney-rate.lock`, starts requests no faster than 1.1 seconds apart, and retries at most 3 times with backoff. HTTP 401/403 stops that host path. 429 obeys increasing wait. Disk floor 15 GiB is enforced. Resume verifies existing raw file hashes and reuses pages, rather than repeating successful calls. Public access is not an assertion of redistribution licensing; use locally for the requested research, review source terms before redistribution.

No account access, credentials, paid API, browser security bypass, proxy rotation or anti-bot evasion is used. Metadata reflects observations, not a guarantee of investment fitness.

## Additional API collections

- `supplemental/`: market-wide earnings forecasts, preliminary earnings releases, and report disclosure schedules (`ACTUAL_PUBLISH_DATE` retained separately from planned dates). A latest forecast is not a complete forecast-revision history.
- `disclosures/`: CNINFO official public JSON announcement metadata for annual, half-year, Q1 and Q3 reports. Retains announcement IDs, UTC and Asia/Shanghai timestamps, original PDF URLs, titles and heuristic correction-title flags. Date ranges are split to avoid the endpoint's high-page fallback; repeated IDs or count mismatches are explicit partial results. PDFs are not mass-downloaded and numerical statements are not asserted to match a particular filing vintage.
- `valuations/`: independent Eastmoney `RPT_VALUEANALYSIS_DET` history by frozen security identity. Original PE/PB/PS/PCF, market capitalizations, total and free A shares are retained; these are separate from any bulk secondary provider's definitions and are not blindly stitched. Dates after the market cutoff 2026-10-30 are flagged. BSE current code aliases may identify histories under the current code rather than a point-in-time security symbol.
- `views/`: reproducible A-share/CDR-only and date-screened views. Their name explicitly says `not-pit`. Future/missing disclosure dates are excluded from the date-screened view, but it still does not establish original report vintages.

All Eastmoney workers share `../catalog/host_gate.py`: no more than two global concurrent requests, at least 1.1 seconds between starts, and shared temporary backpressure to one slot. CNINFO has its own 1.2-second minimum start interval.

### Full-statement scope optimization (2026-11-01 18:04 UTC)
For previously unstarted full-statement partitions only, the API filter now selects
`SECURITY_TYPE_CODE in ("058001001","058001008")` (A-share/CDR), without any
current-stock-list or trade-market exclusion. All four APIs passed an exact count
comparison against locally filtered, unfiltered 2026Q2 snapshots (6,397 / 6,517 /
6,397 / 6,518). Evidence: `source-review/full-statement-a-cdr-scope/verification.json`.
Completed and partially cached partitions retain their original query filter,
read from the first-page receipt. Thus vendor row scope differs by partition;
`source_query_scope` and receipt URL identify this explicitly. Old wider snapshots
remain intact; no numerical value, key, or acquisition timestamp is rewritten to
pretend the source scopes are identical.

## Completed first-pass scope (2026-11-01 UTC)
- Core summary statements/earnings: 124/124 quarterly tasks, 741,900 vendor rows.
- Full statements/indicators: 124/124, 851,670 rows; preserve per-partition scope.
- Financial-sector balance/cashflow: 186/186, 10,517 rows.
- Forecast/express/disclosure schedules: effective 93/93, 276,115 rows including
  eight independently verified stable-sort replacements (original failures retained).
- CNINFO report metadata: effective 95/95 publication-month windows, 252,903 globally
  unique announcement IDs, zero cross-leaf duplicates; one single-day category-split
  replacement recovered the API page-101 truncation. PDF links, not mass PDF contents.
- Daily valuations: all 5,818 frozen securities attempted; 5,600 histories returned,
  218 explicit API no-data, zero download failures, 9,645,425 rows. Of successful
  histories 5,577 reach 2026-10-30 and 23 end earlier. Do not forward-fill gaps.
  19 no-data securities have independent historical valuation fields in the existing
  HF bulk dataset; this is a source-linked alternative, not a merged/PIT-complete series.
- Latest-period immutable refresh: four full families plus six financial-sector
  families for 2026Q3 and already published 2026-year-end forecasts; 11/11 successful.
  Compared with matching earlier snapshots, no source-value/add/remove changes.

Use `catalog/branch-status.json`, `catalog/freshness.json`,
`catalog/pagination-repairs.json`, `catalog/disclosure-effective-coverage.json`,
`catalog/disclosure-id-audit.json`, `valuations/catalog/final-audit.json`, and
`views/manifest.json`. Counts across overlapping families are NOT additive.
No table is certified as historical-vintage PIT. Public access is not a redistribution
license. Future publication fields remain in raw snapshots, and conservative date
screens are explicitly not substitutes for true first-public revision histories.
