# 数据下载、结构与换机器恢复

这里保存**代码、文档和 SQL**。所有新入口的行情、原始响应、转换文件和数据库默认写入仓库根 **`fin_data/`**，该目录必须先由根 `.gitignore` 的 `/fin_data/` 规则忽略，不提交 GitHub。下载命令不接受此目录外的输出路径。

## 三类材料，不能混称

1. `recovered-20261102/original/`：从旧交接包找回的 129 个 Python 文件的公开副本，包含 125 个 11/2 数据湖文件及 4 个 10/31 涨跌停文件，保留原导出与公开副本双 SHA；部分机器路径及交接文档已脱敏，旧运行摘要未发布。不是 11/5 当晚代码。
2. `recovered-20261102/schema/`：一个确证的原 SQLite DDL、一个明确标注的 SQLite 草案。旧说明中的“未推送”描述的是该恢复包准备时状态，不代表本仓库当前状态。
3. `portable/` 与 `sql/001_portable_duckdb_RECONSTRUCTED.sql`：**2026-11-06 新建**的 DuckDB 结构、严格离线导入/检索入口、参数化腾讯下载器与 HF 已归一化 Parquet 转 CSV 适配器。不是恢复出的生产 DDL。

**仍未找回：**11/5 原数据库、原采集代码、原 DDL 和执行证据。仅有代码不能按字节恢复丢失数据。动态接口可能修订、拒绝访问或下线，重新下载只会产生新快照；准确恢复旧库需要另外持有原文件、快照清单及其校验和。

## 新机器快速开始（在仓库根）

```sh
# 根 .gitignore 应已有 /fin_data/，先确认；不要 git add -f
mkdir -p fin_data
git check-ignore fin_data/probe.duckdb
python3 -m venv data/.venv
# Linux/macOS；Windows 使用 data\.venv\Scripts\python.exe
 data/.venv/bin/python -m pip install -r data/requirements.txt
 data/.venv/bin/python data/portable/warehouse.py init
 data/.venv/bin/python -B -m unittest discover -s data/tests -v
 data/.venv/bin/python -B -m unittest discover -s data/recovered-20261102/tests -v
 data/.venv/bin/python -B -m unittest discover -s data/recovered-20261102/original/a-share-data-lake/catalog/tests -v
```

默认创建 `fin_data/research.duckdb`。新层只依赖 DuckDB 1.4.3；本次实际测试解释器为 CPython 3.12，未测试 Windows，不修改主研究项目的 Python 3.11 环境与依赖。旧脚本依赖是历史记录，不是已验证的可安装锁文件。

## 从哪里开始看

- [操作流程](docs/RUNBOOK.md)：下载、导入、来源优先级检索与迁移。
- [各平台来源](docs/SOURCE_PLATFORMS.md)：腾讯、HF、新浪、东方财富、巨潮、交易所、统计局、CFETS、中债、HKEX 等的入口、缺失依赖与限制。
- [数据契约](docs/DATA_CONTRACT.md)：交易日、日期单位、来源版本、复权、缺失、PIT 与级联策略。
- [恢复与许可边界](recovered-20261102/docs/MISSING_INPUTS.md)、[数据权利](recovered-20261102/docs/DATA_RIGHTS.md)、[哈希清单](recovered-20261102/provenance/source_inventory.json)。
- [本次验证结果](validation/RESULTS.md)。

现有 BaoStock 采集器继续使用仓库 `scripts/quantlib/sources/baostock.py` 与 [数据准备说明](../references/data-preparation.md)，没有复制或替换。其后复权价格/模拟量与本层 raw 股数契约不同，不可直接混入。

不自动联网、不启动定时任务、不执行旧脚本导入副作用。遇到 401/403/验证码/明确拒绝，停止该来源，不使用代理、换身份或其他接口绕过。来源“级联”只对已经合法持有的本地独立快照进行选择，不是访问受限后的网络绕过。

公开最小化说明：私下原件保持不变；机器特定路径改为逻辑路径，旧运行/覆盖摘要不发布。变更文件和省略文件的原导出哈希、当前公开哈希见 `recovered-20261102/provenance/publication_transformations.json`（路径相对 data 根）。脱敏不等于修复历史脚本全部迁移问题。
