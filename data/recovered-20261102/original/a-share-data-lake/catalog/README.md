# Coverage audit and catalog

`python catalog/build_coverage.py` reads branch manifests and writes atomic `coverage.json` / `coverage.md`. It does not download, repair, fill, or register research data. Run from the lake or with an explicit `--root`.

Coverage definitions:
- `expected`: frozen branch target, not every instrument/data type that could exist.
- `attempted`: locally recorded terminal items, not merely planned requests.
- `available`, `success`, or `complete` in a branch means the branch's acquisition completed; it does not certify every session, point-in-time availability, financial correctness or redistribution rights.
- `unattempted`: target minus recorded attempts; never reported as successful.
- `partial`: some useful data exists or a bounded acquisition pass finished, but the broader category remains incomplete/unverified.
- `blocked`: a branch encountered a reported source/access/rate/disk condition.

Price and factor universe counts differ intentionally: prices target securities with a lifecycle overlapping 2019–2026; historical factor event acquisition may also include securities delisted before 2019. The vendor factor date `1900-01-01` is a sentinel, not evidence of market coverage since 1900.

Financial data is the latest retrieved vendor vintage. Fiscal period, notice date, original availability and revision availability are distinct. A notice date on or before the desired as-of date is necessary but not sufficient for point-in-time use. Future-dated notices must remain excluded from any as-of view, while preserving original raw responses.

Tests: `python -m unittest discover -s catalog/tests -v`.

`market-sample-audit.json` is a limited independent sample of actual normalized files and receipt hashes, not a full audit of the entire growing dataset. The source branches own complete raw receipts and their data quality reports.

The global disk safety floor is 15 GiB available. The audit reports this value but does not kill or alter collectors. The parent coordinator and collectors enforce limits. The snapshot does not infer that a process is alive solely from a historical running status.

Historical prices can now be provider-sharded. The HF partition is an independent vendor snapshot through 2026-03-03; selected Tencent targets request only the 2026-03-04 onward tail. `market.rows` counts the Tencent partition only, while `bulk_source_partitions.hf_bulk.normalized_manifest` describes the HF partition separately. These row counts must not be added as unique stock-date coverage: earlier Tencent full-history downloads overlap HF and some HF codes may not be in the requested lifecycle universe. Per-stock `requested_start` and `historical_partition` retain the distinction. Missing-session counts are measured within each requested segment, not a certification of the joined history.

Freshness: run `python catalog/build_freshness.py` after the coverage builder. This writes `freshness.json` and `freshness.md`. It separates observation/period end, the collection's daily target, actual receipt retrieval time, and source publication availability. A missing verified publication target is `null`. An old quarterly retained snapshot is not a stale daily series; a current row date does not restore northbound fields that ceased disclosure. Per-fund/per-indicator branch matrices carry finer detail. These two builders can be rerun while collection continues; they do not issue network calls.

`market` 的 `unavailable` 仅表示请求区间内未得到可用行情，不等于证券不存在或已证明供应商遗漏。例如 sh600680 原始响应保留了 2019 年前行情，但请求的 2019 年起区间无记录；退市前长期停牌与数据缺失需要独立生命周期证据区分。`needs_review` 数据保留源值，不能当作质量已通过。

独立两融覆盖快照可用 `python3 a-share-data-lake/catalog/build_margin_union_coverage.py` 更新；它扫描官方逐日文件与已完成 vendor 月分片，仅对市场/日期/证券键及字段非空可用性去重，不合并数值、不把重叠官方月表再加一次。SSE、SZSE 官方字段集合不同，vendor 有额外字段。快照生成时间可能早于总 catalog 生成时间，进度汇报必须同时显示该时间或更新快照，不能拿旧快照冒充实时数量。全市场汇总的末日不等于每个交易所明细末日，API 收全不等于历史日期完整。

跨 Agent 接手、恢复入口和数据语义总览见 [`HANDOFF.md`](HANDOFF.md)。无凭据代码/checkpoint清单由 `build_recovery_manifest.py` 写入 `recovery-manifest.json`；该清单不含原始大数据，也不构成持久化备份承诺。队列终态后须重新生成所有最终 counts/bytes/freshness。
