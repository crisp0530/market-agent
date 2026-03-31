"""Tests for ActionSignalGenerator — TDD: written before implementation."""

from types import SimpleNamespace

import numpy as np
import pytest

from market_analyst.processors.action_signal_generator import ActionSignalGenerator
from market_analyst.schemas_retail import CapitalFlowSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config() -> dict:
    return {
        "action_signal": {
            "resonance_min_count": 3,
            "oversold_rsi": 30,
            "bollinger_touch_margin": 0.02,
            "stop_loss_margin": 0.02,
            "tv_buy_signals": ["Buy", "Strong Buy"],
        }
    }


def _neutral_capital_flow() -> CapitalFlowSignal:
    return CapitalFlowSignal(signal="中性", description="中性资金流")


def _inflow_capital_flow(kind: str = "大幅流入") -> CapitalFlowSignal:
    return CapitalFlowSignal(signal=kind, description="资金流入")


def _full_tv_data(**overrides):
    """Return a SimpleNamespace mimicking TvScreenerData with all resonance fields."""
    defaults = dict(
        rsi_14=25.0,
        macd_hist=0.5,
        price=10.0,
        bollinger_lower=9.9,
        recommendation="Buy",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1-3: Conservative path
# ---------------------------------------------------------------------------

class TestConservative:
    def test_rating_1_advises_avoid(self):
        gen = ActionSignalGenerator(_default_config())
        sig = gen.generate(
            rating=1,
            capital_flow=_neutral_capital_flow(),
            diag_scores={},
        )
        assert sig.level == "conservative"
        assert "回避" in sig.advice

    def test_rating_3_advises_wait(self):
        gen = ActionSignalGenerator(_default_config())
        sig = gen.generate(
            rating=3,
            capital_flow=_neutral_capital_flow(),
            diag_scores={},
        )
        assert sig.level == "conservative"
        assert "观望" in sig.advice

    def test_rating_5_advises_watch(self):
        gen = ActionSignalGenerator(_default_config())
        sig = gen.generate(
            rating=5,
            capital_flow=_neutral_capital_flow(),
            diag_scores={},
        )
        assert sig.level == "conservative"
        assert "关注" in sig.advice


# ---------------------------------------------------------------------------
# 4-6: Resonance vs non-resonance
# ---------------------------------------------------------------------------

class TestResonance:
    def test_3_conditions_trigger_resonance(self):
        gen = ActionSignalGenerator(_default_config())
        tv = _full_tv_data()  # RSI, MACD, Bollinger, TV rec = 4 conditions
        sig = gen.generate(
            rating=3,
            capital_flow=_inflow_capital_flow(),  # +1 = 5
            diag_scores={},
            tv_data=tv,
        )
        assert sig.level == "resonance"
        assert sig.resonance_count >= 3

    def test_5_conditions_all_listed(self):
        gen = ActionSignalGenerator(_default_config())
        tv = _full_tv_data()  # RSI + MACD + Bollinger + TV rec = 4
        sig = gen.generate(
            rating=3,
            capital_flow=_inflow_capital_flow(),  # capital = 5th
            diag_scores={},
            tv_data=tv,
        )
        assert sig.level == "resonance"
        assert sig.resonance_count == 5
        assert len(sig.resonance_details) == 5

    def test_only_2_conditions_stays_conservative(self):
        gen = ActionSignalGenerator(_default_config())
        # Only MACD + TV rec = 2 conditions
        tv = _full_tv_data(rsi_14=50, bollinger_lower=8.0)  # RSI too high, Bollinger too far
        sig = gen.generate(
            rating=3,
            capital_flow=_neutral_capital_flow(),
            diag_scores={},
            tv_data=tv,
        )
        assert sig.level == "conservative"
        assert sig.resonance_count == 2


# ---------------------------------------------------------------------------
# 7: RSI condition — tvscreener preferred, diagnostor fallback
# ---------------------------------------------------------------------------

class TestRSICondition:
    def test_tvscreener_rsi_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        conds = gen._check_resonance(
            capital_flow=_neutral_capital_flow(),
            diag_scores={},
            tv_data=_full_tv_data(rsi_14=25, macd_hist=-1, bollinger_lower=5, recommendation="Sell"),
        )
        assert any("RSI" in c for c in conds)

    def test_diagnostor_sentiment_fallback_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        conds = gen._check_resonance(
            capital_flow=_neutral_capital_flow(),
            diag_scores={"sentiment": 25},
            tv_data=None,
        )
        assert any("RSI" in c for c in conds)


# ---------------------------------------------------------------------------
# 8: MACD condition
# ---------------------------------------------------------------------------

class TestMACDCondition:
    def test_positive_macd_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=0.5, price=10, bollinger_lower=5, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert any("MACD" in c for c in conds)

    def test_negative_macd_does_not_trigger(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=-0.5, price=10, bollinger_lower=5, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert not any("MACD" in c for c in conds)


# ---------------------------------------------------------------------------
# 9: Capital flow condition
# ---------------------------------------------------------------------------

class TestCapitalFlowCondition:
    def test_inflow_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10, bollinger_lower=5, recommendation="Sell")
        conds = gen._check_resonance(_inflow_capital_flow("大幅流入"), {}, tv)
        assert any("资金" in c for c in conds)

    def test_neutral_does_not_trigger(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10, bollinger_lower=5, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert not any("资金" in c for c in conds)


# ---------------------------------------------------------------------------
# 10: Bollinger condition
# ---------------------------------------------------------------------------

class TestBollingerCondition:
    def test_near_lower_band_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        # distance = (10 - 9.9) / 10 = 0.01 < 0.02
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10.0, bollinger_lower=9.9, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert any("布林" in c for c in conds)

    def test_far_from_lower_band_does_not_trigger(self):
        gen = ActionSignalGenerator(_default_config())
        # distance = (10 - 9.5) / 10 = 0.05 > 0.02
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10.0, bollinger_lower=9.5, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert not any("布林" in c for c in conds)


# ---------------------------------------------------------------------------
# 11: TV recommendation condition
# ---------------------------------------------------------------------------

class TestTVRecommendation:
    def test_buy_triggers(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10, bollinger_lower=5, recommendation="Buy")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert any("TV" in c for c in conds)

    def test_sell_does_not_trigger(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(rsi_14=50, macd_hist=-1, price=10, bollinger_lower=5, recommendation="Sell")
        conds = gen._check_resonance(_neutral_capital_flow(), {}, tv)
        assert not any("TV" in c for c in conds)


# ---------------------------------------------------------------------------
# 12: Support price
# ---------------------------------------------------------------------------

class TestSupportPrice:
    def test_support_is_min_of_last_20(self):
        gen = ActionSignalGenerator(_default_config())
        closes = np.array([10 + i * 0.1 for i in range(30)])
        closes[15] = 5.0  # min in last 20 (indices 10-29)
        support = gen._calc_support(closes)
        assert support == 5.0

    def test_none_when_no_closes(self):
        gen = ActionSignalGenerator(_default_config())
        assert gen._calc_support(None) is None
        assert gen._calc_support(np.array([])) is None


# ---------------------------------------------------------------------------
# 13: Stop loss
# ---------------------------------------------------------------------------

class TestStopLoss:
    def test_stop_loss_from_bollinger(self):
        gen = ActionSignalGenerator(_default_config())
        tv = SimpleNamespace(bollinger_lower=10.0)
        assert gen._calc_stop_loss(tv) == 9.80

    def test_none_when_no_tv_data(self):
        gen = ActionSignalGenerator(_default_config())
        assert gen._calc_stop_loss(None) is None


# ---------------------------------------------------------------------------
# 14: No tv_data → max 2 conditions → stays conservative
# ---------------------------------------------------------------------------

class TestNoTvData:
    def test_only_rsi_and_capital_can_trigger(self):
        gen = ActionSignalGenerator(_default_config())
        sig = gen.generate(
            rating=5,
            capital_flow=_inflow_capital_flow(),
            diag_scores={"sentiment": 20},
            tv_data=None,
        )
        # RSI (from sentiment) + capital flow = 2, not enough for resonance
        assert sig.level == "conservative"
        assert sig.resonance_count == 2


# ---------------------------------------------------------------------------
# 15: Resonance advice text
# ---------------------------------------------------------------------------

class TestResonanceAdvice:
    def test_advice_includes_condition_details(self):
        gen = ActionSignalGenerator(_default_config())
        tv = _full_tv_data()
        closes = np.array([9.0 + i * 0.05 for i in range(25)])
        sig = gen.generate(
            rating=3,
            capital_flow=_inflow_capital_flow(),
            diag_scores={},
            tv_data=tv,
            closes=closes,
        )
        assert sig.level == "resonance"
        assert "共振" in sig.advice
        assert "支撑" in sig.advice or "support" in sig.advice.lower()
        assert "止损" in sig.advice or "stop" in sig.advice.lower()
        assert "不构成投资建议" in sig.advice
