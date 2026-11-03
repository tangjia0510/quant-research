# 迁移后研究入口

本目录是轻量研究记录。下方保留历史结论原文，但原文提及的 outputs/、report/、admission.json 等路径属于旧归档，并不表示这些大产物已搬到本目录。

- 当前元信息与数据引用：`research.yaml`、`protocol.json`。
- 尝试/失败历史：`attempts.jsonl`。
- 当前可用关键证据：`evidence/outputs/summary.json`。
- 原文按字节保存在 `evidence/legacy-conclusion.md`，旧路径应通过 `research.yaml` 的 `legacy_ref` 解析。
- 回放入口：`src/replay.py --project-root PROJECT --work-dir PROJECT/work/NEW_ATTEMPT`。
- 该入口已从外部原始响应实际重算并核对六个情景，见 `evidence/migration-replay.json`。
- 曲线、矩阵、账本和新运行报告写入指定 `work/`，不属于迁移包。

## 历史结论（保留当时措辞和路径）

# Faber SMA10 / 510300 完整策略验证

已完成一次固定策略历史模拟，真实ETF raw价格、100份整手、现金/股数/应收股利账本；不使用NAV成交，不是条件分组净值。来源原文、原始HTTP响应、协议、预结果修正及完整交易日志均在本目录。原旧研究未修改。

## 当前
- 数据2140交易日2018–2026-10-30，2018预热，评估2019起。固定1个策略，无调参，无原生Ridge模型。
- outputs/summary.json：主10bp策略累计-3.23%，同ETF基准+53.25%，未获得净超额或最大回撤改善。0/30bp敏感性全部保留。
- 24笔策略整手交易、10段完整持仓；2024-10-08本地保守边界使买入延迟至10-09。blocked是本地分配检查记录，不是交易所回执。
- 8项单测通过；独立完整结果审计已通过；4页DOCX/HTML/两图完成。作者及owner实际复核全部4页；HTML仅结构验证，浏览器受环境限制，未冒称视觉通过。准备最终封存及轻量交付。
- 当前没有运行中的计算或下载进程。禁止再启动参数变体救结果。

## 复现
使用 quant-research-library/runtime/py311/bin/python，OPENBLAS_NUM_THREADS=1。scripts/prepare_inputs.py保存原响应并校验日历/单位；scripts/evaluate.py先检查final输入SHA及协议，再生成所有固定0/10/30bp账本；scripts/diagnose_results.py仅对已有交易做持仓周期和预设分段归纳。
原生skill extract-report确实执行70页；研究Python缺pypdf，系统Python相同CLI成功，未更改任何runtime。完整策略账本为明确supplementary适配，不声称走了原生模型prepare/evaluate。

## 重要边界
历史2025/2026已暴露，非独立未见确认；股利旧7次完整公告asof链未独立核验，2026交易所公告四字段已核。付款日开盘前到账是日粒度假设。开盘成交/流动性与完整涨跌停状态未知，保守开盘边界不是完整真实交易规则。hfq仅源差异诊断，未用于信号或股数。报告不可把较低波动包装成回撤改善或实盘准入。
