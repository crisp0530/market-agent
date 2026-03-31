"""ActionSignalGenerator — generate tiered action signals: conservative by default, upgrade on resonance."""

from __future__ import annotations

import numpy as np

from market_analyst.schemas_retail import ActionSignal, CapitalFlowSignal


class ActionSignalGenerator:
    """Generate tiered action signals: conservative by default, upgrade on resonance."""

    CONSERVATIVE_MAP = {
        1: "建议回避，等待趋势明朗",
        2: "建议回避，等待趋势明朗",
        3: "暂时观望，关注变化",
        4: "可以关注，等待入场信号",
        5: "可以关注，等待入场信号",
    }

    def __init__(self, config: dict):
        cfg = config.get("action_signal", {})
        self.resonance_min = cfg.get("resonance_min_count", 3)
        self.oversold_rsi = cfg.get("oversold_rsi", 30)
        self.bollinger_margin = cfg.get("bollinger_touch_margin", 0.02)
        self.stop_loss_margin = cfg.get("stop_loss_margin", 0.02)
        self.tv_buy_signals = cfg.get("tv_buy_signals", ["Buy", "Strong Buy"])

    def generate(
        self,
        rating: int,
        capital_flow: CapitalFlowSignal,
        diag_scores: dict,
        tv_data=None,
        closes: np.ndarray | None = None,
    ) -> ActionSignal:
        """Generate action signal.

        Args:
            rating: 1-5 star rating from diagnostor
            capital_flow: Capital flow signal from detector
            diag_scores: Dict with keys like 'sentiment', 'trend', etc.
            tv_data: TvScreenerData or None
            closes: Recent close prices array (for support price calculation)
        """
        conditions = self._check_resonance(capital_flow, diag_scores, tv_data)
        resonance_count = len(conditions)

        if resonance_count >= self.resonance_min:
            support = self._calc_support(closes)
            stop_loss = self._calc_stop_loss(tv_data)

            return ActionSignal(
                level="resonance",
                advice=self._build_resonance_advice(conditions, support, stop_loss),
                resonance_count=resonance_count,
                resonance_details=conditions,
                support_price=support,
                stop_loss_price=stop_loss,
            )

        return ActionSignal(
            level="conservative",
            advice=self.CONSERVATIVE_MAP.get(rating, "暂时观望，关注变化"),
            resonance_count=resonance_count,
            resonance_details=conditions,
        )

    def _check_resonance(self, capital_flow, diag_scores, tv_data) -> list[str]:
        """Check 5 resonance conditions, return list of matched descriptions."""
        conditions: list[str] = []

        # Condition 1: RSI oversold — tvscreener preferred, diagnostor fallback
        rsi = None
        if tv_data is not None and getattr(tv_data, "rsi_14", None) is not None:
            rsi = tv_data.rsi_14
        elif diag_scores.get("sentiment") is not None:
            rsi = diag_scores["sentiment"]
        if rsi is not None and rsi < self.oversold_rsi:
            conditions.append(f"RSI超卖({rsi:.1f})")

        # Condition 2: MACD histogram positive
        if tv_data is not None and getattr(tv_data, "macd_hist", None) is not None:
            if tv_data.macd_hist > 0:
                conditions.append("MACD多头")

        # Condition 3: Capital flow inflow
        if capital_flow.signal in ("小幅流入", "大幅流入"):
            conditions.append(f"资金{capital_flow.signal}")

        # Condition 4: Price near Bollinger lower band
        if tv_data is not None:
            price = getattr(tv_data, "price", None)
            lower = getattr(tv_data, "bollinger_lower", None)
            if price is not None and lower is not None and lower > 0:
                distance = (price - lower) / price
                if distance < self.bollinger_margin:
                    conditions.append("触及布林下轨")

        # Condition 5: TradingView recommendation = Buy/Strong Buy
        if tv_data is not None and getattr(tv_data, "recommendation", None) is not None:
            if tv_data.recommendation in self.tv_buy_signals:
                conditions.append(f"TV推荐:{tv_data.recommendation}")

        return conditions

    def _calc_support(self, closes: np.ndarray | None) -> float | None:
        """Support price = recent 20-day low."""
        if closes is None or len(closes) == 0:
            return None
        recent = closes[-20:] if len(closes) >= 20 else closes
        return float(np.min(recent))

    def _calc_stop_loss(self, tv_data) -> float | None:
        """Stop loss = Bollinger lower band * (1 - margin)."""
        if tv_data is None:
            return None
        lower = getattr(tv_data, "bollinger_lower", None)
        if lower is None:
            return None
        return round(float(lower) * (1 - self.stop_loss_margin), 2)

    def _build_resonance_advice(self, conditions, support, stop_loss) -> str:
        count = len(conditions)
        detail = "、".join(conditions)
        advice = f"多重信号共振（{count}/5）：{detail}。可考虑轻仓试探。"
        if support is not None:
            advice += f"参考支撑位{support:.2f}元。"
        if stop_loss is not None:
            advice += f"建议止损{stop_loss:.2f}元。"
        advice += "严格控制仓位，以上不构成投资建议。"
        return advice
