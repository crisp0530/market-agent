# Market-Analyst DeerFlow Integration Design

**Date:** 2026-03-29
**Status:** Approved
**Approach:** MCP Server Integration

## Context

market-analyst 是一个独立的 Python 市场分析管道，包含 6 个数据采集器、9 个处理器、2 个导出器和 1 个 Streamlit Dashboard。已覆盖 88 只 ETF + 10 个宏观指标的强弱排名、异常检测、周期分析、恐慌评分等功能。

DeerFlow 是基于 LangGraph 的 AI Agent 框架，支持 MCP 集成、技能系统、子代理编排。

目标：将 market-analyst 集成进 DeerFlow，优先服务散户用户的对话式交互需求。

## Decisions

| 维度 | 决定 | 原因 |
|------|------|------|
| 目标用户 | 散户优先 | 对话式诊股/解盘是 agent 价值最大的场景 |
| 交互方式 | Web 聊天为主，IM 为辅 | DeerFlow 已有 Next.js 前端 + IM channels |
| 数据范围 | A股 + 美股个股 + ETF | 全覆盖，个股需新增 collector |
| 建议模式 | 多维度技术评分 | 不直接出买卖建议，合规安全 |
| 模型配置 | 复用 DeerFlow config.yaml | 统一管理，不维护两套配置 |
| 部署方式 | 全部迁入 DeerFlow 调度 | pipeline 用 cron trigger，不维护两套运行机制 |
| 集成方式 | MCP Server | 解耦清晰、不侵入 harness、现有代码改动最小 |

## Architecture

```
用户 (Web/IM)
    ↓
DeerFlow Lead Agent
    ↓
Market Analyst Skill (SKILL.md)
    ↓ (tool calls via MCP)
Market Analyst MCP Server (stdio subprocess)
    ├── get_market_overview      — 全局市场概览
    ├── get_sector_strength      — 板块/ETF 强弱排名
    ├── diagnose_stock           — 个股/ETF 多维度诊断
    ├── get_fear_score           — 恐慌/抄底评分
    ├── get_anomalies            — 异常信号列表
    ├── get_cycle_signals        — 周期突破/抛物线信号
    ├── get_market_commentary    — 极简解盘 (早/午/收评)
    ├── scan_momentum            — 动量扫描 (个股级别)
    ├── search_market_news       — 热点新闻搜索与通俗解读
    └── run_full_report          — 触发全量报告生成
    ↓
market-analyst 数据引擎 (现有代码)
    ├── collectors/  — 数据采集 (US ETF, CN ETF, Global, 个股[新增])
    ├── processors/  — 分析处理 (strength, quant, cycle, anomaly, fear...)
    ├── utils/       — 缓存、搜索
    └── exporters/   — Obsidian MD, JSON
```

## MCP Server Design

### Transport

使用 stdio transport，由 DeerFlow 通过 `extensions_config.json` 管理生命周期。无需独立端口。

### Tools

#### 1. `get_market_overview`
- Input: `{ market?: "us" | "cn" | "all" }`
- Output: 市场温度、涨跌统计、T1/T4 板块列表、恐慌指数、关键宏观指标
- 数据源: StrengthCalculator + FearScoreCalculator + GlobalIndexCollector

#### 2. `get_sector_strength`
- Input: `{ market?: "us" | "cn" | "all", top_n?: number }`
- Output: 板块强弱排名表，含 ROC、分位数、tier、delta 动量
- 数据源: StrengthCalculator

#### 3. `diagnose_stock`
- Input: `{ symbol: string, market?: "us" | "cn" }`
- Output: 多维度评分卡
  - 趋势得分 (SMA 位置、ROC 方向)
  - 动量得分 (5d/20d ROC 百分位)
  - 情绪得分 (RSI、恐慌评分)
  - 波动得分 (波动率、最大回撤)
  - 资金流得分 (CMF、MFI — 如有 TV 数据)
  - 综合评级: 1-5 星（不用大吉/大凶，用星级更中性）
- 数据源: 个股 Collector[新增] + QuantMetrics + FearScoreCalculator + TVIndicatorCollector

#### 4. `get_fear_score`
- Input: `{ symbol?: string, market?: "us" | "cn" }`
- Output: Fear Score (0-100) + Bottom Score (0-100) + 各维度明细
- 数据源: FearScoreCalculator

#### 5. `get_anomalies`
- Input: `{ market?: "us" | "cn" | "all", severity?: "high" | "all" }`
- Output: 异常信号列表，含类型、严重度、相关标的、描述
- 数据源: AnomalyDetector

#### 6. `get_cycle_signals`
- Input: `{ market?: "us" | "cn" | "all" }`
- Output: Stage4 突破 / Stage5 抛物线信号列表
- 数据源: CycleAnalyzer + SignalGenerator

#### 7. `get_market_commentary`
- Input: `{ type: "morning" | "midday" | "closing" }`
- Output: 结构化市场数据摘要 (非文本)，包含当日涨跌统计、热门板块、异常信号、关键指标变化
- 注意: 此 tool 返回结构化数据，由 DeerFlow agent (LLM) 根据 SKILL.md 中的话术模板合成 300 字解盘文本
- 数据源: 综合 overview + anomalies + strength

#### 8. `scan_momentum`
- Input: `{ market?: "us" | "cn", min_return_5d?: number }`
- Output: 多日动量排行（个股级别）
- 数据源: MomentumScanner[新增：扩展到个股]

#### 9. `search_market_news`
- Input: `{ query: string, max_results?: number }`
- Output: 新闻列表 + 通俗摘要
- 数据源: WebSearcher (Tavily/DuckDuckGo)
- 注意: DeerFlow 已有 Tavily community tool。v1.0 此 tool 功能与内置 Tavily 基本一致（截断摘要），主要价值是统一在 market-analyst MCP 内调用。v1.1 计划增加金融领域过滤 (排除广告/软文)、自动关联板块/个股、中文通俗化摘要

#### 10. `run_full_report`
- Input: `{ market?: "us" | "cn" | "all", skip_ai?: boolean }`
- Output: 报告文件路径
- 数据源: 整个 pipeline (main.py run())

### Caching Strategy

- 复用现有 DataCache (parquet + MD5 + 时间过期)
- ETF/指数数据: 8 小时缓存 (交易日内有效)
- 个股数据: 4 小时缓存 (实时性要求更高)
- 全量报告: 每日 1 次

### Error Handling

每个 MCP tool 遵循统一降级策略：
- **数据源不可达** (yfinance/akshare 超时): 返回缓存数据。v1.0 缓存命中时 `stale` 默认 false（因为无法区分"刚缓存"和"过期缓存"），v1.1 增加 stale 检测逻辑
- **缓存也无数据** (首次调用且 API 挂): 返回结构化错误 `{ error: "data_unavailable", message: "..." }`
- **部分数据缺失** (如 TV 指标无数据): 返回可用维度，缺失维度标记为 `null`
- **`run_full_report`**: 同步执行，调用方需预期较长等待时间 (1-5 分钟)。建议通过外部调度器 (cron/APScheduler) 在后台触发，而非在用户对话中实时调用。未来如需异步支持，可加 job store + status query tool

### Tool Output Schemas

每个 tool 定义 Pydantic model 作为返回类型，确保 LLM 解析一致性。示例：

```python
class StockDiagnosis(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    scores: dict[str, float | None]  # 各维度 0-100, None 表示数据不可用
    rating: int  # 1-5 星
    available_dimensions: list[str]  # 实际有数据的维度
    stale: bool = False  # 是否为缓存数据
```

## New Components

### 1. 个股数据 Collector (`stock_collector.py`)
- A 股: akshare `ak.stock_zh_a_hist()` 获取日线
- 美股: yfinance 获取日线
- 统一输出 DataFrame 格式，与现有 ETF collector 一致
- 按需获取（用户输入代码时才拉），不全量扫描

### 2. 个股诊断 Processor (`stock_diagnostor.py`)
- 输入: 单只股票 OHLCV 数据
- 计算: SMA 趋势 + ROC 动量 + RSI 情绪 + 波动率 + 资金流
- 输出: 多维度评分卡 (各维度 0-100 分 + 综合星级 1-5)

### 3. MCP Server 入口 (`mcp_server.py`)
- 基于 FastMCP (Python), stdio transport
- 注册上述 10 个 tools
- 初始化时加载 config + ETF universe
- 懒加载 collectors/processors

### 4. 包结构重组 (Phase 0)
现有 `market-analyst/src/` 需重命名为 `market-analyst/market_analyst/`，使其成为可导入的 Python 包：
```
market-analyst/
├── pyproject.toml          # 新增，定义包元数据和依赖
├── market_analyst/         # 原 src/ 重命名
│   ├── __init__.py
│   ├── mcp_server.py       # 新增，MCP 入口
│   ├── collectors/
│   ├── processors/
│   ├── utils/
│   └── exporters/
├── config/                 # 保持不变 (ETF universe, .env)
├── data/                   # 缓存目录
└── tests/
```

### 5. 依赖隔离
market-analyst 使用独立 venv，不与 DeerFlow backend 的 uv 环境混合：
- `pyproject.toml` 声明所有依赖 (yfinance, akshare, fastmcp 等)
- extensions_config.json 中 command 指向独立 venv: `"command": "./market-analyst/.venv/Scripts/python"`
- `make install` 根目录增加 market-analyst 的安装步骤

## DeerFlow Skill

创建 `skills/public/market-analyst/SKILL.md`：

- 定义 agent 何时调用市场分析工具
- 包含散户交互话术模板（通俗、简短、300 字内）
- 定义诊股流程：用户输入代码 → 调 diagnose_stock → 格式化评分卡
- 定义解盘流程：判断时间段 → 调 get_market_commentary
- 免责声明模板

## DeerFlow Configuration

### extensions_config.json 新增

注意：DeerFlow 的 MCP client (`build_server_params()`) 不传 `cwd`，且启动时工作目录在 `backend/`。
DeerFlow 配置系统的 `$VAR_NAME` 只支持**整值替换**，不支持 `$VAR/suffix` 拼接。
因此需设置一个包含完整路径的环境变量 `MARKET_ANALYST_PYTHON`，直接指向 venv 解释器。

```json
{
  "mcpServers": {
    "market-analyst": {
      "type": "stdio",
      "enabled": true,
      "description": "市场分析引擎：板块强弱、个股诊断、恐慌评分、异常检测",
      "command": "$MARKET_ANALYST_PYTHON",
      "args": ["-m", "market_analyst.mcp_server"],
      "env": {}
    }
  }
}
```

安装时需在 `.env` 中设置完整路径：
```bash
# .env
MARKET_ANALYST_PYTHON=E:/字节跳动框架/deer-flow-main/market-analyst/.venv/Scripts/python
```
```

### 定时报告
DeerFlow 目前没有内置 cron 调度。采用外部调度方案：
- 使用系统 cron / Task Scheduler 调用 Gateway API 触发报告
- 或在 Gateway 层集成 APScheduler 作为轻量调度器
- 每日 08:00 触发 `run_full_report` (盘前)
- 每日 15:30 触发 `get_market_commentary(type="closing")` (收盘)

## Migration Path

0. **Phase 0 — 包结构重组 + POC 验证** (Day 1-2)
   - `src/` 重命名为 `market_analyst/`，创建 `pyproject.toml`
   - 搭建独立 venv，验证现有代码在新包结构下正常运行
   - 实现 1 个最小 MCP tool (`get_fear_score`)，验证 FastMCP ↔ DeerFlow 全链路

1. **Phase 1 — 核心 ETF 能力** (Week 1)
   - 包装现有 collectors/processors 到 MCP tools
   - 注册到 DeerFlow extensions_config.json
   - 实现 5 个核心 tools: overview, strength, fear, anomalies, cycle

2. **Phase 2 — 个股诊断** (Week 2)
   - 新增 stock_collector + stock_diagnostor
   - 实现 diagnose_stock tool
   - 创建 SKILL.md 定义散户交互逻辑

3. **Phase 3 — 解盘 + 动量扫描** (Week 3)
   - 实现 commentary, momentum, news tools
   - 完善 SKILL.md 解盘话术

4. **Phase 4 — 定时调度 + IM** (Week 4)
   - 配置 cron trigger 替代独立 pipeline
   - 接入飞书/Telegram channel
   - Obsidian 导出改为可选

## Testing

- 每个 MCP tool 独立单元测试 (mock 数据)
- 集成测试: DeerFlow agent 端到端调用 MCP tool
- 对话场景测试: 模拟散户典型问题 (诊股、解盘、查板块)

## Out of Scope (Future)

- 研究员/基金经理专属功能
- 完整周期分析 (Stage 1-3，需 180+ 天数据)
- 散户情绪抓取 (股吧爬虫)
- 研报管理
- 事件时间轴
- DeerFlow 前端自定义 dashboard 组件
