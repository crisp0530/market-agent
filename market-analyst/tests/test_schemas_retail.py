"""Tests for retail investor Pydantic schemas."""
import pytest
from pydantic import ValidationError

from market_analyst.schemas_retail import (
    StockCharacterization,
    TradeSignal,
    QuarterlyMetric,
    RiskFlag,
    EarningsAnalysis,
    StrategyItem,
    TradingStrategies,
)


class TestStockCharacterization:
    def test_valid_construction(self):
        sc = StockCharacterization(
            symbol="600519",
            name="贵州茅台",
            market="cn",
            character_type="机构票",
            hot_money_score=25.0,
            institutional_score=80.0,
            available_dimensions=["turnover", "volatility", "volume_pattern", "limit_up_freq", "market_cap"],
            key_evidence=["日均换手率1.2%，远低于市场均值", "总市值2.1万亿"],
            analysis_tips="关注基本面、业绩预期、估值水平",
        )
        assert sc.character_type == "机构票"
        assert sc.market == "cn"

    def test_invalid_market_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="invalid",
                character_type="普通票", hot_money_score=50, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_invalid_character_type_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="us",
                character_type="unknown", hot_money_score=50, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            StockCharacterization(
                symbol="X", name="X", market="us",
                character_type="普通票", hot_money_score=150, institutional_score=50,
                available_dimensions=[], key_evidence=[], analysis_tips="",
            )

    def test_stale_defaults_false(self):
        sc = StockCharacterization(
            symbol="AAPL", name="Apple", market="us",
            character_type="机构票", hot_money_score=20, institutional_score=75,
            available_dimensions=["turnover", "volatility"], key_evidence=[], analysis_tips="",
        )
        assert sc.stale is False


class TestTradeSignal:
    def test_valid_construction(self):
        ts = TradeSignal(
            symbol="AAPL", name="Apple", market="us",
            signal="小吉", score=68.0, market_score=55.0, stock_score=78.0,
            character_score=72.0, character_type="机构票",
            score_breakdown={"trend": 80, "momentum": 65, "sentiment": 55, "volatility": 70},
            reasons=["趋势向上"], risk_warnings=[],
        )
        assert ts.signal == "小吉"
        assert ts.character_score == 72.0

    def test_invalid_signal_rejected(self):
        with pytest.raises(ValidationError):
            TradeSignal(
                symbol="X", name="X", market="us",
                signal="超级吉", score=50, market_score=50, stock_score=50,
                character_score=50, character_type="普通票",
                score_breakdown={}, reasons=[], risk_warnings=[],
            )


class TestEarningsAnalysis:
    def test_valid_with_typed_sub_models(self):
        ea = EarningsAnalysis(
            symbol="600519", name="贵州茅台", market="cn",
            latest_quarter="2025Q4", revenue=350.5, net_profit=180.2,
            revenue_yoy=15.3, profit_yoy=12.8,
            expectation_basis="consensus", expectation="小幅超预期", deviation_pct=5.2,
            quarterly_trend=[
                QuarterlyMetric(quarter="2025Q4", revenue=350.5, revenue_yoy=15.3, profit=180.2, profit_yoy=12.8),
                QuarterlyMetric(quarter="2025Q3", revenue=320.0, revenue_yoy=10.0, profit=165.0, profit_yoy=10.5),
            ],
            trend_summary="连续增长",
            risks=[RiskFlag(type="减持风险", level="medium", detail="近90天减持0.5%")],
            plain_summary="茅台四季度营收350亿，同比增15%，净利润超分析师预期5%。",
        )
        assert ea.expectation == "小幅超预期"
        assert ea.expectation_basis == "consensus"
        assert len(ea.quarterly_trend) == 2
        assert ea.risks[0].level == "medium"

    def test_yoy_fallback_basis(self):
        ea = EarningsAnalysis(
            symbol="X", name="X", market="cn",
            latest_quarter="2025Q4", revenue=100, net_profit=30,
            revenue_yoy=35, profit_yoy=40,
            expectation_basis="yoy_fallback", expectation="大幅超预期", deviation_pct=None,
            quarterly_trend=[], trend_summary="波动", risks=[], plain_summary="同比大幅增长",
        )
        assert ea.expectation_basis == "yoy_fallback"

    def test_invalid_risk_type_rejected(self):
        with pytest.raises(ValidationError):
            RiskFlag(type="不存在的风险", level="medium", detail="test")

    def test_quarterly_metric_with_revenue_yoy(self):
        qm = QuarterlyMetric(quarter="2025Q4", revenue=100.0, revenue_yoy=15.0, profit=50.0, profit_yoy=None)
        assert qm.revenue_yoy == 15.0
        assert qm.profit_yoy is None


class TestTradingStrategies:
    def test_valid_with_symbol(self):
        ts = TradingStrategies(
            symbol="AAPL", name="Apple", market="us", character_type="机构票",
            current_situation="趋势向上，站上20日均线",
            recommended=[
                StrategyItem(
                    name="波段持股", match_reason="机构票+趋势向上",
                    description="沿20日均线持股", entry_rule="站上20日线",
                    exit_rule="跌破20日线", stop_loss="-5%",
                    risk_reward="2:1", difficulty="进阶",
                ),
            ],
            risk_reward_lesson="盈亏比是长期盈利的关键。",
        )
        assert ts.recommended[0].difficulty == "进阶"

    def test_valid_without_symbol(self):
        ts = TradingStrategies(
            symbol=None, name=None, market=None, character_type=None,
            current_situation="大盘低估区域",
            recommended=[], risk_reward_lesson="",
        )
        assert ts.symbol is None
