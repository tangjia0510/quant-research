# 表结构证据与重建边界

## 1. 确证原表：daily_limits（2026-10-31）

证据：`original/legacy-price-limits-20261031/build_limits_lookup.py` 中的 SQL 常量。
五字段 `instrument TEXT NOT NULL`、`date TEXT NOT NULL`、`upper_limit REAL`、`lower_limit REAL`、`quality TEXT NOT NULL`，复合主键 `(instrument,date)`，`WITHOUT ROWID`。
该脚本导入已去重 Parquet。保存的 DDL 是原 SQL，不代表原数据库数据已备份。

## 2. 重建表：tencent_daily_unadjusted

证据：`original/a-share-data-lake/market/scripts/acquire_tencent_daily.py` 的 `FIELDS` 常量和 `Collector.stock` 写行逻辑。字段顺序逐一保留：date、instrument、open、high、low、close、volume_lots、volume_shares、amount_10k_cny、amount_cny。

价格不复权；金额 CNY=原 10k CNY×10000；688/689 代码原成交量按股，其他已验证路线按手×100。volume_lots 是统一手数投影，并不表示所有源响应都以手为单位。新 SQLite 表名、TEXT/REAL 类型、可空约束是本次设计；原脚本输出 CSV，不曾给出这张 SQL 表。

## 3. 重建表：hf_daily_unadjusted

证据：`original/a-share-data-lake/market/scripts/normalize_hf_prices.py` 的 `pa.table` 字典。13 个字段逐一保留。volume_shares=volume×100；amount_cny=turnover×1000。原数据截止日和 source_revision 是历史快照约束，不能当作当前覆盖。pa.date32 输出在重建 SQLite 中使用 ISO 日期 TEXT，是新的存储映射。

两个来源各自成表。未推断跨来源主键、来源优先级、复权算法、PIT 公告语义、财务单位、历史动态股票池或交易资格。

## 4. 不足以重建的内容

旧数据湖交接包中未发现持久化 SQL CREATE TABLE/VIEW/SCHEMA。财务 `build_schema_catalog.py` 需要逐分区真实 Parquet 才能观察类型；源代码不能代替丢失的 observed-schemas.json 或原 Parquet。不得猜财务动态字段、列类型、空值率或历史更正版本。

没有材料证明以上任一表等于 2026-11-05 aligned-market DB 的原表。
