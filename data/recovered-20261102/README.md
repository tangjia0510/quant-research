# 数据采集代码恢复与表结构重建包

**准备日期：2026-11-06。未提交、未推送。不是 2026-11-05 当晚原件。**

本包恢复了 2026-11-02 旧数据湖交接包中的采集、转换和审计代码，并补充一个有原始代码确证的 2026-10-31 SQLite 表。公开副本按最小必要原则脱敏；原导出与公开字节的双哈希及变更清单见 provenance/publication_transformations.json。旧机器运行/覆盖摘要不发布。

## 内容与可信度

- `original/a-share-data-lake/`：11/2 交接包导出的历史代码和说明；部分机器路径与交接说明已经脱敏，不能称逐字原件。涵盖行情、参考信息、公司行动、财务、分钟数据和宏观等分支。
- `original/legacy-price-limits-20261031/`：独立的 10/31 历史涨跌停采集、处理和查询代码。不是 11/2 数据湖，也不是 11/5 aligned DB。
- `schema/001_daily_limits_original_20261031.sql`：从原脚本 AST 提取的原始 SQLite SQL 字符串，仅重新保存为 SQL 文件。
- `schema/002_source_prices_RECONSTRUCTED.sql`：按确证字段契约新拟的两个来源独立日线表。表名、SQLite 类型和约束设计是本次重建选择，不是恢复出的历史 DDL。
- `provenance/source_inventory.json`：保留文件、哈希、源包和分类；`provenance/omitted_inventory.json` 说明被排除的大型历史索引。
- `docs/SCHEMA_EVIDENCE.md`、`docs/MISSING_INPUTS.md`、`docs/DATA_RIGHTS.md`：字段依据、缺失内容及公开发布边界。
- `tests/`：离线测试；本次安全检查与实际验证结果见上层 `data/validation/`。

## 尚未恢复

`aligned-market-db-20261105` 和 `data-redownload-20261105` 的原采集脚本、原 DDL、原数据库及当晚执行证据均未从本包恢复。不要将本包改名冒充该晚原件。未复制任何原始行情、Parquet、数据库、PDF、日志、会话或凭据。

## 使用

先看 `docs/RUNBOOK.md`。不要直接批量运行 `original` 中的脚本：部分脚本在导入时也会访问网络或写文件，且依赖已缺失的证券池、日历、原始数据与 checkpoint。没有启动器、安装器或定时任务。

仅离线验证本包：

```sh
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s original/a-share-data-lake/catalog/tests -v
```

建议审核后以独立目录 `project/data-collection/recovered-20261102/` 放入 `tangjia0510/quant-research`。该仓库公开，禁止整包加入原数据目录。现有 BaoStock 采集核心已在 main，不重复复制一份。

## 公开副本变更

`original/` 仅沿用历史目录标签，不保证每个文件逐字不变。只读保留的私下原件未修改。公开副本的当前 SHA 在 source_inventory.json；原导出 SHA、删减文件和变更理由在 publication_transformations.json。需要使用历史脚本时，先按 fin_data 根路径完成迁移，不能把脱敏占位路径当可直接运行配置。
