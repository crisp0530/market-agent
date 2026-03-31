"""Tests for MCP server tools."""
import pytest
import json
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from market_analyst.schemas import (
    FearScoreResult,
    MarketOverview,
    SectorStrength,
    SectorStrengthItem,
    StockDiagnosis,
    AnomalySignal,
    CycleSignal,
    CommentaryData,
    MomentumItem,
    NewsItem,
    ReportResult,
    ToolError,
)
from market_analyst.schemas_retail import ActionSignal, CapitalFlowSignal


class TestGetFearScore:
    def _make_strength_df(self):
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
        assert result.fear_score is not None

    def test_fear_score_symbol_not_found(self):
        from market_analyst.mcp_server import _get_fear_score_impl
        df = self._make_strength_df()
        result = _get_fear_score_impl(df, symbol="ZZZZZ")
        assert isinstance(result, ToolError)
        assert result.error == "symbol_not_found"


class TestGetMarketOverview:
    def _make_data(self):
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


class TestGetSectorStrength:
    def _make_data(self):
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


class TestGetCycleSignals:
    def test_cycle_signals_structure(self):
        from market_analyst.mcp_server import _get_cycle_signals_impl
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
        assert "VIX" in result.key_indices_change


class TestScanMomentum:
    def test_momentum_returns_items(self):
        from market_analyst.mcp_server import _scan_momentum_impl
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


class TestSearchMarketNews:
    def test_news_returns_items(self):
        from market_analyst.mcp_server import _search_news_impl
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


class TestDiagnoseStock:
    def test_diagnose_with_mock_data(self):
        from market_analyst.mcp_server import _diagnose_stock_impl
        np.random.seed(42)
        dates = pd.bdate_range(end="2026-03-27", periods=60)
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

    def test_diagnose_includes_enhanced_fields(self):
        from market_analyst.mcp_server import _diagnose_stock_impl

        np.random.seed(42)
        dates = pd.bdate_range(end="2026-03-27", periods=60)
        closes = 150.0 + np.cumsum(np.random.randn(60) * 1.5)
        df = pd.DataFrame({
            "symbol": "RKLB", "name": "Rocket Lab", "market": "us",
            "sector": "Aerospace", "date": dates.strftime("%Y-%m-%d"),
            "open": closes, "high": closes + 1, "low": closes - 1,
            "close": closes, "volume": np.full(60, 1e6),
        })

        fake_flow = CapitalFlowSignal(signal="小幅流入", description="test")
        fake_action = ActionSignal(level="conservative", advice="观望")

        with patch("market_analyst.mcp_server._build_capital_flow_and_action") as mock_build, \
                patch("market_analyst.mcp_server._load_config") as mock_load_config:
            mock_load_config.return_value = {}
            mock_build.return_value = (fake_flow, fake_action)
            result = _diagnose_stock_impl(df, "RKLB", "Rocket Lab", "us")

        assert isinstance(result, StockDiagnosis)
        assert result.capital_flow == fake_flow
        assert result.action == fake_action

    def test_diagnose_no_data(self):
        from market_analyst.mcp_server import _diagnose_stock_impl
        result = _diagnose_stock_impl(pd.DataFrame(), "ZZZZZ", "Unknown", "us")
        assert isinstance(result, ToolError)


class TestRunFullReport:
    def test_report_returns_result(self):
        from market_analyst.mcp_server import _run_full_report_impl
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
