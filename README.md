# Quant Research

让 Codex、Claude Code 等编码助手用 Qlib 做可复现的日频股票量化研究。助手负责提出假设、实现候选和解释结果，Python 脚本负责数据准备、检查、训练、回测和保存证据。

支持因子研究、模型比较、因子与模型交替改进，以及从报告公式出发的复现。内置 BaoStock 数据适配器、可复用因子库和合成数据示例。

## 安装技能

以下命令获取 `main` 分支的当前源码。源码放在 `~/src/quant-research`，数据和运行环境默认放在 `~/quant-research`，两者需要分开。

```sh
mkdir -p "$HOME/src"
git clone --branch main https://github.com/tangjia0510/quant-research.git "$HOME/src/quant-research"
QR_SKILL_SOURCE="$HOME/src/quant-research"
```

按使用的助手选择一个入口，也可以同时安装。目标路径已有内容时，先检查现有安装。

```sh
# Codex
mkdir -p "$HOME/.codex/skills"
ln -s "$QR_SKILL_SOURCE" "$HOME/.codex/skills/quant-research"

# Claude Code
mkdir -p "$HOME/.claude/skills"
ln -s "$QR_SKILL_SOURCE" "$HOME/.claude/skills/quant-research"
```

重新打开助手会话后即可发现技能。完整说明见 [安装与迁移](references/portability.md)。

## 准备 Python 环境

需要 Python 3.11 和 `uv`。在源码目录执行：

```sh
cd "$QR_SKILL_SOURCE"
python3 scripts/quant.py --help
python3 scripts/quant.py bootstrap --venv "$HOME/quant-research/runtime/py311"

QR_PYTHON="$HOME/quant-research/runtime/py311/bin/python"
"$QR_PYTHON" scripts/quant.py config init
"$QR_PYTHON" scripts/quant.py doctor
"$QR_PYTHON" scripts/quant.py defaults
```

`bootstrap` 根据 `uv.lock` 安装依赖。需要自定义 PyTorch 模型或 PDF 提取时，使用 `bootstrap --extras models reports`。运行环境、行情、研究记录和生成报告均保存在技能目录之外。

## 开始研究

给助手一个具体问题、数据来源和候选数量预算，例如：

> 使用 quant-research 做一次因子研究。先检查已有数据版本，核对日线数据的字段、复权口径和交易日历。以 return_5、volatility_20 和 Ridge 为基线，最多比较 6 个候选。保留失败尝试，冻结候选后评估最终测试集，给出带实验记录的报告。

默认协议固定为 2020 至 2024 年训练、2025 年验证、2026 年测试，初始资金为 10 万元；2025 年上半年用于模型验证，下半年用于研究比较。数据不足时需要明确处理，年份不会自动滚动。可用显式协议调整研究设定。

研究依次经过 `prepare`、`check`、`evaluate`、`freeze`、`finalize` 和 `report`。示例数据是合成数据，仅用于验证软件执行；研究结果需要结合数据覆盖、交易成本和样本外证据解释。

## 文档

- [技能入口](SKILL.md) 与 [四种研究模式](references/research-modes.md)
- [数据准备](references/data-preparation.md) 与 [存储和研究索引](references/storage.md)
- [因子库](references/factor-library.md)、[研究契约](references/contracts.md) 和 [结果验证](references/validation.md)
- [来源与改编说明](references/provenance.md) 及保留的 [RD-Agent 许可文本](references/rd-agent-license.txt)

## 开发验证

开发依赖也安装在源码目录外，测试使用临时目录：

```sh
UV_PROJECT_ENVIRONMENT="$HOME/quant-research/runtime/dev-py311" uv sync --locked --all-extras --python 3.11
QR_DEV_PYTHON="$HOME/quant-research/runtime/dev-py311/bin/python"
"$QR_DEV_PYTHON" -m pytest -q
"$QR_DEV_PYTHON" tests/smoke_modes.py --output /tmp/quant-research-smoke-new
```

冒烟测试的输出目录必须为空或尚不存在。它使用合成数据运行四种模式，验证执行流程、缓存复用和冻结后的候选保护。
