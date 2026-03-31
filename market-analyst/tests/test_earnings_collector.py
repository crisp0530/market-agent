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
