"""Tests for trade signal generator."""
import pytest

from market_analyst.processors.trade_signal_generator import TradeSignalGenerator
from market_analyst.schemas_retail import TradeSignal


@pytest.fixture
def signal_config():
    return {
        "trade_signal": {
            "market_weight": 0.3,
            "stock_weight": 0.5,
            "character_weight": 0.2,
            "hot_money_sentiment_boost": 1.5,
            "hot_money_trend_reduction": 0.7,
            "institutional_trend_boost": 1.3,
            "institutional_sentiment_reduction": 0.8,
        }
    }


class TestTradeSignalGenerator:
    def test_daji_when_all_strong(self, signal_config):
        """All high scores → 大吉."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="AAPL", name="Apple", market="us",
            market_score=85, stock_scores={"trend": 90, "momentum": 85, "sentiment": 80, "volatility": 75, "flow": 70},
            character_type="机构票",
        )
        assert isinstance(result, TradeSignal)
        assert result.signal == "大吉"
        assert result.score >= 80

    def test_daxiong_when_all_weak(self, signal_config):
        """All low scores → 大凶."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="cn",
            market_score=10, stock_scores={"trend": 10, "momentum": 15, "sentiment": 10, "volatility": 20, "flow": 5},
            character_type="普通票",
        )
        assert result.signal == "大凶"
        assert result.score < 20

    def test_ping_when_mixed(self, signal_config):
        """Mixed scores → 平."""
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="us",
            market_score=50, stock_scores={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50, "flow": 50},
            character_type="普通票",
        )
        assert result.signal == "平"

    def test_hot_money_boosts_sentiment(self, signal_config):
        """游资票 should weight sentiment higher."""
        gen = TradeSignalGenerator(signal_config)
        scores = {"trend": 30, "momentum": 50, "sentiment": 90, "volatility": 50, "flow": 50}
        result_hot = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                  stock_scores=scores, character_type="游资票")
        result_normal = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                     stock_scores=scores, character_type="普通票")
        assert result_hot.score > result_normal.score

    def test_institutional_boosts_trend(self, signal_config):
        """机构票 should weight trend higher."""
        gen = TradeSignalGenerator(signal_config)
        scores = {"trend": 90, "momentum": 50, "sentiment": 30, "volatility": 50, "flow": 50}
        result_inst = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                   stock_scores=scores, character_type="机构票")
        result_normal = gen.generate(symbol="X", name="X", market="cn", market_score=50,
                                     stock_scores=scores, character_type="普通票")
        assert result_inst.score > result_normal.score

    def test_reasons_not_empty(self, signal_config):
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="AAPL", name="Apple", market="us",
            market_score=60, stock_scores={"trend": 70, "momentum": 65, "sentiment": 55, "volatility": 60, "flow": 50},
            character_type="机构票",
        )
        assert len(result.reasons) >= 1

    def test_score_in_range(self, signal_config):
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="X", name="X", market="us",
            market_score=50, stock_scores={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            character_type="普通票",
        )
        assert 0 <= result.score <= 100

    def test_ignores_non_score_metadata_fields(self, signal_config):
        gen = TradeSignalGenerator(signal_config)
        result = gen.generate(
            symbol="601868", name="中国能建", market="cn",
            market_score=55,
            stock_scores={
                "trend": 50,
                "momentum": 35,
                "sentiment": 34.5,
                "volatility": 0,
                "flow": 56.4,
                "rating": 2,
                "available_dimensions": ["trend", "momentum", "sentiment", "volatility", "flow"],
            },
            character_type="普通票",
        )
        assert result.stock_score == pytest.approx(35.2, abs=0.1)
        assert result.signal in {"大吉", "小吉", "平", "小凶", "大凶"}
