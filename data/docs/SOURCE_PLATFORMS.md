# 数据来源、原件边界与重新采集前置条件

核查日期：2026-11-06。本文的 `original/`、`provenance/` 和恢复包文档路径均相对 `data/recovered-20261102/`。所有新下载与数据库放仓库根 `fin_data/`（Git 忽略）；归档入口需先迁移路径，不能在原目录直接运行。本文仅静态阅读恢复代码与旧说明，没有请求任何外部接口，没有导入或执行采集脚本。以下链接说明历史代码使用的来源，不承诺今天仍可访问、字段不变或已获数据许可。

## 1. 哪些是恢复原件，哪些不是

- `original/a-share-data-lake/` 是 2026-11-02 交接包保留的代码与说明；其数量、日期、成功状态属于旧快照，不是本包重新验证的当前数据。
- `original/legacy-price-limits-20261031/` 是另一条 2026-10-31 涨跌停处理链。不能与数据湖批次或 11 月 5 日数据库混为一谈。
- 逐文件来源与 SHA 见恢复包 `provenance/source_inventory.json`。哈希验证字节身份，不能恢复丢失数据。
- 11 月 5 日 `aligned-market-db-20261105`、`data-redownload-20261105` 原采集代码、原数据库和原 DDL 未恢复。本文不把重新设计的流程称作该晚原件。
- 本文第 7 节是**建议的新工作流程**，并非已运行过的采集或完成验证的自动安装器。

## 2. 实际平台、接口与脚本

以下脚本路径均相对 `original/a-share-data-lake/`。列出的参数模板是代码证据，不是建议绕过访问限制。网页 Referer 或数据 JS 证据地址不应误当成额外数据 API。

### 腾讯：不复权日线

- 接口：`https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get`。
- 入口：`market/scripts/acquire_tencent_daily.py`，按冻结证券池、证券生命周期与年度窗口请求日线，保存 gzip 原始响应、SHA、请求收据、每证券 checkpoint 和 CSV.gz；部分证券只请求 HF 历史之后的尾段。
- 固定批次 2019-01-01 至 2026-10-30。接口名称里的 `proxy` 是原供应商接口域名，不是代理绕过方案。
- 原字段契约：date、instrument、open、high、low、close、volume_lots、volume_shares、amount_10k_cny、amount_cny。688/689 原成交量是股，其他已核验路线按手处理；不能所有证券统一乘 100。
- 独立补充与 overlap 审计保存整行来源，不拼接不同源的 OHLC/量/金额。恢复代码没有腾讯供应商版本号；冻结日期不是 API revision。

### Hugging Face：两个独立数据集

1. `https://huggingface.co/datasets/ellendan/a-share-prices`
   - 入口：`market/scripts/acquire_hf_bulk.py`；元数据接口 `https://datasets-server.huggingface.co/parquet?dataset=ellendan/a-share-prices`。
   - 原脚本记录 main revision：`c74a2d70361e8cae2a9093e1e293e31e6c421d62`。
   - 实际 Parquet conversion revision：`94d41d1a0f8557682c6acfa829e9fc2c946b4605`。
   - 下载模板：`https://huggingface.co/datasets/ellendan/a-share-prices/resolve/{REV}/main_data/train/{filename}`。
   - 读取已缓存 `market/probes/hf-parquet.txt` 文件索引与声明大小，双线程流式写 `.part`，检查字节数、记录 SHA，再原子改名；不是从零自发现的完整启动器。
   - 数据湖价格投影入口 `market/scripts/normalize_hf_prices.py`。旧快照截至 2026-03-03，主板范围，不是全市场当前数据。原 volume 单位手、turnover 单位千元；证券名冲突与重复行单列审计。
2. `https://huggingface.co/datasets/ellendan/a-share-21`
   - 入口：`market/scripts/acquire_hf_features.py`；对应 datasets-server parquet 元数据接口。
   - main revision：`227be520b89ed737dd65bea4785a41ae39a9b7a4`。
   - Parquet conversion revision：`5e82f37f4c7677d21cb75dfeac9354a3ea6653ef`。
   - 下载模板：`https://huggingface.co/datasets/ellendan/a-share-21/resolve/{REV}/default/train/{filename}`，依赖 `market/hf_features/metadata/parquet-index.json`。
   - 源声明区间 2021-01-01 至 2025-02-27，前复权快照。单位不因同一发布者而继承另一数据集的单位；整体特征表处于隔离状态，仅独立审计过的投影按其限制使用。

两者脚本记录发布者声明 MIT，同时明确上游供应商数据权利未独立核实。数据版本固定不等于下载地址永远可用；main 与转换分支 revision 不可互换。

### 新浪：复权因子与近期分钟窗口

- 因子：`https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js`，`actions/scripts/fetch_factors.py` 与 `fetch_factors_parallel.py`。保存原十进制文本，解析 JS 包装而不执行 JS；1900-01-01 是基准哨兵，不是上市日。当前获取的回溯因子不具备历史版本/PIT 保证。
- 分钟：`https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData`，`intraday/scripts/collect.py`。逐证券获取近期一分钟窗口，存原始响应、收据、CSV.gz 与状态；不是 2019 年以来的分钟历史，也不保证一天 240 根。
- 新浪统一源速率门控；分钟量按股、金额按元保留独立契约。其他历史日线/行情核验的旧说明不等于本包包含完整独立下载器。

### 东方财富：财务、公司行动、两融、资金流、基金

- 主数据中心：`https://datacenter-web.eastmoney.com/api/data/v1/get`；股本使用 `https://datacenter.eastmoney.com/securities/api/data/v1/get`。
- `fundamentals/acquire_statements.py`：`RPT_DMSK_FN_BALANCE`、`RPT_DMSK_FN_INCOME`、`RPT_DMSK_FN_CASHFLOW`、`RPT_LICO_FN_CPD`，按报告期、页号下载。
- `acquire_full_statements.py`：`RPT_F10_FINANCE_GBALANCE`、`RPT_F10_FINANCE_GINCOME`、`RPT_F10_FINANCE_GCASHFLOW`、`RPT_F10_FINANCE_MAINFINADATA`；`acquire_special_financials.py` 包含银行/券商/保险资产负债与现金流表。
- `acquire_supplemental.py` / `acquire_forward_forecast.py`：`RPT_PUBLIC_OP_NEWPREDICT`、`RPT_FCI_PERFORMANCEE`、`RPT_PUBLIC_BS_APPOIN`；`acquire_valuations.py` 使用 `RPT_VALUEANALYSIS_DET` 逐证券分页。
- 公司行动入口 `actions/scripts/fetch_sharebonus.py`、`fetch_equity.py`、`fetch_suspensions.py`、`fetch_event_tables.py`：分红 `RPT_SHAREBONUS_DET`、股本 `RPT_F10_EH_EQUITY`、配股 `RPT_IPO_ALLOTMENT`、增发 `RPT_SEO_DETAIL`、回购 `RPTA_WEB_GETHGLIST_NEW`、解禁 `RPT_LIFT_STAGE` 及停复牌响应。停牌结果是当前每证券事件快照，不是完整历史可交易掩码。
- 宏观入口 `macro/scripts/collect_flows.py`、`collect_margin_detail.py`：汇总与逐证券两融/北向响应。两融按月组织、使用七日子窗口规避已记录的深分页缺陷；接口实际页容量 500。完成的月分区与其子窗口重叠，不能一起追加。
- 基金：`https://fund.eastmoney.com/cnjy_dwjz.html`、`https://fund.eastmoney.com/pingzhongdata/{code}.js`，`collect_funds.py` 解析数据字面量，不执行远程 JS。补充 NAV 接口 `https://api.fund.eastmoney.com/f10/lsjz`；持仓入口 `https://fundf10.eastmoney.com/FundArchivesDatas.aspx`（`collect_benchmark_fund_holdings.py`），可能仅前十大，不代表全组合。
- 金额与数量单位以各源字段为准。基金货基收益、单位净值、累计净值是不同数据类型；财务期间、公告日、更新日、抓取时间不得合并为单一可得日期。

### 巨潮资讯：公告元数据

- POST `https://www.cninfo.com.cn/new/hisAnnouncement/query`，PDF URL 基址 `https://static.cninfo.com.cn/`。
- `fundamentals/acquire_disclosures.py` 保存查询、分页响应、hash；分页修复结果由单独索引选择。
- 有公告标题和 PDF URL 不表示 PDF 已全部下载，更不构成完整数值修订链。

### 官方交易所与指数平台：证券参考、两融、指数、风险与衍生品

- 上交所：`https://query.sse.com.cn/commonQuery.do`、`commonSoaQuery.do`；`reference/scripts/fetch_extras.py` / `fetch_fund_master.py` 及 supplementary 下风险、期权脚本。两融 XLS 使用 `https://www.sse.com.cn/market/dealingdata/overview/margin/a/rzrqjygk` 日期模板，入口 `macro/scripts/collect_sse_margin_bulk.py`；实际拼接规则见原脚本。
- 深交所：`https://www.szse.cn/api/report/ShowReport`（XLSX）、`/ShowReport/data`（JSON）。基金名单、风险警示、逐日两融分别由 reference 与 `collect_szse_margin_bulk.py`、`refresh_latest_margin_day.py` 使用。JSON 空响应不自动证明同日官方导出为空；旧说明记录过两者差异。
- 北交所：`https://www.bse.cn/nq/listedcompany.html`、`/nqxxController/nqxxCnzq.do`、`/service/code_mapping.html`。存在访问受限与历史代码生效日未知记录；不能把当前 920 代码推回全部历史。
- 中证指数：`https://www.csindex.com.cn/csindex-home/perf/index-perf`；公告查询 `/csindex-home/announcement/queryAnnouncementByVonew`、`queryAnnouncementById`；文件主机 `https://oss-ch.csindex.com.cn/` 与历史 `/uploads/file/autofile/cons/`、`weight/` 路径。对应 `reference/scripts/fetch_index_*.py`、`normalize_csi_history.py`、`macro/scripts/collect_csi_benchmarks.py`。价格指数不是全收益指数，当前成分不是历史成分。
- 中金所：`http://www.cffex.com.cn/sj/jycs/{YYYYMM}/{DD}/index.xml`，`reference/supplementary/scripts/cffex_monthly.py`。
- 申万与方正补充证据：`https://www.swsresearch.com/swindex/pdf/SwClass2021/SwClassCode_2021.xls`、`https://datacube.foundersc.com/document/2?doc_id=10858`，`industry_probes.py`。它们是探测/分类材料，不代表成功取得完整历史行业库。
- `reference/scripts/build_master.py` 从旧缓存的沪深在市/退市响应构建主表，**它自身不是原始名单下载器**。缺这些缓存时不能只运行它恢复股票池。

### 官方宏观、利率与港交所

- 中国货币网 CFETS：`https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborHis`（月窗口）、`/ags/ms/cm-u-bk-currency/LprHis`（年窗口），`macro/scripts/collect_rates.py`。
- 中债：`https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery`，`collect_yields.py` 按年获取国债、AAA 普通金融债及中短期票据收益率。
- 国家统计局：`https://data.stats.gov.cn/dg/website/publicrelease/web/external/` 下 `new/queryIndexTreeAsync`、`new/queryIndicatorsByCid`、`stream/esData`；`collect_nbs.py` 遍历全国月/季与选定年度类别，再由 `normalize_nbs.py` 归一化。不是所有地区/指标普查；统计期不是发布日期，后修订值不能当原始 vintage。
- 港交所持仓：`https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=`，`collect_hkex_holdings.py`，旧任务仅四个季度沪/深快照。2024-08-19 披露变化证据为 HKEX 通函 `ce_HKSCC_NOM_217_2024.pdf`，由 `annotate_flows.py` 引用；变更后缺失字段或占位零不得当真实零。
- 所有这些动态接口均未见供应商可固定的内容 revision。需要保留请求参数、抓取时间、原始 hash、原始字节及字段契约，不能用本文核查日期代替原抓取日期。

## 3. 10 月 31 日 legacy 链路

- `acquire_limit_parquet.py` 从缺失的 `/tmp/hfparquet.json` 读取 URL/大小，两个线程下载并记录 hash。它在顶层执行，没有数据湖统一 host gate、显式 403 家族停止逻辑或自动恢复设计，不能当安全的一键入口。
- `extract_limits.py` 依赖旧 `listing_delisting.csv` 与临时 Parquet；DuckDB 过滤目标股票及 2021-06-01 至 2026-10-30，投影供应商 high_limit/low_limit，保留 missing/sentinel/invalid/OHLC 越界标记。
- 其代码称发布者流水线归因 Tushare `stk_limit`，这不是本包直接调用 Tushare，也不是官方交易所认证。本目录没有独立固定的下载 revision，不能把后来数据湖 revision 反填成它的证据。
- `build_limits_lookup.py` 消费缺失的 `daily_limits_deduplicated.parquet`，创建只读研究查询用 SQLite；已有 DB 时拒绝覆盖。原提取脚本输出 reported 文件，不能假定缺失的去重中间步骤已可完整复现。
- `limits_lookup.py` 是查询辅助，不是数据获取服务。BaoStock 仅在数据湖 gap 证据/运行时记录中出现；恢复范围不含一套可替代上述源的完整 BaoStock 采集链。

## 4. 输入、依赖与运行风险

必须先补齐并核验的输入包括：

- 腾讯 `market/manifests/universe-sharded-with-bse.csv`、旧缓存 `calendar.txt`，以及原缓存收据；日历为观察到的上证指数交易日期，不是独立认证的交易所全集。
- HF 两套索引/README/revision 元数据、原 Parquet 与审计结果；仅脚本无法重新生成丢失内容。normalizer 还依赖 duplicate-audit 等证据。
- reference 原始沪深名单；actions 冻结 `catalog/universe-input.csv/json`；各分支 catalog、逐页 raw、checkpoint、下游分区与市场证券池。
- legacy 的下载清单、旧证券列表和去重 Parquet。本代码包未携带这些真实数据。

运行时记录为 Python 3.11；选取版本 requests 2.34.2、pandas 2.3.3、pyarrow 25.0.1、beautifulsoup4 4.15.0、baostock 0.9.4。另有脚本需要 duckdb、openpyxl、xlrd、lxml；旧记录中部分包仅在另一个解释器存在或为 null。`catalog/runtime-dependencies.json` 不是锁文件，不能证明新机器可安装相同环境。跨进程锁/原子替换/硬编码路径也需要按目标系统检查。

部分文件在 import 时读写文件、启动线程或发起网络请求。**只能先静态检查，不能通过 import 来探查依赖或字段。** `macro/scripts/prefetch_margin_2019.py` 是明确禁止运行的未启用实验，顶层 RuntimeError 防止与主采集器争用；规范两融入口仍是 serial collector。

## 5. 访问、停止与公开发布规则

- 免费可访问、robots 缺失、软件许可证、HF 发布者 MIT 声明，都不自动授予返回数据的公开再分发权。本包只发布代码、来源说明与结构，不附 JSON/CSV/Parquet/数据库/PDF 原数据，不给供应商内容新增许可证。
- 401/403、验证码、明确访问控制：停止该来源路径并记录，不改身份、IP、代理或凭据绕过，不自动反复重试。本文没有重新尝试旧拒绝。
- 429：停止/暂停并尊重 Retry-After 与来源要求；后续仅在允许时降低并发恢复。部分旧脚本将 401/403/429/567 都作全源停止，必须保留更严格行为，不能解释为正常失败后无限重试。
- 新工作流程应统一检查每个入口的停止实现；不能因 README 有要求就声称每份 legacy 脚本已实现。普通暂时故障采用有界重试，而访问限制不进入普通重试链。
- 数据湖最低空余磁盘 15 GiB；共享源 gate 避免多个分支各自放大并发。新浪常见 1.05 秒、东方财富 1.1 秒最小启动间隔，最多两并发且压力时降低。分支预算另有 15/8/5/3 GiB，实际入口需逐个确认。
- 不执行下载的 JavaScript、宏或外部链接；只解析数据。不得把凭据、cookie、环境转储或认证 URL 放入公开包。

## 6. 原表结构是否存在

**只有一个明确恢复的持久化 SQL 表：**

`legacy-price-limits-20261031/build_limits_lookup.py` 中原 SQL 定义 `daily_limits`：instrument TEXT NOT NULL、date TEXT NOT NULL、upper_limit REAL、lower_limit REAL、quality TEXT NOT NULL，主键 `(instrument,date)`，`WITHOUT ROWID`。这证明原 DDL，不证明原 DB 或数据仍在。

数据湖恢复代码提供 CSV 字段顺序、PyArrow 构造字段和 JSON 结构，没有发现持久化 SQL CREATE TABLE/VIEW/SCHEMA。`fundamentals/build_schema_catalog.py` 读取成功分区的真实 Parquet schema 并写 `catalog/observed-schemas.json`；原分区与输出缺失时不能凭脚本猜出全部动态字段、类型、单位和空值率。

任何新 SQLite/DuckDB 表名、存储类型映射、主键、索引、导入器及跨源选择策略都必须标记为**新建/重建**。不能称为恢复了 11 月 5 日 aligned DB，也不能据此声称财务、复权和交易资格已统一。

## 7. 建议的新机器工作流程（未执行）

1. 只复制代码与本文，先验证来源清单 hash。私下原件不改，公开副本的脱敏变更需保留双哈希；迁移适配器放独立目录。
2. 在允许的来源权利和访问条件下确定要重新获得哪些输入。原文件缺失就明确使用新批次，不能伪造旧 hash/checkpoint 或把新数据称为旧快照。
3. 将路径、截止日、证券池、输出目录参数化；先校验输入与磁盘，再显式 opt-in 网络，禁止 import 副作用。依赖在独立环境按实际入口验证。
4. 先做合成数据离线测试，再在获授权的来源做最小试采。确认限速、403 停止、响应大小、分页、单位、重复键和原始 SHA，之后才扩到有界批次。
5. 每来源单独保存 raw、receipt、normalized、quality 与版本；断点只恢复已验证项目。已有写入者时不启动第二个；旧终态不等于当前有进程。
6. 新数据库导入只消费经验证的文件。数据验证与交易可用性/PIT 验证分别给结论，绝不以“下载结束”宣称全部数据齐全。

主要本地证据：各分支 README、`catalog/HANDOFF.md`、`catalog/runtime-dependencies.json`、上述具体脚本；恢复包 `docs/MISSING_INPUTS.md`、`docs/SCHEMA_EVIDENCE.md`、`docs/DATA_RIGHTS.md`。这些是历史与静态证据，不是今天对外部服务的在线验证。

公开最小化说明：私下原件保持不变；机器特定路径改为逻辑路径，旧运行/覆盖摘要不发布。变更文件和省略文件的原导出哈希、当前公开哈希见 `recovered-20261102/provenance/publication_transformations.json`（路径相对 data 根）。脱敏不等于修复历史脚本全部迁移问题。
