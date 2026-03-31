"""Tests for strategy matching engine."""
import pytest

from market_analyst.processors.strategy_matcher import StrategyMatcher
from market_analyst.schemas_retail import TradingStrategies


@pytest.fixture
def strategy_config():
    return {"strategies": {"max_recommendations": 3}}


class TestStrategyMatcher:
    def test_hot_money_high_momentum_gets_dragon(self, strategy_config):
        """游资票 + 高动量 → 龙头战法."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="301234", name="游资概念股", market="cn",
            character_type="游资票",
            diagnosis={"trend": 70, "momentum": 85, "sentiment": 80, "volatility": 30},
            fear_score=40, sector_tier="T1",
        )
        assert isinstance(result, TradingStrategies)
        names = [s.name for s in result.recommended]
        assert "龙头战法" in names or "打板战法" in names

    def test_institutional_uptrend_gets_swing(self, strategy_config):
        """机构票 + 趋势向上 → 波段持股."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="600519", name="贵州茅台", market="cn",
            character_type="机构票",
            diagnosis={"trend": 75, "momentum": 60, "sentiment": 55, "volatility": 70},
            fear_score=45, sector_tier="T2",
        )
        names = [s.name for s in result.recommended]
        assert "波段持股" in names

    def test_oversold_gets_bounce(self, strategy_config):
        """超跌 + 恐慌高 → 低吸反弹."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="cn",
            character_type="游资票",
            diagnosis={"trend": 20, "momentum": 15, "sentiment": 15, "volatility": 30},
            fear_score=80, sector_tier="T4",
        )
        names = [s.name for s in result.recommended]
        assert "低吸反弹" in names

    def test_no_symbol_returns_general(self, strategy_config):
        """No symbol → general market strategies."""
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match_general(market_score=40, fear_score=75)
        assert result.symbol is None
        assert len(result.recommended) >= 1

    def test_max_recommendations(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="cn", character_type="普通票",
            diagnosis={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            fear_score=50, sector_tier="T2",
        )
        assert len(result.recommended) <= 3

    def test_risk_reward_lesson_present(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="X", name="X", market="us", character_type="普通票",
            diagnosis={"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50},
            fear_score=50, sector_tier="T2",
        )
        assert len(result.risk_reward_lesson) > 0

    def test_each_strategy_has_all_fields(self, strategy_config):
        matcher = StrategyMatcher(strategy_config)
        result = matcher.match(
            symbol="AAPL", name="Apple", market="us", character_type="机构票",
            diagnosis={"trend": 70, "momentum": 60, "sentiment": 55, "volatility": 65},
            fear_score=45, sector_tier="T1",
        )
        for s in result.recommended:
            assert s.name
            assert s.entry_rule
            assert s.exit_rule
            assert s.stop_loss
            assert s.risk_reward
            assert s.difficulty in ("新手", "进阶", "高阶")
