# Momentum Scanner + Portfolio Advisor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add market-wide multi-day momentum scanning and portfolio-based action recommendations to the market-analyst pipeline.

**Architecture:** Two independent modules inserted into the existing `main.py` pipeline. `MomentumScanner` scans TradingView for 5d/1M momentum outliers (Step 5.6). `PortfolioAdvisor` reads `portfolio.yaml`, computes EMA/RSI metrics via yfinance, then feeds structured data to AI for natural-language recommendations (Step 5.7). Both modules output to existing Obsidian MD and JSON exporters.

**Tech Stack:** Python 3.10+, tvscreener (TradingView), yfinance, pandas, existing AI provider (Gemini/Claude via MarketAnalyzer pattern)

**Spec:** `docs/2026-03-11-momentum-scanner-portfolio-advisor-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/processors/momentum_scanner.py` | Create | TradingView multi-day momentum scan for US + CN markets |
| `tests/test_momentum_scanner.py` | Create | Unit tests for MomentumScanner |
| `config/config.yaml` | Modify | Add `momentum_scan` config section |
| `main.py` | Modify (L244-251) | Insert Step 5.6 momentum scan call |
| `src/exporters/obsidian_exporter.py` | Modify | Add momentum surge section + portfolio advice section |
| `src/exporters/json_exporter.py` | Modify | Add `momentum_surge` + `portfolio_advice` fields |
| `config/portfolio.yaml` | Create | User portfolio/watchlist configuration (template) |
| `src/processors/portfolio_advisor.py` | Create | Portfolio metrics calculation + AI advice generation |
| `tests/test_portfolio_advisor.py` | Create | Unit tests for PortfolioAdvisor |
| `main.py` | Modify (after Step 5.6) | Insert Step 5.7 portfolio advisor call |

---

## Chunk 1: Momentum Scanner (Module B)

### Task 1: Add momentum_scan config

**Files:**
- Modify: `config/config.yaml` (append at end)

- [ ] **Step 1: Add config section**

Append to `config/config.yaml`:

```yaml
momentum_scan:
  enabled: true
  us:
    min_market_cap: 3e9
    min_avg_volume: 300000
  cn:
    min_market_cap: 3e9
    min_avg_volume: 100000
  thresholds:
    perf_5d: 15
    perf_20d: 30
  max_results: 20
```

- [ ] **Step 2: Commit**

```bash
git add config/config.yaml
git commit -m "config: add momentum_scan section"
```

---

### Task 2: Write MomentumScanner tests

**Files:**
- Create: `tests/test_momentum_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for MomentumScanner."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd


@pytest.fixture
def default_config():
    return {
        "momentum_scan": {
            "enabled": True,
            "us": {"min_market_cap": 3e9, "min_avg_volume": 300000},
            "cn": {"min_market_cap": 3e9, "min_avg_volume": 100000},
            "thresholds": {"perf_5d": 15, "perf_20d": 30},
            "max_results": 20,
        }
    }


class TestMomentumScanner:
    def test_disabled_returns_empty(self):
        from src.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner({"momentum_scan": {"enabled": False}})
        result = scanner.scan()
        assert result == {"us_momentum": [], "cn_momentum": []}

    def test_scan_returns_correct_structure(self, default_config):
        from src.processors.momentum_scanner import MomentumScanner

        # Mock tvscreener to return a fake DataFrame
        mock_df = pd.DataFrame({
            "Symbol": ["NASDAQ:AAOI"],
            "Name": ["Applied Optoelectronics"],
            "Price": [110.55],
            "Change %": [7.9],
            "Perf 5d": [33.2],
            "Monthly Performance": [45.8],
            "Relative Volume": [3.2],
            "Relative Strength Index (14)": [72.0],
            "Chaikin Money Flow (20)": [0.25],
            "Market Capitalization": [7.2e9],
            "Sector": ["Electronic Technology"],
            "Industry": ["Fiber Optics"],
            "Average Volume (30 day)": [500000],
        })

        scanner = MomentumScanner(default_config)
        with patch.object(scanner, "_scan_market", return_value=[{
            "symbol": "AAOI",
            "name": "Applied Optoelectronics",
            "market": "us",
            "price": 110.55,
            "change_pct": 7.9,
            "perf_5d": 33.2,
            "perf_20d": 45.8,
            "trigger": "both",
            "rel_volume": 3.2,
            "rsi": 72.0,
            "cmf": 0.25,
            "market_cap_b": 7.2,
            "sector": "Electronic Technology",
            "industry": "Fiber Optics",
        }]):
            result = scanner.scan()

        assert "us_momentum" in result
        assert len(result["us_momentum"]) == 1
        item = result["us_momentum"][0]
        assert item["symbol"] == "AAOI"
        assert item["trigger"] in ("5d", "20d", "both")
        assert item["perf_5d"] > 15

    def test_trigger_classification(self, default_config):
        from src.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner(default_config)

        assert scanner._classify_trigger(20.0, 10.0) == "5d"
        assert scanner._classify_trigger(5.0, 35.0) == "20d"
        assert scanner._classify_trigger(20.0, 35.0) == "both"
        assert scanner._classify_trigger(5.0, 10.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/market-analyst && python -m pytest tests/test_momentum_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.processors.momentum_scanner'`

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_momentum_scanner.py
git commit -m "test: add momentum scanner tests (red)"
```

---

### Task 3: Implement MomentumScanner

**Files:**
- Create: `src/processors/momentum_scanner.py`

- [ ] **Step 1: Write implementation**

```python
"""Market-wide multi-day momentum scanner.

Scans US and CN markets via TradingView Screener for stocks with
strong multi-day momentum (5d >15% or monthly >30%), independent
of ETF tier rankings.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

try:
    from tvscreener import Market, StockField, StockScreener
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False


class MomentumScanner:
    """Scan for multi-day momentum surges across entire markets."""

    def __init__(self, config: dict = None):
        cfg = (config or {}).get("momentum_scan", {})
        self.enabled = cfg.get("enabled", True) and TV_AVAILABLE

        us_cfg = cfg.get("us", {})
        self.us_min_cap = us_cfg.get("min_market_cap", 3e9)
        self.us_min_avg_vol = us_cfg.get("min_avg_volume", 300000)

        cn_cfg = cfg.get("cn", {})
        self.cn_min_cap = cn_cfg.get("min_market_cap", 3e9)
        self.cn_min_avg_vol = cn_cfg.get("min_avg_volume", 100000)

        thresholds = cfg.get("thresholds", {})
        self.threshold_5d = thresholds.get("perf_5d", 15)
        self.threshold_20d = thresholds.get("perf_20d", 30)

        self.max_results = cfg.get("max_results", 20)

    def scan(self) -> dict:
        """Scan US and CN markets for momentum surges.

        Returns: {"us_momentum": [...], "cn_momentum": [...]}
        """
        if not self.enabled:
            logger.info("Momentum scan: disabled")
            return {"us_momentum": [], "cn_momentum": []}

        us = self._scan_market(
            Market.AMERICA, self.us_min_cap, self.us_min_avg_vol, "us"
        )
        cn = self._scan_market(
            Market.CHINA, self.cn_min_cap, self.cn_min_avg_vol, "cn"
        )

        logger.info(
            f"Momentum scan: {len(us)} US + {len(cn)} CN surges"
        )
        return {"us_momentum": us, "cn_momentum": cn}

    def _scan_market(
        self, tv_market, min_cap: float, min_avg_vol: float, market_label: str
    ) -> list[dict]:
        """Query TradingView for momentum stocks in one market."""
        try:
            # 5-day momentum scan
            results_5d = self._query_tv(
                tv_market, min_cap, min_avg_vol,
                StockField.PERF_5D, self.threshold_5d
            )
            # Monthly momentum scan
            results_1m = self._query_tv(
                tv_market, min_cap, min_avg_vol,
                StockField.MONTHLY_PERFORMANCE, self.threshold_20d
            )

            # Merge and deduplicate by symbol
            merged = {}
            for row in results_5d:
                sym = row["symbol"]
                row["_hit_5d"] = True
                merged[sym] = row

            for row in results_1m:
                sym = row["symbol"]
                if sym in merged:
                    merged[sym]["_hit_20d"] = True
                    # Update 20d value if available from this query
                    if row.get("perf_20d") and not merged[sym].get("perf_20d"):
                        merged[sym]["perf_20d"] = row["perf_20d"]
                else:
                    row["_hit_20d"] = True
                    merged[sym] = row

            # Classify triggers and build output
            output = []
            for sym, item in merged.items():
                perf_5d = item.get("perf_5d", 0) or 0
                perf_20d = item.get("perf_20d", 0) or 0
                trigger = self._classify_trigger(perf_5d, perf_20d)
                if trigger is None:
                    continue
                item["trigger"] = trigger
                item["market"] = market_label
                # Clean internal keys
                item.pop("_hit_5d", None)
                item.pop("_hit_20d", None)
                output.append(item)

            # Sort by 5d performance descending
            output.sort(key=lambda x: x.get("perf_5d", 0), reverse=True)
            return output[: self.max_results]

        except Exception as e:
            logger.warning(f"Momentum scan ({market_label}) failed: {e}")
            return []

    def _query_tv(
        self, tv_market, min_cap: float, min_avg_vol: float,
        perf_field, threshold: float
    ) -> list[dict]:
        """Execute a single TradingView screener query."""
        ss = StockScreener()
        ss.set_markets(tv_market)
        ss.set_range(0, 50)
        ss.select(
            StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
            StockField.PERF_5D, StockField.MONTHLY_PERFORMANCE,
            StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
            StockField.CHAIKIN_MONEY_FLOW_20,
            StockField.MARKET_CAPITALIZATION,
            StockField.SECTOR, StockField.INDUSTRY,
            StockField.AVERAGE_VOLUME_30_DAY,
        )
        ss.where(StockField.MARKET_CAPITALIZATION > min_cap)
        ss.where(StockField.AVERAGE_VOLUME_30_DAY > min_avg_vol)
        ss.where(perf_field > threshold)

        df = ss.get()
        if df.empty:
            return []

        # Filter out OTC
        df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]

        is_cn = (tv_market == Market.CHINA)
        results = []
        for _, r in df.iterrows():
            sym = str(r.get("Symbol", "")).split(":")[-1]
            cap = float(r.get("Market Capitalization", 0))
            cap_display = round(cap / 1e8, 1) if is_cn else round(cap / 1e9, 1)
            results.append({
                "symbol": sym,
                "name": r.get("Name", sym),
                "price": round(float(r.get("Price", 0)), 2),
                "change_pct": round(float(r.get("Change %", 0)), 2),
                "perf_5d": round(float(r.get("Perf 5d", 0)), 2),
                "perf_20d": round(float(r.get("Monthly Performance", 0)), 2),
                "rel_volume": round(float(r.get("Relative Volume", 0)), 2),
                "rsi": round(float(r.get("Relative Strength Index (14)", 0)), 1),
                "cmf": round(float(r.get("Chaikin Money Flow (20)", 0)), 3),
                "market_cap_b": cap_display,
                "market_cap_unit": "亿" if is_cn else "B",
                "sector": str(r.get("Sector", "")),
                "industry": str(r.get("Industry", "")),
            })
        return results

    def _classify_trigger(self, perf_5d: float, perf_20d: float) -> str | None:
        """Classify which threshold was triggered."""
        hit_5d = perf_5d >= self.threshold_5d
        hit_20d = perf_20d >= self.threshold_20d
        if hit_5d and hit_20d:
            return "both"
        if hit_5d:
            return "5d"
        if hit_20d:
            return "20d"
        return None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/market-analyst && python -m pytest tests/test_momentum_scanner.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/processors/momentum_scanner.py
git commit -m "feat: add MomentumScanner for market-wide multi-day momentum detection"
```

---

### Task 4: Integrate MomentumScanner into main.py

**Files:**
- Modify: `main.py` (after L250, Step 5.5 sector scan)

- [ ] **Step 1: Add Step 5.6 in main.py**

After the `stock_picks` block (L244-250), insert:

```python
    momentum_data: dict = {}
    if config.get("momentum_scan", {}).get("enabled", True):
        logger.info("Step 5.6: momentum scan...")
        from src.processors.momentum_scanner import MomentumScanner

        mom_scanner = MomentumScanner(config)
        momentum_data = mom_scanner.scan()
```

- [ ] **Step 2: Pass momentum_data to ObsidianExporter**

Modify the `exporter.export()` call (L254-262) to add `momentum_data=momentum_data`:

```python
    filepath = exporter.export(
        strength_df,
        anomalies,
        analysis_text,
        search_results,
        cycle_signals=cycle_signals,
        lead_lag=lead_lag,
        stock_picks=stock_picks,
        momentum_data=momentum_data,
    )
```

- [ ] **Step 3: Pass momentum_data to JsonExporter**

Modify `json_exporter.export()` call (L267-270) to add `momentum_data=momentum_data`:

```python
    json_path = json_exporter.export(
        strength_df, anomalies, analysis_text,
        cycle_signals, stock_picks, config,
        momentum_data=momentum_data,
    )
```

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: integrate momentum scanner into pipeline (Step 5.6)"
```

---

### Task 5: Add momentum section to exporters

**Files:**
- Modify: `src/exporters/obsidian_exporter.py`
- Modify: `src/exporters/json_exporter.py`

- [ ] **Step 1: Update ObsidianExporter.export() signature and forwarding**

Add `momentum_data: dict | None = None` parameter to `export()` (L21-31). Update the `_generate_markdown()` call inside `export()` (L42-51) to forward the new parameter:

```python
        content = self._generate_markdown(
            strength_df,
            anomalies,
            analysis_text,
            search_results or [],
            date,
            cycle_signals or [],
            lead_lag or [],
            stock_picks or {},
            momentum_data=momentum_data or {},
        )
```

Add `momentum_data: dict | None = None` parameter to `_generate_markdown()` (L57-67). After the `stock_picks` section (L82-83), add:

```python
        if momentum_data:
            sections.append(self._section_momentum(momentum_data))
```

- [ ] **Step 2: Add _section_momentum method to ObsidianExporter**

Add before `_section_cycle`:

```python
    def _section_momentum(self, momentum_data: dict) -> str:
        lines = ["## Momentum Surges\n"]

        for market_key, label, currency, cap_unit in [
            ("us_momentum", "US Momentum (5d >15% or 1M >30%)", "$", "B"),
            ("cn_momentum", "CN Momentum (5d >15% or 1M >30%)", "¥", "亿"),
        ]:
            items = momentum_data.get(market_key, [])
            if not items:
                continue
            lines.append(f"### {label}\n")
            lines.append("| Name | Symbol | Price | Day % | 5d % | 1M % | Trigger | RSI | RelVol | MktCap | Industry |")
            lines.append("|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|")
            for s in items:
                unit = s.get("market_cap_unit", cap_unit)
                lines.append(
                    f"| {s.get('name', '')} | {s['symbol']} | {currency}{s.get('price', 0):.2f} | "
                    f"{self._fmt_pct(s.get('change_pct'))} | {self._fmt_pct(s.get('perf_5d'))} | "
                    f"{self._fmt_pct(s.get('perf_20d'))} | {s.get('trigger', '')} | "
                    f"{s.get('rsi', 0):.0f} | {s.get('rel_volume', 0):.2f}x | "
                    f"{s.get('market_cap_b', 0):.0f}{unit} | {str(s.get('industry', ''))[:20]} |"
                )
            lines.append("")

        if not any(momentum_data.get(k) for k in ("us_momentum", "cn_momentum")):
            lines.append("*No multi-day momentum surges detected*\n")

        return "\n".join(lines)
```

- [ ] **Step 3: Update JsonExporter.export()**

Add `momentum_data: dict | None = None` parameter to `export()` (L17-19). In the `data` dict (L22-31), add:

```python
            "momentum_surge": momentum_data or {},
```

- [ ] **Step 4: Run full pipeline to verify**

Run: `cd tools/market-analyst && python main.py --skip-ai --skip-search`
Expected: Log shows "Step 5.6: momentum scan..." and report includes momentum section.

- [ ] **Step 5: Commit**

```bash
git add src/exporters/obsidian_exporter.py src/exporters/json_exporter.py
git commit -m "feat: add momentum surge section to Obsidian and JSON exporters"
```

---

## Chunk 2: Portfolio Advisor (Module A)

### Task 6: Create portfolio.yaml template

**Files:**
- Create: `config/portfolio.yaml`

- [ ] **Step 1: Write template file**

```yaml
# Portfolio configuration for Market Analyst
# Update this file with your holdings and watchlist

holdings:
  # - symbol: PLTR
  #   name: Palantir
  #   avg_cost: 140
  #   target_buy: 140        # target price to add more
  #   target_sell: null       # target price to sell (optional)
  #   position_pct: 10        # % of total portfolio (optional)
  #   notes: "Wait for pullback to $140"

watchlist:
  # - symbol: NVDA
  #   name: NVIDIA
  #   target_buy: 170
  #   target_sell: null
  #   logic: "200-day EMA support, GTC catalyst"
  #   position_plan: "First batch 40%"

settings:
  ema_periods: [20, 50, 100, 200]
  proximity_threshold: 4     # alert when price within N% of target
```

- [ ] **Step 2: Commit**

```bash
git add config/portfolio.yaml
git commit -m "config: add portfolio.yaml template"
```

---

### Task 7: Write PortfolioAdvisor tests

**Files:**
- Create: `tests/test_portfolio_advisor.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for PortfolioAdvisor."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def sample_portfolio():
    return {
        "holdings": [
            {"symbol": "MSFT", "name": "Microsoft", "avg_cost": 395, "target_buy": None, "notes": "Hold"},
        ],
        "watchlist": [
            {"symbol": "NVDA", "name": "NVIDIA", "target_buy": 170, "logic": "200 EMA support", "position_plan": "First batch 40%"},
        ],
        "settings": {
            "ema_periods": [20, 50, 100, 200],
            "proximity_threshold": 4,
        },
    }


@pytest.fixture
def mock_price_data():
    """Fake yfinance history for MSFT and NVDA."""
    dates = pd.date_range("2025-12-01", periods=250, freq="B")
    return {
        "MSFT": pd.DataFrame({
            "Close": np.linspace(380, 400, 250),
        }, index=dates),
        "NVDA": pd.DataFrame({
            "Close": np.linspace(150, 176, 250),
        }, index=dates),
    }


class TestPortfolioAdvisor:
    def test_no_portfolio_file_returns_empty(self, tmp_path):
        from src.processors.portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor(str(tmp_path / "nonexistent.yaml"), {})
        result = advisor.analyze()
        assert result == {"items": [], "advice_text": ""}

    def test_status_classification(self, sample_portfolio):
        from src.processors.portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor.__new__(PortfolioAdvisor)
        advisor.proximity_threshold = 4

        # in_zone: current <= target
        assert advisor._classify_status(168, 170) == "in_zone"
        # approaching: within 4%
        assert advisor._classify_status(174, 170) == "approaching"
        # away: more than 4%
        assert advisor._classify_status(190, 170) == "away"
        # holding: no target
        assert advisor._classify_status(400, None) == "holding"

    def test_signal_strength(self, sample_portfolio):
        from src.processors.portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor.__new__(PortfolioAdvisor)
        advisor.proximity_threshold = 4

        assert advisor._signal_strength(170, 170) == "strong"   # at target
        assert advisor._signal_strength(173, 170) == "medium"   # within 4%
        assert advisor._signal_strength(190, 170) == "weak"     # far away

    def test_compute_metrics_structure(self, sample_portfolio, mock_price_data):
        from src.processors.portfolio_advisor import PortfolioAdvisor

        advisor = PortfolioAdvisor.__new__(PortfolioAdvisor)
        advisor.portfolio = sample_portfolio
        advisor.ema_periods = [20, 50, 100, 200]
        advisor.proximity_threshold = 4

        with patch.object(advisor, "_fetch_price_data", return_value=mock_price_data):
            metrics = advisor._compute_metrics()

        assert len(metrics) == 2
        nvda = next(m for m in metrics if m["symbol"] == "NVDA")
        assert "current_price" in nvda
        assert "ema_200" in nvda
        assert "status" in nvda
        assert "signal_strength" in nvda
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/market-analyst && python -m pytest tests/test_portfolio_advisor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Commit**

```bash
git add tests/test_portfolio_advisor.py
git commit -m "test: add portfolio advisor tests (red)"
```

---

### Task 8: Implement PortfolioAdvisor

**Files:**
- Create: `src/processors/portfolio_advisor.py`

- [ ] **Step 1: Write implementation**

```python
"""Portfolio-based action recommendations.

Reads portfolio.yaml, fetches current prices and EMA levels,
computes structured metrics, then optionally generates natural
language advice via AI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf
from loguru import logger


class PortfolioAdvisor:
    """Generate action recommendations for user's holdings and watchlist."""

    def __init__(self, portfolio_path: str, config: dict):
        self.portfolio_path = Path(portfolio_path)
        self.config = config

        if self.portfolio_path.exists():
            with open(self.portfolio_path, "r", encoding="utf-8") as f:
                self.portfolio = yaml.safe_load(f) or {}
        else:
            self.portfolio = {}

        settings = self.portfolio.get("settings", {})
        self.ema_periods = settings.get("ema_periods", [20, 50, 100, 200])
        self.proximity_threshold = settings.get("proximity_threshold", 4)

    def analyze(self) -> dict:
        """Run portfolio analysis. Returns {"items": [...], "advice_text": str}."""
        if not self.portfolio or (
            not self.portfolio.get("holdings") and not self.portfolio.get("watchlist")
        ):
            return {"items": [], "advice_text": ""}

        metrics = self._compute_metrics()
        if not metrics:
            return {"items": [], "advice_text": ""}

        advice_text = self._generate_advice(metrics)
        return {"items": metrics, "advice_text": advice_text}

    def _compute_metrics(self) -> list[dict]:
        """Compute structured metrics for all portfolio items."""
        all_items = []
        for item in self.portfolio.get("holdings", []):
            all_items.append({**item, "_type": "holding"})
        for item in self.portfolio.get("watchlist", []):
            all_items.append({**item, "_type": "watchlist"})

        if not all_items:
            return []

        price_data = self._fetch_price_data(all_items)
        results = []

        for item in all_items:
            symbol = item["symbol"]
            hist = price_data.get(symbol)
            if hist is None or hist.empty:
                logger.warning(f"Portfolio: no data for {symbol}")
                continue

            closes = hist["Close"]
            current_price = round(float(closes.iloc[-1]), 2)
            daily_change = round(float(closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2) if len(closes) > 1 else 0

            # Calculate EMAs
            emas = {}
            for period in self.ema_periods:
                if len(closes) >= period:
                    ema_val = round(float(closes.ewm(span=period, adjust=False).mean().iloc[-1]), 2)
                    emas[f"ema_{period}"] = ema_val

            # RSI 14
            rsi = self._calc_rsi(closes, 14)

            # CMF 20
            cmf = self._calc_cmf(hist, 20)

            # Distance to key EMAs
            distance_to_ema200_pct = None
            if "ema_200" in emas and emas["ema_200"]:
                distance_to_ema200_pct = round((current_price / emas["ema_200"] - 1) * 100, 2)

            target_buy = item.get("target_buy")
            target_sell = item.get("target_sell")

            distance_to_target = None
            if target_buy:
                distance_to_target = round((current_price / target_buy - 1) * 100, 2)

            status = self._classify_status(current_price, target_buy)
            strength = self._signal_strength(current_price, target_buy)

            result = {
                "symbol": symbol,
                "name": item.get("name", symbol),
                "type": item["_type"],
                "current_price": current_price,
                "daily_change_pct": daily_change,
                "avg_cost": item.get("avg_cost"),
                "target_buy": target_buy,
                "target_sell": target_sell,
                "distance_to_target_pct": distance_to_target,
                "distance_to_ema200_pct": distance_to_ema200_pct,
                "rsi": rsi,
                "cmf": cmf,
                "status": status,
                "signal_strength": strength,
                "notes": item.get("notes", ""),
                "logic": item.get("logic", ""),
                "position_plan": item.get("position_plan", ""),
            }
            result.update(emas)
            results.append(result)

        return results

    def _fetch_price_data(self, items: list[dict]) -> dict[str, pd.DataFrame]:
        """Fetch historical price data for all symbols."""
        symbols = [item["symbol"] for item in items]
        max_period = max(self.ema_periods) + 50  # Extra buffer for EMA warmup
        data = {}
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period=f"{max_period}d")
                if not hist.empty:
                    data[sym] = hist
            except Exception as e:
                logger.warning(f"Portfolio: failed to fetch {sym}: {e}")
        return data

    def _classify_status(self, current: float, target_buy: float | None) -> str:
        if target_buy is None:
            return "holding"
        if current <= target_buy:
            return "in_zone"
        pct_above = (current / target_buy - 1) * 100
        if pct_above < self.proximity_threshold:
            return "approaching"
        return "away"

    def _signal_strength(self, current: float, target_buy: float | None) -> str:
        if target_buy is None:
            return "none"
        pct_above = (current / target_buy - 1) * 100
        if pct_above <= 0:
            return "strong"
        if pct_above < self.proximity_threshold:
            return "medium"
        return "weak"

    def _generate_advice(self, metrics: list[dict]) -> str:
        """Generate AI advice from metrics, with fallback to data-only."""
        analysis_cfg = self.config.get("analysis", {})
        if not analysis_cfg.get("enabled", True):
            return ""

        prompt = self._build_prompt(metrics)
        try:
            return self._call_ai(prompt, analysis_cfg)
        except Exception as e:
            logger.warning(f"Portfolio AI advice failed: {e}")
            if analysis_cfg.get("fallback_to_data_only", True):
                return ""
            return ""

    def _build_prompt(self, metrics: list[dict]) -> str:
        lines = [
            "You are a concise trading advisor. Based on the following portfolio data, "
            "generate action recommendations in Chinese.",
            "",
            "For each item, output:",
            "- Status icon: ✅ (in zone) / 🟡 (approaching) / ❌ (hold/away)",
            "- Item name — one-line summary",
            "- Current state (price, target, EMA distances)",
            "- Logic (2-3 sentences using the provided notes/logic)",
            "- Action instruction (specific price levels and position sizing)",
            "",
            "End with a priority ranking of actionable items.",
            "",
            "Portfolio data:",
            "```json",
        ]

        import json
        lines.append(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        return "\n".join(lines)

    def _call_ai(self, prompt: str, analysis_cfg: dict) -> str:
        """Call configured AI provider."""
        provider = analysis_cfg.get("provider", "gemini")
        model = analysis_cfg.get("model", "gemini-3.1-pro-preview")
        max_tokens = analysis_cfg.get("max_tokens", 4096)
        temperature = analysis_cfg.get("temperature", 0.3)

        if provider == "gemini":
            from google import genai
            import os
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return response.text or ""

        elif provider == "claude":
            import anthropic
            import os
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif provider == "openai":
            import openai
            import os
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""

        return ""

    @staticmethod
    def _calc_rsi(closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(window=period).mean()
        loss = (-delta.clip(upper=0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 1)

    @staticmethod
    def _calc_cmf(hist: pd.DataFrame, period: int = 20) -> float:
        """Chaikin Money Flow over given period."""
        if len(hist) < period or "Volume" not in hist.columns:
            return 0.0
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        volume = hist["Volume"]
        hl_range = high - low
        hl_range = hl_range.replace(0, 1e-10)
        mfm = ((close - low) - (high - close)) / hl_range
        mfv = mfm * volume
        cmf = mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, 1e-10)
        return round(float(cmf.iloc[-1]), 3)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd tools/market-analyst && python -m pytest tests/test_portfolio_advisor.py -v`
Expected: 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/processors/portfolio_advisor.py
git commit -m "feat: add PortfolioAdvisor with rule engine + AI advice generation"
```

---

### Task 9: Integrate PortfolioAdvisor into main.py

**Files:**
- Modify: `main.py` (after momentum scan block)

- [ ] **Step 1: Add Step 5.7 in main.py**

After the momentum_data block, insert:

```python
    portfolio_advice: dict = {}
    portfolio_path = base_dir / "config" / "portfolio.yaml"
    if portfolio_path.exists():
        logger.info("Step 5.7: portfolio advice...")
        from src.processors.portfolio_advisor import PortfolioAdvisor

        advisor = PortfolioAdvisor(str(portfolio_path), config)
        portfolio_advice = advisor.analyze()
        if portfolio_advice.get("items"):
            logger.info(f"  Portfolio: {len(portfolio_advice['items'])} items analyzed")
        else:
            logger.info("  Portfolio: no items configured")
```

- [ ] **Step 2: Pass portfolio_advice to ObsidianExporter**

Add `portfolio_advice=portfolio_advice` to the `exporter.export()` call.

- [ ] **Step 3: Pass portfolio_advice to JsonExporter**

Add `portfolio_advice=portfolio_advice` to the `json_exporter.export()` call.

- [ ] **Step 4: Add portfolio section to ObsidianExporter**

Add `portfolio_advice: dict | None = None` parameter to `export()` and `_generate_markdown()`. Also update the `_generate_markdown()` call inside `export()` to forward `portfolio_advice`:

```python
            portfolio_advice=portfolio_advice or {},
```

In `_generate_markdown()`, after the momentum section, add:

```python
        if portfolio_advice and portfolio_advice.get("items"):
            sections.append(self._section_portfolio(portfolio_advice))
```

Add method:

```python
    def _section_portfolio(self, portfolio_advice: dict) -> str:
        lines = ["## Portfolio Action Plan\n"]

        items = portfolio_advice.get("items", [])
        advice_text = portfolio_advice.get("advice_text", "")

        if advice_text:
            lines.append(advice_text)
            lines.append("")
        else:
            # Fallback: structured table
            holdings = [i for i in items if i["type"] == "holding"]
            watchlist = [i for i in items if i["type"] == "watchlist"]

            if holdings:
                lines.append("### Holdings\n")
                lines.append("| Name | Symbol | Cost | Current | P/L % | Status | Notes |")
                lines.append("|---|---|---:|---:|---:|---|---|")
                for h in holdings:
                    pnl = ""
                    if h.get("avg_cost") and h.get("current_price"):
                        pnl_val = (h["current_price"] / h["avg_cost"] - 1) * 100
                        pnl = f"{pnl_val:+.1f}"
                    lines.append(
                        f"| {h['name']} | {h['symbol']} | ${h.get('avg_cost', '—')} | "
                        f"${h.get('current_price', '—')} | {pnl} | {h.get('status', '')} | "
                        f"{h.get('notes', '')} |"
                    )
                lines.append("")

            if watchlist:
                lines.append("### Watchlist\n")
                lines.append("| Name | Symbol | Target | Current | Distance | Status | Signal |")
                lines.append("|---|---|---:|---:|---:|---|---|")
                for w in watchlist:
                    lines.append(
                        f"| {w['name']} | {w['symbol']} | ${w.get('target_buy', '—')} | "
                        f"${w.get('current_price', '—')} | {w.get('distance_to_target_pct', '—')}% | "
                        f"{w.get('status', '')} | {w.get('signal_strength', '')} |"
                    )
                lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 5: Add portfolio_advice to JsonExporter**

Add `portfolio_advice: dict | None = None` parameter to `export()`. In `data` dict add:

```python
            "portfolio_advice": portfolio_advice or {},
```

- [ ] **Step 6: Commit**

```bash
git add main.py src/exporters/obsidian_exporter.py src/exporters/json_exporter.py
git commit -m "feat: integrate portfolio advisor into pipeline (Step 5.7)"
```

---

### Task 10: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Fill in portfolio.yaml with test data**

Uncomment the example entries in `config/portfolio.yaml` and add real symbols.

- [ ] **Step 2: Run full pipeline**

Run: `cd tools/market-analyst && python main.py --skip-search`
Expected: Log shows Steps 5.6 and 5.7, report includes momentum + portfolio sections.

- [ ] **Step 3: Verify Obsidian report has new sections**

Open the generated `03_output/market-analysis/YYYY-MM-DD_market_analysis.md` and confirm:
- "Momentum Surges" section with US + CN tables
- "Portfolio Action Plan" section with AI-generated advice (or fallback table)

- [ ] **Step 4: Verify JSON export has new fields**

Check `data/YYYY-MM-DD.json` contains `momentum_surge` and `portfolio_advice` keys.

- [ ] **Step 5: Run all tests**

Run: `cd tools/market-analyst && python -m pytest tests/ -v`
Expected: All tests PASS (including existing + new tests).

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "test: end-to-end verification of momentum scanner + portfolio advisor"
```
