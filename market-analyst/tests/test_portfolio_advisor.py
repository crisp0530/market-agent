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
        from market_analyst.processors.portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor(str(tmp_path / "nonexistent.yaml"), {})
        result = advisor.analyze()
        assert result == {"items": [], "advice_text": ""}

    def test_status_classification(self, sample_portfolio):
        from market_analyst.processors.portfolio_advisor import PortfolioAdvisor
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
        from market_analyst.processors.portfolio_advisor import PortfolioAdvisor
        advisor = PortfolioAdvisor.__new__(PortfolioAdvisor)
        advisor.proximity_threshold = 4

        assert advisor._signal_strength(170, 170) == "strong"   # at target
        assert advisor._signal_strength(173, 170) == "medium"   # within 4%
        assert advisor._signal_strength(190, 170) == "weak"     # far away

    def test_compute_metrics_structure(self, sample_portfolio, mock_price_data):
        from market_analyst.processors.portfolio_advisor import PortfolioAdvisor

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
