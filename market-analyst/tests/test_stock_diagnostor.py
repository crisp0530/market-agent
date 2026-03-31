"""Tests for stock diagnosis processor."""
import pytest
import pandas as pd
import numpy as np

from market_analyst.processors.stock_diagnostor import StockDiagnostor


@pytest.fixture
def sample_stock_df():
    """60 days of realistic OHLCV for one stock."""
    np.random.seed(42)
    dates = pd.bdate_range(end="2026-03-27", periods=60)
    base = 150.0
    closes = base + np.cumsum(np.random.randn(60) * 1.5)
    closes = np.maximum(closes, 50)  # floor

    return pd.DataFrame({
        "symbol": "AAPL",
        "name": "Apple",
        "market": "us",
        "sector": "Technology",
        "date": dates.strftime("%Y-%m-%d").tolist(),
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
