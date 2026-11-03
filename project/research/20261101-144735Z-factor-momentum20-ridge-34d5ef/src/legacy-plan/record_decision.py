import pathlib,json,hashlib,datetime,csv
p=pathlib.Path(__file__).parent;w=p.parents[1]/'studies/20261101-144735Z-factor-momentum20-ridge-34d5ef';run=w/'runs/discovery/momentum20-ridge-v1/attempt-1';m=json.loads((run/'metrics.json').read_text())
gates={'positive_rank_ic_increment':m['increment']['mean_rank_ic_increment']>0,'positive_hac95_lower':m['increment']['hac_ci95'][0]>0,'net_return_above_baseline':m['portfolio']['total_net_return']>m['baseline']['portfolio']['total_net_return'],'drawdown_no_worse':m['portfolio']['max_drawdown']>=m['baseline']['portfolio']['max_drawdown']}
assert not all(gates.values())
d={'schema_version':1,'decided_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'study_id':w.name,'candidate_id':m['candidate_id'],'research_decision':'reject_incremental_hypothesis','run_status':'complete','gates':gates,'final_run':'not_run_gate_failed','final_return':None,'parameter_search':False,'trials_used':1,'repairs_used':0,'preregistration_sha256':hashlib.sha256((p/'preregistration.json').read_bytes()).hexdigest(),'metrics_sha256':hashlib.sha256((run/'metrics.json').read_bytes()).hexdigest(),'summary_zh':'20日动量在本固定样本/协议下没有提供相对两因子Ridge基线的可信增量；停止本候选，不进入2026 final。此结论不等于所有动量策略无效。','signal_metric_scope':'prediction-vs-forward-return Pearson IC / Spearman RankIC, not raw standalone momentum factor IC'}
(w/'research-decision.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
text='''# 20日动量增量研究：结论与限制

## 结论
唯一候选完成 discovery，未通过预注册四项门槛；拒绝本次增量假设，**不运行 2026 final，不调参重试**。这不证明所有动量策略无效。

| 指标 | 两因子固定 Ridge 基线 | 增加20日动量 |
|---|---:|---:|
| 预测 IC | 0.047454 | 0.044042 |
| 预测 RankIC | -0.003167 | -0.005477 |
| 期间扣费收益 | 17.0409% | 16.3669% |
| 最大回撤 | -12.5476% | -13.2399% |

配对 RankIC 增量 -0.002309，探索性 HAC 95% 区间 [-0.009482, 0.004863]。样本等权可执行组合收益9.0485%。候选费用加倍收益14.3773%；延迟一天信号收益9.8301%。这些是历史模拟，不是投资有效性的认证。

## 口径
- 训练2020–2024，验证2025上半年，discovery 2025下半年；已执行净值曲线为2025-07-02至2025-12-31（125天）。预测日IC有120天，因下一开盘进入、5天持有标签在阶段末尾清除。
- 两个基线特征 return_5、volatility_20；唯一新增特征 close/close.shift(20)-1，共享交易日历，原始行情不补填。Ridge alpha=1、seed42固定；训练期中位数/IQR预处理；缺失特征由训练中位数填补，不等于补填原始价格。缺失标签排除。
- IC 为模型预测对未来收益的日截面相关，不是单独20日动量原始因子的IC。
- 10万元初始资金，top10、95%仓位、5日再平衡、100股单位；买费0.05%、卖费0.15%。下一交易日开盘交易。
- 30只样本按预先冻结代码排序分层选择，包含退市股；不是沪深300或全A，不代表行业分散。样本等权曲线不是官方指数；引擎另有不扣费的合成QRBENCH，不能混淆。

## 数据证据与限制
2019-01-02至2026-10-30，56,090条真实观察记录。Tencent原始价格与Sina高精度日期复权乘数相乘，成交量按原始手数×100/乘数转换。拒绝了Tencent原生后复权OHLC不满足统一乘法因子的初始方案。153源下载回执哈希和162复权事件已审核。

原质量检查141个生命周期无报价日期保持原件：分类补充证据解释138个停牌日和2个摘牌日，1个warmup日（000004，2019-11-06）仍未取得直接原件，保持未核验。prepare在观察起止区间内增加104条NaN日期，不填价格；37个终端无报价日期未伪造记录。2025下半年无缺口。

复权因子是事后获取、非独立PIT认证；日历来自观察到的上证指数交易日；混合数据供应商可能有修订。统一涨跌停代理不能精确模拟历史ST/创业板规则；退市清算、容量及真实成交不完整。000004在2026-06-23退市整理首日发生约88.77%下跌，官方公告明确首日不限幅，此行情保留，但本次没有对2026运行策略。

study.json 的 final_exposed=false 仅表示本引擎未运行final；不声称研究者从未接触2026市场历史。研究结论来自实际产物，研究决策独立记录于research-decision.json；自动生成report.md/report.html保持原样。
'''
(w/'interpretation.md').write_text(text)
artifacts={str(f.relative_to(w)):hashlib.sha256(f.read_bytes()).hexdigest() for f in w.rglob('*') if f.is_file() and f.name!='artifact-receipt.json' and not f.name.endswith('.lock')}
(w/'artifact-receipt.json').write_text(json.dumps({'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'study_id':w.name,'sha256':artifacts},ensure_ascii=False,indent=2));print(json.dumps(d,ensure_ascii=False,indent=2))
