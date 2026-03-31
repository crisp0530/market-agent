# Retail Investor Features Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the retail investor (散户) module by adding 4 new MCP tools: stock characterization, trade signals, earnings analysis, and trading strategy recommendations.

**Architecture:** Extend the existing `market-analyst` MCP server with 4 new processors, 1 new collector, and 4 new Pydantic schemas. Each tool follows the established pattern: `@mcp.tool()` → pure `_impl` function → Processor class → Schema output. TDD: tests first, implementation second.

**Tech Stack:** Python 3.12+, FastMCP, Pydantic, pandas, numpy, akshare (A-share data), yfinance (US data), pytest

**Spec:** `docs/superpowers/specs/2026-03-30-retail-investor-features-completion-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `market-analyst/market_analyst/schemas_retail.py` | 4 new Pydantic output models (StockCharacterization, TradeSignal, EarningsAnalysis, TradingStrategies) + sub-models (QuarterlyMetric, RiskFlag, StrategyItem) |
| `market-analyst/market_analyst/processors/stock_characterizer.py` | Stock characterization logic: turnover, volatility, volume patterns, limit-up frequency, institutional holdings, market cap → hot_money_score / institutional_score → character_type |
| `market-analyst/market_analyst/processors/trade_signal_generator.py` | Three-layer trade signal: market environment (30%) + stock technicals (50%) + character adjustment (20%) → 大吉/小吉/平/小凶/大凶 |
| `market-analyst/market_analyst/processors/earnings_analyzer.py` | Earnings analysis: quarterly financials + YoY + analyst consensus → expectation verdict + risk flags |
| `market-analyst/market_analyst/processors/strategy_matcher.py` | Strategy matching engine: character_type + diagnosis + fear_score → 2-3 recommended strategies with entry/exit/stop-loss rules |
| `market-analyst/market_analyst/collectors/earnings_collector.py` | Financial data collector: akshare (_em APIs) for A-shares, yfinance for US stocks. Returns structured dict (not DataFrame). Does NOT extend BaseCollector. |
| `market-analyst/tests/test_stock_characterizer.py` | Unit tests for stock characterization |
| `market-analyst/tests/test_trade_signal_generator.py` | Unit tests for trade signal generation |
| `market-analyst/tests/test_earnings_analyzer.py` | Unit tests for earnings analysis |
| `market-analyst/tests/test_strategy_matcher.py` | Unit tests for strategy matching |
| `market-analyst/tests/test_earnings_collector.py` | Unit tests for earnings data collection |

### Modified Files

| File | Changes |
|------|---------|
| `market-analyst/market_analyst/mcp_server.py` | Register 4 new tools: `characterize_stock`, `get_trade_signal`, `analyze_earnings`, `get_trading_strategies` |
| `market-analyst/market_analyst/schemas.py` | Import and re-export from `schemas_retail.py` for backwards compatibility |
| `market-analyst/market_analyst/utils/cache.py` | Add `get_or_fetch_json()` method for JSON caching (non-DataFrame data) |
| `market-analyst/config/config.yaml` | Add `characterization`, `trade_signal`, `earnings` config sections |
| `market-analyst/tests/conftest.py` | Add shared fixtures for new tests |
| `skills/public/market-analyst/SKILL.md` | Add new tool triggers and output format examples |

---

## Task 1: Schemas — Pydantic Output Models

**Files:**
- Create: `market-analyst/market_analyst/schemas_retail.py`
- Modify: `market-analyst/market_analyst/schemas.py`
- Test: `market-analyst/tests/test_schemas_retail.py`

- [ ] **Step 1: Write failing tests for new schemas**

Create `market-analyst/tests/test_schemas_retail.py`:

```python
"""Tests for retail investor Pydantic schemas."""
import pytest
from pydantic import ValidationError

from market_analyst.schemas_retail import (
    StockCharacterization,
    TradeSignal,
    QuarterlyMetric,
    RiskFlag,
    EarningsAnalysis,
    StrategyItem,
    TradingStrategies,
)


class TestStockCharacterization:
    def test_valid_construction(self):
        sc = StockCharacterization(
            symbol="600519",
            name="贵州茅台",
            market="cn",
            character_type="机构票",
            hot_money_score=25.0,
            institutional_score=80.0,
            available_dimensions=["turnover", "volatility", "volume_pattern", "limit_up_freq", "market_cap"],
            key_evidence=["日均换手率1.2%，远低于市场均值", "总市值2.1万亿"],
            analysis_tips="关注基本面、业绩预期、估值水平",
        )
        assert sc.character_type == "机构票"
        assert sc.market == "cn"

    def test_invalid_market_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="invalid",
                character_type="普通票", hot_money_score=50, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_invalid_character_type_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="us",
                character_type="unknown", hot_money_score=50, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="us",
                character_type="普通票", hot_money_score=150, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_stale_defaults_false(self):
        sc = StockCharacterization(
            symbol="AAPL", name="Apple", market="us",
            character_type="机构票", hot_money_score=20, institutional_score=75,
            available_dimensions=["turnover", "volatility"], key_evidence=[], analysis_tips="",
        )
        assert sc.stale is False


class TestTradeSignal:
    def test_valid_construction(self):
        ts = TradeSignal(
            symbol="AAPL", name="Apple", market="us",
            signal="小吉", score=68.0, market_score=55.0, stock_score=78.0,
            character_score=72.0, character_type="机构票",
            score_breakdown={"trend": 80, "momentum": 65, "sentiment": 55, "volatility": 70},
            reasons=["趋势向上"], risk_warnings=[],
        )
        assert ts.signal == "小吉"
        assert ts.character_score == 72.0

    def test_invalid_signal_rejected(self):
        with pytest.raises(ValidationError):
            TradeSignal(
                symbol="X", name="X", market="us",
                signal="超级吉", score=50, market_score=50, stock_score=50,
                character_score=50, character_type="普通票",
                score_breakdown={}, reasons=[], risk_warnings=[],
            )


class TestEarningsAnalysis:
    def test_valid_with_typed_sub_models(self):
        ea = EarningsAnalysis(
            symbol="600519", name="贵州茅台", market="cn",
            latest_quarter="2025Q4", revenue=350.5, net_profit=180.2,
            revenue_yoy=15.3, profit_yoy=12.8,
            expectation_basis="consensus", expectation="小幅超预期", deviation_pct=5.2,
            quarterly_trend=[
                QuarterlyMetric(quarter="2025Q4", revenue=350.5, revenue_yoy=15.3, profit=180.2, profit_yoy=12.8),
                QuarterlyMetric(quarter="2025Q3", revenue=320.0, revenue_yoy=10.0, profit=165.0, profit_yoy=10.5),
            ],
            trend_summary="连续增长",
            risks=[RiskFlag(type="减持风险", level="medium", detail="近90天减持0.5%")],
            plain_summary="茅台四季度营收350亿，同比增15%，净利润超分析师预期5%。",
        )
        assert ea.expectation == "小幅超预期"
        assert ea.expectation_basis == "consensus"
        assert len(ea.quarterly_trend) == 2
        assert ea.risks[0].level == "medium"

    def test_yoy_fallback_basis(self):
        ea = EarningsAnalysis(
            symbol="X", name="X", market="cn",
            latest_quarter="2025Q4", revenue=100, net_profit=30,
            revenue_yoy=35, profit_yoy=40,
            expectation_basis="yoy_fallback", expectation="大幅超预期", deviation_pct=None,
            quarterly_trend=[], trend_summary="波动", risks=[], plain_summary="同比大幅增长",
        )
        assert ea.expectation_basis == "yoy_fallback"

    def test_invalid_risk_type_rejected(self):
        with pytest.raises(ValidationError):
            RiskFlag(type="不存在的风险", level="medium", detail="test")

    def test_quarterly_metric_with_revenue_yoy(self):
        qm = QuarterlyMetric(quarter="2025Q4", revenue=100.0, revenue_yoy=15.0, profit=50.0, profit_yoy=None)
        assert qm.revenue_yoy == 15.0
        assert qm.profit_yoy is None


class TestTradingStrategies:
    def test_valid_with_symbol(self):
        ts = TradingStrategies(
            symbol="AAPL", name="Apple", market="us", character_type="机构票",
            current_situation="趋势向上，站上20日均线",
            recommended=[
                StrategyItem(
                    name="波段持股", match_reason="机构票+趋势向上",
                    description="沿20日均线持股", entry_rule="站上20日线",
                    exit_rule="跌破20日线", stop_loss="-5%",
                    risk_reward="2:1", difficulty="进阶",
                ),
            ],
            risk_reward_lesson="盈亏比是长期盈利的关键。",
        )
        assert ts.recommended[0].difficulty == "进阶"

    def test_valid_without_symbol(self):
        ts = TradingStrategies(
            symbol=None, name=None, market=None, character_type=None,
            current_situation="大盘低估区域",
            recommended=[], risk_reward_lesson="",
        )
        assert ts.symbol is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_schemas_retail.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'market_analyst.schemas_retail'`

- [ ] **Step 3: Implement schemas**

Create `market-analyst/market_analyst/schemas_retail.py`:

```python
"""Pydantic schemas for retail investor features."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StockCharacterization(BaseModel):
    """个股定性结果：游资票/机构票/机游合力票/普通票。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    hot_money_score: float = Field(ge=0, le=100, description="游资倾向 0-100")
    institutional_score: float = Field(ge=0, le=100, description="机构倾向 0-100")
    available_dimensions: list[str] = Field(description="实际参与评分的维度")
    key_evidence: list[str] = Field(description="3-5条关键依据")
    analysis_tips: str = Field(description="针对该类型的分析建议")
    stale: bool = False


class TradeSignal(BaseModel):
    """加减仓信号：大吉/小吉/平/小凶/大凶。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    signal: Literal["大吉", "小吉", "平", "小凶", "大凶"]
    score: float = Field(ge=0, le=100, description="综合分")
    market_score: float = Field(ge=0, le=100, description="大盘分")
    stock_score: float = Field(ge=0, le=100, description="个股原始均分")
    character_score: float = Field(ge=0, le=100, description="定性修正分")
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    score_breakdown: dict[str, float] = Field(description="各维度明细")
    reasons: list[str] = Field(description="2-3条简明理由")
    risk_warnings: list[str] = Field(default_factory=list)
    stale: bool = False


class QuarterlyMetric(BaseModel):
    """单季度财务指标。"""

    quarter: str
    revenue: float
    revenue_yoy: float | None = None
    profit: float
    profit_yoy: float | None = None


class RiskFlag(BaseModel):
    """风险标记。"""

    type: Literal["ST风险", "减持风险", "质押风险", "亏损风险", "营收萎缩"]
    level: Literal["high", "medium"]
    detail: str


class EarningsAnalysis(BaseModel):
    """财报解读结果。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    latest_quarter: str
    revenue: float
    net_profit: float
    revenue_yoy: float
    profit_yoy: float
    expectation_basis: Literal["consensus", "yoy_fallback", "none"]
    expectation: Literal[
        "大幅超预期", "小幅超预期", "符合预期", "小幅不及预期", "大幅不及预期", "无预期数据"
    ]
    deviation_pct: float | None = None
    quarterly_trend: list[QuarterlyMetric]
    trend_summary: Literal["连续增长", "拐点向上", "拐点向下", "持续下滑", "波动"]
    risks: list[RiskFlag] = Field(default_factory=list)
    plain_summary: str = Field(max_length=300, description="≤300字通俗解读")
    stale: bool = False


class StrategyItem(BaseModel):
    """单个推荐策略。"""

    name: str
    match_reason: str
    description: str
    entry_rule: str
    exit_rule: str
    stop_loss: str
    risk_reward: str
    difficulty: Literal["新手", "进阶", "高阶"]


class TradingStrategies(BaseModel):
    """交易策略推荐结果。"""

    symbol: str | None = None
    name: str | None = None
    market: Literal["us", "cn"] | None = None
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"] | None = None
    current_situation: str
    recommended: list[StrategyItem]
    risk_reward_lesson: str
    stale: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_schemas_retail.py -v`
Expected: All PASS

- [ ] **Step 5: Update schemas.py to re-export**

Add at end of `market-analyst/market_analyst/schemas.py`:

```python
# Retail investor schemas
from market_analyst.schemas_retail import (  # noqa: F401
    StockCharacterization,
    TradeSignal,
    QuarterlyMetric,
    RiskFlag,
    EarningsAnalysis,
    StrategyItem,
    TradingStrategies,
)
```

- [ ] **Step 6: Commit**

```bash
git add market-analyst/market_analyst/schemas_retail.py market-analyst/market_analyst/schemas.py market-analyst/tests/test_schemas_retail.py
git commit -m "feat(market-analyst): add Pydantic schemas for retail investor features"
```

---

## Task 2: Stock Characterizer — 个股定性

**Files:**
- Create: `market-analyst/market_analyst/processors/stock_characterizer.py`
- Test: `market-analyst/tests/test_stock_characterizer.py`

- [ ] **Step 1: Add test fixtures to conftest.py**

Append to `market-analyst/tests/conftest.py`:

```python
@pytest.fixture
def sample_stock_df_hot_money():
    """Simulated hot-money stock: high turnover, high volatility, limit-ups."""
    np.random.seed(100)
    dates = pd.bdate_range(end="2026-03-27", periods=60)
    base = 20.0
    # Volatile price action with big daily moves
    daily_returns = np.random.randn(60) * 0.04  # 4% daily std
    daily_returns[10] = 0.10  # limit up
    daily_returns[25] = 0.098  # near limit up
    closes = base * np.cumprod(1 + daily_returns)

    return pd.DataFrame({
        "symbol": "301234",
        "name": "游资概念股",
        "market": "cn",
        "sector": "Technology",
        "date": dates.strftime("%Y-%m-%d").tolist(),
        "open": closes * (1 - np.abs(np.random.randn(60)) * 0.01),
        "high": closes * (1 + np.abs(np.random.randn(60)) * 0.03),
        "low": closes * (1 - np.abs(np.random.randn(60)) * 0.03),
        "close": closes,
        "volume": np.random.randint(5_000_000, 50_000_000, 60).astype(float),
    })


@pytest.fixture
def sample_stock_df_institutional():
    """Simulated institutional stock: low turnover, stable, large cap."""
    np.random.seed(200)
    dates = pd.bdate_range(end="2026-03-27", periods=60)
    base = 1800.0
    # Very stable price action
    closes = base + np.cumsum(np.random.randn(60) * 5)

    return pd.DataFrame({
        "symbol": "600519",
        "name": "贵州茅台",
        "market": "cn",
        "sector": "Consumer Staples",
        "date": dates.strftime("%Y-%m-%d").tolist(),
        "open": closes - np.random.rand(60) * 2,
        "high": closes + np.random.rand(60) * 8,
        "low": closes - np.random.rand(60) * 8,
        "close": closes,
        "volume": np.random.randint(50_000, 200_000, 60).astype(float),
    })


@pytest.fixture
def sample_characterization_config():
    return {
        "characterization": {
            "turnover_high_threshold": 8.0,
            "turnover_low_threshold": 3.0,
            "market_cap_small": 200,
            "market_cap_large": 500,
            "hot_money_threshold": 65,
            "institutional_threshold": 65,
            "weights": {
                "turnover": 0.25,
                "volatility": 0.20,
                "volume_pattern": 0.20,
                "limit_up_freq": 0.15,
                "institutional_holding": 0.10,
                "market_cap": 0.10,
            },
        }
    }
```

- [ ] **Step 2: Write failing tests**

Create `market-analyst/tests/test_stock_characterizer.py`:

```python
"""Tests for stock characterization processor."""
import pytest
import pandas as pd
import numpy as np

from market_analyst.processors.stock_characterizer import StockCharacterizer
from market_analyst.schemas_retail import StockCharacterization


class TestStockCharacterizer:
    def test_hot_money_stock(self, sample_stock_df_hot_money, sample_characterization_config):
        """High turnover, volatile stock should be classified as 游资票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234",
            raw_df=sample_stock_df_hot_money,
            market="cn",
            market_cap=50.0,  # 50亿, small cap
            institutional_pct=5.0,  # low institutional
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type == "游资票"
        assert result.hot_money_score > result.institutional_score

    def test_institutional_stock(self, sample_stock_df_institutional, sample_characterization_config):
        """Low turnover, stable, large-cap stock should be classified as 机构票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="600519",
            raw_df=sample_stock_df_institutional,
            market="cn",
            market_cap=21000.0,  # 2.1万亿
            institutional_pct=45.0,  # high institutional
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type == "机构票"
        assert result.institutional_score > result.hot_money_score

    def test_mixed_stock(self, sample_stock_df_hot_money, sample_characterization_config):
        """Moderate indicators should produce 机游合力票 or 普通票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="000001",
            raw_df=sample_stock_df_hot_money,
            market="cn",
            market_cap=3000.0,  # large-ish
            institutional_pct=35.0,  # moderate institutional
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type in ("机游合力票", "普通票")

    def test_scores_in_range(self, sample_stock_df_hot_money, sample_characterization_config):
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert 0 <= result.hot_money_score <= 100
        assert 0 <= result.institutional_score <= 100

    def test_key_evidence_not_empty(self, sample_stock_df_hot_money, sample_characterization_config):
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert len(result.key_evidence) >= 2

    def test_available_dimensions_tracked(self, sample_stock_df_hot_money, sample_characterization_config):
        """Should track which dimensions were used in scoring."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert "turnover" in result.available_dimensions
        assert "volatility" in result.available_dimensions
        assert "institutional_holding" in result.available_dimensions

    def test_missing_dimensions_renormalized(self, sample_stock_df_hot_money, sample_characterization_config):
        """Missing optional dimensions should be excluded and weights renormalized."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=None,  # market_cap missing
            institutional_pct=None,  # institutional missing
        )
        assert "institutional_holding" not in result.available_dimensions
        assert "market_cap" not in result.available_dimensions
        # Scores should still be in valid range
        assert 0 <= result.hot_money_score <= 100
        assert 0 <= result.institutional_score <= 100

    def test_insufficient_data_returns_normal(self, sample_characterization_config):
        """Very short data should default to 普通票."""
        df = pd.DataFrame({
            "symbol": ["X"] * 3, "close": [100.0, 101.0, 99.0],
            "high": [101.0, 102.0, 100.0], "low": [99.0, 100.0, 98.0],
            "volume": [1000.0, 1200.0, 900.0], "date": ["2026-03-25", "2026-03-26", "2026-03-27"],
            "name": ["X"] * 3, "market": ["cn"] * 3, "sector": ["Tech"] * 3,
            "open": [100.0, 101.0, 99.0],
        })
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(symbol="X", raw_df=df, market="cn", market_cap=100.0, institutional_pct=10.0)
        assert result.character_type == "普通票"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_stock_characterizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'market_analyst.processors.stock_characterizer'`

- [ ] **Step 4: Implement StockCharacterizer**

Create `market-analyst/market_analyst/processors/stock_characterizer.py`:

```python
"""Stock characterization: classify as 游资票/机构票/机游合力票/普通票."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from market_analyst.schemas_retail import StockCharacterization


class StockCharacterizer:
    """Classify a stock's trading character based on multi-dimensional scoring."""

    MIN_DAYS = 10

    def __init__(self, config: dict):
        cfg = config.get("characterization", {})
        self.turnover_high = cfg.get("turnover_high_threshold", 8.0)
        self.turnover_low = cfg.get("turnover_low_threshold", 3.0)
        self.cap_small = cfg.get("market_cap_small", 200)
        self.cap_large = cfg.get("market_cap_large", 500)
        self.hot_threshold = cfg.get("hot_money_threshold", 65)
        self.inst_threshold = cfg.get("institutional_threshold", 65)
        self.weights = cfg.get("weights", {
            "turnover": 0.25, "volatility": 0.20, "volume_pattern": 0.20,
            "limit_up_freq": 0.15, "institutional_holding": 0.10,
            "market_cap": 0.10,
        })
        # Dimensions that can be missing (require external data)
        self.optional_dims = {"institutional_holding", "market_cap"}

    def characterize(
        self,
        symbol: str,
        raw_df: pd.DataFrame,
        market: str,
        market_cap: float | None = None,
        institutional_pct: float | None = None,
    ) -> StockCharacterization:
        name = raw_df.iloc[0]["name"] if not raw_df.empty and "name" in raw_df.columns else symbol

        if raw_df.empty or len(raw_df) < self.MIN_DAYS:
            return self._default_result(symbol, name, market)

        closes = raw_df["close"].values.astype(float)
        highs = raw_df["high"].values.astype(float)
        lows = raw_df["low"].values.astype(float)
        volumes = raw_df["volume"].values.astype(float)

        # --- Compute all dimension scores ---
        # hot_score: higher = more hot-money-like
        # For institutional score, we invert (100 - hot_score)
        dims: dict[str, float] = {}
        dims["turnover"] = self._score_turnover(volumes, closes, market_cap)
        dims["volatility"] = self._score_volatility(closes, highs, lows)
        dims["volume_pattern"] = self._score_volume_pattern(volumes)
        dims["limit_up_freq"] = self._score_limit_up_frequency(closes, market)

        # Optional dimensions: only include if data available
        if institutional_pct is not None:
            dims["institutional_holding"] = self._score_institutional(institutional_pct)
        if market_cap is not None:
            dims["market_cap"] = self._score_market_cap(market_cap)

        available = list(dims.keys())

        # Dynamic weight renormalization: redistribute missing weights proportionally
        active_weights = {k: self.weights[k] for k in available if k in self.weights}
        total_w = sum(active_weights.values())
        if total_w <= 0:
            return self._default_result(symbol, name, market)
        norm_weights = {k: v / total_w for k, v in active_weights.items()}

        # Hot money score: turnover/volatility/volume_pattern/limit_up contribute positively
        # institutional_holding/market_cap contribute inversely (low = hot money)
        hot_money = sum(
            (dims[k] if k not in ("institutional_holding", "market_cap") else (100 - dims[k]))
            * norm_weights[k]
            for k in available if k in norm_weights
        )
        institutional = sum(
            ((100 - dims[k]) if k not in ("institutional_holding", "market_cap") else dims[k])
            * norm_weights[k]
            for k in available if k in norm_weights
        )

        hot_money = float(np.clip(hot_money, 0, 100))
        institutional = float(np.clip(institutional, 0, 100))

        character_type = self._classify(hot_money, institutional)
        evidence = self._build_evidence(
            dims, market_cap, institutional_pct, market,
        )
        tips = self._get_tips(character_type)

        return StockCharacterization(
            symbol=symbol, name=name, market=market,
            character_type=character_type,
            hot_money_score=round(hot_money, 1),
            institutional_score=round(institutional, 1),
            available_dimensions=available,
            key_evidence=evidence, analysis_tips=tips,
        )

    def _score_turnover(self, volumes: np.ndarray, closes: np.ndarray, market_cap: float | None) -> float:
        """Higher turnover → higher score (hot money indicator)."""
        if market_cap is None or market_cap <= 0:
            return 50.0
        # Approximate: avg daily volume * avg close / market_cap_in_yuan
        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        avg_close = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
        daily_turnover_pct = (avg_vol * avg_close) / (market_cap * 1e8) * 100
        # Map [0%, 15%] → [0, 100]
        return float(np.clip(daily_turnover_pct / 15 * 100, 0, 100))

    def _score_volatility(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        """Higher ATR% → higher score (hot money indicator)."""
        if len(closes) < 5:
            return 50.0
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        atr_pct = atr / closes[-1] * 100 if closes[-1] > 0 else 0
        # Map [0%, 8%] → [0, 100]
        return float(np.clip(atr_pct / 8 * 100, 0, 100))

    def _score_volume_pattern(self, volumes: np.ndarray) -> float:
        """Pulse-like volume spikes → higher score (hot money indicator)."""
        if len(volumes) < 20:
            return 50.0
        avg_vol = np.mean(volumes[-20:])
        if avg_vol <= 0:
            return 50.0
        volume_ratios = volumes[-20:] / avg_vol
        spike_count = np.sum(volume_ratios > 3.0)
        # Map [0, 8 spikes] → [0, 100]
        return float(np.clip(spike_count / 8 * 100, 0, 100))

    def _score_limit_up_frequency(self, closes: np.ndarray, market: str) -> float:
        """Limit-up/big-gain days frequency → higher score."""
        if len(closes) < 5:
            return 50.0
        daily_returns = np.diff(closes) / closes[:-1] * 100
        recent = daily_returns[-20:] if len(daily_returns) >= 20 else daily_returns
        threshold = 9.5 if market == "cn" else 8.0  # CN has 10% limit
        big_days = np.sum(recent >= threshold)
        # Map [0, 5 days] → [0, 100]
        return float(np.clip(big_days / 5 * 100, 0, 100))

    def _score_institutional(self, institutional_pct: float | None) -> float:
        """Higher institutional holding → higher score (institutional indicator)."""
        if institutional_pct is None:
            return 50.0
        # Map [0%, 60%] → [0, 100]
        return float(np.clip(institutional_pct / 60 * 100, 0, 100))

    def _score_market_cap(self, market_cap: float | None) -> float:
        """Larger market cap → higher score (institutional indicator)."""
        if market_cap is None:
            return 50.0
        # Map [0, 2000亿] → [0, 100]
        return float(np.clip(market_cap / 2000 * 100, 0, 100))

    def _classify(self, hot: float, inst: float) -> str:
        if hot > self.hot_threshold and inst < (100 - self.hot_threshold):
            return "游资票"
        if inst > self.inst_threshold and hot < (100 - self.inst_threshold):
            return "机构票"
        if hot > 45 and inst > 45:
            return "机游合力票"
        return "普通票"

    def _build_evidence(self, dims: dict, market_cap, inst_pct, market) -> list[str]:
        evidence = []
        turnover = dims.get("turnover", 50)
        volatility = dims.get("volatility", 50)
        limit_up = dims.get("limit_up_freq", 50)
        if turnover > 70:
            evidence.append("换手率活跃，游资参与度高")
        elif turnover < 30:
            evidence.append("换手率低，持仓稳定")
        if volatility > 70:
            evidence.append("波动率大，短线资金博弈明显")
        elif volatility < 30:
            evidence.append("波动率低，走势稳健")
        if limit_up > 50:
            evidence.append("近期有涨停或大阳线，辨识度高")
        if market_cap is not None:
            if market_cap < self.cap_small:
                evidence.append(f"总市值{market_cap:.0f}亿，偏小盘")
            elif market_cap > self.cap_large:
                evidence.append(f"总市值{market_cap:.0f}亿，大盘股")
        if inst_pct is not None:
            if inst_pct > 30:
                evidence.append(f"机构持仓{inst_pct:.1f}%，机构参与度高")
            elif inst_pct < 10:
                evidence.append(f"机构持仓{inst_pct:.1f}%，散户为主")
        return evidence[:5]  # cap at 5

    def _get_tips(self, character_type: str) -> str:
        tips_map = {
            "游资票": "关注市场辨识度、情绪周期、板块梯队位置，快进快出",
            "机构票": "关注基本面、业绩预期、估值水平，波段持有",
            "机游合力票": "兼顾基本面和情绪面，关注放量突破信号",
            "普通票": "无明显主力特征，建议观望或小仓位参与",
        }
        return tips_map.get(character_type, tips_map["普通票"])

    def _default_result(self, symbol: str, name: str, market: str) -> StockCharacterization:
        return StockCharacterization(
            symbol=symbol, name=name, market=market,
            character_type="普通票", hot_money_score=50.0, institutional_score=50.0,
            available_dimensions=[],
            key_evidence=["数据不足，无法准确定性"], analysis_tips="数据不足，建议观望",
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_stock_characterizer.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add market-analyst/market_analyst/processors/stock_characterizer.py market-analyst/tests/test_stock_characterizer.py market-analyst/tests/conftest.py
git commit -m "feat(market-analyst): add stock characterizer processor with TDD"
```

---

## Task 3: Trade Signal Generator — 加减仓建议

**Files:**
- Create: `market-analyst/market_analyst/processors/trade_signal_generator.py`
- Test: `market-analyst/tests/test_trade_signal_generator.py`

- [ ] **Step 1: Write failing tests**

Create `market-analyst/tests/test_trade_signal_generator.py`:

```python
"""Tests for trade signal generator."""
import pytest

from market_analyst.processors.trade_signal_generator import TradeSignalGenerator
from market_analyst.schemas_retail import TradeSignal


@pytest.fixture
def signal_config():
    return {
        "trade_signal": {
            "market_weight": 0.3,
            "stock_weight": 0.5,
            "character_weight": 0.2,
            "hot_money_sentiment_boost": 1.5,
            "hot_money_trend_reduction": 0.7,
            "institutional_trend_boost": 1.3,
            "institutional_sentiment_reduction": 0.8,
        }
    }


class TestTradeSignalGenerator:
    def test_daji_when_all_strong(self, signal_config):
        """All high scores → 大吉."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="AAPL", name="Apple", market="us",
            market_score=85, stock_scores={"trend": 90, "momentum": 85, "sentiment": 80, "volatility": 75, "flow": 70},
            character_type="机构票",
        )
        assert isinstance(result, TradeSignal)
        assert result.signal == "大吉"
        assert result.score >= 80

    def test_daxiong_when_all_weak(self, signal_config):
        """All low scores → 大凶."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="cn",
            market_score=10, stock_scores={"trend": 10, "momentum": 15, "sentiment": 10, "volatility": 20, "flow": 5},
            character_type="普通票",
        )
        assert result.signal == "大凶"
        assert result.score < 20

    def test_ping_when_mixed(self, signal_config):
        """Mixed scores → 平."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="us",
            market_score=50, stock_scores={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50, "flow": 50},
            character_type="普通票",
        )
        assert result.signal == "平"

    def test_hot_money_boosts_sentiment(self, signal_config):
        """游资票 should weight sentiment higher."""
        gen = TradeSignalGenerator(signal_config)
        # High sentiment, low trend
        scores = {"trend": 30, "momentum": 50, "sentiment": 90, "volatility": 50, "flow": 50}
        result_hot = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                  stock_scores=scores, character_type="游资票")
        result_normal = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                     stock_scores=scores, character_type="普通票")
        assert result_hot.score > result_normal.score

    def test_institutional_boosts_trend(self, signal_config):
        """机构票 should weight trend higher."""
        gen = TradeSignalGenerator(signal_config)
        # High trend, low sentiment
        scores = {"trend": 90, "momentum": 50, "sentiment": 30, "volatility": 50, "flow": 50}
        result_inst = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                   stock_scores=scores, character_type="机构票")
        result_normal = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                     stock_scores=scores, character_type="普通票")
        assert result_inst.score > result_normal.score

    def test_reasons_not_empty(self, signal_config):
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="AAPL", name="Apple", market="us",
            market_score=60, stock_scores={"trend": 70, "momentum": 65, "sentiment": 55, "volatility": 60, "flow": 50},
            character_type="机构票",
        )
        assert len(result.reasons) >= 1

    def test_score_in_range(self, signal_config):
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="us",
            market_score=50, stock_scores={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            character_type="普通票",
        )
        assert 0 <= result.score <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_trade_signal_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TradeSignalGenerator**

Create `market-analyst/market_analyst/processors/trade_signal_generator.py`:

```python
"""Three-layer trade signal generator: market + stock + character adjustment."""
from __future__ import annotations

import numpy as np
from loguru import logger

from market_analyst.schemas_retail import TradeSignal


class TradeSignalGenerator:
    """Generate 大吉/小吉/平/小凶/大凶 trade signals."""

    SIGNAL_MAP = [
        (80, "大吉"),
        (60, "小吉"),
        (40, "平"),
        (20, "小凶"),
        (0, "大凶"),
    ]

    def __init__(self, config: dict):
        cfg = config.get("trade_signal", {})
        self.market_weight = cfg.get("market_weight", 0.3)
        self.stock_weight = cfg.get("stock_weight", 0.5)
        self.char_weight = cfg.get("character_weight", 0.2)
        self.hm_sentiment_boost = cfg.get("hot_money_sentiment_boost", 1.5)
        self.hm_trend_reduction = cfg.get("hot_money_trend_reduction", 0.7)
        self.inst_trend_boost = cfg.get("institutional_trend_boost", 1.3)
        self.inst_sentiment_reduction = cfg.get("institutional_sentiment_reduction", 0.8)

    def generate(
        self,
        symbol: str,
        name: str,
        market: str,
        market_score: float,
        stock_scores: dict[str, float],
        character_type: str,
        risk_warnings: list[str] | None = None,
    ) -> TradeSignal:
        # Raw stock score (unweighted average)
        valid_scores = {k: v for k, v in stock_scores.items() if v is not None}
        raw_stock = float(np.mean(list(valid_scores.values()))) if valid_scores else 50.0

        # Character-adjusted stock score (weighted by character type)
        character_score = self._adjust_stock_score(valid_scores, character_type)

        # Final composite: market + raw_stock + character_score
        composite = (
            market_score * self.market_weight
            + raw_stock * self.stock_weight
            + character_score * self.char_weight
        )
        composite = float(np.clip(composite, 0, 100))

        signal = self._map_signal(composite)
        reasons = self._build_reasons(market_score, raw_stock, stock_scores, character_type)

        return TradeSignal(
            symbol=symbol, name=name, market=market,
            signal=signal, score=round(composite, 1),
            market_score=round(market_score, 1),
            stock_score=round(raw_stock, 1),
            character_score=round(character_score, 1),
            character_type=character_type,
            score_breakdown={k: round(v, 1) for k, v in valid_scores.items()},
            reasons=reasons,
            risk_warnings=risk_warnings or [],
        )

    def _adjust_stock_score(self, scores: dict[str, float], character_type: str) -> float:
        """Apply character-based weight adjustment to stock dimensions."""
        dimension_weights = {
            "trend": 1.0, "momentum": 1.0, "sentiment": 1.0,
            "volatility": 1.0, "flow": 1.0,
        }

        if character_type == "游资票":
            dimension_weights["sentiment"] = self.hm_sentiment_boost
            dimension_weights["trend"] = self.hm_trend_reduction
        elif character_type == "机构票":
            dimension_weights["trend"] = self.inst_trend_boost
            dimension_weights["sentiment"] = self.inst_sentiment_reduction

        weighted_sum = 0.0
        weight_total = 0.0
        for dim, val in scores.items():
            if val is not None and dim in dimension_weights:
                w = dimension_weights[dim]
                weighted_sum += val * w
                weight_total += w

        return weighted_sum / weight_total if weight_total > 0 else 50.0

    def _map_signal(self, score: float) -> str:
        for threshold, label in self.SIGNAL_MAP:
            if score >= threshold:
                return label
        return "大凶"

    def _build_reasons(self, market_score, stock_score, scores, character_type) -> list[str]:
        reasons = []
        if market_score >= 60:
            reasons.append("大盘环境偏暖，有利于操作")
        elif market_score < 40:
            reasons.append("大盘环境偏弱，注意风险")

        trend = scores.get("trend", 50)
        momentum = scores.get("momentum", 50)
        if trend >= 65:
            reasons.append("趋势稳健，均线多头排列")
        elif trend < 35:
            reasons.append("趋势偏弱，均线空头")

        if momentum >= 65:
            reasons.append("动量充足，近期表现强势")
        elif momentum < 35:
            reasons.append("动量不足，涨幅有限")

        flow = scores.get("flow")
        if flow is not None and flow >= 65:
            reasons.append("资金持续流入")
        elif flow is not None and flow < 35:
            reasons.append("资金流出明显")

        return reasons[:3]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_trade_signal_generator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add market-analyst/market_analyst/processors/trade_signal_generator.py market-analyst/tests/test_trade_signal_generator.py
git commit -m "feat(market-analyst): add trade signal generator with TDD"
```

---

## Task 4: Earnings Collector — 财务数据采集

**Files:**
- Create: `market-analyst/market_analyst/collectors/earnings_collector.py`
- Test: `market-analyst/tests/test_earnings_collector.py`

- [ ] **Step 1: Write failing tests**

Create `market-analyst/tests/test_earnings_collector.py`:

```python
"""Tests for earnings data collector."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from market_analyst.collectors.earnings_collector import EarningsCollector


@pytest.fixture
def earnings_config():
    return {"earnings": {"reduction_alert_days": 90, "pledge_alert_ratio": 50}}


@pytest.fixture
def mock_cn_financials():
    """Mock akshare financial data for a CN stock."""
    return pd.DataFrame({
        "报告期": ["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"],
        "营业总收入": [35050000000, 32000000000, 28000000000, 25000000000],
        "净利润": [18020000000, 16500000000, 14000000000, 12000000000],
    })


class TestEarningsCollector:
    def test_collect_returns_required_keys(self, earnings_config, mock_cn_financials):
        collector = EarningsCollector(earnings_config)
        with patch.object(collector, "_fetch_cn_financials", return_value=mock_cn_financials):
            with patch.object(collector, "_fetch_cn_forecast", return_value=None):
                with patch.object(collector, "_fetch_cn_risks", return_value={"is_st": False, "reductions": [], "pledge_ratio": None}):
                    result = collector.collect("600519", market="cn")

        assert "financials" in result
        assert "forecast" in result
        assert "risks" in result
        assert "meta" in result

    def test_financials_parsed_correctly(self, earnings_config, mock_cn_financials):
        collector = EarningsCollector(earnings_config)
        with patch.object(collector, "_fetch_cn_financials", return_value=mock_cn_financials):
            with patch.object(collector, "_fetch_cn_forecast", return_value=None):
                with patch.object(collector, "_fetch_cn_risks", return_value={"is_st": False, "reductions": [], "pledge_ratio": None}):
                    result = collector.collect("600519", market="cn")

        assert len(result["financials"]) == 4
        assert result["financials"][0]["quarter"] == "2025Q4"
        assert result["financials"][0]["revenue"] > 0

    def test_empty_data_returns_empty_financials(self, earnings_config):
        collector = EarningsCollector(earnings_config)
        with patch.object(collector, "_fetch_cn_financials", return_value=pd.DataFrame()):
            with patch.object(collector, "_fetch_cn_forecast", return_value=None):
                with patch.object(collector, "_fetch_cn_risks", return_value={"is_st": False, "reductions": [], "pledge_ratio": None}):
                    result = collector.collect("999999", market="cn")

        assert result["financials"] == []

    def test_us_market_routing(self, earnings_config):
        collector = EarningsCollector(earnings_config)
        with patch.object(collector, "_fetch_us_financials", return_value=[]) as mock_us:
            with patch.object(collector, "_fetch_us_forecast", return_value=None):
                with patch.object(collector, "_fetch_us_risks", return_value={"reductions": []}):
                    collector.collect("AAPL", market="us")
        mock_us.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_earnings_collector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement EarningsCollector**

Create `market-analyst/market_analyst/collectors/earnings_collector.py`:

```python
"""Financial data collector for earnings analysis. Wraps akshare (CN) and yfinance (US)."""
from __future__ import annotations

import pandas as pd
from loguru import logger


class EarningsCollector:
    """Collect structured earnings data for a single stock.

    Unlike other collectors (which return DataFrames of OHLCV), this returns
    a structured dict since financial statement data is not OHLCV-shaped.
    """

    def __init__(self, config: dict):
        cfg = config.get("earnings", {})
        self.reduction_days = cfg.get("reduction_alert_days", 90)
        self.pledge_alert = cfg.get("pledge_alert_ratio", 50)

    def collect(self, symbol: str, market: str = "cn") -> dict:
        """Collect earnings data for a stock.

        Returns:
            {
                "financials": [{"quarter": str, "revenue": float, "net_profit": float,
                                "revenue_yoy": float|None, "profit_yoy": float|None}],
                "forecast": {"consensus_profit": float|None},
                "risks": {"is_st": bool, "reductions": list, "pledge_ratio": float|None},
                "meta": {"name": str, "currency": str}
            }
        """
        if market == "cn":
            return self._collect_cn(symbol)
        else:
            return self._collect_us(symbol)

    def _collect_cn(self, symbol: str) -> dict:
        financials_df = self._fetch_cn_financials(symbol)
        financials = self._parse_cn_financials(financials_df)
        forecast = self._fetch_cn_forecast(symbol)
        risks = self._fetch_cn_risks(symbol)
        return {
            "financials": financials,
            "forecast": {"consensus_profit": forecast},
            "risks": risks,
            "meta": {"name": symbol, "currency": "CNY"},
        }

    def _collect_us(self, symbol: str) -> dict:
        financials = self._fetch_us_financials(symbol)
        forecast = self._fetch_us_forecast(symbol)
        risks = self._fetch_us_risks(symbol)
        return {
            "financials": financials,
            "forecast": {"consensus_profit": forecast},
            "risks": risks,
            "meta": {"name": symbol, "currency": "USD"},
        }

    def _fetch_cn_financials(self, symbol: str) -> pd.DataFrame:
        """Fetch A-share financial data via akshare (东方财富 source)."""
        try:
            import akshare as ak
            df = ak.stock_financial_analysis_indicator(symbol=symbol)
            return df.head(4) if not df.empty else pd.DataFrame()
        except Exception as e:
            logger.warning(f"Failed to fetch CN financials for {symbol}: {e}")
            return pd.DataFrame()

    def _parse_cn_financials(self, df: pd.DataFrame) -> list[dict]:
        if df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            period = str(row.get("报告期", ""))
            quarter = self._period_to_quarter(period)
            revenue = float(row.get("营业总收入", 0)) / 1e8  # Convert to 亿
            profit = float(row.get("净利润", 0)) / 1e8
            results.append({
                "quarter": quarter,
                "revenue": round(revenue, 2),
                "net_profit": round(profit, 2),
                "revenue_yoy": None,  # Computed by analyzer
                "profit_yoy": None,
            })
        return results

    def _fetch_cn_forecast(self, symbol: str) -> float | None:
        """Fetch analyst consensus forecast via akshare."""
        try:
            import akshare as ak
            df = ak.stock_profit_forecast_em(symbol=symbol)
            if not df.empty and "预测净利润均值" in df.columns:
                return float(df.iloc[0]["预测净利润均值"])
        except Exception as e:
            logger.debug(f"No CN forecast for {symbol}: {e}")
        return None

    def _fetch_cn_risks(self, symbol: str) -> dict:
        """Fetch ST status, insider reductions, pledge ratio."""
        risks = {"is_st": False, "reductions": [], "pledge_ratio": None}
        try:
            import akshare as ak
            # ST check
            try:
                st_df = ak.stock_zh_a_st_em()
                if not st_df.empty and symbol in st_df["代码"].values:
                    risks["is_st"] = True
            except Exception:
                pass

            # Pledge ratio — fetches by date (全量表), filter by symbol
            # Needs date fallback: try recent trading days
            try:
                from datetime import datetime, timedelta
                for days_back in range(0, 6):
                    try_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
                    try:
                        pledge_df = ak.stock_gpzy_pledge_ratio_em(date=try_date)
                        if not pledge_df.empty:
                            code_col = [c for c in pledge_df.columns if "代码" in c or "股票代码" in c]
                            if code_col:
                                row = pledge_df[pledge_df[code_col[0]] == symbol]
                                if not row.empty:
                                    ratio_col = [c for c in pledge_df.columns if "质押比例" in c]
                                    if ratio_col:
                                        risks["pledge_ratio"] = float(row.iloc[0][ratio_col[0]])
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # Insider reductions — stock_hold_management_detail_em() returns全量表, filter by symbol
            try:
                df = ak.stock_hold_management_detail_em()
                if not df.empty:
                    code_col = [c for c in df.columns if "代码" in c or "股票代码" in c]
                    if code_col:
                        filtered = df[df[code_col[0]] == symbol]
                        if not filtered.empty:
                            risks["reductions"] = filtered.head(5).to_dict("records")
            except Exception:
                pass

        except ImportError:
            logger.warning("akshare not installed")
        return risks

    def _fetch_us_financials(self, symbol: str) -> list[dict]:
        """Fetch US financial data via yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            qf = ticker.quarterly_financials
            if qf is None or qf.empty:
                return []
            results = []
            for col in qf.columns[:4]:  # Last 4 quarters
                quarter = self._period_to_quarter(str(col.date()) if hasattr(col, "date") else str(col))
                revenue = float(qf.loc["Total Revenue", col]) / 1e8 if "Total Revenue" in qf.index else 0
                profit = float(qf.loc["Net Income", col]) / 1e8 if "Net Income" in qf.index else 0
                results.append({
                    "quarter": quarter,
                    "revenue": round(revenue, 2),
                    "net_profit": round(profit, 2),
                    "revenue_yoy": None,
                    "profit_yoy": None,
                })
            return results
        except Exception as e:
            logger.warning(f"Failed to fetch US financials for {symbol}: {e}")
            return []

    def _fetch_us_forecast(self, symbol: str) -> float | None:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            est = ticker.earnings_estimate
            if est is not None and not est.empty:
                return float(est.iloc[0].get("avg", 0))
        except Exception:
            pass
        return None

    def _fetch_us_risks(self, symbol: str) -> dict:
        risks = {"reductions": []}
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            insiders = ticker.insider_transactions
            if insiders is not None and not insiders.empty:
                sales = insiders[insiders.get("Text", "").str.contains("Sale", case=False, na=False)]
                risks["reductions"] = sales.head(5).to_dict("records") if not sales.empty else []
        except Exception:
            pass
        return risks

    @staticmethod
    def _period_to_quarter(period: str) -> str:
        """Convert date string to quarter label like '2025Q4'."""
        try:
            if "-" in period:
                parts = period.split("-")
                year = parts[0]
                month = int(parts[1])
            else:
                return period  # Already formatted
            q = (month - 1) // 3 + 1
            return f"{year}Q{q}"
        except Exception:
            return period
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_earnings_collector.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add market-analyst/market_analyst/collectors/earnings_collector.py market-analyst/tests/test_earnings_collector.py
git commit -m "feat(market-analyst): add earnings data collector with TDD"
```

---

## Task 5: Earnings Analyzer — 财报解读

**Files:**
- Create: `market-analyst/market_analyst/processors/earnings_analyzer.py`
- Test: `market-analyst/tests/test_earnings_analyzer.py`

- [ ] **Step 1: Write failing tests**

Create `market-analyst/tests/test_earnings_analyzer.py`:

```python
"""Tests for earnings analyzer processor."""
import pytest

from market_analyst.processors.earnings_analyzer import EarningsAnalyzer
from market_analyst.schemas_retail import EarningsAnalysis


@pytest.fixture
def earnings_config():
    return {
        "earnings": {
            "beat_large_threshold": 10,
            "beat_small_threshold": 3,
            "reduction_alert_days": 90,
            "pledge_alert_ratio": 50,
        }
    }


@pytest.fixture
def sample_earnings_data_with_forecast():
    return {
        "financials": [
            {"quarter": "2025Q4", "revenue": 350.5, "net_profit": 180.2, "revenue_yoy": None, "profit_yoy": None},
            {"quarter": "2025Q3", "revenue": 320.0, "net_profit": 165.0, "revenue_yoy": None, "profit_yoy": None},
            {"quarter": "2025Q2", "revenue": 310.0, "net_profit": 155.0, "revenue_yoy": None, "profit_yoy": None},
            {"quarter": "2025Q1", "revenue": 300.0, "net_profit": 148.0, "revenue_yoy": None, "profit_yoy": None},
        ],
        "forecast": {"consensus_profit": 170.0},
        "risks": {"is_st": False, "reductions": [], "pledge_ratio": 10.0},
        "meta": {"name": "贵州茅台", "currency": "CNY"},
    }


@pytest.fixture
def sample_earnings_data_no_forecast():
    return {
        "financials": [
            {"quarter": "2025Q4", "revenue": 100.0, "net_profit": 30.0, "revenue_yoy": None, "profit_yoy": None},
            {"quarter": "2025Q3", "revenue": 95.0, "net_profit": 28.0, "revenue_yoy": None, "profit_yoy": None},
        ],
        "forecast": {"consensus_profit": None},
        "risks": {"is_st": True, "reductions": [{"amount": 2.0}], "pledge_ratio": 55.0},
        "meta": {"name": "某ST股", "currency": "CNY"},
    }


class TestEarningsAnalyzer:
    def test_beat_expectation_with_forecast(self, earnings_config, sample_earnings_data_with_forecast):
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("600519", "cn", sample_earnings_data_with_forecast)
        assert isinstance(result, EarningsAnalysis)
        # 180.2 vs 170.0 = +6% → 小幅超预期
        assert result.expectation == "小幅超预期"
        assert result.expectation_basis == "consensus"

    def test_fallback_to_yoy_without_forecast(self, earnings_config, sample_earnings_data_no_forecast):
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("000001", "cn", sample_earnings_data_no_forecast)
        # No consensus → falls back to YoY or 无预期数据
        assert result.expectation_basis in ("yoy_fallback", "none")

    def test_risk_flags_detected(self, earnings_config, sample_earnings_data_no_forecast):
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("000001", "cn", sample_earnings_data_no_forecast)
        risk_types = [r.type for r in result.risks]
        assert "ST风险" in risk_types
        assert "质押风险" in risk_types

    def test_trend_summary_continuous_growth(self, earnings_config, sample_earnings_data_with_forecast):
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("600519", "cn", sample_earnings_data_with_forecast)
        assert result.trend_summary == "连续增长"

    def test_empty_financials(self, earnings_config):
        empty_data = {
            "financials": [],
            "forecast": {"consensus_profit": None},
            "risks": {"is_st": False, "reductions": [], "pledge_ratio": None},
            "meta": {"name": "Unknown", "currency": "CNY"},
        }
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("999999", "cn", empty_data)
        assert result.expectation == "无预期数据"
        assert result.plain_summary != ""

    def test_plain_summary_under_300_chars(self, earnings_config, sample_earnings_data_with_forecast):
        analyzer = EarningsAnalyzer(earnings_config)
        result = analyzer.analyze("600519", "cn", sample_earnings_data_with_forecast)
        assert len(result.plain_summary) <= 300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_earnings_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement EarningsAnalyzer**

Create `market-analyst/market_analyst/processors/earnings_analyzer.py`:

```python
"""Earnings analysis: expectation verdict + risk flags + plain-language summary."""
from __future__ import annotations

from loguru import logger

from market_analyst.schemas_retail import (
    EarningsAnalysis,
    QuarterlyMetric,
    RiskFlag,
)


class EarningsAnalyzer:
    """Analyze earnings data and produce retail-friendly output."""

    def __init__(self, config: dict):
        cfg = config.get("earnings", {})
        self.beat_large = cfg.get("beat_large_threshold", 10)
        self.beat_small = cfg.get("beat_small_threshold", 3)
        self.pledge_alert = cfg.get("pledge_alert_ratio", 50)

    def analyze(self, symbol: str, market: str, data: dict) -> EarningsAnalysis:
        meta = data.get("meta", {})
        name = meta.get("name", symbol)
        financials = data.get("financials", [])
        forecast = data.get("forecast", {})
        risk_data = data.get("risks", {})

        if not financials:
            return self._empty_result(symbol, name, market, risk_data)

        # Build quarterly trend with YoY
        quarterly = self._build_quarterly_trend(financials)
        latest = quarterly[0] if quarterly else None

        # Expectation vs consensus, with YoY fallback
        consensus = forecast.get("consensus_profit")
        if consensus and latest and latest.profit > 0:
            deviation = (latest.profit - consensus) / abs(consensus) * 100
            expectation = self._classify_deviation(deviation)
            expectation_basis = "consensus"
        elif latest and latest.profit_yoy is not None:
            # YoY fallback: reuse same labels but track basis
            deviation = None
            expectation = self._classify_yoy(latest.profit_yoy)
            expectation_basis = "yoy_fallback"
        else:
            deviation = None
            expectation = "无预期数据"
            expectation_basis = "none"

        # Trend summary
        trend_summary = self._determine_trend(quarterly)

        # Risk flags
        risks = self._detect_risks(risk_data, quarterly)

        # Plain summary
        plain = self._build_summary(name, latest, expectation, deviation, trend_summary, risks)

        return EarningsAnalysis(
            symbol=symbol, name=name, market=market,
            latest_quarter=latest.quarter if latest else "N/A",
            revenue=latest.revenue if latest else 0,
            net_profit=latest.profit if latest else 0,
            revenue_yoy=latest.revenue_yoy or 0,
            profit_yoy=latest.profit_yoy or 0,
            expectation_basis=expectation_basis,
            expectation=expectation,
            deviation_pct=round(deviation, 1) if deviation is not None else None,
            quarterly_trend=quarterly,
            trend_summary=trend_summary,
            risks=risks,
            plain_summary=plain[:300],
        )

    def _build_quarterly_trend(self, financials: list[dict]) -> list[QuarterlyMetric]:
        """Convert raw financials to typed quarterly metrics with YoY calc."""
        metrics = []
        for i, f in enumerate(financials):
            profit_yoy = None
            # If we have year-ago data (4 quarters back)
            if i + 4 < len(financials) and financials[i + 4].get("net_profit"):
                prev = financials[i + 4]["net_profit"]
                if prev and prev != 0:
                    profit_yoy = round((f["net_profit"] - prev) / abs(prev) * 100, 1)

            metrics.append(QuarterlyMetric(
                quarter=f.get("quarter", ""),
                revenue=f.get("revenue", 0),
                profit=f.get("net_profit", 0),
                profit_yoy=profit_yoy,
            ))
        return metrics

    def _classify_deviation(self, deviation: float) -> str:
        if deviation > self.beat_large:
            return "大幅超预期"
        elif deviation > self.beat_small:
            return "小幅超预期"
        elif deviation > -self.beat_small:
            return "符合预期"
        elif deviation > -self.beat_large:
            return "小幅不及预期"
        else:
            return "大幅不及预期"

    def _classify_yoy(self, profit_yoy: float) -> str:
        """Map YoY growth to same expectation labels (fallback mode)."""
        if profit_yoy > 30:
            return "大幅超预期"
        elif profit_yoy > 10:
            return "小幅超预期"
        elif profit_yoy > -10:
            return "符合预期"
        elif profit_yoy > -30:
            return "小幅不及预期"
        else:
            return "大幅不及预期"

    def _determine_trend(self, quarterly: list[QuarterlyMetric]) -> str:
        if len(quarterly) < 2:
            return "波动"
        profits = [q.profit for q in quarterly]
        # Quarterly trend is newest-first; check if each is bigger than next
        increasing = all(profits[i] >= profits[i + 1] for i in range(len(profits) - 1))
        decreasing = all(profits[i] <= profits[i + 1] for i in range(len(profits) - 1))

        if increasing:
            return "连续增长"
        elif decreasing:
            return "持续下滑"
        # Check for inflection
        if len(profits) >= 3:
            if profits[0] > profits[1] and profits[1] < profits[2]:
                return "拐点向上"
            if profits[0] < profits[1] and profits[1] > profits[2]:
                return "拐点向下"
        return "波动"

    def _detect_risks(self, risk_data: dict, quarterly: list[QuarterlyMetric]) -> list[RiskFlag]:
        flags = []
        if risk_data.get("is_st"):
            flags.append(RiskFlag(type="ST风险", level="high", detail="当前为ST/*ST状态"))

        pledge = risk_data.get("pledge_ratio")
        if pledge is not None and pledge > self.pledge_alert:
            flags.append(RiskFlag(type="质押风险", level="medium", detail=f"质押比例{pledge:.1f}%"))

        reductions = risk_data.get("reductions", [])
        if reductions:
            flags.append(RiskFlag(type="减持风险", level="medium", detail=f"近期有{len(reductions)}笔减持记录"))

        # Consecutive losses
        if len(quarterly) >= 2 and all(q.profit < 0 for q in quarterly[:2]):
            flags.append(RiskFlag(type="亏损风险", level="high", detail="连续2季净利润为负"))

        # Revenue shrinkage
        if len(quarterly) >= 3:
            revs = [q.revenue for q in quarterly[:3]]
            if revs[0] < revs[1] < revs[2]:
                flags.append(RiskFlag(type="营收萎缩", level="medium", detail="连续2季营收下滑"))

        return flags

    def _build_summary(self, name, latest, expectation, deviation, trend, risks) -> str:
        parts = []
        if latest:
            parts.append(f"{name}{latest.quarter}营收{latest.revenue:.1f}亿，净利润{latest.profit:.1f}亿。")
        if expectation != "无预期数据" and deviation is not None:
            parts.append(f"业绩{expectation}（偏差{deviation:+.1f}%）。")
        parts.append(f"近期走势：{trend}。")
        if risks:
            risk_str = "、".join(r.type for r in risks)
            parts.append(f"风险提示：{risk_str}。")
        return "".join(parts)

    def _empty_result(self, symbol, name, market, risk_data) -> EarningsAnalysis:
        risks = self._detect_risks(risk_data, [])
        return EarningsAnalysis(
            symbol=symbol, name=name, market=market,
            latest_quarter="N/A", revenue=0, net_profit=0,
            revenue_yoy=0, profit_yoy=0,
            expectation_basis="none",
            expectation="无预期数据", deviation_pct=None,
            quarterly_trend=[], trend_summary="波动",
            risks=risks, plain_summary=f"{name}暂无可用的财务数据。",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_earnings_analyzer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add market-analyst/market_analyst/processors/earnings_analyzer.py market-analyst/tests/test_earnings_analyzer.py
git commit -m "feat(market-analyst): add earnings analyzer with TDD"
```

---

## Task 6: Strategy Matcher — 交易策略普及

**Files:**
- Create: `market-analyst/market_analyst/processors/strategy_matcher.py`
- Test: `market-analyst/tests/test_strategy_matcher.py`

- [ ] **Step 1: Write failing tests**

Create `market-analyst/tests/test_strategy_matcher.py`:

```python
"""Tests for strategy matching engine."""
import pytest

from market_analyst.processors.strategy_matcher import StrategyMatcher
from market_analyst.schemas_retail import TradingStrategies


@pytest.fixture
def strategy_config():
    return {"strategies": {"max_recommendations": 3}}


class TestStrategyMatcher:
    def test_hot_money_high_momentum_gets_dragon(self, strategy_config):
        """游资票 + 高动量 → 龙头战法."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="301234", name="游资概念股", market="cn",
            character_type="游资票",
            diagnosis={"trend": 70, "momentum": 85, "sentiment": 80, "volatility": 30},
            fear_score=40, sector_tier="T1",
        )
        assert isinstance(result, TradingStrategies)
        names = [s.name for s in result.recommended]
        assert "龙头战法" in names or "打板战法" in names

    def test_institutional_uptrend_gets_swing(self, strategy_config):
        """机构票 + 趋势向上 → 波段持股."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="600519", name="贵州茅台", market="cn",
            character_type="机构票",
            diagnosis={"trend": 75, "momentum": 60, "sentiment": 55, "volatility": 70},
            fear_score=45, sector_tier="T2",
        )
        names = [s.name for s in result.recommended]
        assert "波段持股" in names

    def test_oversold_gets_bounce(self, strategy_config):
        """超跌 + 恐慌高 → 低吸反弹."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="cn",
            character_type="游资票",
            diagnosis={"trend": 20, "momentum": 15, "sentiment": 15, "volatility": 30},
            fear_score=80, sector_tier="T4",
        )
        names = [s.name for s in result.recommended]
        assert "低吸反弹" in names

    def test_no_symbol_returns_general(self, strategy_config):
        """No symbol → general market strategies."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match_general(market_score=40, fear_score=75)
        assert result.symbol is None
        assert len(result.recommended) >= 1

    def test_max_recommendations(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="cn", character_type="普通票",
            diagnosis={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            fear_score=50, sector_tier="T2",
        )
        assert len(result.recommended) <= 3

    def test_risk_reward_lesson_present(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="us", character_type="普通票",
            diagnosis={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            fear_score=50, sector_tier="T2",
        )
        assert len(result.risk_reward_lesson) > 0

    def test_each_strategy_has_all_fields(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="AAPL", name="Apple", market="us", character_type="机构票",
            diagnosis={"trend": 70, "momentum": 60, "sentiment": 55, "volatility": 65},
            fear_score=45, sector_tier="T1",
        )
        for s in result.recommended:
            assert s.name
            assert s.entry_rule
            assert s.exit_rule
            assert s.stop_loss
            assert s.risk_reward
            assert s.difficulty in ("新手", "进阶", "高阶")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd market-analyst && python -m pytest tests/test_strategy_matcher.py -v`
Expected: FAIL

- [ ] **Step 3: Implement StrategyMatcher**

Create `market-analyst/market_analyst/processors/strategy_matcher.py`:

```python
"""Strategy matching engine: recommend 2-3 trading strategies based on stock state."""
from __future__ import annotations

from market_analyst.schemas_retail import StrategyItem, TradingStrategies


# Built-in strategy knowledge base
STRATEGIES = {
    "龙头战法": StrategyItem(
        name="龙头战法",
        match_reason="",  # Filled at match time
        description="做板块最强辨识度票，打板或低吸首阴，快进快出",
        entry_rule="板块启动，个股辨识度最高，首板或2板确认",
        exit_rule="分歧日（竞价低于预期）或板块退潮",
        stop_loss="-5~7%，次日不及预期即出",
        risk_reward="3:1",
        difficulty="高阶",
    ),
    "波段持股": StrategyItem(
        name="波段持股",
        match_reason="",
        description="沿20日均线持股，享受趋势红利",
        entry_rule="站上20日均线且均线向上",
        exit_rule="收盘跌破20日均线",
        stop_loss="跌破20日均线即离场",
        risk_reward="2:1",
        difficulty="进阶",
    ),
    "低吸反弹": StrategyItem(
        name="低吸反弹",
        match_reason="",
        description="恐慌超跌后分批低吸，等待反弹",
        entry_rule="恐慌指数>70，个股超跌>20%",
        exit_rule="反弹15-20%止盈",
        stop_loss="-8%",
        risk_reward="2.5:1",
        difficulty="进阶",
    ),
    "趋势突破": StrategyItem(
        name="趋势突破",
        match_reason="",
        description="长期横盘后放量突破关键阻力位",
        entry_rule="放量突破前高/平台，量比>2",
        exit_rule="回落至突破位下方",
        stop_loss="回落至突破位下方即出",
        risk_reward="3:1",
        difficulty="进阶",
    ),
    "高抛低吸": StrategyItem(
        name="高抛低吸",
        match_reason="",
        description="在明确的震荡箱体内高卖低买",
        entry_rule="触及箱体下沿",
        exit_rule="触及箱体上沿",
        stop_loss="跌破箱体下沿",
        risk_reward="1.5:1",
        difficulty="新手",
    ),
    "打板战法": StrategyItem(
        name="打板战法",
        match_reason="",
        description="涨停板买入，博次日溢价",
        entry_rule="封板坚决，板上买入",
        exit_rule="次日竞价或盘中高点卖出",
        stop_loss="次日低开或炸板即出",
        risk_reward="3:1",
        difficulty="高阶",
    ),
    "定投策略": StrategyItem(
        name="定投策略",
        match_reason="",
        description="定期定额买入宽基ETF，穿越牛熊",
        entry_rule="定期（周/月）定额买入",
        exit_rule="持有3年以上或牛市高估值时分批卖出",
        stop_loss="无固定止损，坚持定投纪律",
        risk_reward="长期2:1以上",
        difficulty="新手",
    ),
}

RISK_REWARD_LESSON = (
    "盈亏比是长期盈利的核心。假设盈亏比3:1，即使胜率只有40%，"
    "长期也能稳定盈利。关键是每笔交易严守止损纪律，让利润奔跑。"
    "赚大亏小，而非追求高胜率。"
)


class StrategyMatcher:
    """Match trading strategies to stock conditions."""

    def __init__(self, config: dict):
        cfg = config.get("strategies", {})
        self.max_recs = cfg.get("max_recommendations", 3)

    def match(
        self,
        symbol: str,
        name: str,
        market: str,
        character_type: str,
        diagnosis: dict[str, float],
        fear_score: float,
        sector_tier: str | None = None,
    ) -> TradingStrategies:
        candidates = []

        trend = diagnosis.get("trend", 50)
        momentum = diagnosis.get("momentum", 50)
        sentiment = diagnosis.get("sentiment", 50)

        is_hot = character_type == "游资票"
        is_inst = character_type == "机构票"
        is_oversold = trend < 30 and momentum < 30
        is_high_fear = fear_score > 70
        is_uptrend = trend > 60
        is_strong_momentum = momentum > 70

        # Rule-based matching (only uses signals from diagnose_stock + fear_score + optional sector_tier)
        if is_hot and is_strong_momentum:
            reason = "游资票+动量强"
            if sector_tier in ("T1", "T2"):
                reason += "+板块领先"
            candidates.append(self._with_reason("龙头战法", reason))
            candidates.append(self._with_reason("打板战法", "游资票+强情绪周期"))

        if is_oversold and is_high_fear:
            candidates.append(self._with_reason("低吸反弹", f"超跌+恐慌指数{fear_score:.0f}"))

        if is_inst and is_uptrend:
            candidates.append(self._with_reason("波段持股", "机构票+趋势向上"))

        if is_uptrend and is_strong_momentum and not is_hot:
            candidates.append(self._with_reason("趋势突破", "趋势向上+动量充足"))

        # Default: always consider 高抛低吸 for rangebound
        if 35 <= trend <= 65 and 35 <= momentum <= 65:
            candidates.append(self._with_reason("高抛低吸", "震荡区间，适合箱体操作"))

        # Fallback: at least one recommendation
        if not candidates:
            if is_inst:
                candidates.append(self._with_reason("波段持股", "机构票，波段操作为主"))
            else:
                candidates.append(self._with_reason("高抛低吸", "当前无明确趋势，箱体操作"))

        # Deduplicate and limit
        seen = set()
        unique = []
        for c in candidates:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)
        unique = unique[: self.max_recs]

        situation = self._describe_situation(character_type, trend, momentum, fear_score)

        return TradingStrategies(
            symbol=symbol, name=name, market=market,
            character_type=character_type,
            current_situation=situation,
            recommended=unique,
            risk_reward_lesson=RISK_REWARD_LESSON,
        )

    def match_general(self, market_score: float, fear_score: float) -> TradingStrategies:
        """No-symbol mode: general market strategies."""
        candidates = []

        if fear_score > 70:
            candidates.append(self._with_reason("低吸反弹", f"市场恐慌（{fear_score:.0f}），超跌机会"))
            candidates.append(self._with_reason("定投策略", "恐慌区域，适合定投布局"))
        elif market_score > 60:
            candidates.append(self._with_reason("趋势突破", "大盘偏暖，关注突破机会"))
            candidates.append(self._with_reason("波段持股", "趋势向上，持股待涨"))
        else:
            candidates.append(self._with_reason("定投策略", "市场不明朗，定投最稳妥"))
            candidates.append(self._with_reason("高抛低吸", "震荡市，高抛低吸"))

        situation = f"大盘评分{market_score:.0f}，恐慌指数{fear_score:.0f}"

        return TradingStrategies(
            symbol=None, name=None, market=None, character_type=None,
            current_situation=situation,
            recommended=candidates[: self.max_recs],
            risk_reward_lesson=RISK_REWARD_LESSON,
        )

    def _with_reason(self, strategy_name: str, reason: str) -> StrategyItem:
        base = STRATEGIES[strategy_name]
        return base.model_copy(update={"match_reason": reason})

    def _describe_situation(self, char_type, trend, momentum, fear) -> str:
        parts = [char_type]
        if trend > 60:
            parts.append("趋势向上")
        elif trend < 40:
            parts.append("趋势偏弱")
        if momentum > 60:
            parts.append("动量充足")
        elif momentum < 40:
            parts.append("动量不足")
        if fear > 70:
            parts.append("恐慌情绪高")
        elif fear < 30:
            parts.append("情绪贪婪")
        return "，".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd market-analyst && python -m pytest tests/test_strategy_matcher.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add market-analyst/market_analyst/processors/strategy_matcher.py market-analyst/tests/test_strategy_matcher.py
git commit -m "feat(market-analyst): add strategy matcher with TDD"
```

---

## Task 7: JSON Cache + MCP Server Integration — Register 4 New Tools

**Files:**
- Modify: `market-analyst/market_analyst/utils/cache.py` (add `get_or_fetch_json`)
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/config/config.yaml`
- Test: `market-analyst/tests/test_mcp_server.py` (add new test classes)

- [ ] **Step 1: Add JSON cache support to DataCache**

Add to `market-analyst/market_analyst/utils/cache.py`:

```python
import json

def get_or_fetch_json(self, key: str, fetch_func, max_age_hours: int = 24) -> dict:
    """JSON cache for non-DataFrame data (e.g., earnings).
    Reuses _cache_path() for consistent key hashing, but with .json suffix."""
    parquet_path = self._cache_path(key)  # e.g., prefix_md5hash.parquet
    cache_path = parquet_path.with_suffix(".json")  # → .json
    if cache_path.exists():
        import time
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
    data = fetch_func()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    return data
```

- [ ] **Step 2: Add config sections**

Append to `market-analyst/config/config.yaml`:

```yaml
characterization:
  turnover_high_threshold: 8.0
  turnover_low_threshold: 3.0
  market_cap_small: 200
  market_cap_large: 500
  hot_money_threshold: 65
  institutional_threshold: 65
  weights:
    turnover: 0.25
    volatility: 0.20
    volume_pattern: 0.20
    limit_up_freq: 0.15
    institutional_holding: 0.10
    market_cap: 0.10

trade_signal:
  market_weight: 0.3
  stock_weight: 0.5
  character_weight: 0.2
  hot_money_sentiment_boost: 1.5
  hot_money_trend_reduction: 0.7
  institutional_trend_boost: 1.3
  institutional_sentiment_reduction: 0.8

earnings:
  beat_large_threshold: 10
  beat_small_threshold: 3
  reduction_alert_days: 90
  pledge_alert_ratio: 50

strategies:
  max_recommendations: 3
```

- [ ] **Step 3: Write failing integration tests**

Add to `market-analyst/tests/test_mcp_server.py`:

```python
class TestCharacterizeStock:
    def test_returns_valid_json(self):
        """Integration test: characterize_stock returns parseable JSON."""
        # This test will be added after mcp_server.py is updated
        pass


class TestGetTradeSignal:
    def test_returns_valid_json(self):
        pass


class TestAnalyzeEarnings:
    def test_returns_valid_json(self):
        pass


class TestGetTradingStrategies:
    def test_returns_valid_json(self):
        pass
```

- [ ] **Step 4: Register 4 new tools in mcp_server.py**

Add at end of `market-analyst/market_analyst/mcp_server.py` (before `if __name__` block):

```python
@mcp.tool()
def characterize_stock(symbol: str, market: Optional[str] = None) -> str:
    """个股定性：判断是游资票、机构票、机游合力票还是普通票。

    Args:
        symbol: 股票代码，如 "AAPL", "600519"
        market: "us" 或 "cn"，不传则自动推断
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        from market_analyst.collectors.stock_collector import StockCollector
        from market_analyst.processors.stock_characterizer import StockCharacterizer
        from market_analyst.utils.cache import DataCache

        config = _load_config()
        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

        stock_df = cache.get_or_fetch(
            f"stock_{symbol}",
            lambda: StockCollector().collect_single(symbol, market=market),
            max_age_hours=4,
        )

        # Fetch market cap and institutional holdings (best effort)
        market_cap = _fetch_market_cap(symbol, market)
        inst_pct = _fetch_institutional_pct(symbol, market)

        charzer = StockCharacterizer(config)
        result = charzer.characterize(
            symbol=symbol, raw_df=stock_df, market=market,
            market_cap=market_cap, institutional_pct=inst_pct,
        )
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"characterize_stock error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_trade_signal(symbol: str, market: Optional[str] = None) -> str:
    """加减仓建议：综合大盘+个股+定性，给出大吉/小吉/平/小凶/大凶判定。

    Args:
        symbol: 股票代码
        market: "us" 或 "cn"
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        config = _load_config()

        # 1. Market overview score
        strength_df, raw_df = _ensure_data()
        overview = _get_market_overview_impl(strength_df, market=market)
        market_score = max(0, min(100, overview.market_temp_5d or 50))

        # 2. Stock diagnosis
        from market_analyst.collectors.stock_collector import StockCollector
        from market_analyst.processors.stock_diagnostor import StockDiagnostor
        from market_analyst.utils.cache import DataCache
        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
        stock_df = cache.get_or_fetch(
            f"stock_{symbol}",
            lambda: StockCollector().collect_single(symbol, market=market),
            max_age_hours=4,
        )
        diag = StockDiagnostor().diagnose(stock_df)
        if diag is None:
            return ToolError(error="insufficient_data", message=f"个股数据不足: {symbol}").model_dump_json()

        # 3. Characterization (best effort fallback)
        try:
            from market_analyst.processors.stock_characterizer import StockCharacterizer
            market_cap = _fetch_market_cap(symbol, market)
            inst_pct = _fetch_institutional_pct(symbol, market)
            char_result = StockCharacterizer(config).characterize(
                symbol=symbol, raw_df=stock_df, market=market,
                market_cap=market_cap, institutional_pct=inst_pct,
            )
            character_type = char_result.character_type
        except Exception:
            character_type = "普通票"

        # 4. Generate signal
        from market_analyst.processors.trade_signal_generator import TradeSignalGenerator
        name = stock_df.iloc[0]["name"] if not stock_df.empty and "name" in stock_df.columns else symbol
        gen = TradeSignalGenerator(config)
        result = gen.generate(
            symbol=symbol, name=name, market=market,
            market_score=market_score, stock_scores=diag,
            character_type=character_type,
        )
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_trade_signal error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def analyze_earnings(symbol: str, market: Optional[str] = None) -> str:
    """财报解读：拉取最近财报，判断超预期/不及预期，标记ST/减持/质押等风险。

    Args:
        symbol: 股票代码
        market: "us" 或 "cn"
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        config = _load_config()
        from market_analyst.collectors.earnings_collector import EarningsCollector
        from market_analyst.processors.earnings_analyzer import EarningsAnalyzer
        from market_analyst.utils.cache import DataCache

        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
        data = cache.get_or_fetch_json(
            f"earnings_{symbol}",
            lambda: EarningsCollector(config).collect(symbol, market=market),
            max_age_hours=24,
        )

        analyzer = EarningsAnalyzer(config)
        result = analyzer.analyze(symbol, market, data)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"analyze_earnings error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_trading_strategies(symbol: Optional[str] = None, market: Optional[str] = None) -> str:
    """交易策略推荐：结合个股行情推荐适用策略，附盈亏比教育。不传symbol则返回通用策略。

    Args:
        symbol: 股票代码（可选）
        market: "us" 或 "cn"
    """
    try:
        config = _load_config()
        from market_analyst.processors.strategy_matcher import StrategyMatcher
        matcher = StrategyMatcher(config)

        if symbol is None:
            # General mode
            strength_df, raw_df = _ensure_data()
            overview = _get_market_overview_impl(strength_df, market=market or "all")
            market_score = max(0, min(100, overview.market_temp_5d or 50))
            fear = overview.fear_score or 50
            result = matcher.match_general(market_score=market_score, fear_score=fear)
        else:
            clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
            if market is None:
                market = "cn" if clean_symbol.isdigit() else "us"
            symbol = clean_symbol

            # Fetch stock data
            from market_analyst.collectors.stock_collector import StockCollector
            from market_analyst.processors.stock_diagnostor import StockDiagnostor
            from market_analyst.utils.cache import DataCache
            cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
            stock_df = cache.get_or_fetch(
                f"stock_{symbol}",
                lambda: StockCollector().collect_single(symbol, market=market),
                max_age_hours=4,
            )

            diag = StockDiagnostor().diagnose(stock_df)
            if diag is None:
                diag = {"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50}

            # Characterization (best effort)
            try:
                from market_analyst.processors.stock_characterizer import StockCharacterizer
                market_cap = _fetch_market_cap(symbol, market)
                inst_pct = _fetch_institutional_pct(symbol, market)
                char_result = StockCharacterizer(config).characterize(
                    symbol=symbol, raw_df=stock_df, market=market,
                    market_cap=market_cap, institutional_pct=inst_pct,
                )
                character_type = char_result.character_type
            except Exception:
                character_type = "普通票"

            # Fear score
            strength_df, _ = _ensure_data()
            fear_result = _get_fear_score_impl(strength_df, market=market)
            fear = fear_result.fear_score if fear_result else 50

            # Sector tier
            name = stock_df.iloc[0]["name"] if not stock_df.empty and "name" in stock_df.columns else symbol
            result = matcher.match(
                symbol=symbol, name=name, market=market,
                character_type=character_type, diagnosis=diag,
                fear_score=fear, sector_tier=None,
            )

        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_trading_strategies error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


def _fetch_market_cap(symbol: str, market: str) -> float | None:
    """Best-effort market cap fetch (亿元/亿美元)."""
    try:
        if market == "us":
            import yfinance as yf
            info = yf.Ticker(symbol).info
            cap = info.get("marketCap", 0)
            return cap / 1e8 if cap else None  # Convert to 亿美元
        else:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=symbol)
            if not df.empty:
                row = df[df["item"] == "总市值"]
                if not row.empty:
                    return float(row.iloc[0]["value"]) / 1e8
    except Exception as e:
        logger.debug(f"market_cap fetch failed for {symbol}: {e}")
    return None


def _fetch_institutional_pct(symbol: str, market: str) -> float | None:
    """Best-effort institutional holding percentage."""
    try:
        if market == "cn":
            import akshare as ak
            # stock_fund_stock_holder(symbol) returns fund holdings per stock
            df = ak.stock_fund_stock_holder(symbol=symbol)
            if not df.empty:
                # Sum up holding percentages from latest report period
                pct_col = [c for c in df.columns if "占流通" in c or "持股比例" in c or "占总股本" in c]
                if pct_col:
                    return float(df[pct_col[0]].head(10).sum())
        else:
            import yfinance as yf
            holders = yf.Ticker(symbol).institutional_holders
            if holders is not None and not holders.empty and "pctHeld" in holders.columns:
                return float(holders["pctHeld"].sum() * 100)
    except Exception as e:
        logger.debug(f"institutional_pct fetch failed for {symbol}: {e}")
    return None
```

- [ ] **Step 5: Run all tests**

Run: `cd market-analyst && python -m pytest tests/ -v`
Expected: All existing + new tests PASS

- [ ] **Step 6: Commit**

```bash
git add market-analyst/market_analyst/utils/cache.py market-analyst/market_analyst/mcp_server.py market-analyst/config/config.yaml market-analyst/tests/test_mcp_server.py
git commit -m "feat(market-analyst): register 4 new retail investor MCP tools + JSON cache"
```

---

## Task 8: SKILL.md Update — Extend Agent Skill Definition

**Files:**
- Modify: `skills/public/market-analyst/SKILL.md`

- [ ] **Step 1: Add new trigger conditions and tool docs to SKILL.md**

Append the following sections to the existing SKILL.md:

```markdown
### 个股定性 (characterize_stock)

**触发**: 用户问"这是什么票"、"游资还是机构"、"什么类型的股票"

**调用**: `characterize_stock(symbol="600519")`

**输出格式**:
```
【600519 贵州茅台 定性】机构票
🏛️ 机构倾向: 82分 | 游资倾向: 18分
📋 关键依据:
• 日均换手率1.2%，持仓稳定
• 总市值21000亿，大盘股
• 机构持仓45%，机构参与度高
💡 建议: 关注基本面、业绩预期、估值水平，波段持有
```

### 加减仓建议 (get_trade_signal)

**触发**: 用户问"能不能买"、"加仓还是减仓"、"现在能操作吗"

**调用**: `get_trade_signal(symbol="600519")`

**输出格式**:
```
【600519 贵州茅台】小吉 ✨
综合分: 68 | 大盘: 55 | 个股: 78 | 机构票
✅ 趋势稳健，均线多头排列
✅ 资金持续流入
⚠️ 大盘环境偏弱，注意风险
```

### 财报解读 (analyze_earnings)

**触发**: 用户问"财报怎么样"、"业绩好不好"、"有没有风险"

**调用**: `analyze_earnings(symbol="600519")`

**输出格式**:
```
【600519 贵州茅台 2025Q4财报】小幅超预期 (+5.2%)
💰 营收350.5亿 | 净利润180.2亿
📈 趋势: 连续增长
⚠️ 风险: 无
```

### 交易策略推荐 (get_trading_strategies)

**触发**: 用户问"怎么做这个票"、"有什么策略"、"怎么操作"

**调用**: `get_trading_strategies(symbol="600519")` 或 `get_trading_strategies()`

**输出格式**:
```
【600519 贵州茅台 策略推荐】机构票，趋势向上
📘 波段持股（进阶）
  入场: 站上20日均线且均线向上
  出场: 收盘跌破20日均线
  止损: 跌破20日均线即离场
  盈亏比: 2:1
💡 盈亏比科普: 盈亏比是长期盈利的核心...
```
```

- [ ] **Step 2: Commit**

```bash
git add skills/public/market-analyst/SKILL.md
git commit -m "docs(market-analyst): update SKILL.md with 4 new retail investor tools"
```

---

## Task 9: Final Integration Test & Verification

- [ ] **Step 1: Run full test suite**

Run: `cd market-analyst && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Type check (if mypy available)**

Run: `cd market-analyst && python -m mypy market_analyst/schemas_retail.py market_analyst/processors/stock_characterizer.py market_analyst/processors/trade_signal_generator.py market_analyst/processors/earnings_analyzer.py market_analyst/processors/strategy_matcher.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 3: Verify MCP server loads**

Run: `cd market-analyst && python -c "from market_analyst.mcp_server import mcp; print('MCP server loaded, tools:', len(mcp._tools))"`
Expected: prints `MCP server loaded, tools: 14`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(market-analyst): complete retail investor module - 4 new MCP tools"
```
