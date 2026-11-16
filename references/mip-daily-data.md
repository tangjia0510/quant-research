# MIP 日线数据引用

读取本引用的场景：使用本地 MIP 前复权/不复权日线、在另一台机器恢复备份，或将该快照转换为研究输入。快照固定为 **2026-11-16-v1**，不随行情更新。

## 数据、格式与范围

| 口径 | 标识 | 行数 | 证券代码数 | 整体日期范围 | 归档内格式 | 压缩载荷 |
|---|---|---:|---:|---|---|---:|
| 前复权 | `qfq` | 9,353,034 | 5,246 | 2018-01-02—2026-11-16 | 紧凑 DuckDB + XZ | 266.241 MiB |
| 不复权 | `none` | 4,961,305 | 4,086 | 2018-01-02—2026-11-16 | Parquet + Zstd-22，重复核验证据独立字典 | 164.519 MiB |

两类数据合并为 `mip-daily-20261116.tar.zst`，**451,292,748 字节（430.386 MiB）**。载荷大小之和不等于外层归档大小。归档内含 `restore.py`、固定依赖、`schema.sql`、文件 SHA-256 清单及来源/压缩比较记录。恢复会重新拼接字典，保留全部 17 字段、NULL、DOUBLE 位值及 `raw_json` 原文。恢复出的 DuckDB 物理布局不保证与原库相同。

上述日期、代码数表示整体覆盖，不表示所有证券每天都有两种价格。备份沿用原有证券范围，包含不同证券类型；它不是完整全市场、历史成分股清单或历史可交易资格库。仅包含 `kline_daily_bars` 中 `period='daily' AND adjust IN ('qfq','none')` 的记录；不包含后复权、财务、ST/停牌历史、指数成分、行业、因子缓存及研究记录库。

归档固定 SHA-256：

```text
2223a8ac2522c2911347c2c410ad97d756926cd001eda3ff25e3958b1ff03eb2
```

## 从仓库下载并恢复

数据通过本仓库的 [data-mip-daily-20261116-v1 Release](https://github.com/tangjia0510/quant-research/releases/tag/data-mip-daily-20261116-v1) 附件分发；普通 Git 和源代码 ZIP 不包含它。选择仓库外的新目录，需 GitHub CLI、Zstd、Python 3.11，以及安装固定 `duckdb==1.5.3` 的隔离环境。预留数 GiB 恢复空间。

```sh
mkdir -p "$HOME/quant-data/mip-20261116-v1"
cd "$HOME/quant-data/mip-20261116-v1"
gh release download data-mip-daily-20261116-v1 \
  --repo tangjia0510/quant-research \
  --pattern 'mip-daily-20261116.tar.zst' \
  --pattern 'mip-daily-20261116.tar.zst.sha256'
printf '%s  %s\n' \
  '2223a8ac2522c2911347c2c410ad97d756926cd001eda3ff25e3958b1ff03eb2' \
  'mip-daily-20261116.tar.zst' | shasum -a 256 -c - || exit 1
set -o pipefail
zstd -dc mip-daily-20261116.tar.zst | tar -xf - || exit 1
python3.11 -m venv .restore-venv
.restore-venv/bin/python -m pip install -r mip-daily-20261116/requirements.txt
.restore-venv/bin/python mip-daily-20261116/restore.py \
  "$PWD/mip-daily-20261116.duckdb"
```

输出目标必须是不存在的新文件；不要指向正在使用的 MIP 数据库。恢复程序先验证归档成员的大小和 SHA-256，再创建表并检查两类行数。预期总行数 **14,314,339**。如果有失败的 `.partial` 文件，保留排查，另选新目标路径重试。

此快照在本地制作时已完成从归档恢复、17 字段逐行比较、DOUBLE 位值/NULL 和原始 JSON 字符串比较。这个数据完整性结果不等于研究口径或交易可用性认证。新下载的归档仍需校验固定 SHA-256。

## 只读查询

继续在上面的下载目录运行：

```sh
.restore-venv/bin/python - mip-daily-20261116.duckdb <<'PY'
import sys
import duckdb

with duckdb.connect(sys.argv[1], read_only=True) as con:
    print(con.execute("""
        SELECT adjust, count(*) AS row_count, count(DISTINCT symbol) AS symbols,
               min(trade_date) AS first_date, max(trade_date) AS last_date
        FROM kline_daily_bars
        GROUP BY adjust ORDER BY adjust
    """).fetchall())
    print(con.execute("""
        SELECT q.symbol, q.trade_date, q.close AS qfq_close,
               r.close AS raw_close, r.volume AS raw_volume,
               r.turnover AS raw_turnover
        FROM kline_daily_bars q
        LEFT JOIN kline_daily_bars r
          ON r.symbol=q.symbol AND r.period=q.period
         AND r.trade_date=q.trade_date AND r.adjust='none'
        WHERE q.period='daily' AND q.adjust='qfq'
          AND q.symbol='600519.SH' AND q.trade_date >= DATE '2026-11-01'
        ORDER BY q.trade_date
    """).fetchall())
PY
```

个股查询只是用法示例，不定义研究股票池。使用 LEFT JOIN 保留未匹配原始价的行；先输出缺口清单，再判断研究是否可以继续。

## 字段和含义

主键：`(symbol, period, adjust, trade_date)`。

| 字段 | 说明 |
|---|---|
| `symbol`, `period`, `adjust`, `trade_date` | MIP 证券代码、日频标识、复权口径、交易日期；示例代码为 `600519.SH` |
| `open`, `high`, `low`, `close`, `prev_close` | 对应复权口径的价格；`prev_close` 可为空，不能无条件当作独立认证的除权参考价 |
| `volume`, `turnover` | 保留 MIP 原值；`turnover` 是成交额字段，不是换手率。成交量单位、成交额币种/尺度应按来源和证券类型核验后声明 |
| `source`, `remote_symbol`, `remote_period`, `remote_split` | 供应商及远端请求标识；这些字符串不是数值复权因子 |
| `raw_json` | 原始响应或核验证据字符串，可为空；不复权载荷中的字典仅是无损存储编码 |
| `updated_at` | 本地入库/更新时间，不是市场信息首次可得时点 |

## 用于量化研究

1. 从研究问题确定证券范围和日期；逐日检查所需 qfq/none 交集、重复键、异常价、停牌/缺日、上市退市及原始成交量单位。不可按“未来能取到完整数据”筛选历史股票池。缺失不等于停牌，也不能补成前一天价格来制造成交。
2. `qfq` 可供收益率、反转和低波动信号探索；`none` 用于真实价格、股数、整手和费用检查。前复权是当前快照口径，未来企业行为可能修订历史价格；不是历史时点冻结价。需要 PIT 或完整分红现金账时，另取对应数据，不能以本备份替代。
3. 进入 Qlib 前生成新的规范化文件及质量报告，映射为 `datetime,instrument,open,high,low,close,volume,factor`。例如将 `600519.SH` 映射成 `sh.600519`；先明确支持的市场/证券类型，不能对整个备份直接沿用 A 股执行规则。
4. 如用调整价交易，只有在同证券、同日 qfq/none OHLC 确实共享一个乘法比例时，才可使用 `factor=qfq_close/raw_close`，并按已核实的原始股数设置 `volume=raw_shares/factor`。先验证各 OHLC 比例；不满足时拒绝该转换、另建经核验的口径，不能只凭收盘比值赋因子。不要把前复权价格和未转换成交量直接作为相同计价单位送入 Qlib。
5. 按 [数据准备](data-preparation.md) 和 [数据注册](storage.md) 的流程注册**新的不可变版本**，记录本归档 SHA、证券/日期过滤、单位、转换规则、缺口及输入输出哈希，再固定协议运行研究。这里没有新增 MIP 自动适配器，恢复 DuckDB 和目录引用均不会自动完成这些转换。

已有“反转＋低波动”研究使用的是独立冻结的**后复权**、原始价补充、历史成分和状态快照。本备份只有 qfq/none，不能直接替换旧输入、沿用旧哈希或宣称复现了旧结果。

## 关联轻量研究项目

仓库有两个目录引用：`mip-daily-qfq-20261116-v1`、`mip-daily-none-20261116-v1`。它们指向同一个归档和同一个 SHA，`component` 指明数据口径，不代表下载了两个文件。

在已存在的 `project/local-paths.json` 中**合并**以下绑定，保留其他配置；路径必须改成实际下载目录，文件不提交 Git：

```json
{"mip_backup": "/absolute/path/to/mip-20261116-v1"}
```

```sh
python3 scripts/project.py --project project resolve --id mip-daily-qfq-20261116-v1
python3 scripts/project.py --project project resolve --id mip-daily-none-20261116-v1
```

`resolve` 只验证归档身份，不解压、不验证研究质量。批量行情继续保留在仓库外；更新数据时新建版本和独立 Release，不覆盖该快照或旧研究证据。数据是供应商历史快照，本仓库的代码许可不构成对供应商数据的重新授权。
