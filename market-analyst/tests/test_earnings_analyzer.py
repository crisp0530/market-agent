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
