# 设计文档：全市场动量扫描 + 持仓操作建议

> 日期：2026-03-11
> 状态：已确认，待实现

## 背景

当前 market-analyst 系统采用"自上而下"逻辑：ETF 板块强弱 → 钻取个股。这导致两个盲区：

1. **板块弱但个股强的漏捕**：AAOI（光通信）所在板块 SMH/SOXX 为 T4，系统跳过了整个 Electronic Technology 板块扫描，漏掉了 AAOI 5日+33%、20日+45% 的爆发。
2. **缺乏个股级操作建议**：系统只输出板块排名和异常信号，没有针对用户持仓/关注标的的操作指导。

## 方案选择

**方案一（已选）：最小侵入，新增独立模块插入现有流水线。**

- 新建 `momentum_scanner.py` 和 `portfolio_advisor.py`，各自独立
- 不修改现有模块逻辑，只在 `main.py` 流水线中追加步骤
- 零风险，坏了不影响原有报告

否决方案：扩展 sector_scanner（职责过重）、统一重构扫描层（过度设计）。

## 模块 B：全市场动量扫描

### 文件

`src/processors/momentum_scanner.py`

### 职责

独立于板块 ETF 梯队，直接扫全市场个股的多日动量异常。

### 数据源

TradingView Screener（复用 `tvscreener` 依赖），查询字段：
- `StockField.PERF_5D`（严格5交易日涨幅%，列名 `"Perf 5d"`）
- `StockField.MONTHLY_PERFORMANCE`（月涨幅%，约21-23交易日，列名 `"Monthly Performance"`）
- `StockField.CHANGE_PERCENT`（当日涨跌，列名 `"Change %"`）
- `StockField.RELATIVE_VOLUME`、`StockField.RELATIVE_STRENGTH_INDEX_14`、`StockField.CHAIKIN_MONEY_FLOW_20`
- `StockField.MARKET_CAPITALIZATION`、`StockField.SECTOR`、`StockField.INDUSTRY`

注意：月涨幅不严格等于20交易日，但作为动量筛选足够用，无需 yfinance 自算。

### 扫描规则

```
美股: Market Cap > $3B, Avg Volume > 300K
A股: Market Cap > 30亿, Avg Volume > 100K

信号触发（满足任一）:
  - 短期爆发: 5交易日涨幅 > 15%（PERF_5D）
  - 中期趋势: 月涨幅 > 30%（MONTHLY_PERFORMANCE，约21-23交易日）
```

### 输出格式

```python
{
    "momentum_surge": [
        {
            "symbol": "AAOI",
            "name": "Applied Optoelectronics",
            "market": "us",
            "price": 110.55,
            "change_pct": 7.9,
            "perf_5d": 33.2,
            "perf_20d": 45.8,
            "trigger": "5d",       # 5d / 20d / both
            "rel_volume": 3.2,
            "rsi": 72,
            "cmf": 0.25,
            "market_cap_b": 7.2,
            "sector": "Electronic Technology",
            "industry": "Fiber Optics"
        }
    ]
}
```

### 流水线位置

Step 5.5（板块扫描）之后，新增 **Step 5.6: 全市场动量扫描**。

### 报告展示

Obsidian MD 新增章节：

```markdown
## 全市场动量异动

### 美股动量飙升（5日 >15% 或 20日 >30%）
| 标的 | 代码 | 价格 | 当日% | 5日% | 20日% | 触发 | RSI | 相对量 | 市值 | 行业 |

### A股动量飙升
| 标的 | 代码 | 价格 | 当日% | 5日% | 20日% | 触发 | RSI | 相对量 | 市值(亿) | 行业 |
```

JSON 导出包含 `momentum_surge` 字段。

### config.yaml 新增

```yaml
momentum_scan:
  enabled: true
  us:
    min_market_cap: 3e9
    min_avg_volume: 300000
  cn:
    min_market_cap: 3e9      # 约30亿人民币
    min_avg_volume: 100000
  thresholds:
    perf_5d: 15              # 5日涨幅 > 15%
    perf_20d: 30             # 20日涨幅 > 30%
  max_results: 20            # 每个市场最多返回数量
```

---

## 模块 A：持仓操作建议

### 文件

- `src/processors/portfolio_advisor.py`
- `config/portfolio.yaml`（新建）

### portfolio.yaml 格式

```yaml
holdings:
  - symbol: PLTR
    name: Palantir
    avg_cost: 140
    target_buy: 140
    target_sell: null
    position_pct: 10
    notes: "等跌回$140附近再补"

  - symbol: MSFT
    name: Microsoft
    avg_cost: 395
    target_buy: null
    target_sell: null
    notes: "拿着就行，不需要追加"

watchlist:
  - symbol: NVDA
    name: NVIDIA
    target_buy: 170
    target_sell: null
    logic: "200日EMA支撑位，GTC催化剂"
    position_plan: "第一批40%"

  - symbol: TSLA
    name: Tesla
    target_buy: 385
    target_sell: null
    logic: "SpaceX IPO催化剂，FSD叙事"
    position_plan: "385以下第一批40%，350-360第二批"

  - symbol: AMD
    name: AMD
    target_buy: 185
    target_sell: null
    logic: "100日EMA区间，AI芯片受益"
    position_plan: "小仓介入"

settings:
  ema_periods: [20, 50, 100, 200]
  proximity_threshold: 4         # 距目标价 <4% 触发提醒
```

### 数据采集

用 yfinance 拉取 holdings + watchlist 中所有标的的：
- 最新价、当日涨跌
- EMA 20/50/100/200（从日线计算）
- RSI 14、CMF 20
- 距建仓均价 / 目标价的百分比

### 规则引擎

对每个标的生成结构化判断：

```python
{
    "symbol": "NVDA",
    "current_price": 176.46,
    "target_buy": 170,
    "distance_to_target_pct": -3.7,
    "ema_200": 169.5,
    "distance_to_ema200_pct": -4.1,
    "rsi": 45,
    "cmf": 0.12,
    "daily_change_pct": -2.1,
    "status": "approaching",
    "signal_strength": "medium",
    "notes_from_config": "200日EMA支撑位，GTC催化剂"
}
```

status 规则：
- `in_zone`：当前价 <= target_buy
- `approaching`：距 target_buy < proximity_threshold%
- `away`：距 target_buy >= proximity_threshold%
- `holding`：已持仓且无 target_buy

### AI 生成建议

将结构化数据 + portfolio.yaml 中的 notes/logic 打包成 prompt，交给配置中的 AI provider（复用 `config.yaml` 的 `analysis.provider` 和 `analysis.model` 配置）。

**Prompt 模板要点**：
- 输入：所有标的的结构化判断（JSON）+ 用户填写的 notes/logic/position_plan
- 输出要求：对每个标的生成状态图标 + 一句话状态 + 操作逻辑（2-3句）+ 具体操作指令（价位+仓位），最后输出操作优先级排序
- 风格：简洁、直接、可操作，参考截图中 Nico 的风格

**Fallback 策略**：复用现有 `analysis.fallback_to_data_only` 配置。AI 调用失败时，只输出规则引擎的结构化表格（status/signal_strength/distance），不生成自然语言建议。

**成本**：每次运行增加约 1 次 AI 调用（~2K input tokens），与现有 AI 分析步骤成本相当。

### 流水线位置

Step 5（AI 分析）之后，**Step 5.7: 持仓操作建议**。仅当 `config/portfolio.yaml` 存在时执行。

### 报告展示

```markdown
## 持仓操作建议

### 暂时不动的持仓
| 标的 | 原因 |
| PLTR | 建仓均价 $140+，现价 $154-157，不在折扣区；等跌回 $140 附近再补 |
| MSFT | 均价 $395 建仓，现在 ~$400，拿着就行，不需要追加 |

### NVDA — 差一步，今天盯着
当前状态：$176.46，目标位 $170（200日EMA支撑位），差不到4%
逻辑：...
操作：$170以下可以第一批动手。$176不追，等它来。

### TSLA — 进入可操作区间
...

### 操作优先级
MU（最紧迫）→ NVDA $170（等信号）→ TSLA $385（等位置）
```

---

## 改动清单

| 文件 | 改动 |
|------|------|
| `src/processors/momentum_scanner.py` | 新建 |
| `src/processors/portfolio_advisor.py` | 新建 |
| `config/portfolio.yaml` | 新建（示例模板） |
| `config/config.yaml` | 新增 `momentum_scan` 配置段 |
| `main.py` | 新增 Step 5.6 和 Step 5.7 + portfolio.yaml 文件存在性检查 |
| `src/exporters/obsidian_exporter.py` | 新增动量异动和操作建议章节（追加 keyword args，与 stock_picks 平级） |
| `src/exporters/json_exporter.py` | 新增 `momentum_surge` 和 `portfolio_advice` 顶层字段 |
| `web/src/` | 后续新增对应页面（不在本次范围） |

## 不做的事

- 不改现有 sector_scanner / anomaly_detector 逻辑
- 不上 Redis / 分布式缓存
- Web Dashboard 页面留到后续迭代
- 不做自动交易 / 下单
