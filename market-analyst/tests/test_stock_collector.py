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

    def test_cn_stock_falls_back_to_daily_when_hist_fails(self):
        mock_daily = pd.DataFrame({
            "date": ["2026-03-27", "2026-03-28"],
            "open": [10.0, 10.1],
            "high": [10.5, 10.6],
            "low": [9.8, 9.9],
            "close": [10.2, 10.3],
            "volume": [500000, 600000],
        })
        mock_info = pd.DataFrame({
            "item": ["股票简称"],
            "value": ["贵州茅台"],
        })

        with patch("market_analyst.collectors.stock_collector.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.side_effect = ConnectionError("upstream disconnected")
            mock_ak.stock_zh_a_daily.return_value = mock_daily
            mock_ak.stock_individual_info_em.return_value = mock_info

            collector = StockCollector()
            df = collector.collect_single("600519", market="cn", lookback_days=5)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert df.iloc[0]["symbol"] == "600519"
            assert df.iloc[0]["name"] == "贵州茅台"
            assert df.iloc[0]["market"] == "cn"
            mock_ak.stock_zh_a_daily.assert_called_once_with(symbol="sh600519")

    def test_invalid_symbol_returns_empty(self):
        with patch("market_analyst.collectors.stock_collector.yf") as mock_yf:
            ticker = MagicMock()
            ticker.history.return_value = pd.DataFrame()
            ticker.info = {}
            mock_yf.Ticker.return_value = ticker

            collector = StockCollector()
            df = collector.collect_single("ZZZZZ", market="us")
            assert df.empty
