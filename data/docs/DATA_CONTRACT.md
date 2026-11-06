# 新 DuckDB 契约与研究边界

这是 2026-11-06 的新设计，不是 11/5 原库恢复。SQLite 历史表仍独立放在 recovered 目录，不改名伪装成 DuckDB。

## 表及当前可用程度

- `ingestion_batch`：source、source_revision、retrieved_at、available_at、输入 SHA、normalizer 版本、行数、元数据；批次不可覆盖。SHA 不是数据内容本身，也不是供应商承诺。
- `instrument_lifecycle`：每批独立的上市/退市区间，非历史指数成分。
- `trading_calendar`：每批、每交易所、每自然日开放状态。
- `daily_price`：同批次/证券/日期/价格口径唯一，原价 OHLC、股数、人民币金额、源 prev_close、交易状态。
- `adjustment_factor`：独立因子身份、可得时间，不能直接跨源套用。
- `financial_fact`：长表存 metric、报告期、公告时间、可得时间、单位和报表版本；**新通用契约，不是已找回的东方财富全部字段结构**。
- `corporate_event`、`daily_limit`、`macro_observation`：独立公司行动、源涨跌停质量、宏观 vintage 契约。
- `retrieval_audit`：检索请求、候选批次和选择原因，不含另一份原始响应。

目前有完成离线实现和测试的 CLI：日历、生命周期、日线 CSV 导入以及日线来源级联。财务/宏观/因子/事件/涨跌停表的 DDL 已实际建表，字段约束有局部测试，但尚无经过真实供应商文件验证的通用导入器。不要把空表称作已采集到数据。分钟数据保留历史脚本，尚未设计统一生产分钟库。

## 日期、上市区间与交易日

- date 是对应交易所本地日期，保留 YYYY-MM-DD，不拿 UTC 截日代替交易日期。
- 抓取/公告/可得时间必须为带时区 instant，统一以 TIMESTAMPTZ 比较；CLI 拒绝无时区时间。
- 查询需明确日历与生命周期批次，日历覆盖请求生命周期内全部自然日。缺日历、生命周期未知、交易所不匹配、非开市日价格均不静默修复。
- 缺日线可能为源遗漏、停牌、上市边界或错误。没有证据时记 missing_unknown，不 ffill，不写零，也不合成 OHLC。停牌必须来自明确证据；存在一行不等于可成交。
- 证券代码可能变更或复用。当前格式校验不等于完整代码身份映射；不能仅凭当前代码拼接旧证券，更不能把新北交所代码倒推所有历史。

## 来源和版本隔离

- 存储可同库，但一条价格结果必须属于同一 source、同一 batch/source_revision、同一 unadjusted 口径。
- 级联是显式来源优先级上的**整段选择**。不将某源 close 与另一源 volume 混用，不按天补另一源，不自动跨年批次拼装。严格完整性失败才尝试下一本地来源。
- 每源默认取 as-of 前该证券最新批次；最新批次不完整时不能用更旧批次补洞，也不能默认读未来修订。
- 来源没有固定 revision 时，使用响应 SHA 清单作为本地快照身份，并标明不是厂商 API 版本。
- 403/验证码等拒绝不是“找另一个接口绕过去”的信号。下载层停止；查询层只看已获准持有的独立本地证据，不发网络请求。

## 单位与复权

- CLI 日线只接纳 unadjusted + adjustment_id=none，volume_shares=股、amount_cny=人民币元。空值保持 NULL。OHLC 必须有限、正数且满足高低边界；数量/金额非负有限。
- 腾讯科创板原量按股，普通沪深路线按手乘 100，源金额按万元乘 10000；新入口仅开放已有验证范围，不猜 BSE/CDR。
- HF a-share-prices 旧归一化映射为 volume×100、turnover×1000；新 adapter 仅接受该已归一化 Parquet，拒绝不一致 revision 与重复键。
- prev_close_reported 保留来源原值，不自动替换为前一天 close；除权日这两者可能不同。
- qfq/hfq 是快照与基准相关的历史修订，价格复权、总收益、现金红利再投资是不同概念。DDL 留出口径与 adjustment_id，但新导入器拒绝已复权价格/量，直到有单独验证的映射。
- 仓库 BaoStock 当前流程的 adjusted 价格与 raw_shares/factor 模拟量不能当成本层 raw_shares。禁止把其 hfq 价标成 unadjusted。
- financial metric 的单位必须逐字段核定，不能把所有财务值乘某固定倍率；percent/ratio、元/万元/亿元、股/万股需要独立契约。原观察 schema 缺失仍明确缺失。

## PIT 和历史回测

period_end（报告期）≠ announced_at（公告时刻）≠ retrieved_at（本次取得时刻）≠ available_at（本版本可使用时刻）。

- 默认 available_at = retrieved_at，禁止导入时把今天新抓到的修订值标成过去已知。首次取得证据不足时采取保守时间，不假造历史 vintage。
- 日线检索要求价格、日历、生命周期批次在 as-of 之前已可用；这可防止代码层未来泄漏，但**不自动认证供应商历史 PIT 数据或真实历史可交易性**。
- `financial_fact_observation` / `macro_vintage_observation` 视图将行级可得时间与批次可得时间取最大值，返回 safe_available_at。历史研究按该字段过滤，并在同一 source 内按报告期/指标选择版本。
- 仅有公告日期没有公告时刻时不能假设开盘前可见。按明确策略保守映射下一可交易时间，另存策略版本，再验证时区、盘前/盘后与节假日。此包没有擅自生成该映射。
- 当前下载的“历史财务值”可能包含更正，统计局观测期也不是初次发布时间。未持有历史快照与发布证据时，不能声称能够无偏复现过去所见。

DuckDB 查询示例（仅示意同来源财务版本选择，source 与日期需替换）：

```sql
SELECT * EXCLUDE(rn) FROM (
  SELECT *, row_number() OVER (
    PARTITION BY source,instrument,metric,period_end
    ORDER BY safe_available_at DESC, batch_id DESC, statement_version DESC
  ) AS rn
  FROM financial_fact_observation
  WHERE source = 'YOUR_VERIFIED_SOURCE'
    AND safe_available_at <= TIMESTAMPTZ '2026-11-06T12:00:00Z'
) WHERE rn = 1;
```

DDL CHECK 不能跨表验证所有业务语义。直接手写 SQL 可绕过 importer 的额外校验，应限制给经过复核的 ETL。单进程写库、私有备份、原字节校验、样本审计及覆盖报告仍是运行责任。

日线 CSV 导入也采用保守完整日规则：date 必须早于 retrieved_at 对应的上海自然日，拒绝未来或进行中的当日价格。需要当日收盘后更新时，应先单独实现并验证明确的收盘时刻契约。
