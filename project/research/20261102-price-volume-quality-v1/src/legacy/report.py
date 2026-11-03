from pathlib import Path
import json,hashlib,datetime
import pandas as pd
R=Path(__file__).resolve().parents[1];A=R/'artifacts'
def save(n,o):(A/n).write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str,allow_nan=False))
def f(x,d=4):return '未定义' if x is None else f'{x:.{d}f}'
def main():
 q=json.loads((A/'quality-summary.json').read_text());m=json.loads((A/'metrics.json').read_text());cov=json.loads((A/'split-coverage.json').read_text());per=pd.read_csv(A/'per-security-quality.csv');total=q['quality_totals'];
 txt=['# 沪深日频量价数据质量与固定20日动量诊断','',f'生成时间：{datetime.datetime.now(datetime.timezone.utc).isoformat()}','',
 '## 结论口径','本研究检查当前数据是否足以形成可信的研究输入，不是盈利策略验收。不是原生 Qlib 完整模拟流程；使用遵循同一日期/隔离原则的独立只读诊断程序。没有拟合模型，没有试多个参数挑最好结果。2026 段在固定协议后读取，已登记 exposed，后续调参不得再把它叫作未见测试集。','',
 '## 数据与质量门槛',f'- 冻结沪深目标 {q["universe"]:,} 个，包含当前已退市 {q["statuses"].get("delisted",0)} 个；北交所排除，未使用当前指数成分筛历史。',f'- 观察日期 2019-01-02 至 2026-10-30；2019 用于预热及质量检查。日历来自上证指数观察，非交易所认证完整日历。',
 '- 整行优先级为 Tencent 已规范化行情、Tencent 缺日补片、HF 未复权历史。绝不跨源拼同一行 OHLCV。股数/CNY 已统一，不再重复乘100。',
 '- 原价乘按生效日 backward-asof 匹配的新浪后复权因子；缺因子不填1。源自带1900基准记录保留，但不是公司行动。复权生效日匹配不证明历史版本或事件时点全部正确。',
 '- 因子为 t 日复权收盘 / t-20 交易日复权收盘 -1；信号需要21连续合格交易日日线、IPO后至少60日。旧IPO在2019开头也保守等待60个观察日。',
 '- 标签为 t+6 复权开盘 / t+1 复权开盘 -1；要求6个未来日均满足质量门槛，缺日不压缩、不开未来同收盘交易。跨分段的标签剔除。',
 '- 合格日要求有限正OHLC、成交量/额、价格排序、量额隐含VWAP位于高低价±2%、因子有效、代码/生命周期有效。超过50%单日复权涨跌作为保守异常标记；这可能排除真实事件，不等于认定源错误。','',
 '|质量项目|数量|','|---|---:|']
 labels={'observed_rows':'去重后观察股日','missing_within_lifecycle':'存续区间内缺观察股日','outside_lifecycle_observed':'生命周期之外仍有行情的股日','invalid_numeric':'非有限字段股日','ohlc_ordering_fail':'OHLC排序异常股日','nonpositive_ohlcv_amount':'非正价量额股日','vwap_outside_2pct':'量额隐含VWAP超±2%股日','factor_missing_or_invalid':'复权因子缺失/无效股日','adjusted_move_over_50pct':'单日复权涨跌超50%股日','good_bars':'基本质量合格股日','signal_rows':'可形成固定动量信号股日','signal_with_missing_outcome':'有信号但未来标签缺失股日','signal_labeled':'有信号及完整标签股日'}
 for k,l in labels.items():txt.append(f'|{l}|{total.get(k,0):,}|')
 txt+=['',f'来源重叠键 {q["source_overlap_dates"]:,} 个，OHLC差异大于0.011的键 {q["source_ohlc_conflicts"]:,} 个。不同质量类别有重叠，不能相加当总缺失。样本末尾6交易日的未来标签自然未成熟，不算源漏采；split-coverage.json将其与内部未来数据缺失分列。无任何原价的标识另列在 per-security-quality.csv，不凭空造日线。','',
 '## 固定外样本因子结果','IC 是因子本身与未来5日收益的截面相关，不是 XGBoost 或 Ridge 预测IC。HAC标准误采用Newey–West lag5；只是固定样本统计，不抵消幸存/观测/修订偏差。','',
 '|分段|信号股日|可用标签股日|证券|Pearson IC均值|Rank IC均值|Rank IC HAC t|Q5-Q1平均5日收益|','|---|---:|---:|---:|---:|---:|---:|---:|']
 for c in cov:
  s=c['split'];z=m[s];txt.append(f'|{s}|{c["signal_rows"]:,}|{c["eligible_rows"]:,}|{c["securities"]:,}|{f(z["pearson_ic"]["mean"])}|{f(z["rank_ic"]["mean"])}|{f(z["rank_ic"]["hac_t"],2)}|{f(z["q5_minus_q1_forward5"]["mean"]*100,3)}%|')
 txt+=['','### 分组前瞻收益（非策略净值）','按每日固定信号排序分5组，1为低动量、5为高动量；并列按证券代码顺序确定，不使用标签。以下是重叠5日收益的日期平均，不能逐日复利为组合净值。','', '|分段|Q1|Q2|Q3|Q4|Q5|','|---|---:|---:|---:|---:|---:|']
 for s in ['discovery','final']:txt.append('|'+s+'|'+'|'.join(f'{m[s]["group_mean_forward5"][str(i)]*100:.3f}%' for i in range(1,6))+'|')
 txt+=['','## 为什么还不能等同可交易策略','- 标签是否齐全是未来才知道的事。按未来数据可得性保留样本会造成选择偏差，尤其停牌、退市终止收益；有信号而缺标签的记录已保留，不将其视为现金收益0。',
 '- 纳入了有历史记录的退市股票，仍不等于完整退市总收益建模。没有退市现金处置/终止收益、股票借贷、交易费用、冲击、涨跌停成交约束或T+1组合模拟。',
 '- 完整历史ST状态未知，没有将未知状态认定为可交易。观察日线价格也不保证能在目标开盘成交。',
 '- volume/VWAP门槛是保守质量筛选，可能删去合法大宗/取整口径，不能把该筛选后结果推广为全市场无偏结果。',
 '- nonoverlap-diagnostic-wealth.csv 仅为每分段全局日历固定相位每5日的合成等权分组财富轨迹，没有执行约束；缺期不代表现金可投资。不得作为策略净值宣传。',
 '- 证券代码迁移存在明确边界：供应商在302132名下回映射了1,472个2025-02-17之前的观察股日，已排除；冻结master没有独立300114目标，所以不能声称迁移前中航电测历史已完整覆盖。没有把两代码自动拼成连续序列。',
 '- 数据主要为抓取时的最新供应商版本。原始数据和因子是否历史vintage均未认证；高IC不反向证明源数据正确。','',
 '## 产物与复现',
 '- protocol.json：指标读取前固定协议；implementation-repairs.json：指标前生命周期与性能修正；exposure-ledger.json：测试段暴露记录。',
 '- dataset/*.parquet：每证券全局日历诊断面板（缺日保留NaN）、源、原价、因子、质量掩码。',
 '- artifacts/input-manifest.json：全部使用原文件SHA；未修改数据湖。',
 '- per-security-quality.csv/json、daily-quality-coverage.csv、flagged-observations.parquet：质量证据。',
 '- signal-samples.parquet：包括尚无未来标签的全部信号；split-coverage.json：分段排除及退市统计。',
 '- daily-ic.csv、daily-quintile-forward-returns.csv、metrics.json：真实测量结果。',
 '- factor-diagnostic.png、coverage-diagnostic.png：因子与覆盖图。',
 '- scripts/test_diagnostic.py：日期、缺日、因子缺失、未来扰动、缩放、生命周期和量单位回归。','',
 '复现：使用 quant-research-library/runtime/py311/bin/python 依次运行 scripts/build_diagnostic.py、scripts/test_diagnostic.py、scripts/evaluate.py、scripts/plot_coverage.py、scripts/report.py。对已交付研究重新运行前应复制新版本目录，避免覆盖已经冻结的结果。']
 (R/'REPORT.md').write_text('\n'.join(txt)+'\n')
 files={}
 for p in sorted(R.rglob('*')):
  if p.is_file() and '__pycache__' not in str(p) and p.name!='artifact-manifest.json':files[str(p.relative_to(R))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 save('artifact-manifest.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'research_kind':'data_quality_factor_diagnostic','native_qlib_run':False})
if __name__=='__main__':main()
