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
