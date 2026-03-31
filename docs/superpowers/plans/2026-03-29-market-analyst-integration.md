# Market-Analyst DeerFlow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the standalone market-analyst data engine into DeerFlow as an MCP Server, enabling conversational stock diagnosis, market commentary, and multi-dimensional scoring for retail investors.

**Architecture:** market-analyst becomes a FastMCP stdio server registered in DeerFlow's `extensions_config.json`. Existing collectors/processors are wrapped as MCP tools. A DeerFlow Skill (`SKILL.md`) defines the conversational interaction patterns for retail users.

**Tech Stack:** Python 3.12+, FastMCP, pandas, yfinance, akshare, Pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-03-29-market-analyst-deerflow-integration-design.md`

---

## File Structure

### New Files
```
market-analyst/
├── pyproject.toml                              # Package metadata + dependencies
├── main.py                                     # Thin wrapper → market_analyst.main
├── market_analyst/                             # Renamed from src/
│   ├── __init__.py
│   ├── main.py                                 # Pipeline entry (moved from root)
│   ├── mcp_server.py                           # FastMCP entry point
│   ├── schemas.py                              # Pydantic output models for all tools
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base_collector.py                   # (moved from src/)
│   │   ├── us_etf_collector.py                 # (moved)
│   │   ├── cn_etf_collector.py                 # (moved)
│   │   ├── global_index_collector.py           # (moved)
│   │   ├── premarket_collector.py              # (moved)
│   │   ├── tv_indicator_collector.py           # (moved)
│   │   ├── sector_scanner.py                   # (moved)
│   │   └── stock_collector.py                  # NEW: individual stock data
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── strength_calculator.py              # (moved)
│   │   ├── quant_metrics.py                    # (moved)
│   │   ├── anomaly_detector.py                 # (moved)
│   │   ├── cycle_analyzer.py                   # (moved)
│   │   ├── signal_generator.py                 # (moved)
│   │   ├── fear_score_calculator.py            # (moved)
│   │   ├── market_analyzer.py                  # (moved)
│   │   ├── momentum_scanner.py                 # (moved)
│   │   ├── portfolio_advisor.py                # (moved)
│   │   └── stock_diagnostor.py                 # NEW: multi-dimensional stock scoring
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── cache.py                            # (moved)
│   │   └── web_search.py                       # (moved)
│   └── exporters/
│       ├── __init__.py
│       ├── obsidian_exporter.py                # (moved)
│       └── json_exporter.py                    # (moved)
├── tests/
│   ├── conftest.py                             # (update imports)
│   ├── test_mcp_server.py                      # NEW: MCP tool tests
│   ├── test_schemas.py                         # NEW: Pydantic model tests
│   ├── test_stock_collector.py                 # NEW
│   ├── test_stock_diagnostor.py                # NEW
│   ├── test_strength_calculator.py             # (update imports)
│   ├── test_anomaly_detector.py                # (update imports)
│   └── test_quant_metrics.py                   # (update imports)
├── config/                                     # unchanged
├── data/                                       # unchanged
└── main.py                                     # (update imports)

skills/public/market-analyst/
└── SKILL.md                                    # NEW: DeerFlow skill definition
```

### Modified Files
```
extensions_config.json                          # Add market-analyst MCP server
Makefile                                        # Add market-analyst install step
```

---

## Task 0: Package Restructure

### Task 0.1: Rename `src/` to `market_analyst/` and create `pyproject.toml`

**Files:**
- Rename: `market-analyst/src/` → `market-analyst/market_analyst/`
- Create: `market-analyst/pyproject.toml`
- Modify: `market-analyst/main.py`
- Modify: `market-analyst/dashboard.py`

- [ ] **Step 1: Rename the source directory**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
# Git Bash / Unix:
mv src market_analyst
# Windows cmd: ren src market_analyst
# Verify __init__.py exists in all sub-packages
ls market_analyst/__init__.py market_analyst/collectors/__init__.py market_analyst/processors/__init__.py market_analyst/utils/__init__.py market_analyst/exporters/__init__.py
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "market-analyst"
version = "0.1.0"
description = "Market analysis MCP server for DeerFlow"
requires-python = ">=3.11"
dependencies = [
    "yfinance>=0.2.31,<1.0",
    "akshare>=1.12.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "pyyaml>=6.0.1",
    "python-dotenv>=1.0.0",
    "loguru>=0.7.2",
    "pyarrow>=14.0",
    "pydantic>=2.0",
    "fastmcp>=0.1.0",
    "tavily-python>=0.5.0",
    "duckduckgo-search>=4.0",
    "tvscreener>=0.1.0",
]

[project.optional-dependencies]
ai = [
    "google-genai>=1.0.0",
    "anthropic>=0.25.0",
    "openai>=1.0.0",
]
dashboard = [
    "streamlit>=1.35.0",
    "plotly>=5.20.0",
]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 3: Move `main.py` into the package and update imports**

```bash
# Git Bash / Unix:
mv main.py market_analyst/main.py
# Windows cmd: move main.py market_analyst\main.py
```

Create a thin wrapper at root for backwards compatibility:
```python
# market-analyst/main.py (new, thin wrapper)
"""Backwards-compatible entry point."""
from market_analyst.main import main

if __name__ == "__main__":
    main()
```

In `market_analyst/main.py` (the moved file), replace all `from src.` with `from market_analyst.`:

```python
# Before: from src.collectors.us_etf_collector import USETFCollector
# After:  from market_analyst.collectors.us_etf_collector import USETFCollector
```

Apply to all imports (approx 15 import lines).

- [ ] **Step 4: Update imports in `dashboard.py`**

Same pattern: replace all `from src.` → `from market_analyst.`.

- [ ] **Step 5: Update imports in `scripts/sector_scan.py`**

Same pattern.

- [ ] **Step 6: Update imports in test files**

Update all test files — replace `from src.` → `from market_analyst.`:
- `tests/conftest.py`
- `tests/test_strength_calculator.py`
- `tests/test_anomaly_detector.py`
- `tests/test_quant_metrics.py`
- `tests/test_momentum_scanner.py` (if exists)
- Any other test files found via `grep -r "from src\." tests/`

- [ ] **Step 7: Clean up `__pycache__` directories**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
# Windows Git Bash:
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
# Or Windows cmd:
# for /d /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
```

- [ ] **Step 8: Create venv and install**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

- [ ] **Step 9: Run existing tests to verify nothing broke**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
.venv/Scripts/python -m pytest tests/ -v
```

Expected: All existing tests pass.

- [ ] **Step 10: Commit**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
git add -A
git commit -m "refactor: rename src/ to market_analyst/ and add pyproject.toml"
```

---

## Task 1: Pydantic Output Schemas

### Task 1.1: Define shared Pydantic models for all MCP tool outputs

**Files:**
- Create: `market-analyst/market_analyst/schemas.py`
- Create: `market-analyst/tests/test_schemas.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_schemas.py
"""Tests for Pydantic output schemas."""
import pytest
from market_analyst.schemas import (
    MarketOverview,
    SectorStrength,
    StockDiagnosis,
    FearScoreResult,
    AnomalySignal,
    CycleSignal,
    CommentaryData,
    MomentumItem,
    NewsItem,
    ReportResult,
    ToolError,
)


class TestMarketOverview:
    def test_valid_overview(self):
        data = MarketOverview(
            market="us",
            market_temp_5d=1.2,
            advancing=30,
            declining=15,
            t1_sectors=[{"symbol": "XLK", "name": "科技", "roc_5d": 3.5}],
            t4_sectors=[{"symbol": "XLE", "name": "能源", "roc_5d": -2.1}],
            fear_score=45.0,
            fear_label="中性",
            key_indices={"VIX": 18.5, "DXY": 104.2},
            stale=False,
        )
        assert data.market == "us"
        assert data.advancing == 30
        assert data.stale is False

    def test_stale_flag(self):
        data = MarketOverview(
            market="cn", market_temp_5d=0.5,
            advancing=20, declining=10,
            t1_sectors=[], t4_sectors=[],
            fear_score=None, fear_label=None,
            key_indices={}, stale=True,
        )
        assert data.stale is True
        assert data.fear_score is None


class TestStockDiagnosis:
    def test_full_diagnosis(self):
        d = StockDiagnosis(
            symbol="AAPL", name="Apple", market="us",
            scores={"trend": 72, "momentum": 65, "sentiment": 55, "volatility": 40, "flow": None},
            rating=4,
            available_dimensions=["trend", "momentum", "sentiment", "volatility"],
            stale=False,
        )
        assert d.rating == 4
        assert d.scores["flow"] is None
        assert "flow" not in d.available_dimensions

    def test_rating_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StockDiagnosis(
                symbol="X", name="X", market="us",
                scores={}, rating=6,  # out of 1-5
                available_dimensions=[], stale=False,
            )


class TestToolError:
    def test_error_model(self):
        e = ToolError(error="data_unavailable", message="yfinance timeout")
        assert e.error == "data_unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
.venv/Scripts/python -m pytest tests/test_schemas.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'market_analyst.schemas'`

- [ ] **Step 3: Implement schemas**

```python
# market_analyst/schemas.py
"""Pydantic output models for all MCP tools."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ToolError(BaseModel):
    """Returned when a tool cannot produce results."""
    error: str
    message: str


class MarketOverview(BaseModel):
    market: Literal["us", "cn", "all"]
    market_temp_5d: float | None = None
    advancing: int = 0
    declining: int = 0
    t1_sectors: list[dict] = Field(default_factory=list)
    t4_sectors: list[dict] = Field(default_factory=list)
    fear_score: float | None = None
    fear_label: str | None = None
    key_indices: dict[str, float] = Field(default_factory=dict)
    stale: bool = False


class SectorStrengthItem(BaseModel):
    symbol: str
    name: str
    sector: str
    market: str
    close: float
    roc_5d: float
    roc_20d: float
    roc_60d: float
    composite_score: float
    tier: str
    delta_roc_5d: float | None = None


class SectorStrength(BaseModel):
    market: str
    items: list[SectorStrengthItem]
    stale: bool = False


class StockDiagnosis(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    scores: dict[str, float | None]
    rating: int = Field(ge=1, le=5)
    available_dimensions: list[str]
    stale: bool = False


class FearScoreResult(BaseModel):
    symbol: str | None = None
    market: str | None = None
    fear_score: float | None = None
    fear_label: str | None = None
    bottom_score: float | None = None
    bottom_label: str | None = None
    dimensions: dict[str, float] = Field(default_factory=dict)
    stale: bool = False


class AnomalySignal(BaseModel):
    type: str
    severity: Literal["high", "medium", "low"]
    symbols: list[str]
    description: str
    data: dict = Field(default_factory=dict)


class CycleSignal(BaseModel):
    symbol: str
    name: str
    signal_type: str  # "breakout" or "parabolic"
    confidence: str
    details: dict = Field(default_factory=dict)


class CommentaryData(BaseModel):
    """Structured data for the agent to compose commentary."""
    type: Literal["morning", "midday", "closing"]
    market_temp: dict[str, float] = Field(default_factory=dict)
    top_movers: list[dict] = Field(default_factory=list)
    worst_movers: list[dict] = Field(default_factory=list)
    anomalies_summary: list[str] = Field(default_factory=list)
    key_indices_change: dict[str, float] = Field(default_factory=dict)
    fear_score: float | None = None
    fear_label: str | None = None


class MomentumItem(BaseModel):
    symbol: str
    name: str
    market: str
    perf_5d: float | None = None
    perf_20d: float | None = None
    trigger: str | None = None  # "5d" / "20d" / "both"
    avg_volume: float | None = None


class NewsItem(BaseModel):
    title: str
    url: str
    summary: str | None = None
    related_sectors: list[str] = Field(default_factory=list)


class ReportResult(BaseModel):
    status: Literal["completed", "running", "failed"]
    filepath: str | None = None
    job_id: str | None = None
    message: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
.venv/Scripts/python -m pytest tests/test_schemas.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
git add market_analyst/schemas.py tests/test_schemas.py
git commit -m "feat: add Pydantic output schemas for MCP tools"
```

---

## Task 2: MCP Server Skeleton + POC (`get_fear_score`)

### Task 2.1: Minimal MCP server with one tool to validate the full chain

**Files:**
- Create: `market-analyst/market_analyst/mcp_server.py`
- Create: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_mcp_server.py
"""Tests for MCP server tools."""
import pytest
import json
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from market_analyst.schemas import FearScoreResult, ToolError


class TestGetFearScore:
    """Test the get_fear_score MCP tool logic."""

    def _make_strength_df(self):
        """Create a minimal strength_df with fear score columns."""
        return pd.DataFrame([
            {
                "symbol": "SPY", "name": "S&P 500", "market": "us",
                "sector": "大盘指数", "close": 500.0,
                "roc_5d": 1.5, "roc_20d": 3.0, "roc_60d": 8.0,
                "composite_score": 75.0, "tier": "T1",
                "fear_score": 35.0, "fear_label": "贪婪",
                "bottom_score": 20.0, "bottom_label": "无迹象",
                "fear_rsi_dim": 8.0, "fear_drawdown_dim": 10.0,
                "fear_streak_dim": 7.0, "fear_momentum_dim": 10.0,
            },
            {
                "symbol": "QQQ", "name": "纳斯达克100", "market": "us",
                "sector": "大盘指数", "close": 440.0,
                "roc_5d": -2.0, "roc_20d": -1.0, "roc_60d": 5.0,
                "composite_score": 40.0, "tier": "T3",
                "fear_score": 65.0, "fear_label": "恐慌",
                "bottom_score": 55.0, "bottom_label": "有迹象",
                "fear_rsi_dim": 18.0, "fear_drawdown_dim": 15.0,
                "fear_streak_dim": 17.0, "fear_momentum_dim": 15.0,
            },
        ])

    def test_fear_score_specific_symbol(self):
        from market_analyst.mcp_server import _get_fear_score_impl
        df = self._make_strength_df()
        result = _get_fear_score_impl(df, symbol="SPY")
        assert isinstance(result, FearScoreResult)
        assert result.symbol == "SPY"
        assert result.fear_score == 35.0
        assert result.fear_label == "贪婪"

    def test_fear_score_market_average(self):
        from market_analyst.mcp_server import _get_fear_score_impl
        df = self._make_strength_df()
        result = _get_fear_score_impl(df, market="us")
        assert isinstance(result, FearScoreResult)
        assert result.market == "us"
        assert result.fear_score is not None  # should be average

    def test_fear_score_symbol_not_found(self):
        from market_analyst.mcp_server import _get_fear_score_impl
        df = self._make_strength_df()
        result = _get_fear_score_impl(df, symbol="ZZZZZ")
        assert isinstance(result, ToolError)
        assert result.error == "symbol_not_found"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
.venv/Scripts/python -m pytest tests/test_mcp_server.py::TestGetFearScore -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement MCP server with `get_fear_score`**

```python
# market_analyst/mcp_server.py
"""Market Analyst MCP Server — FastMCP entry point."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from dotenv import load_dotenv
from loguru import logger
from fastmcp import FastMCP

from market_analyst.schemas import (
    FearScoreResult,
    ToolError,
)

# ---------------------------------------------------------------------------
# Globals (lazy-loaded)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
_strength_df: pd.DataFrame | None = None
_raw_df: pd.DataFrame | None = None
_config: dict | None = None
_universe: dict | None = None

mcp = FastMCP(
    "market-analyst",
    description="市场分析引擎：板块强弱、个股诊断、恐慌评分、异常检测",
)


def _load_config() -> dict:
    global _config, _universe
    if _config is None:
        env_path = BASE_DIR / "config" / ".env"
        if env_path.exists():
            load_dotenv(str(env_path))
        config_path = BASE_DIR / "config" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    if _universe is None:
        universe_path = BASE_DIR / "config" / "etf_universe.yaml"
        with open(universe_path, "r", encoding="utf-8") as f:
            _universe = yaml.safe_load(f)
    return _config


def _ensure_data(market: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load or refresh the core pipeline data (strength_df + raw_df).

    Uses DataCache so repeated calls within cache TTL are instant.
    """
    global _strength_df, _raw_df

    if _strength_df is not None and _raw_df is not None:
        if market and market != "all":
            mask = _strength_df["market"] == market
            return _strength_df[mask], _raw_df[_raw_df["symbol"].isin(_strength_df[mask]["symbol"])]
        return _strength_df, _raw_df

    config = _load_config()
    from market_analyst.utils.cache import DataCache
    cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

    # Try to load from today's cache first
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    cached_strength = cache.get("_strength", max_age_hours=8)

    if cached_strength is not None and not cached_strength.empty:
        _strength_df = cached_strength
        # Also load raw data for processors that need it
        raw_parts = []
        for prefix in ["us_etf", "cn_etf", "global_idx"]:
            part = cache.get(f"{prefix}_{today}", max_age_hours=8)
            if part is not None and not part.empty:
                raw_parts.append(part)
        _raw_df = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    else:
        # Run the pipeline to generate fresh data
        logger.info("No cached data, running pipeline...")
        from market_analyst.collectors.us_etf_collector import USETFCollector
        from market_analyst.collectors.cn_etf_collector import CNETFCollector
        from market_analyst.collectors.global_index_collector import GlobalIndexCollector
        from market_analyst.processors.strength_calculator import StrengthCalculator
        from market_analyst.processors.quant_metrics import QuantMetrics
        from market_analyst.processors.fear_score_calculator import FearScoreCalculator

        lookback = config.get("data", {}).get("lookback_days", 60)
        all_data = []

        if config.get("data", {}).get("us_market", True):
            us = cache.get_or_fetch(
                f"us_etf_{today}",
                lambda: USETFCollector().collect(_universe.get("us_etfs", []), lookback),
                max_age_hours=8,
            )
            all_data.append(us)

        if config.get("data", {}).get("cn_market", True):
            cn = cache.get_or_fetch(
                f"cn_etf_{today}",
                lambda: CNETFCollector().collect(_universe.get("cn_etfs", []), lookback),
                max_age_hours=8,
            )
            all_data.append(cn)

        if config.get("data", {}).get("global_indices", True):
            gl = cache.get_or_fetch(
                f"global_idx_{today}",
                lambda: GlobalIndexCollector().collect(_universe.get("global_indices", []), lookback),
                max_age_hours=8,
            )
            all_data.append(gl)

        valid = [d for d in all_data if d is not None and not d.empty]
        if not valid:
            _raw_df = pd.DataFrame()
            _strength_df = pd.DataFrame()
        else:
            _raw_df = pd.concat(valid, ignore_index=True)
            calc = StrengthCalculator(config)
            _strength_df = calc.calculate(_raw_df)

            qm = QuantMetrics(periods_per_year=252)
            _strength_df = qm.calculate_all(_raw_df, _strength_df)

            if config.get("fear_score", {}).get("enabled", True):
                fc = FearScoreCalculator(config)
                _strength_df = fc.calculate_all(_raw_df, _strength_df)

            cache.set("_strength", _strength_df)

    if market and market != "all":
        mask = _strength_df["market"] == market
        return _strength_df[mask], _raw_df[_raw_df["symbol"].isin(_strength_df[mask]["symbol"])]
    return _strength_df, _raw_df


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fear_label(score: float | None) -> str | None:
    """Convert fear score (0-100) to Chinese label."""
    if score is None: return None
    if score < 25: return "极贪婪"
    if score < 40: return "贪婪"
    if score < 60: return "中性"
    if score < 75: return "恐慌"
    return "极恐慌"


# ---------------------------------------------------------------------------
# Tool implementations (pure functions, testable without MCP)
# ---------------------------------------------------------------------------

def _get_fear_score_impl(
    strength_df: pd.DataFrame,
    symbol: str | None = None,
    market: str | None = None,
) -> FearScoreResult | ToolError:
    """Pure implementation of get_fear_score, separated for testing."""
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data loaded")

    dim_cols = ["fear_rsi_dim", "fear_drawdown_dim", "fear_streak_dim", "fear_momentum_dim"]

    if symbol:
        row = strength_df[strength_df["symbol"] == symbol]
        if row.empty:
            return ToolError(error="symbol_not_found", message=f"Symbol {symbol} not found")
        r = row.iloc[0]
        dims = {c: float(r[c]) for c in dim_cols if c in r and pd.notna(r[c])}
        return FearScoreResult(
            symbol=symbol,
            market=str(r.get("market", "")),
            fear_score=float(r["fear_score"]) if pd.notna(r.get("fear_score")) else None,
            fear_label=str(r.get("fear_label", "")),
            bottom_score=float(r["bottom_score"]) if pd.notna(r.get("bottom_score")) else None,
            bottom_label=str(r.get("bottom_label", "")),
            dimensions=dims,
        )
    else:
        mkt = market or "all"
        df = strength_df if mkt == "all" else strength_df[strength_df["market"] == mkt]
        if df.empty:
            return ToolError(error="no_data_for_market", message=f"No data for market={mkt}")
        avg_fear = float(df["fear_score"].mean()) if "fear_score" in df.columns else None
        avg_bottom = float(df["bottom_score"].mean()) if "bottom_score" in df.columns else None

        return FearScoreResult(
            market=mkt,
            fear_score=round(avg_fear, 1) if avg_fear else None,
            fear_label=_fear_label(avg_fear),
            bottom_score=round(avg_bottom, 1) if avg_bottom else None,
        )


# ---------------------------------------------------------------------------
# MCP Tool registrations
# ---------------------------------------------------------------------------

@mcp.tool()
def get_fear_score(symbol: Optional[str] = None, market: Optional[str] = None) -> str:
    """获取恐慌/抄底评分。

    指定 symbol 返回单只标的评分，指定 market ("us"/"cn") 返回市场平均评分。

    Args:
        symbol: 股票/ETF 代码，如 "SPY", "510300"
        market: 市场筛选 "us" / "cn" / "all"
    """
    try:
        strength_df, _ = _ensure_data(market)
        result = _get_fear_score_impl(strength_df, symbol=symbol, market=market)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_fear_score error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server via stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
.venv/Scripts/python -m pytest tests/test_mcp_server.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd "E:/字节跳动框架/deer-flow-main/market-analyst"
git add market_analyst/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add MCP server skeleton with get_fear_score tool"
```

---

### Task 2.2: Register MCP server in DeerFlow and validate end-to-end

**Files:**
- Modify: `E:/字节跳动框架/deer-flow-main/extensions_config.json`

- [ ] **Step 1: Add market-analyst to extensions config**

If `extensions_config.json` does not exist, copy from example first:
```bash
cd "E:/字节跳动框架/deer-flow-main"
# Git Bash / Unix:
cp extensions_config.example.json extensions_config.json 2>/dev/null || true
# Windows cmd: copy extensions_config.example.json extensions_config.json
```

Then add the market-analyst entry to the `mcpServers` section:

DeerFlow MCP client 不传 `cwd`，且启动时 cwd 在 `backend/`。
DeerFlow 的 `$VAR_NAME` 只支持整值替换，不支持 `$VAR/suffix` 拼接。
因此需设置完整路径的环境变量 `MARKET_ANALYST_PYTHON`。

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

确保 `.env` 中设置了完整解释器路径：
```bash
# .env
MARKET_ANALYST_PYTHON=E:/字节跳动框架/deer-flow-main/market-analyst/.venv/Scripts/python
```
```

Note: On Linux/Mac change `Scripts` to `bin`.

- [ ] **Step 2: Manual smoke test**

Start DeerFlow dev server and verify the tool is visible:

```bash
cd "E:/字节跳动框架/deer-flow-main"
make dev
```

Then in the DeerFlow chat, ask: "查看恐慌评分" — the agent should call `market-analyst_get_fear_score`.

- [ ] **Step 3: Commit**

```bash
cd "E:/字节跳动框架/deer-flow-main"
git add extensions_config.json
git commit -m "feat: register market-analyst MCP server in DeerFlow"
```

---

## Task 3: Core MCP Tools (Phase 1)

### Task 3.1: `get_market_overview` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

Add to `tests/test_mcp_server.py`:

```python
from market_analyst.schemas import MarketOverview


class TestGetMarketOverview:
    def _make_data(self):
        """Strength df with mixed tiers and fear scores."""
        return pd.DataFrame([
            {"symbol": "XLK", "name": "科技", "market": "us", "sector": "板块",
             "close": 200, "roc_5d": 4.0, "roc_20d": 8.0, "roc_60d": 15.0,
             "composite_score": 90, "tier": "T1", "delta_roc_5d": 1.0,
             "fear_score": 30, "fear_label": "贪婪",
             "bottom_score": 15, "bottom_label": "无迹象",
             "market_temp_5d": 1.5},
            {"symbol": "XLE", "name": "能源", "market": "us", "sector": "板块",
             "close": 80, "roc_5d": -3.0, "roc_20d": -5.0, "roc_60d": -10.0,
             "composite_score": 15, "tier": "T4", "delta_roc_5d": -0.5,
             "fear_score": 70, "fear_label": "恐慌",
             "bottom_score": 60, "bottom_label": "有迹象",
             "market_temp_5d": 1.5},
            {"symbol": "XLF", "name": "金融", "market": "us", "sector": "板块",
             "close": 42, "roc_5d": 1.0, "roc_20d": 2.0, "roc_60d": 5.0,
             "composite_score": 55, "tier": "T2", "delta_roc_5d": 0.2,
             "fear_score": 45, "fear_label": "中性",
             "bottom_score": 25, "bottom_label": "无迹象",
             "market_temp_5d": 1.5},
        ])

    def test_overview_us(self):
        from market_analyst.mcp_server import _get_market_overview_impl
        df = self._make_data()
        result = _get_market_overview_impl(df, market="us")
        assert isinstance(result, MarketOverview)
        assert result.market == "us"
        assert len(result.t1_sectors) == 1
        assert result.t1_sectors[0]["symbol"] == "XLK"
        assert len(result.t4_sectors) == 1
        assert result.advancing >= 1
        assert result.declining >= 1

    def test_overview_empty(self):
        from market_analyst.mcp_server import _get_market_overview_impl
        result = _get_market_overview_impl(pd.DataFrame(), market="us")
        assert isinstance(result, ToolError)
```

- [ ] **Step 2: Run test — expect fail**

```bash
.venv/Scripts/python -m pytest tests/test_mcp_server.py::TestGetMarketOverview -v
```

- [ ] **Step 3: Implement `_get_market_overview_impl` and register tool**

Add to `mcp_server.py`:

```python
from market_analyst.schemas import MarketOverview

def _extract_key_indices(strength_df: pd.DataFrame) -> dict[str, float]:
    """Extract key macro indices (VIX, DXY, Gold etc) from global symbols in strength_df."""
    # These symbols come from global_indices in etf_universe.yaml
    key_symbols = {"^VIX": "VIX", "DX-Y.NYB": "DXY", "GC=F": "黄金", "CL=F": "原油"}
    indices = {}
    for sym, label in key_symbols.items():
        row = strength_df[strength_df["symbol"] == sym]
        if not row.empty and "close" in row.columns:
            indices[label] = round(float(row.iloc[0]["close"]), 2)
    return indices


def _get_market_overview_impl(
    strength_df: pd.DataFrame,
    market: str = "all",
) -> MarketOverview | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data")

    df = strength_df if market == "all" else strength_df[strength_df["market"] == market]
    if df.empty:
        return ToolError(error="no_data_for_market", message=f"No data for {market}")

    t1 = df[df["tier"] == "T1"].sort_values("composite_score", ascending=False)
    t4 = df[df["tier"] == "T4"].sort_values("composite_score", ascending=True)
    advancing = int((df["roc_5d"] > 0).sum())
    declining = int((df["roc_5d"] < 0).sum())

    avg_fear = float(df["fear_score"].mean()) if "fear_score" in df.columns else None
    # _fear_label is a module-level helper defined above

    temp = float(df["market_temp_5d"].iloc[0]) if "market_temp_5d" in df.columns else None

    return MarketOverview(
        market=market,
        market_temp_5d=temp,
        advancing=advancing,
        declining=declining,
        t1_sectors=[
            {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
            for _, r in t1.head(10).iterrows()
        ],
        t4_sectors=[
            {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
            for _, r in t4.head(10).iterrows()
        ],
        fear_score=round(avg_fear, 1) if avg_fear else None,
        fear_label=_fear_label(avg_fear),
        key_indices=_extract_key_indices(strength_df),
    )


@mcp.tool()
def get_market_overview(market: Optional[str] = "all") -> str:
    """获取市场全局概览：温度、涨跌统计、强弱板块、恐慌评分。

    Args:
        market: "us" / "cn" / "all"
    """
    try:
        strength_df, _ = _ensure_data(market)
        result = _get_market_overview_impl(strength_df, market=market or "all")
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_market_overview error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/Scripts/python -m pytest tests/test_mcp_server.py -v
```

- [ ] **Step 5: Commit**

```bash
git add market_analyst/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add get_market_overview MCP tool"
```

---

### Task 3.2: `get_sector_strength` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import SectorStrength, SectorStrengthItem


class TestGetSectorStrength:
    def _make_data(self):
        # reuse TestGetMarketOverview._make_data pattern
        return pd.DataFrame([
            {"symbol": "XLK", "name": "科技", "market": "us", "sector": "板块",
             "close": 200, "roc_5d": 4.0, "roc_20d": 8.0, "roc_60d": 15.0,
             "composite_score": 90, "tier": "T1", "delta_roc_5d": 1.0},
            {"symbol": "XLE", "name": "能源", "market": "us", "sector": "板块",
             "close": 80, "roc_5d": -3.0, "roc_20d": -5.0, "roc_60d": -10.0,
             "composite_score": 15, "tier": "T4", "delta_roc_5d": -0.5},
        ])

    def test_strength_returns_sorted(self):
        from market_analyst.mcp_server import _get_sector_strength_impl
        df = self._make_data()
        result = _get_sector_strength_impl(df, market="us", top_n=10)
        assert isinstance(result, SectorStrength)
        assert len(result.items) == 2
        assert result.items[0].composite_score >= result.items[1].composite_score

    def test_strength_top_n(self):
        from market_analyst.mcp_server import _get_sector_strength_impl
        df = self._make_data()
        result = _get_sector_strength_impl(df, market="us", top_n=1)
        assert len(result.items) == 1
```

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement `_get_sector_strength_impl` and register `@mcp.tool()`**

```python
from market_analyst.schemas import SectorStrength, SectorStrengthItem

def _get_sector_strength_impl(
    strength_df: pd.DataFrame,
    market: str = "all",
    top_n: int = 50,
) -> SectorStrength | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No data")

    df = strength_df if market == "all" else strength_df[strength_df["market"] == market]
    df = df.sort_values("composite_score", ascending=False).head(top_n)

    items = []
    for _, r in df.iterrows():
        items.append(SectorStrengthItem(
            symbol=r["symbol"], name=r["name"], sector=r.get("sector", ""),
            market=r["market"], close=round(float(r["close"]), 2),
            roc_5d=round(float(r["roc_5d"]), 2),
            roc_20d=round(float(r["roc_20d"]), 2),
            roc_60d=round(float(r["roc_60d"]), 2),
            composite_score=round(float(r["composite_score"]), 1),
            tier=r["tier"],
            delta_roc_5d=round(float(r["delta_roc_5d"]), 2) if pd.notna(r.get("delta_roc_5d")) else None,
        ))

    return SectorStrength(market=market, items=items)
```

- [ ] **Step 4: Run — expect pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add get_sector_strength MCP tool"
```

---

### Task 3.3: `get_anomalies` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import AnomalySignal


class TestGetAnomalies:
    def test_anomalies_structure(self):
        from market_analyst.mcp_server import _get_anomalies_impl
        anomalies = [
            {"type": "zscore", "severity": "high", "symbols": ["XLK"],
             "description": "XLK z-score > 2.5", "data": {"zscore": 2.8}},
            {"type": "divergence", "severity": "medium", "symbols": ["VIX", "QQQ"],
             "description": "VIX/QQQ divergence", "data": {}},
        ]
        result = _get_anomalies_impl(anomalies, severity="all")
        assert len(result) == 2
        assert all(isinstance(a, AnomalySignal) for a in result)

    def test_anomalies_filter_high(self):
        from market_analyst.mcp_server import _get_anomalies_impl
        anomalies = [
            {"type": "zscore", "severity": "high", "symbols": ["XLK"],
             "description": "test", "data": {}},
            {"type": "divergence", "severity": "low", "symbols": ["VIX"],
             "description": "test", "data": {}},
        ]
        result = _get_anomalies_impl(anomalies, severity="high")
        assert len(result) == 1
        assert result[0].severity == "high"
```

- [ ] **Step 2: Run — fail**
- [ ] **Step 3: Implement**

```python
def _get_anomalies_impl(
    anomalies: list[dict],
    severity: str = "all",
) -> list[AnomalySignal]:
    results = []
    for a in anomalies:
        if severity != "all" and a.get("severity") != severity:
            continue
        results.append(AnomalySignal(
            type=a["type"],
            severity=a["severity"],
            symbols=a.get("symbols", []),
            description=a.get("description", ""),
            data=a.get("data", {}),
        ))
    return results
```

The MCP tool wrapper calls `AnomalyDetector.detect()` using `_ensure_data()`, then passes to `_get_anomalies_impl`.

- [ ] **Step 4: Run — pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add get_anomalies MCP tool"
```

---

### Task 3.4: `get_cycle_signals` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import CycleSignal


class TestGetCycleSignals:
    def test_cycle_signals_structure(self):
        from market_analyst.mcp_server import _get_cycle_signals_impl
        # SignalGenerator uses "signal_type" field, not "type"
        signals = [
            {"symbol": "XLK", "name": "科技", "signal_type": "breakout",
             "confidence": "high", "roc_20d": 5.0, "position_pct": 85.0},
        ]
        result = _get_cycle_signals_impl(signals)
        assert len(result) == 1
        assert isinstance(result[0], CycleSignal)
        assert result[0].signal_type == "breakout"

    def test_empty_signals(self):
        from market_analyst.mcp_server import _get_cycle_signals_impl
        result = _get_cycle_signals_impl([])
        assert result == []

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement**

```python
def _get_cycle_signals_impl(signals: list[dict]) -> list[CycleSignal]:
    return [
        CycleSignal(
            symbol=s["symbol"],
            name=s.get("name", s["symbol"]),
            signal_type=s["signal_type"],  # "breakout" or "parabolic"
            confidence=s.get("confidence", "medium"),
            details={k: v for k, v in s.items()
                     if k not in ("symbol", "name", "signal_type", "confidence")},
        )
        for s in signals
    ]


@mcp.tool()
def get_cycle_signals(market: Optional[str] = "all") -> str:
    """获取周期突破和抛物线加速信号。

    Args:
        market: "us" / "cn" / "all"
    """
    try:
        config = _load_config()
        strength_df, raw_df = _ensure_data(market)
        if strength_df.empty:
            return json.dumps([])

        from market_analyst.processors.cycle_analyzer import CycleAnalyzer
        from market_analyst.processors.signal_generator import SignalGenerator

        cycle = CycleAnalyzer(config)
        strength_df = cycle.analyze(raw_df, strength_df)
        gen = SignalGenerator(config)
        signals = gen.generate(strength_df, raw_df)

        if market and market != "all":
            # Filter by market using strength_df symbol lookup
            market_symbols = set(strength_df[strength_df["market"] == market]["symbol"])
            signals = [s for s in signals if s["symbol"] in market_symbols]

        results = _get_cycle_signals_impl(signals)
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"get_cycle_signals error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — expect pass**
```

- [ ] **Step 2-5: TDD cycle + commit**

```bash
git commit -m "feat: add get_cycle_signals MCP tool"
```

---

## Task 4: Individual Stock Collector

### Task 4.1: `StockCollector` for on-demand individual stock data

**Files:**
- Create: `market-analyst/market_analyst/collectors/stock_collector.py`
- Create: `market-analyst/tests/test_stock_collector.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_stock_collector.py
"""Tests for individual stock data collector."""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from market_analyst.collectors.stock_collector import StockCollector


class TestStockCollector:
    def test_us_stock_returns_dataframe(self):
        """Test with mock yfinance data."""
        mock_hist = pd.DataFrame({
            "Open": [150.0, 151.0],
            "High": [152.0, 153.0],
            "Low": [149.0, 150.0],
            "Close": [151.0, 152.0],
            "Volume": [1000000, 1100000],
        }, index=pd.to_datetime(["2026-03-27", "2026-03-28"]))

        with patch("market_analyst.collectors.stock_collector.yf") as mock_yf:
            ticker = MagicMock()
            ticker.history.return_value = mock_hist
            ticker.info = {"shortName": "Apple Inc."}
            mock_yf.Ticker.return_value = ticker

            collector = StockCollector()
            df = collector.collect_single("AAPL", market="us", lookback_days=5)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert "symbol" in df.columns
            assert "close" in df.columns
            assert df.iloc[0]["symbol"] == "AAPL"
            assert df.iloc[0]["market"] == "us"

    def test_cn_stock_returns_dataframe(self):
        """Test with mock akshare data."""
        mock_data = pd.DataFrame({
            "日期": ["2026-03-27", "2026-03-28"],
            "开盘": [10.0, 10.1],
            "最高": [10.5, 10.6],
            "最低": [9.8, 9.9],
            "收盘": [10.2, 10.3],
            "成交量": [500000, 600000],
        })

        with patch("market_analyst.collectors.stock_collector.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = mock_data

            collector = StockCollector()
            df = collector.collect_single("600519", market="cn", lookback_days=5)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert df.iloc[0]["symbol"] == "600519"
            assert df.iloc[0]["market"] == "cn"

    def test_invalid_symbol_returns_empty(self):
        with patch("market_analyst.collectors.stock_collector.yf") as mock_yf:
            ticker = MagicMock()
            ticker.history.return_value = pd.DataFrame()
            ticker.info = {}
            mock_yf.Ticker.return_value = ticker

            collector = StockCollector()
            df = collector.collect_single("ZZZZZ", market="us")
            assert df.empty
```

- [ ] **Step 2: Run — fail**
- [ ] **Step 3: Implement**

```python
# market_analyst/collectors/stock_collector.py
"""On-demand individual stock data collector."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import akshare as ak
except ImportError:
    ak = None


class StockCollector:
    """Collects OHLCV data for individual stocks on demand."""

    def collect_single(
        self,
        symbol: str,
        market: str = "us",
        lookback_days: int = 60,
    ) -> pd.DataFrame:
        """Fetch OHLCV for a single stock.

        Args:
            symbol: Stock ticker (e.g. "AAPL", "600519")
            market: "us" or "cn"
            lookback_days: Number of trading days to fetch

        Returns:
            DataFrame with columns: symbol, name, sector, market, date, open, high, low, close, volume
        """
        try:
            if market == "cn":
                return self._fetch_cn(symbol, lookback_days)
            else:
                return self._fetch_us(symbol, lookback_days)
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")
            return pd.DataFrame()

    def _fetch_us(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        if yf is None:
            logger.error("yfinance not installed")
            return pd.DataFrame()

        ticker = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=int(lookback_days * 1.5))
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if hist.empty:
            return pd.DataFrame()

        name = ticker.info.get("shortName", symbol)
        sector = ticker.info.get("sector", "个股")

        df = pd.DataFrame({
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "market": "us",
            "date": hist.index.strftime("%Y-%m-%d"),
            "open": hist["Open"].values,
            "high": hist["High"].values,
            "low": hist["Low"].values,
            "close": hist["Close"].values,
            "volume": hist["Volume"].values,
        })
        return df.tail(lookback_days)

    def _fetch_cn(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        if ak is None:
            logger.error("akshare not installed")
            return pd.DataFrame()

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime("%Y%m%d")

        raw = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start, end_date=end, adjust="qfq",
        )
        if raw.empty:
            return pd.DataFrame()

        df = pd.DataFrame({
            "symbol": symbol,
            "name": symbol,  # akshare doesn't always return name
            "sector": "个股",
            "market": "cn",
            "date": pd.to_datetime(raw["日期"]).dt.strftime("%Y-%m-%d"),
            "open": raw["开盘"].values,
            "high": raw["最高"].values,
            "low": raw["最低"].values,
            "close": raw["收盘"].values,
            "volume": raw["成交量"].values,
        })
        return df.tail(lookback_days)
```

- [ ] **Step 4: Run — pass**
- [ ] **Step 5: Commit**

```bash
git add market_analyst/collectors/stock_collector.py tests/test_stock_collector.py
git commit -m "feat: add StockCollector for individual stock data"
```

---

## Task 5: Stock Diagnostor

### Task 5.1: Multi-dimensional stock scoring processor

**Files:**
- Create: `market-analyst/market_analyst/processors/stock_diagnostor.py`
- Create: `market-analyst/tests/test_stock_diagnostor.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_stock_diagnostor.py
"""Tests for stock diagnosis processor."""
import pytest
import pandas as pd
import numpy as np

from market_analyst.processors.stock_diagnostor import StockDiagnostor


@pytest.fixture
def sample_stock_df():
    """60 days of realistic OHLCV for one stock."""
    np.random.seed(42)
    dates = pd.bdate_range(end="2026-03-28", periods=60)
    base = 150.0
    closes = base + np.cumsum(np.random.randn(60) * 1.5)
    closes = np.maximum(closes, 50)  # floor

    return pd.DataFrame({
        "symbol": "AAPL",
        "name": "Apple",
        "market": "us",
        "sector": "Technology",
        "date": dates.strftime("%Y-%m-%d"),
        "open": closes - np.random.rand(60) * 0.5,
        "high": closes + np.random.rand(60) * 2,
        "low": closes - np.random.rand(60) * 2,
        "close": closes,
        "volume": np.random.randint(500000, 2000000, 60).astype(float),
    })


class TestStockDiagnostor:
    def test_diagnose_returns_all_dimensions(self, sample_stock_df):
        diag = StockDiagnostor()
        result = diag.diagnose(sample_stock_df)
        assert "trend" in result
        assert "momentum" in result
        assert "sentiment" in result
        assert "volatility" in result
        # flow may be None without TV data
        for key in ["trend", "momentum", "sentiment", "volatility"]:
            assert 0 <= result[key] <= 100

    def test_rating_in_range(self, sample_stock_df):
        diag = StockDiagnostor()
        result = diag.diagnose(sample_stock_df)
        assert 1 <= result["rating"] <= 5

    def test_empty_df_returns_none(self):
        diag = StockDiagnostor()
        result = diag.diagnose(pd.DataFrame())
        assert result is None

    def test_insufficient_data(self):
        df = pd.DataFrame({
            "symbol": ["X"], "close": [100.0],
            "high": [101.0], "low": [99.0], "volume": [1000.0],
            "date": ["2026-03-28"],
        })
        diag = StockDiagnostor()
        result = diag.diagnose(df)
        assert result is None  # need >= 14 days for RSI
```

- [ ] **Step 2: Run — fail**
- [ ] **Step 3: Implement**

```python
# market_analyst/processors/stock_diagnostor.py
"""Multi-dimensional stock scoring for retail investor diagnosis."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


class StockDiagnostor:
    """Computes 5-dimension scores (0-100) and 1-5 star rating."""

    MIN_DAYS = 14  # Minimum data points for RSI calculation

    def diagnose(self, df: pd.DataFrame) -> dict | None:
        """Score a single stock across multiple dimensions.

        Args:
            df: OHLCV DataFrame for one stock, sorted by date.

        Returns:
            Dict with keys: trend, momentum, sentiment, volatility, flow (nullable),
            rating (1-5), available_dimensions.
            Returns None if insufficient data.
        """
        if df.empty or len(df) < self.MIN_DAYS:
            return None

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float) if "high" in df.columns else closes
        lows = df["low"].values.astype(float) if "low" in df.columns else closes
        volumes = df["volume"].values.astype(float) if "volume" in df.columns else None

        trend = self._score_trend(closes)
        momentum = self._score_momentum(closes)
        sentiment = self._score_sentiment(closes)
        volatility = self._score_volatility(closes, highs, lows)
        flow = self._score_flow(closes, highs, lows, volumes) if volumes is not None else None

        available = ["trend", "momentum", "sentiment", "volatility"]
        scores = [trend, momentum, sentiment, volatility]
        if flow is not None:
            available.append("flow")
            scores.append(flow)

        avg = np.mean(scores)
        rating = max(1, min(5, int(round(avg / 20))))

        return {
            "trend": round(float(trend), 1),
            "momentum": round(float(momentum), 1),
            "sentiment": round(float(sentiment), 1),
            "volatility": round(float(volatility), 1),
            "flow": round(float(flow), 1) if flow is not None else None,
            "rating": rating,
            "available_dimensions": available,
        }

    def _score_trend(self, closes: np.ndarray) -> float:
        """Trend score: SMA position + direction. 100 = strong uptrend."""
        sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
        sma60 = np.mean(closes[-60:]) if len(closes) >= 60 else np.mean(closes)
        current = closes[-1]

        score = 50.0
        # Price vs SMA20: +/- 25
        if sma20 > 0:
            pct_above_20 = (current - sma20) / sma20
            score += np.clip(pct_above_20 * 500, -25, 25)  # 5% above = +25

        # SMA20 vs SMA60: +/- 25
        if sma60 > 0:
            sma_spread = (sma20 - sma60) / sma60
            score += np.clip(sma_spread * 500, -25, 25)

        return np.clip(score, 0, 100)

    def _score_momentum(self, closes: np.ndarray) -> float:
        """Momentum score: ROC percentile. 100 = strong acceleration."""
        if len(closes) < 5:
            return 50.0

        roc_5d = (closes[-1] / closes[-5] - 1) * 100
        roc_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else roc_5d

        # Map 5d ROC [-10%, +10%] → [0, 100]
        score_5d = np.clip((roc_5d + 10) / 20 * 100, 0, 100)
        # Map 20d ROC [-20%, +20%] → [0, 100]
        score_20d = np.clip((roc_20d + 20) / 40 * 100, 0, 100)

        return float(score_5d * 0.6 + score_20d * 0.4)

    def _score_sentiment(self, closes: np.ndarray) -> float:
        """Sentiment score based on RSI. 50 = neutral, 100 = overbought (bullish momentum)."""
        rsi = self._calc_rsi(closes, 14)
        # RSI naturally ranges 0-100, map to our score
        return float(rsi)

    def _score_volatility(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        """Volatility score. 100 = low vol (stable), 0 = high vol (risky)."""
        if len(closes) < 5:
            return 50.0

        # ATR-based
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        atr_pct = atr / closes[-1] * 100 if closes[-1] > 0 else 0

        # Map ATR% [0%, 5%] → [100, 0] (lower vol = higher score)
        score = np.clip((5 - atr_pct) / 5 * 100, 0, 100)
        return float(score)

    def _score_flow(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray) -> float:
        """Money flow score using CMF-like calculation. 100 = strong inflow."""
        if len(closes) < 5 or volumes is None:
            return 50.0

        hl_range = highs - lows
        hl_range = np.where(hl_range == 0, 1e-10, hl_range)
        mf_multiplier = ((closes - lows) - (highs - closes)) / hl_range
        mf_volume = mf_multiplier * volumes

        cmf_20 = np.sum(mf_volume[-20:]) / np.sum(volumes[-20:]) if len(closes) >= 20 else 0

        # Map CMF [-0.5, +0.5] → [0, 100]
        score = np.clip((cmf_20 + 0.5) * 100, 0, 100)
        return float(score)

    @staticmethod
    def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - 100 / (1 + rs))
```

- [ ] **Step 4: Run — pass**
- [ ] **Step 5: Commit**

```bash
git add market_analyst/processors/stock_diagnostor.py tests/test_stock_diagnostor.py
git commit -m "feat: add StockDiagnostor multi-dimensional scoring"
```

---

## Task 6: `diagnose_stock` MCP Tool

### Task 6.1: Wire StockCollector + StockDiagnostor into MCP tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import StockDiagnosis


class TestDiagnoseStock:
    def test_diagnose_with_mock_data(self):
        from market_analyst.mcp_server import _diagnose_stock_impl
        np.random.seed(42)
        dates = pd.bdate_range(end="2026-03-28", periods=60)
        closes = 150.0 + np.cumsum(np.random.randn(60) * 1.5)
        df = pd.DataFrame({
            "symbol": "AAPL", "name": "Apple", "market": "us",
            "sector": "Tech", "date": dates.strftime("%Y-%m-%d"),
            "open": closes, "high": closes + 1, "low": closes - 1,
            "close": closes, "volume": np.full(60, 1e6),
        })
        result = _diagnose_stock_impl(df, "AAPL", "Apple", "us")
        assert isinstance(result, StockDiagnosis)
        assert result.symbol == "AAPL"
        assert 1 <= result.rating <= 5
        assert len(result.available_dimensions) >= 4

    def test_diagnose_no_data(self):
        from market_analyst.mcp_server import _diagnose_stock_impl
        result = _diagnose_stock_impl(pd.DataFrame(), "ZZZZZ", "Unknown", "us")
        assert isinstance(result, ToolError)
```

- [ ] **Step 2: Run — fail**
- [ ] **Step 3: Implement**

```python
def _diagnose_stock_impl(
    stock_df: pd.DataFrame,
    symbol: str,
    name: str,
    market: str,
) -> StockDiagnosis | ToolError:
    if stock_df.empty:
        return ToolError(error="data_unavailable", message=f"No data for {symbol}")

    from market_analyst.processors.stock_diagnostor import StockDiagnostor
    diag = StockDiagnostor()
    result = diag.diagnose(stock_df)

    if result is None:
        return ToolError(error="insufficient_data", message=f"Not enough data for {symbol}")

    return StockDiagnosis(
        symbol=symbol,
        name=name,
        market=market,
        scores={k: result[k] for k in ["trend", "momentum", "sentiment", "volatility", "flow"]},
        rating=result["rating"],
        available_dimensions=result["available_dimensions"],
    )


@mcp.tool()
def diagnose_stock(symbol: str, market: Optional[str] = None) -> str:
    """个股/ETF多维度诊断：趋势、动量、情绪、波动、资金流五维评分 + 综合星级。

    Args:
        symbol: 股票代码，如 "AAPL", "600519", "SPY"
        market: "us" 或 "cn"，不传则自动推断
    """
    try:
        # Normalize symbol: strip exchange suffix (.SZ, .SS, .SH)
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            # Pure digits = A-share; digits with leading 6/0/3 = A-share
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol  # use cleaned version for data fetching

        # First check if it's in our ETF universe
        strength_df, raw_df = _ensure_data()
        etf_data = raw_df[raw_df["symbol"] == symbol] if not raw_df.empty else pd.DataFrame()

        if not etf_data.empty:
            name = etf_data.iloc[0].get("name", symbol)
            result = _diagnose_stock_impl(etf_data, symbol, name, market)
        else:
            # Fetch individual stock data
            from market_analyst.collectors.stock_collector import StockCollector
            from market_analyst.utils.cache import DataCache
            config = _load_config()
            cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

            stock_df = cache.get_or_fetch(
                f"stock_{symbol}",
                lambda: StockCollector().collect_single(symbol, market=market),
                max_age_hours=4,
            )
            name = stock_df.iloc[0]["name"] if not stock_df.empty else symbol
            result = _diagnose_stock_impl(stock_df, symbol, name, market)

        return result.model_dump_json()
    except Exception as e:
        logger.error(f"diagnose_stock error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add diagnose_stock MCP tool"
```

---

## Task 7: Commentary + Momentum + News Tools

### Task 7.1: `get_market_commentary` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import CommentaryData


class TestGetMarketCommentary:
    def test_commentary_structure(self):
        from market_analyst.mcp_server import _get_commentary_impl
        strength_df = pd.DataFrame([
            {"symbol": "XLK", "name": "科技", "market": "us", "roc_5d": 4.0,
             "composite_score": 90, "tier": "T1", "market_temp_5d": 1.5,
             "fear_score": 30, "fear_label": "贪婪"},
            {"symbol": "XLE", "name": "能源", "market": "us", "roc_5d": -3.0,
             "composite_score": 15, "tier": "T4", "market_temp_5d": 1.5,
             "fear_score": 70, "fear_label": "恐慌"},
            {"symbol": "^VIX", "name": "VIX恐慌指数", "market": "global", "roc_5d": 8.5,
             "composite_score": 50, "tier": "T2", "market_temp_5d": 0,
             "fear_score": 60, "fear_label": "中性"},
        ])
        result = _get_commentary_impl(strength_df, anomalies=[], commentary_type="closing")
        assert isinstance(result, CommentaryData)
        assert result.type == "closing"
        assert len(result.top_movers) > 0
        assert len(result.worst_movers) > 0
        assert "VIX" in result.key_indices_change  # key indices populated
```

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement**

```python
def _get_commentary_impl(
    strength_df: pd.DataFrame,
    anomalies: list[dict],
    commentary_type: str = "closing",
) -> CommentaryData | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data")

    # Top/worst movers by 5d ROC
    sorted_df = strength_df.sort_values("roc_5d", ascending=False)
    top = sorted_df.head(5)
    worst = sorted_df.tail(5)

    top_movers = [
        {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
        for _, r in top.iterrows()
    ]
    worst_movers = [
        {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
        for _, r in worst.iterrows()
    ]

    # Market temperatures per market
    market_temp = {}
    for mkt in strength_df["market"].unique():
        mkt_df = strength_df[strength_df["market"] == mkt]
        if "market_temp_5d" in mkt_df.columns and not mkt_df.empty:
            market_temp[mkt] = round(float(mkt_df["market_temp_5d"].iloc[0]), 2)

    # Anomaly summaries (high severity only)
    anomaly_summaries = [
        a.get("description", "") for a in anomalies
        if a.get("severity") == "high"
    ][:5]

    # Fear score average
    avg_fear = float(strength_df["fear_score"].mean()) if "fear_score" in strength_df.columns else None

    # Key indices changes (reuse _extract_key_indices + compute ROC)
    key_indices_change = {}
    key_symbols = {"^VIX": "VIX", "DX-Y.NYB": "DXY", "GC=F": "黄金", "CL=F": "原油"}
    for sym, label in key_symbols.items():
        row = strength_df[strength_df["symbol"] == sym]
        if not row.empty and "roc_5d" in row.columns:
            key_indices_change[label] = round(float(row.iloc[0]["roc_5d"]), 2)

    return CommentaryData(
        type=commentary_type,
        market_temp=market_temp,
        top_movers=top_movers,
        worst_movers=worst_movers,
        anomalies_summary=anomaly_summaries,
        key_indices_change=key_indices_change,
        fear_score=round(avg_fear, 1) if avg_fear else None,
        fear_label=_fear_label(avg_fear),
    )


@mcp.tool()
def get_market_commentary(type: str = "closing") -> str:
    """获取结构化市场数据摘要，供 agent 合成极简解盘文本。

    返回结构化数据（非文本），包含涨跌统计、强弱板块、异常信号等。
    Agent 根据 SKILL.md 话术模板合成 300 字以内的解盘。

    Args:
        type: "morning" / "midday" / "closing"
    """
    try:
        config = _load_config()
        strength_df, raw_df = _ensure_data()
        if strength_df.empty:
            return ToolError(error="data_unavailable", message="No data").model_dump_json()

        # Run anomaly detection for commentary context
        from market_analyst.processors.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(config)
        anomalies = detector.detect(strength_df, raw_df)

        result = _get_commentary_impl(strength_df, anomalies, commentary_type=type)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_market_commentary error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — expect pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add get_market_commentary MCP tool"
```

### Task 7.2: `scan_momentum` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import MomentumItem


class TestScanMomentum:
    def test_momentum_returns_items(self):
        from market_analyst.mcp_server import _scan_momentum_impl
        # MomentumScanner.scan() returns keys: "us_momentum", "cn_momentum"
        raw_data = {
            "us_momentum": [
                {"symbol": "NVDA", "name": "NVIDIA", "perf_5d": 18.5,
                 "perf_20d": 35.0, "trigger": "both", "avg_volume": 5e7},
            ],
            "cn_momentum": [],
        }
        result = _scan_momentum_impl(raw_data, market="us")
        assert len(result) == 1
        assert isinstance(result[0], MomentumItem)
        assert result[0].symbol == "NVDA"
        assert result[0].trigger == "both"

    def test_momentum_empty(self):
        from market_analyst.mcp_server import _scan_momentum_impl
        result = _scan_momentum_impl({}, market="us")
        assert result == []
```

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement**

```python
def _scan_momentum_impl(
    momentum_data: dict,
    market: str = "us",
) -> list[MomentumItem]:
    # MomentumScanner returns keys: "us_momentum", "cn_momentum"
    items = momentum_data.get(f"{market}_momentum", [])
    return [
        MomentumItem(
            symbol=i["symbol"], name=i.get("name", i["symbol"]),
            market=market,
            perf_5d=i.get("perf_5d"), perf_20d=i.get("perf_20d"),
            trigger=i.get("trigger"), avg_volume=i.get("avg_volume"),
        )
        for i in items
    ]


@mcp.tool()
def scan_momentum(market: Optional[str] = "us", min_return_5d: Optional[float] = None) -> str:
    """扫描多日动量飙升的个股。

    Args:
        market: "us" 或 "cn"
        min_return_5d: 最小 5 日涨幅过滤 (%)
    """
    try:
        config = _load_config()
        from market_analyst.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner(config)
        raw_data = scanner.scan()
        results = _scan_momentum_impl(raw_data, market=market or "us")
        if min_return_5d is not None:
            results = [r for r in results if r.perf_5d and r.perf_5d >= min_return_5d]
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"scan_momentum error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — expect pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add scan_momentum MCP tool"
```

### Task 7.3: `search_market_news` tool

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import NewsItem


class TestSearchMarketNews:
    def test_news_returns_items(self):
        from market_analyst.mcp_server import _search_news_impl
        # WebSearcher returns "snippet" field, not "content"
        raw_results = [
            {"title": "Fed holds rates", "url": "https://example.com/1",
             "snippet": "The Federal Reserve held rates steady..."},
            {"title": "NVIDIA earnings beat", "url": "https://example.com/2",
             "snippet": "NVIDIA reported Q4 earnings above expectations..."},
        ]
        result = _search_news_impl(raw_results)
        assert len(result) == 2
        assert isinstance(result[0], NewsItem)
        assert result[0].title == "Fed holds rates"
        assert result[0].summary is not None

    def test_news_empty(self):
        from market_analyst.mcp_server import _search_news_impl
        result = _search_news_impl([])
        assert result == []
```

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement**

```python
def _search_news_impl(raw_results: list[dict]) -> list[NewsItem]:
    items = []
    for r in raw_results:
        # WebSearcher returns "snippet" field
        snippet = r.get("snippet", "")
        summary = snippet[:200] + "..." if len(snippet) > 200 else snippet
        items.append(NewsItem(
            title=r.get("title", ""),
            url=r.get("url", ""),
            summary=summary or None,
        ))
    return items


@mcp.tool()
def search_market_news(query: str, max_results: Optional[int] = 5) -> str:
    """搜索市场新闻并生成通俗摘要。优先使用金融相关源。

    DeerFlow 已有内置 Tavily 工具用于通用搜索。此工具增加了金融领域过滤和中文摘要。

    Args:
        query: 搜索关键词，如 "半导体 行情" 或 "NVIDIA earnings"
        max_results: 最大返回条数
    """
    try:
        config = _load_config()
        from market_analyst.utils.web_search import WebSearcher
        searcher = WebSearcher(config)
        # Use the internal search methods
        raw = searcher._search_tavily(query) if config.get("web_search", {}).get("provider") == "tavily" \
            else searcher._search_ddg(query)
        raw = raw[:max_results] if max_results else raw
        results = _search_news_impl(raw)
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"search_market_news error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — expect pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add search_market_news MCP tool"
```

---

## Task 8: `run_full_report` Tool

### Task 8.1: Async full-report trigger

**Files:**
- Modify: `market-analyst/market_analyst/mcp_server.py`
- Modify: `market-analyst/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

```python
from market_analyst.schemas import ReportResult


class TestRunFullReport:
    def test_report_returns_result(self):
        from market_analyst.mcp_server import _run_full_report_impl
        # Mock main.run() — the real entry point in main.py
        with patch("market_analyst.mcp_server._import_and_run_pipeline") as mock_run:
            mock_run.return_value = "/path/to/report.md"
            result = _run_full_report_impl(skip_ai=True)
            assert isinstance(result, ReportResult)
            assert result.status == "completed"
            assert result.filepath == "/path/to/report.md"

    def test_report_failure(self):
        from market_analyst.mcp_server import _run_full_report_impl
        with patch("market_analyst.mcp_server._import_and_run_pipeline") as mock_run:
            mock_run.return_value = None
            result = _run_full_report_impl(skip_ai=True)
            assert isinstance(result, ReportResult)
            assert result.status == "failed"
```

- [ ] **Step 2: Run — expect fail**
- [ ] **Step 3: Implement**

```python
def _import_and_run_pipeline(skip_ai: bool = False, skip_search: bool = False) -> str | None:
    """Wrapper around main.run() for mocking in tests."""
    from market_analyst.main import run  # actual entry point: main.py:run()
    return run(skip_ai=skip_ai, skip_search=skip_search)


def _run_full_report_impl(skip_ai: bool = False) -> ReportResult:
    """Synchronous full report generation. Expect 1-5 min execution time."""
    try:
        filepath = _import_and_run_pipeline(skip_ai=skip_ai)
        if filepath:
            return ReportResult(status="completed", filepath=str(filepath))
        else:
            return ReportResult(status="failed", message="Pipeline returned no result")
    except Exception as e:
        return ReportResult(status="failed", message=str(e))


@mcp.tool()
def run_full_report(market: Optional[str] = "all", skip_ai: Optional[bool] = False) -> str:
    """触发全量市场分析报告。同步执行，耗时约 1-5 分钟。建议通过外部调度器定时触发。

    Args:
        market: "us" / "cn" / "all"
        skip_ai: 跳过 AI 分析，仅生成数据报告
    """
    try:
        result = _run_full_report_impl(skip_ai=skip_ai)
        return result.model_dump_json()
    except Exception as e:
        return ReportResult(status="failed", message=str(e)).model_dump_json()
```

- [ ] **Step 4: Run — expect pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add run_full_report MCP tool (synchronous)"
```

---

## Task 9: DeerFlow Skill

### Task 9.1: Create `SKILL.md` for retail investor interaction

**Files:**
- Create: `skills/public/market-analyst/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: market-analyst
description: |
  市场分析助手：板块强弱排名、个股诊断、恐慌评分、异常检测、极简解盘。
  当用户提到以下内容时触发：
  - 查看/分析市场、大盘、板块
  - 诊断/分析某只股票（输入股票代码，如 AAPL、600519、000001）
  - 恐慌指数、情绪、抄底信号
  - 今日解盘、早评、午评、收评
  - 异动、异常、突破信号
  - 强势/弱势板块、轮动
  - 动量排行、趋势扫描
---

# 市场分析助手

## 角色定位
你是一位面向散户的市场分析助手。你的回答必须：
- **通俗易懂**：避免专业术语，用大白话解释
- **简短精炼**：核心信息控制在 300 字以内
- **有数据支撑**：所有结论附带具体数字
- **附免责声明**：每次回复末尾附上免责声明

## 工具使用指南

### 用户问市场/大盘
1. 调用 `market-analyst_get_market_overview`
2. 如需详细板块排名，追加 `market-analyst_get_sector_strength`
3. 用通俗语言总结：今天市场整体如何、哪些板块强/弱、情绪偏贪婪还是恐慌

### 用户输入股票代码（如 AAPL、600519、000001.SZ）
注意：当前只支持代码输入，不支持名称搜索。如用户输入名称（如"苹果"），请提示他们输入代码。
1. 调用 `market-analyst_diagnose_stock(symbol=代码)`
2. 用评分卡格式展示五维得分和星级
3. 对每个维度用一句话解释含义

输出格式示例：
```
【AAPL 诊断报告】 ★★★★☆ (4/5星)

📊 趋势: 72分 — 价格在均线上方，中期趋势向上
🚀 动量: 65分 — 近期涨势温和，没有过热
💭 情绪: 55分 — RSI 中性偏强
📉 波动: 78分 — 波动较小，走势稳健
💰 资金: 60分 — 资金流入温和

综合来看：该股处于稳健上升通道，适合持有观察。
```

### 用户问恐慌/抄底
1. 调用 `market-analyst_get_fear_score`
2. 解释恐慌评分和抄底信号的含义
3. 说明当前处于什么阶段

### 用户问解盘
1. 调用 `market-analyst_get_market_commentary(type=时段)`
   - 上午问 → type="morning"
   - 中午问 → type="midday"
   - 下午/晚上问 → type="closing"
2. 用结构化数据合成 300 字以内的解盘文本

### 用户问异常/异动
1. 调用 `market-analyst_get_anomalies`
2. 挑选 severity=high 的信号重点解读
3. 用"XX出现异常，可能是因为YY"的句式

## 免责声明模板
> 以上内容仅供参考，不构成任何投资建议。市场有风险，投资需谨慎。数据来源于公开市场信息，可能存在延迟。

## 注意事项
- 永远不要直接说"买入"或"卖出"
- 用评分和星级让用户自己判断
- 如果数据返回 stale=true，提醒用户"数据可能有延迟"
- 如果某个维度为 null，说明"该维度暂无数据"
```

- [ ] **Step 2: Verify skill is discoverable**

```bash
cd "E:/字节跳动框架/deer-flow-main"
ls skills/public/market-analyst/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add skills/public/market-analyst/SKILL.md
git commit -m "feat: add market-analyst DeerFlow skill for retail investors"
```

---

## Task 10: Root-Level Integration

### Task 10.1: Update Makefile for market-analyst install

**Files:**
- Modify: `E:/字节跳动框架/deer-flow-main/Makefile`

- [ ] **Step 1: Read current Makefile install target**
- [ ] **Step 2: Add market-analyst install step to existing `install` target**

The root Makefile has a single `install` target. Append market-analyst setup at the end:

```makefile
# Add after the existing install steps:
install-market-analyst:
	@echo "Installing market-analyst dependencies..."
	cd market-analyst && python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"
```

Then modify the existing `install` target to include it:
```makefile
install: install-market-analyst
	@echo "Installing backend dependencies..."
	# ... existing backend/frontend install steps remain unchanged ...
```

Note: On Windows the Makefile uses `SHELL := cmd.exe`. Use backslash paths and `&&` chaining compatible with cmd.

- [ ] **Step 3: Test the install**

```bash
cd "E:/字节跳动框架/deer-flow-main"
make install-market-analyst
```

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "chore: add market-analyst to root Makefile install"
```

---

## Task 11: End-to-End Integration Test

### Task 11.1: Verify the full chain works

- [ ] **Step 1: Start DeerFlow dev**

```bash
cd "E:/字节跳动框架/deer-flow-main"
make dev
```

- [ ] **Step 2: Test in Web UI — market overview**

Open browser, go to DeerFlow chat. Ask: "今天市场怎么样"

Expected: Agent calls `market-analyst_get_market_overview`, returns formatted response.

- [ ] **Step 3: Test — stock diagnosis**

Ask: "帮我看看 AAPL"

Expected: Agent calls `market-analyst_diagnose_stock(symbol="AAPL")`, returns 5-dimension scorecard.

- [ ] **Step 4: Test — fear score**

Ask: "现在市场恐慌吗"

Expected: Agent calls `market-analyst_get_fear_score`, returns fear/bottom scores.

- [ ] **Step 5: Test — anomalies**

Ask: "今天有什么异动"

Expected: Agent calls `market-analyst_get_anomalies`, returns highlighted signals.

- [ ] **Step 6: Document any issues found**

If any test fails, create a follow-up fix task.

- [ ] **Step 7: Final commit if any fixes needed**

```bash
git commit -m "fix: e2e integration fixes for market-analyst MCP"
```

---

## Summary

| Task | Description | Est. Steps |
|------|-------------|------------|
| 0 | Package restructure + pyproject.toml | 10 |
| 1 | Pydantic output schemas | 5 |
| 2 | MCP server skeleton + POC (get_fear_score) + DeerFlow registration | 8 |
| 3 | Core tools: overview, strength, anomalies, cycle | 16 |
| 4 | StockCollector (individual stocks) | 5 |
| 5 | StockDiagnostor (multi-dimensional scoring) | 5 |
| 6 | diagnose_stock MCP tool | 5 |
| 7 | Commentary + momentum + news tools | 15 |
| 8 | run_full_report tool | 4 |
| 9 | SKILL.md for retail investors | 3 |
| 10 | Makefile integration | 4 |
| 11 | E2E integration test | 7 |
| **Total** | | **~87 steps** |

## Deferred Items (Future Tasks)

- **Cron scheduling**: Phase 4 定时报告需要 APScheduler 或系统 cron 集成，不在本次 plan 范围内
- **`run_full_report` 异步模式**: 当前为同步执行，未来可加 job_id + 后台线程实现异步
- **Stale data fallback**: `_ensure_data()` 缓存未命中时的 `stale=True` 标记需要在后续迭代中完善
- **Cross-platform venv path**: extensions_config.json 中的 `.venv/Scripts/python` 是 Windows 路径，Linux/Mac 需改为 `.venv/bin/python`
- **Docker 场景**: 独立 venv 方案仅适用于宿主机开发，Docker 部署需在 Dockerfile 中处理 market-analyst 依赖安装
- **股票名称搜索**: 当前 diagnose_stock 只支持 symbol，未来可加名称→代码的模糊匹配
- **金融新闻过滤**: search_market_news 当前只做文本截断摘要，未来需加金融领域关键词过滤和通俗化改写
