# 散户模块补齐设计文档

**日期**: 2026-03-30
**状态**: 已确认
**范围**: 在现有 market-analyst MCP server 中新增 4 个工具，补齐散户功能模块

---

## 1. 概述

### 背景

market-analyst MCP server 已实现 10 个工具，覆盖散户约 60-70% 的需求。本设计补齐剩余 4 个功能：

1. **个股定性** (`characterize_stock`) — 判定游资票/机构票/机游合力票
2. **加减仓建议** (`get_trade_signal`) — 大吉/小吉/平/小凶/大凶
3. **财报解读** (`analyze_earnings`) — 超预期判定 + 风险标记
4. **交易策略普及** (`get_trading_strategies`) — 策略匹配 + 盈亏比教育

### 架构决策

**方案 A（已选定）**：全部作为 MCP 工具集成到现有 `market-analyst` server，复用已有架构（缓存、错误处理、schema 模式、collector 体系）。工具总数从 10 增至 14。

### 依赖关系

```
characterize_stock      ← get_trade_signal（定性修正权重）
                        ← get_trading_strategies（策略匹配依据）
diagnose_stock          ← get_trade_signal（个股技术面）
                        ← get_trading_strategies（行情状态）
get_market_overview     ← get_trade_signal（大盘环境）
get_fear_score          ← get_trading_strategies（恐慌匹配）
get_sector_strength     ← get_trading_strategies（板块 tier，可选）
```

### 工具实现模式

所有新工具遵循现有 `_xxx_impl() + @mcp.tool()` 包装模式：
- 纯函数 `_characterize_stock_impl()` 等，可独立测试
- `@mcp.tool()` 装饰器仅负责参数解析、缓存调用、异常捕获
- 测试分两层：processor 单元测试 + `_impl` 集成测试（写入 `test_mcp_server.py`）

---

## 2. 个股定性 `characterize_stock`

### 功能

输入股票代码，判定其交易特征类型，为后续分析提供基础分类。

### 定性维度

| 维度 | 游资票特征 | 机构票特征 | 数据源 | 可用性 |
|------|-----------|-----------|--------|--------|
| 换手率 | 高（>8% 日均） | 低（<3% 日均） | OHLCV volume / market_cap 估算 | CN/US 均可（US 用 yfinance `sharesOutstanding`；CN 用 akshare `stock_individual_info_em` 获取总股本） |
| 波动率 | 高 ATR% | 低 ATR% | OHLCV 直接计算 | 始终可用 |
| 成交量模式 | 脉冲式放量（量比>3） | 稳定温和放量 | OHLCV volume | 始终可用 |
| 涨停/大阳频率 | 频繁（近20日涨停≥2次） | 罕见 | 日涨跌幅统计 | 始终可用（CN 用 9.5% 阈值，US 用 8%） |
| 机构持仓占比 | 低 | 高（>30%） | CN: `stock_fund_stock_holder(symbol=代码)` 按 symbol 返回基金持股；US: yfinance `Ticker.institutional_holders` | 可选（季报滞后，可能缺失） |
| 市值 | 偏小（<200亿） | 偏大（>500亿） | CN: `stock_individual_info_em(symbol=代码)`；US: yfinance `Ticker(symbol).info["marketCap"]` | 通常可用 |

> **已移除"板块辨识度"维度**：当前 A 股 StockCollector 的 sector 字段是硬编码 "个股"，无法提供真实板块归属和板块时间序列。在没有可靠板块数据前，该维度不纳入评分。

### 评分机制

每个维度 0-100 分，**动态加权求和**（缺失维度自动剔除并重归一化权重）：

| 维度 | 基础权重 | 游资倾向计算 | 机构倾向计算 | 可缺失 |
|------|---------|-------------|-------------|--------|
| 换手率 | 25% | 越高越高分 | 越低越高分 | 否（OHLCV 始终可算） |
| 波动率 | 20% | ATR% 越高越高分 | ATR% 越低越高分 | 否 |
| 成交量模式 | 20% | 量比脉冲越多越高分 | 成交量稳定性越高越高分 | 否 |
| 涨停/大阳频率 | 15% | 近20日涨停次数越多越高分 | 越少越高分 | 否 |
| 机构持仓占比 | 10% | 越低越高分 | 越高越高分 | **是**（季报滞后30-45天，可能缺失） |
| 市值 | 10% | 越小越高分 | 越大越高分 | **是**（API 调用可能失败） |

**动态权重重归一化**：当可选维度（机构持仓、市值）缺失时，将其权重按比例分摊到其余维度。例如机构持仓缺失时，其 10% 权重按比例分配给换手率(+2.8%)、波动率(+2.2%)、成交量(+2.2%)、涨停频率(+1.7%)、市值(+1.1%)。

**Schema 增加 `available_dimensions`**：记录实际参与评分的维度列表，便于 Agent 解释结果。

> **注意**: 机构持仓数据来自季报披露，存在 30-45 天滞后。当数据超过 45 天时，在 `key_evidence` 中标注数据新鲜度。

### 判定规则

| 条件 | 判定 |
|------|------|
| 游资倾向 > 65 且 机构倾向 < 40 | **游资票** |
| 机构倾向 > 65 且 游资倾向 < 40 | **机构票** |
| 两者都 > 45 | **机游合力票** |
| 其他 | **普通票** |

### 分析建议联动

- 游资票 → 关注市场辨识度、情绪周期、板块梯队位置
- 机构票 → 关注基本面、业绩预期、估值水平
- 机游合力 → 兼顾基本面和情绪面，关注放量突破信号

### 输出 Schema

```python
class StockCharacterization(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    hot_money_score: float = Field(ge=0, le=100)   # 游资倾向
    institutional_score: float = Field(ge=0, le=100) # 机构倾向
    available_dimensions: list[str]  # 实际参与评分的维度
    key_evidence: list[str]   # 3-5条关键依据
    analysis_tips: str        # 针对该类型的分析建议
    stale: bool = False
```

### 新增 Processor

`processors/stock_characterizer.py`

```python
class StockCharacterizer:
    def __init__(self, config: dict): ...
    def characterize(self, symbol: str, raw_df: DataFrame, market: str) -> StockCharacterization: ...
```

数据获取：复用 `StockCollector.collect_single()` 获取 OHLCV，新增 akshare 调用获取机构持仓/市值（A股），yfinance info 获取 marketCap（美股）。

---

## 3. 加减仓建议 `get_trade_signal`

### 功能

输入股票代码，综合大盘 + 个股 + 定性，输出吉凶判定及理由。

### 三层评估模型

| 层级 | 权重 | 评估内容 | 数据来源 |
|------|------|---------|----------|
| 大盘环境 | 30% | 市场温度 + 恐慌指数 + 涨跌家数比 | `_get_market_overview_impl` |
| 个股技术面 | 50% | 趋势 + 动量 + 情绪 + 资金流 + 波动率 | `StockDiagnostor.diagnose()` |
| 定性修正 | 20% | 游资票加大情绪权重，机构票加大趋势权重 | `StockCharacterizer.characterize()` |

### 综合评分

```
综合分 = 大盘分 × 0.3 + 个股分 × 0.5 + 定性修正分 × 0.2
```

### 定性修正逻辑

**character_score 始终通过加权计算得出，而非固定值**：

1. 取 diagnose_stock 的 5 维度分数
2. 按 character_type 调整各维度权重：
   - **游资票**：sentiment ×1.5, trend ×0.7, 其余 ×1.0
   - **机构票**：trend ×1.3, sentiment ×0.8, 其余 ×1.0
   - **机游合力**：所有维度 ×1.0（均衡权重）
   - **普通票**：所有维度 ×1.0（均衡权重）
3. 加权求均值得到 `adjusted_stock_score`
4. `character_score = adjusted_stock_score`（不是固定 50）

**效果**：游资票/机构票的 character_score 会偏离原始均值（因为权重调整），机游合力/普通票的 character_score 等于原始均值（权重未调整）。

### 吉凶映射

| 综合分 | 判定 | 含义 |
|--------|------|------|
| 80-100 | 大吉 | 多维共振向好，可积极操作 |
| 60-79 | 小吉 | 偏多但有瑕疵，轻仓试探 |
| 40-59 | 平 | 多空胶着，建议观望 |
| 20-39 | 小凶 | 偏空信号，减仓或回避 |
| 0-19 | 大凶 | 多维共振向下，远离 |

### 输出 Schema

```python
class TradeSignal(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    signal: Literal["大吉", "小吉", "平", "小凶", "大凶"]
    score: float = Field(ge=0, le=100)             # 综合分
    market_score: float = Field(ge=0, le=100)      # 大盘分
    stock_score: float = Field(ge=0, le=100)       # 个股原始均分
    character_score: float = Field(ge=0, le=100)   # 定性修正分（加权调整后的个股分）
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    score_breakdown: dict[str, float]  # 各维度明细 {"trend": 72, "momentum": 65, ...}
    reasons: list[str]       # 2-3条简明理由
    risk_warnings: list[str] # 风险提示
    stale: bool = False
```

### 依赖失败回退

- `characterize_stock` 失败 → 默认 `character_type="普通票"`，以均衡权重（所有维度 ×1.0）重算 `character_score`
- `diagnose_stock` 失败 → 返回 `ToolError`（个股技术面是核心，不能省略）
- `get_market_overview` 失败 → 返回 `ToolError`（大盘环境是必要输入）

### 新增 Processor

`processors/trade_signal_generator.py`

```python
class TradeSignalGenerator:
    def __init__(self, config: dict): ...
    def generate(self, symbol: str, market_overview: MarketOverview,
                 diagnosis: StockDiagnosis, characterization: StockCharacterization) -> TradeSignal: ...
```

---

## 4. 财报解读 `analyze_earnings`

### 功能

输入股票代码，拉取最近财报，判断超预期/不及预期，标记风险。

### 数据获取

| 数据项 | A股（akshare） | 美股（yfinance） | 备注 |
|--------|---------------|-----------------|------|
| 营收/净利润（近4季） | `stock_financial_analysis_indicator(symbol)` | `Ticker.quarterly_financials` | 东方财富源，按 symbol 返回多期数据 |
| 同比增速 | 计算得出 | 计算得出 | |
| 分析师预期 | `stock_profit_forecast_em(symbol)` | `Ticker.earnings_estimate` | 覆盖率因股票而异，无数据时退化为 YoY |
| ST 状态 | `stock_zh_a_st_em()` → 全量表过滤 | N/A | 返回全市场 ST 列表，按代码过滤 |
| 减持公告 | `stock_hold_management_detail_em()` → 全量表按 symbol 过滤 | `Ticker(symbol).insider_transactions` | 接口无参数，返回全市场高管增减持明细，需按股票代码过滤 |
| 质押比例 | `stock_gpzy_pledge_ratio_em(date=最近交易日)` → 全量表按 symbol 过滤 | N/A | 按日期拉全市场数据再过滤，需最近可用日期回退逻辑 |

> **API 稳定性原则**:
> 1. 统一优先使用 akshare 的 `_em`（东方财富）系列接口
> 2. 实现时必须验证 akshare 安装版本（项目约束 `>=1.12.0`）的函数签名
> 3. 每个 API 调用都需 try/except，失败时该维度标记为不可用而非崩溃
> 4. 质押比例接口特殊：按交易日拉全量表后过滤，需实现"最近可用日期回退"（最多回退 5 个交易日）

### 超预期判定

```
差异率 = (实际 - 预期) / |预期| × 100%

> +10%   → 大幅超预期
> +3%    → 小幅超预期
±3%      → 符合预期
< -3%    → 小幅不及预期
< -10%   → 大幅不及预期
```

无预期数据时退化为同比分析（复用同一套标签，通过 `expectation_basis` 区分来源）：

```
净利润同比 > +30%  → 大幅超预期（basis=yoy_fallback）
净利润同比 > +10%  → 小幅超预期（basis=yoy_fallback）
±10%               → 符合预期（basis=yoy_fallback）
< -10%             → 小幅不及预期（basis=yoy_fallback）
< -30%             → 大幅不及预期（basis=yoy_fallback）
无足够数据         → 无预期数据
```

### 风险标记

| 风险项 | 触发条件 | 等级 |
|--------|---------|------|
| ST 风险 | 当前为 ST/*ST | 高 |
| 减持风险 | 近90天大股东减持 > 1% | 中 |
| 质押风险 | 质押比例 > 50% | 中 |
| 亏损风险 | 连续2季净利润为负 | 高 |
| 营收萎缩 | 连续2季营收同比下滑 | 中 |

### 输出 Schema

```python
class QuarterlyMetric(BaseModel):
    quarter: str              # "2025Q4"
    revenue: float            # 营收（亿元/亿美元）
    revenue_yoy: float | None # 营收同比%
    profit: float             # 净利润
    profit_yoy: float | None  # 净利润同比%

class RiskFlag(BaseModel):
    type: Literal["ST风险", "减持风险", "质押风险", "亏损风险", "营收萎缩"]
    level: Literal["high", "medium"]
    detail: str               # 具体描述

class EarningsAnalysis(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    latest_quarter: str               # "2025Q4"
    revenue: float                    # 营收（亿元/亿美元）
    net_profit: float                 # 净利润
    revenue_yoy: float                # 营收同比%
    profit_yoy: float                 # 净利润同比%
    expectation_basis: Literal["consensus", "yoy_fallback", "none"]  # 判定依据来源
    expectation: Literal["大幅超预期", "小幅超预期", "符合预期", "小幅不及预期", "大幅不及预期", "无预期数据"]
    deviation_pct: float | None       # 偏差率%
    quarterly_trend: list[QuarterlyMetric]  # 近4季数据
    trend_summary: Literal["连续增长", "拐点向上", "拐点向下", "持续下滑", "波动"]
    risks: list[RiskFlag]             # 风险标记
    plain_summary: str = Field(max_length=300)  # ≤300字通俗解读
    stale: bool = False
```

### 新增文件

- `processors/earnings_analyzer.py` — 核心逻辑
- `collectors/earnings_collector.py` — 财务数据采集（封装 akshare/yfinance 差异）

### Collector 接口

**设计决策**：EarningsCollector **不继承 BaseCollector**，不返回 DataFrame。理由：
1. 财报数据是异构结构（财务指标 + 预期 + 风险标志），无法自然映射为 OHLCV DataFrame
2. 强行塞入 DataFrame 会导致大量 NaN 列和类型混乱
3. 独立的 dict 接口更清晰，代价是不能复用 DataCache 的 parquet 缓存

**缓存方案**：新增 `JsonCache` 类（或在现有 `DataCache` 中增加 `get_or_fetch_json` 方法），支持 JSON 格式缓存。这是一个通用能力，未来的非 OHLCV 数据源也能复用。

```python
class EarningsCollector:
    """财务数据采集器。不继承 BaseCollector（非 OHLCV 数据）。"""
    def __init__(self, config: dict): ...
    def collect(self, symbol: str, market: str = "cn") -> dict:
        """返回:
        {
            "financials": [{quarter, revenue, net_profit, revenue_yoy, profit_yoy}],
            "forecast": {consensus_profit: float | None},
            "risks": {is_st: bool, reductions: [...], pledge_ratio: float | None},
            "meta": {name: str, currency: str}
        }
        """
```

**DataCache 扩展**：

```python
# 在 utils/cache.py 中新增
def get_or_fetch_json(self, key: str, fetch_func, max_age_hours: int = 24) -> dict:
    """JSON 缓存，用于非 DataFrame 数据。存储为 .json 文件。"""
```

---

## 5. 交易策略普及 `get_trading_strategies`

### 功能

结合个股行情推荐适用策略，附带盈亏比教育。支持带/不带 symbol 两种模式。

### 策略知识库

| 策略 | 适用场景 | 止损 | 盈亏比 | 难度 |
|------|---------|------|--------|------|
| 龙头战法 | 游资票 + 动量高 + 板块T1 | -5~7% | 3:1 | 高阶 |
| 波段持股 | 机构票 + 趋势向上 | 跌破20日线 | 2:1 | 进阶 |
| 低吸反弹 | 超跌 + 恐慌>70 | -8% | 2.5:1 | 进阶 |
| 趋势突破 | 横盘后放量突破 | 回落至突破位下方 | 3:1 | 进阶 |
| 高抛低吸 | 震荡区间明确 | 跌破箱体下沿 | 1.5:1 | 新手 |
| 打板战法 | 游资票 + 强情绪 | 次日不及预期即出 | 3:1 | 高阶 |
| 定投策略 | 大盘低估 | 无固定止损 | 长期 | 新手 |

### 策略匹配规则

**输入信号（全部来自已有工具的结构化输出）**：
- `character_type`: 来自 `characterize_stock`
- `trend`, `momentum`, `sentiment`, `volatility`, `flow`: 来自 `diagnose_stock` (0-100)
- `fear_score`: 来自 `get_fear_score` (0-100)
- `sector_tier`（可选）: 来自 `get_sector_strength`，若该股所属板块可匹配到 ETF

**匹配规则（仅使用上述信号，不依赖未输出的字段如"横盘"/"突破信号"）**：

```
游资票 + momentum>70 + (sector_tier in T1,T2 if available)  → 龙头战法、打板战法
游资票 + trend<30 + momentum<30 + fear_score>70             → 低吸反弹
机构票 + trend>60                                           → 波段持股
任意 + trend>60 + momentum>70 + 非游资票                     → 趋势突破
任意 + 35≤trend≤65 + 35≤momentum≤65                        → 高抛低吸
大盘 fear_score>70 + 无 symbol                              → 定投策略
```

**降级规则**：
- `sector_tier` 缺失：龙头战法仅依赖 `character_type + momentum`，不再要求板块 tier
- `characterize_stock` 失败：默认 `普通票`，跳过游资/机构专属策略
- 无匹配规则命中：fallback 推荐"高抛低吸"（机构票）或"定投策略"（其他）

每次推荐 2-3 个最匹配策略。

### 两种调用模式

1. **带 symbol**: `get_trading_strategies(symbol="600519")` → 调用 `characterize_stock` + `diagnose_stock` + `get_fear_score`，针对该股推荐
2. **不带 symbol**: `get_trading_strategies()` → 调用 `_get_market_overview_impl` + `_get_fear_score_impl` 评估大盘环境，推荐通用策略（通常推荐定投/低吸反弹等防守型策略）

### 输出 Schema

```python
class StrategyItem(BaseModel):
    name: str              # 策略名称
    match_reason: str      # 推荐理由
    description: str       # 策略简介（≤100字）
    entry_rule: str        # 入场条件
    exit_rule: str         # 出场条件
    stop_loss: str         # 止损纪律
    risk_reward: str       # 盈亏比
    difficulty: Literal["新手", "进阶", "高阶"]

class TradingStrategies(BaseModel):
    symbol: str | None
    name: str | None
    market: Literal["us", "cn"] | None
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"] | None
    current_situation: str        # 当前行情概述
    recommended: list[StrategyItem]  # 2-3个推荐策略
    risk_reward_lesson: str       # 盈亏比科普（≤150字）
    stale: bool = False
```

### 新增文件

- `processors/strategy_matcher.py` — 匹配逻辑
- `config/strategies.yaml` — 策略知识库（便于维护和扩展）

---

## 6. 新增文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `processors/stock_characterizer.py` | Processor | 个股定性 |
| `processors/trade_signal_generator.py` | Processor | 加减仓信号 |
| `processors/earnings_analyzer.py` | Processor | 财报分析 |
| `processors/strategy_matcher.py` | Processor | 策略匹配 |
| `collectors/earnings_collector.py` | Collector | 财务数据采集 |
| `config/strategies.yaml` | Config | 策略知识库 |
| `schemas.py` | 修改 | 新增 4 个输出 Schema |
| `mcp_server.py` | 修改 | 注册 4 个新工具 |
| `skills/public/market-analyst/SKILL.md` | 修改 | 扩展散户功能说明 |

---

## 7. SKILL.md 扩展

新增触发条件：
- 用户问"这是什么票"、"游资还是机构" → `characterize_stock`
- 用户问"能不能买"、"加仓还是减仓" → `get_trade_signal`
- 用户问"财报怎么样"、"业绩好不好" → `analyze_earnings`
- 用户问"怎么做这个票"、"有什么策略" → `get_trading_strategies`

输出规范（沿用现有）：
- 通俗语言，≤300字
- 附免责声明
- 不直接说"买入/卖出"，用评分/星级/吉凶替代
- 数据过期标记 `stale=true`

---

## 8. 配置扩展

`config/config.yaml` 新增：

```yaml
characterization:
  turnover_high_threshold: 8.0    # 游资换手率阈值%
  turnover_low_threshold: 3.0     # 机构换手率阈值%
  market_cap_small: 200           # 小市值阈值（亿）
  market_cap_large: 500           # 大市值阈值（亿）
  hot_money_threshold: 65         # 游资判定阈值
  institutional_threshold: 65     # 机构判定阈值

trade_signal:
  market_weight: 0.3
  stock_weight: 0.5
  character_weight: 0.2
  hot_money_sentiment_boost: 1.5
  hot_money_trend_reduction: 0.7
  institutional_trend_boost: 1.3
  institutional_sentiment_reduction: 0.8

earnings:
  beat_large_threshold: 10        # 大幅超预期%
  beat_small_threshold: 3         # 小幅超预期%
  reduction_alert_days: 90        # 减持监控天数
  pledge_alert_ratio: 50          # 质押预警比例%

strategies:
  config_file: "config/strategies.yaml"
  max_recommendations: 3
```

---

## 9. 缓存策略

| 数据类型 | max_age_hours | 缓存格式 | 理由 |
|---------|---------------|---------|------|
| 个股定性 (characterization) | 8 | Parquet (OHLCV 部分) | 定性特征日内不变 |
| 加减仓信号 (trade_signal) | 不缓存 | — | 信号时效性强，每次重算 |
| 财报数据 (earnings) | 24 | **JSON** (新增) | 财报数据季度更新，非 OHLCV 结构 |
| 策略推荐 (strategies) | 不缓存 | — | 依赖多个实时信号，每次重算 |

### stale 传播规则

当工具的上游数据源标记为 stale 时，输出也应标记 `stale=True`：
- `get_trade_signal` 依赖 market_overview 和 diagnose_stock，任一 stale → 输出 stale
- `get_trading_strategies` 同理
- `analyze_earnings` 的 stale 取决于 EarningsCollector 缓存是否过期

---

## 10. 测试计划

每个新功能需要单元测试：

| 测试文件 | 覆盖内容 |
|---------|----------|
| `tests/test_stock_characterizer.py` | 游资/机构/合力/普通票判定、边界值 |
| `tests/test_trade_signal_generator.py` | 吉凶映射、定性修正、三层权重 |
| `tests/test_earnings_analyzer.py` | 超预期判定、退化逻辑、风险标记、A股/美股差异 |
| `tests/test_strategy_matcher.py` | 策略匹配规则、无symbol模式、边界 |

使用 mock 数据避免依赖外部 API。
