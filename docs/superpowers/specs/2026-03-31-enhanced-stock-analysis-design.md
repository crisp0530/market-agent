# Enhanced Stock Analysis: Capital Flow Detection & Action Signals

**Date:** 2026-03-31
**Status:** Approved (revised after Codex review)

## Overview

增强现有 `characterize_stock` 工具输出，新增两个板块：
1. **大额资金流入检测** — 双数据源（现有 CMF + tvscreener）交叉验证
2. **操作建议（分级型）** — 默认保守建议，多信号共振时升级为具体操作建议

同时引入 tvscreener 作为**补充指标数据源**（非 OHLCV fallback）。

## Design Decisions

- **方案 B: tvscreener 作为补充数据源**，保留现有 akshare/yfinance 计算逻辑，tvscreener 数据作为第二信号源交叉验证
- **方案 C: 分级型操作建议**，默认保守，多信号共振时自动升级
- **方案 A: 增强现有工具输出**，用户无需学新指令，发"分析 601866"即自动带上新板块

## Codex Review Fixes

以下是根据 Codex 审核反馈修正的关键问题：

1. **Schema 归属修正**：新增字段放在 `StockCharacterization`（而非 `StockDiagnosis`），因为 `characterize_stock` 返回的是 `StockCharacterization`
2. **移除 OHLCV fallback 声明**：tvscreener 是 screener API，只返回当前快照指标，无法提供历史 OHLCV 数据，不能替代 yfinance
3. **MACD 条件修正**：从"由负转正"改为"MACD histogram > 0"（正值 = 多头），因为 tvscreener 只有当前快照
4. **信号判定条件补全**：确保条件穷尽，"中性"作为兜底默认值
5. **移除小幅流入的成交量要求**：消除流入/流出判定的不对称偏差
6. **CMF 值域明确**：交叉验证统一使用 0-100 评分，TvScreenerProvider 内部将原始 CMF/MFI 转换为评分
7. **止损位修正**：布林下轨下方 2% 作为止损（避免与共振条件循环）
8. **支撑位修正**：使用近期低点而非 SMA20（下跌趋势中 SMA20 在价格上方是阻力不是支撑）
9. **北交所支持**：新增 4/8 开头 symbol 映射说明

## Architecture

### 新增文件

| 文件 | 职责 |
|------|------|
| `market_analyst/providers/tvscreener_provider.py` | 封装 tvscreener 脚本调用，提供实时技术指标数据 |
| `market_analyst/processors/capital_flow_detector.py` | 资金流交叉验证逻辑 |
| `market_analyst/processors/action_signal_generator.py` | 操作建议生成逻辑（分级型） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `market_analyst/schemas_retail.py` | 新增 `CapitalFlowSignal`、`ActionSignal` schema；扩展 `StockCharacterization` 新增可选字段 |
| `market_analyst/mcp_server.py` | `characterize_stock` 整合 tvscreener 数据，调用新处理器，组装增强输出 |
| `config/config.yaml` | 新增 `capital_flow`、`action_signal`、`tvscreener` 配置段 |

### 数据流

```
用户发 "分析 601866"
    → characterize_stock(symbol="601866")
    → 并行获取:
        ├── StockCollector (akshare/yfinance) → 60天 OHLCV → 定性评分 + CMF
        └── TvScreenerProvider (tvscreener) → 实时快照指标 (MFI, RELATIVE_VOLUME, MACD 等)
    → StockDiagnostor.diagnose() → 五维评分（含 CMF flow score）
    → CapitalFlowDetector.detect() → 交叉验证资金流
    → ActionSignalGenerator.generate() → 操作建议
    → 组装到 StockCharacterization → 返回给用户
```

## Component Details

### 1. TvScreenerProvider

```python
# market_analyst/providers/tvscreener_provider.py

@dataclass
class TvScreenerData:
    relative_volume: float | None      # 相对成交量（放量倍数）
    cmf_20: float | None               # 佳庆资金流(20) — 已转换为 0-100 评分
    mfi_14: float | None               # 资金流指标(14) — 原始值 0-100
    rsi_14: float | None               # RSI — 原始值 0-100
    macd_hist: float | None            # MACD 柱（原始值）
    recommendation: str | None         # TradingView 综合推荐
    price: float | None                # 当前价格
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    bollinger_upper: float | None
    bollinger_lower: float | None

class TvScreenerProvider:
    def fetch(self, symbol: str, market: str) -> TvScreenerData | None:
        """调用 tvscreener 脚本获取实时数据，失败返回 None。

        内部将原始 CMF [-0.5, +0.5] 转换为 0-100 评分，
        与 diagnostor 的 flow score 保持同一值域。
        """
```

**Symbol 映射规则**：
- A 股：`6` 开头 → `SHSE:{symbol}`，`0/3` 开头 → `SZSE:{symbol}`
- 北交所：`4/8` 开头 → 不支持 tvscreener（返回 None，降级为单源判断）
- 美股：先试 `NASDAQ:{symbol}`，失败试 `NYSE:{symbol}`

**实现方式**：通过 `subprocess` 调用 tvscreener 的 `query_symbol.py` 脚本，解析 JSON 输出。设置 `timeout_seconds` 超时保护。

**容错**：tvscreener 获取失败时返回 None，不影响现有功能。

### 2. 大额资金流入检测

```python
# market_analyst/processors/capital_flow_detector.py

class CapitalFlowDetector:
    def detect(self, cmf_score: float | None, tv_data: TvScreenerData | None, config: dict) -> CapitalFlowSignal:
        """交叉验证资金流信号。cmf_score 和 mfi 均为 0-100 评分。"""
```

**交叉验证规则**（CMF score 和 MFI 均为 0-100 评分）：

判定按优先级从上到下匹配，第一个命中即返回：

| 优先级 | 信号等级 | 条件 | 输出文案 |
|-------|---------|------|---------|
| 1 | 大幅流入 | CMF > 60 且 MFI > 70 且 相对成交量 > 1.5 | "资金大幅流入，主力积极介入" |
| 2 | 大幅流出 | CMF < 30 且 MFI < 30 且 相对成交量 > 1.5 | "放量资金流出，主力撤离" |
| 3 | 小幅流入 | CMF > 55 且 MFI > 45（双源）；或单源 CMF > 65 | "资金小幅流入" |
| 4 | 流出 | CMF < 40 且 MFI < 40 | "资金流出，注意风险" |
| 5 | 中性（兜底） | 以上均不满足 | "资金流向不明确" |

**降级策略**（tvscreener 失败，MFI 为 None 时）：
- 跳过主判定表，直接走单源逻辑：
  - CMF > `single_source_inflow`(65) → 小幅流入
  - CMF < `single_source_outflow`(35) → 流出
  - 其他 → 中性
- 大幅流入/大幅流出在单源模式下不触发（需要双源验证）

### 3. 操作建议（分级型）

```python
# market_analyst/processors/action_signal_generator.py

class ActionSignalGenerator:
    def generate(self, rating: int, capital_flow: CapitalFlowSignal,
                 diag_scores: dict, tv_data: TvScreenerData | None,
                 config: dict) -> ActionSignal:
        """基于星级给保守建议，检测共振条件决定是否升级。"""
```

**默认保守建议**（基于五维评分综合星级）：

| 星级 | 建议 |
|------|------|
| 1-2 星 | "建议回避，等待趋势明朗" |
| 3 星 | "暂时观望，关注变化" |
| 4-5 星 | "可以关注，等待入场信号" |

**信号共振条件**（满足 3 个及以上升级）：

| 编号 | 条件 | 数据来源 | 说明 |
|------|------|---------|------|
| 1 | RSI < 30（超卖） | tvscreener rsi_14 优先，不可用时用 diagnostor sentiment score | 单一权威源 |
| 2 | MACD histogram > 0（多头） | tvscreener macd_hist | 正值表示多头动能（非金叉检测，因为只有快照） |
| 3 | 资金流入 | capital_flow.signal in ["小幅流入", "大幅流入"] | 上一步交叉验证结果 |
| 4 | 价格在布林下轨附近（距离 < margin） | tvscreener price vs bollinger_lower | `(price - lower) / price < margin` |
| 5 | TradingView 综合推荐 = 买入/强买 | tvscreener recommendation | "Buy" 或 "Strong Buy" |

**升级后输出**：
- 列出满足的共振条件
- 参考支撑位：近 20 日最低收盘价（从 diagnostor OHLCV 数据获取）
- 参考止损位：布林下轨 × (1 - margin)，即下轨下方 2%
- 附带风险提示："以上不构成投资建议"

**tvscreener 不可用时**：最多只能满足条件 1（RSI 来自 diagnostor）和条件 3（资金流来自 CMF 单源），无法达到 3 个共振门槛，自动退化为保守建议。

### 4. Schema 扩展

**新增 schema（在 `market_analyst/schemas_retail.py`）：**

```python
class CapitalFlowSignal(BaseModel):
    """资金流入检测结果。"""
    signal: Literal["大幅流入", "小幅流入", "中性", "流出", "大幅流出"]
    cmf_score: float | None = None          # 内部指标（diagnostor CMF 评分 0-100）
    mfi_score: float | None = None          # 外部指标（tvscreener MFI 0-100）
    relative_volume: float | None = None    # 成交量倍数（tvscreener）
    description: str                        # 文案描述
    dual_source: bool = False               # 是否双源验证

class ActionSignal(BaseModel):
    """操作建议（分级型）。"""
    level: Literal["conservative", "resonance"]
    advice: str                              # 建议文案
    resonance_count: int = 0                 # 共振条件满足数
    resonance_details: list[str] = Field(default_factory=list)  # 满足的条件列表
    support_price: float | None = None       # 参考支撑位（近20日最低价）
    stop_loss_price: float | None = None     # 参考止损位（布林下轨 × 0.98）
```

**扩展现有 schema（在 `market_analyst/schemas_retail.py` 的 `StockCharacterization`）：**

```python
class StockCharacterization(BaseModel):
    # ... 现有字段保持不变
    capital_flow: CapitalFlowSignal | None = None   # 新增，可选
    action: ActionSignal | None = None              # 新增，可选
```

新增字段默认为 `None`，不影响现有调用方。

### 5. 输出格式

完整回复结构（由 agent 根据 JSON 数据格式化，非工具硬编码）：

```
📊 {股票名}（{代码}）综合分析

⭐ 综合评级：{星级}

【五维评分】
• 趋势: {score} ({label})
• 动量: {score} ({label})
• 情绪: {score} ({label})
• 波动: {score} ({label})
• 资金流: {score} ({label})

【资金流入检测】
{emoji} 资金信号：{signal}
• 内部指标(CMF): {value}，{description}
• 外部指标(MFI): {value}，{description}（或"数据不可用"）
• 成交量: {relative_volume}倍均量，{放量/缩量}状态
→ {总结}

【操作建议】
{保守建议 或 共振升级建议}

⚖️ 以上分析仅供参考，不构成投资建议。
```

### 6. 配置项

```yaml
# config/config.yaml 新增
capital_flow:
  # 交叉验证阈值（CMF 和 MFI 均为 0-100 评分）
  strong_inflow_cmf: 60
  strong_inflow_mfi: 70
  strong_inflow_volume: 1.5
  mild_inflow_threshold: 55
  outflow_threshold: 40
  strong_outflow_threshold: 30
  strong_outflow_volume: 1.5
  # 单源降级阈值
  single_source_inflow: 65
  single_source_outflow: 35

action_signal:
  # 共振升级门槛
  resonance_min_count: 3
  # 各条件阈值
  oversold_rsi: 30
  macd_hist_positive: true       # MACD histogram > 0 视为多头
  bollinger_touch_margin: 0.02   # 价格距下轨 2% 以内视为触及
  stop_loss_margin: 0.02         # 止损设在下轨下方 2%
  tv_buy_signals: ["Buy", "Strong Buy"]

tvscreener:
  enabled: true
  scripts_dir: "scripts/tvscreener"  # tvscreener 脚本目录路径
  timeout_seconds: 15
```

## Testing

每个组件需要单元测试：
- `test_tvscreener_provider.py` — Symbol 映射（含北交所降级）、JSON 解析、CMF 值域转换、超时处理、失败返回 None
- `test_capital_flow_detector.py` — 5 种信号等级的判定逻辑、优先级顺序、单源降级、边界条件
- `test_action_signal_generator.py` — 保守建议（各星级）、共振升级（3/5条件）、tvscreener 不可用时自动退化、支撑/止损价格计算
- `test_enhanced_characterize_stock.py` — 完整集成测试，含 tvscreener 成功/失败两种路径、新字段向后兼容
