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
        from market_analyst.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner({"momentum_scan": {"enabled": False}})
        result = scanner.scan()
        assert result == {"us_momentum": [], "cn_momentum": []}

    def test_scan_returns_correct_structure(self, default_config):
        from market_analyst.processors.momentum_scanner import MomentumScanner

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
        from market_analyst.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner(default_config)

        assert scanner._classify_trigger(20.0, 10.0) == "5d"
        assert scanner._classify_trigger(5.0, 35.0) == "20d"
        assert scanner._classify_trigger(20.0, 35.0) == "both"
        assert scanner._classify_trigger(5.0, 10.0) is None
