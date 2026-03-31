"""Integration tests for enhanced characterize_stock with capital flow and action signal."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from market_analyst.schemas_retail import (
    CapitalFlowSignal,
    ActionSignal,
    StockCharacterization,
)


def _make_stock_df(n=30, base_close=10.0):
    """Create a simple OHLCV DataFrame for testing."""
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    closes = np.linspace(base_close, base_close * 1.1, n)
    return pd.DataFrame({
        "symbol": "TEST",
        "name": "Test Stock",
        "sector": "个股",
        "market": "cn",
        "date": dates.strftime("%Y-%m-%d"),
        "open": closes * 0.99,
        "high": closes * 1.02,
        "low": closes * 0.97,
        "close": closes,
        "volume": np.full(n, 1000000),
    })


class TestCapitalFlowIntegration:
    """Test CapitalFlowDetector + TvScreenerProvider integration logic."""

    def test_dual_source_detection(self):
        from market_analyst.processors.capital_flow_detector import CapitalFlowDetector
        detector = CapitalFlowDetector({})
        result = detector.detect(cmf_score=65, mfi_score=75, relative_volume=1.8)
        assert result.signal == "大幅流入"
        assert result.dual_source is True

    def test_single_source_fallback(self):
        from market_analyst.processors.capital_flow_detector import CapitalFlowDetector
        detector = CapitalFlowDetector({})
        result = detector.detect(cmf_score=70, mfi_score=None)
        assert result.signal == "小幅流入"
        assert result.dual_source is False


class TestActionSignalIntegration:
    """Test ActionSignalGenerator with real data structures."""

    def test_conservative_with_low_rating(self):
        from market_analyst.processors.action_signal_generator import ActionSignalGenerator
        gen = ActionSignalGenerator({})
        cf = CapitalFlowSignal(signal="中性", description="test")
        result = gen.generate(rating=2, capital_flow=cf, diag_scores={"sentiment": 50})
        assert result.level == "conservative"
        assert "回避" in result.advice

    def test_resonance_with_tv_data(self):
        from market_analyst.processors.action_signal_generator import ActionSignalGenerator
        gen = ActionSignalGenerator({})
        cf = CapitalFlowSignal(signal="大幅流入", description="test")
        tv = SimpleNamespace(
            rsi_14=25, macd_hist=0.5, price=10.0,
            bollinger_lower=9.9, recommendation="Buy",
        )
        closes = np.array([10.5, 10.3, 10.1, 9.8, 9.9] * 4)
        result = gen.generate(rating=3, capital_flow=cf, diag_scores={}, tv_data=tv, closes=closes)
        assert result.level == "resonance"
        assert result.resonance_count >= 3


class TestStockCharacterizationBackwardCompat:
    """Ensure existing code still works with new optional fields."""

    def test_existing_construction_still_works(self):
        sc = StockCharacterization(
            symbol="600519", name="贵州茅台", market="cn",
            character_type="机构票", hot_money_score=25, institutional_score=80,
            available_dimensions=["turnover"], key_evidence=["test"], analysis_tips="test",
        )
        assert sc.capital_flow is None
        assert sc.action is None

    def test_json_serialization_with_new_fields(self):
        cf = CapitalFlowSignal(signal="小幅流入", cmf_score=60, mfi_score=55, description="test", dual_source=True)
        action = ActionSignal(level="conservative", advice="观望")
        sc = StockCharacterization(
            symbol="600519", name="贵州茅台", market="cn",
            character_type="机构票", hot_money_score=25, institutional_score=80,
            available_dimensions=[], key_evidence=[], analysis_tips="",
            capital_flow=cf, action=action,
        )
        data = json.loads(sc.model_dump_json())
        assert data["capital_flow"]["signal"] == "小幅流入"
        assert data["action"]["level"] == "conservative"

    def test_json_serialization_without_new_fields(self):
        sc = StockCharacterization(
            symbol="AAPL", name="Apple", market="us",
            character_type="普通票", hot_money_score=50, institutional_score=50,
            available_dimensions=[], key_evidence=[], analysis_tips="",
        )
        data = json.loads(sc.model_dump_json())
        assert data["capital_flow"] is None
        assert data["action"] is None


class TestTvScreenerProviderSymbolMapping:
    """Quick integration check for symbol mapping."""

    def test_cn_symbol_mapping(self):
        from market_analyst.providers.tvscreener_provider import TvScreenerProvider
        provider = TvScreenerProvider("/nonexistent")
        assert provider._map_symbol("601866", "cn") == "SHSE:601866"
        assert provider._map_symbol("000858", "cn") == "SZSE:000858"
        assert provider._map_symbol("430047", "cn") is None  # 北交所

    def test_us_symbol_mapping(self):
        from market_analyst.providers.tvscreener_provider import TvScreenerProvider
        provider = TvScreenerProvider("/nonexistent")
        assert provider._map_symbol("RKLB", "us") == "NASDAQ:RKLB"
