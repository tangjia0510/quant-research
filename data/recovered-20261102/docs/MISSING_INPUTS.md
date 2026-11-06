# 仍缺少什么

1. 11/5 原 `aligned-market-db-20261105`、`data-redownload-20261105` 目录未恢复；无原代码哈希或 DDL 可证明等同当晚运行版本。
2. 11/2 日线入口依赖 `market/manifests/universe-sharded-with-bse.csv`、旧 mixed-source `calendar.txt` 和可选缓存 receipts。交接包没有这些原始输入，不能直接重跑完整采集。
3. HF normalizer 依赖 `hf_bulk/raw/*.parquet`、audit、duplicate-audit、metadata 原件；本包没有供应商原始字节。
4. 财务、参考、宏观和公司行动各分支依赖自己的 catalog、证券池、逐页 raw、checkpoint 和下游分区。仅有源代码不等于所有输入齐全。
5. 10/31 旧 HF downloader 依赖 `fin_data/legacy-inputs/hfparquet.json`；SQLite builder 依赖 `daily_limits_deduplicated.parquet`；提取器依赖旧股票列表。本包均不附带，先核实来源权利和范围再获得输入。
6. 原冻结日期大多为 2026-10-30，不能直接当作长期更新器。参数化、迁移、网络运行、全量集成测试均尚未完成。
7. 大型历史 coverage/freshness 输出留在源归档，未装入 GitHub 候选包。SHA 只能检验已有字节，不能恢复不存在的行情。
