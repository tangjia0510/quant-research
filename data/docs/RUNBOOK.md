# 可运行入口与迁移操作

所有命令在仓库根执行。Python 指向 `data/.venv/bin/python`（Windows 使用对应 Scripts 路径）。`fin_data/` 是下载/数据库唯一默认根路径，Git 忽略必须先验证。旧归档不可直接当新入口运行。

## 1. 离线初始化

```sh
mkdir -p fin_data
git check-ignore fin_data/probe.duckdb
python data/portable/warehouse.py init
```

实际 DDL 在 `data/sql/001_portable_duckdb_RECONSTRUCTED.sql`。可用 DuckDB 1.4.3 客户端执行同一文件；新层是空库结构，不意味着已恢复数据。导入使用事务，失败全部回滚；相同原文件字节、元数据和 normalizer 版本重复导入返回原 batch_id。不同内容或版本另存批次，不覆盖。

## 2. 独立来源下载

### 腾讯：新的参数化入口

先核实来源权利和可访问范围，再显式运行，例如：

```sh
python data/portable/fetch_tencent.py --instrument sh600000 \
  --start 2025-01-01 --end 2025-01-31 --source-access-reviewed
```

本例不是已完成下载证据。默认创建 `fin_data/tencent/<代码>/<UTC批次>/`，包含原始窗口响应、prices.csv、metadata.json 与 SHA 收据。只取完整的过去上海自然日，不取进行中的当日；年度窗口最多约 250 交易日，接口上限 640，串行间隔至少 1.1 秒，超时 30 秒，响应最多 32 MiB。没有网络自动重试、自动换源、身份或代理切换。HTTP 401/403/429/567，或 HTTP 200 内明确拒绝/验证码/非零错误码，写 `fin_data/tencent/ACCESS_BLOCKED.json` 来源级标记及本批次标记后停止；再次运行即使新证券/新输出目录也先拒绝。原响应与收据先落盘再解析，解析失败的证据仍留在 fin_data。明确拒绝即需先处理授权条件，不能换目录绕过限制。没有自动解锁命令，先核实授权/限制原因再人工审查。一次只启动一个腾讯采集进程，当前版本不提供跨进程并发调度。

支持已经有单位契约的普通沪深 A 股 `sh60xxxx`、`sh688xxx`、`sz00xxxx`、`sz30xxxx`。不猜北交所/CDR 单位。不复权价，科创板原量按股，其余原量按手乘 100，金额原万元乘 10000；金额/量隐含价格越界则失败而不猜转换。网站契约变化会停止，需重新审核。

此入口仅做单证券 bounded snapshot，不是全市场一键下载器。证券池/交易日必须另外取得并留版本，实际在线采集和供应商当前条款本次**未验证**。

### HF：固定来源版本与离线转换

两个原下载器与各自 main/conversion revision 见 [来源清单](SOURCE_PLATFORMS.md)。旧下载器依赖丢失的 Parquet 索引，并非自发现安装器；先在获准条件下取得完整索引和固定 revision 内容，校验哈希与重复键，不要将 main 的 SHA 放入转换分支 URL。所有私有下载保存到 `fin_data/hf/`。

对已经持有且通过旧审计的 normalized_prices Parquet，可运行：

```sh
python data/portable/normalize_hf.py \
  --parquet fin_data/hf/normalized/part.parquet \
  --revision 94d41d1a0f8557682c6acfa829e9fc2c946b4605 \
  --retrieved-at 2026-11-06T00:00:00Z
```

示例时间必须替换为该文件可证实的实际取得时间；不是建议补造旧收据。适配器校验每行 source_revision、拒绝重复键，只接受旧归一化字段，不接收原始 HF 字段，不自动重跑 2025-12-18 特定去重或复制旧统计。输出 `fin_data/hf-normalized/<UTC批次>/prices.csv` 和 metadata.json。若仅有 raw Parquet，需要重新完成源审计与归一化，不能跳过。

### 其他平台与 BaoStock

[来源清单](SOURCE_PLATFORMS.md)逐个平台给出历史下载器、接口、输入、依赖和限制。归档代码保留历史算法，公开副本的机器路径已脱敏并记录双哈希，有冻结日期、绝对旧路径与 import 副作用。迁移前必须在独立副本里把输出根改为 `fin_data/<来源>/`，核验输入与停止逻辑，然后最小试采；不要直接在 `data/recovered-20261102/original/` 下运行。未声称所有旧入口已改为可运行新流程。

BaoStock 继续用仓库现有 data-preparation 流程，但其输出根也应指定 `fin_data/` 内的位置。其 hfq 价格和反向调整成交量不能直接导入本层 raw 表，不把沪深普通股票覆盖假称全市场/BSE。

## 3. 准备必须的参照输入

新 CLI 接受 CSV/CSV.gz。文件保存在 `fin_data/`，不提交 Git。下面是**字段契约**，不是供应商原始数据：

- 日历：`exchange,date,is_open`。exchange 为 SSE/SZSE/BSE，is_open 为 0 或 1。必须包含请求区间**每一个自然日**，周末/节假日显式为 0；仅“观测到有成交的日期”不足以认证完整日历。
- 生命周期：`instrument,exchange,listed_on,delisted_on`。代码为 sh/sz/bj + 6 位数字，退市日可空；上市日必须已知。日期 YYYY-MM-DD。最新股票名单不能证明历史成分/历史全市场完整。
- 价格：`instrument,date,open,high,low,close,volume_shares,amount_cny`，可选 `prev_close_reported,trade_status`。trade_status 默认 unknown，显式 suspended 才允许 OHLC 全空；未知缺失不是停牌。

每个文件带独立 metadata.json，最少如下（自行替换来源和时间）：

```json
{
  "source": "YOUR_VERIFIED_SOURCE",
  "source_revision": "YOUR_PINNED_REVISION_OR_RESPONSE_HASH",
  "retrieved_at": "2026-11-06T00:00:00Z",
  "price_basis": "unadjusted",
  "adjustment_id": "none",
  "volume_unit": "shares",
  "amount_unit": "CNY"
}
```

日历/生命周期不需要最后四个价格字段。`available_at` 可省略，取 retrieved_at；如提供，不得早于 retrieved_at。来源没有 revision 时用原响应 SHA 清单身份并明确它不是供应商版本。新文件不能伪造旧 acquired/available 时间。

```sh
python data/portable/warehouse.py import-calendar --csv fin_data/calendar.csv --metadata fin_data/calendar-meta.json
python data/portable/warehouse.py import-instruments --csv fin_data/instruments.csv --metadata fin_data/instruments-meta.json
python data/portable/warehouse.py import-prices --csv fin_data/tencent/SNAPSHOT/prices.csv --metadata fin_data/tencent/SNAPSHOT/metadata.json
```

记录命令返回的 batch_id。日历、生命周期与每个价格来源各用自己的元数据，禁止共享一个伪“统一来源”。每批 CSV 会载入内存并严格校验，当前实现适合分证券/分区输入，不适合把全湖拼成单个超大 CSV。

## 4. 日期对齐与来源级联

```sh
python data/portable/warehouse.py query --instrument sh600000 \
  --start 2025-01-01 --end 2025-01-31 \
  --calendar-batch CALENDAR_BATCH_ID --instruments-batch LIFECYCLE_BATCH_ID \
  --sources tencent,hf:ellendan/a-share-prices --as-of 2026-11-06T12:00:00Z
```

来源次序由用户明确给出；示例不表示腾讯一定优于其他源。每来源选本证券在 as-of 前最新可用批次，整段覆盖失败才选下一来源，**不会按天或字段拼源，也不会将较新的残缺批次与旧版本混填**。若仅有分年独立批次，需先明确制作一个来源同版本、完整区间的规范批次，而不是让查询自动跨版本拼接。

严格模式缺任一开市日就拒绝该批次；默认缺失不填，不把缺失推断成停牌。`--allow-gaps` 显式放宽为按优先级选第一个有观测的批次，返回缺失日期及 missing_unknown；不会自动把它补成可回测序列。任何非开市日价格都拒绝整个候选。日期区间按真实上市/退市日期裁剪。

结果携带选择的 source/revision/batch、替代来源拒绝原因、缺失日期、日历/生命周期版本和 query_id。选择过程写 retrieval_audit，但不复制行情数值进审计字段。查询会写审计，单 DuckDB 写入进程使用，不作为多写者服务。

## 5. 换机器时怎样恢复

1. 克隆本仓库获得 /data 代码与 SQL，先验证 `/fin_data/` 已忽略，再建立隔离环境并跑离线测试。
2. 若另有合法持有的私人备份，将 raw、metadata/receipts、normalized 和数据库复制到新机器 fin_data/，逐文件核对 SHA。不要上传公开仓库；其他共享目的需要单独授权。
3. 有同一原始文件字节时，使用本包固定 normalizer/元数据重新导入可复现存储值与批次身份；DuckDB 文件二进制布局、query_id/审计时间不保证一致。DB 本身可以私人备份后校验整体 SHA。
4. 没有备份就按平台权利和当前可用性重新下载，保留新时间、新版本、新缺失报告。内容修订、接口变化和访问限制可能无法重建旧结果；不要声称恢复旧字节。
5. 发布前检查 `git ls-files fin_data` 应无输出，`git check-ignore fin_data/probe.duckdb` 应命中，`git status --short` 不应出现真实数据。

日线 CSV 导入也采用保守完整日规则：date 必须早于 retrieved_at 对应的上海自然日，拒绝未来或进行中的当日价格。需要当日收盘后更新时，应先单独实现并验证明确的收盘时刻契约。

公开最小化说明：私下原件保持不变；机器特定路径改为逻辑路径，旧运行/覆盖摘要不发布。变更文件和省略文件的原导出哈希、当前公开哈希见 `recovered-20261102/provenance/publication_transformations.json`（路径相对 data 根）。脱敏不等于修复历史脚本全部迁移问题。
