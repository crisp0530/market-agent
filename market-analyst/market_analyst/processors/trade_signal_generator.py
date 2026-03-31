"""Three-layer trade signal generator: market + stock + character adjustment."""
from __future__ import annotations

import numpy as np
from loguru import logger

from market_analyst.schemas_retail import TradeSignal


class TradeSignalGenerator:
    """Generate 大吉/小吉/平/小凶/大凶 trade signals."""

    SIGNAL_MAP = [
        (80, "大吉"),
        (60, "小吉"),
        (40, "平"),
        (20, "小凶"),
        (0, "大凶"),
    ]

    def __init__(self, config: dict):
        cfg = config.get("trade_signal", {})
        self.market_weight = cfg.get("market_weight", 0.3)
        self.stock_weight = cfg.get("stock_weight", 0.5)
        self.char_weight = cfg.get("character_weight", 0.2)
        self.hm_sentiment_boost = cfg.get("hot_money_sentiment_boost", 1.5)
        self.hm_trend_reduction = cfg.get("hot_money_trend_reduction", 0.7)
        self.inst_trend_boost = cfg.get("institutional_trend_boost", 1.3)
        self.inst_sentiment_reduction = cfg.get("institutional_sentiment_reduction", 0.8)

    def generate(
        self,
        symbol: str,
        name: str,
        market: str,
        market_score: float,
        stock_scores: dict[str, float],
        character_type: str,
        risk_warnings: list[str] | None = None,
    ) -> TradeSignal:
        valid_scores = {k: v for k, v in stock_scores.items() if v is not None}
        raw_stock = float(np.mean(list(valid_scores.values()))) if valid_scores else 50.0

        character_score = self._adjust_stock_score(valid_scores, character_type)

        composite = (
            market_score * self.market_weight
            + raw_stock * self.stock_weight
            + character_score * self.char_weight
        )
        composite = float(np.clip(composite, 0, 100))

        signal = self._map_signal(composite)
        reasons = self._build_reasons(market_score, raw_stock, stock_scores, character_type)

        return TradeSignal(
            symbol=symbol, name=name, market=market,
            signal=signal, score=round(composite, 1),
            market_score=round(market_score, 1),
            stock_score=round(raw_stock, 1),
            character_score=round(character_score, 1),
            character_type=character_type,
            score_breakdown={k: round(v, 1) for k, v in valid_scores.items()},
            reasons=reasons,
            risk_warnings=risk_warnings or [],
        )

    def _adjust_stock_score(self, scores: dict[str, float], character_type: str) -> float:
        dimension_weights = {
            "trend": 1.0, "momentum": 1.0, "sentiment": 1.0,
            "volatility": 1.0, "flow": 1.0,
        }

        if character_type == "游资票":
            dimension_weights["sentiment"] = self.hm_sentiment_boost
            dimension_weights["trend"] = self.hm_trend_reduction
        elif character_type == "机构票":
            dimension_weights["trend"] = self.inst_trend_boost
            dimension_weights["sentiment"] = self.inst_sentiment_reduction

        weighted_sum = 0.0
        weight_total = 0.0
        for dim, val in scores.items():
            if val is not None and dim in dimension_weights:
                w = dimension_weights[dim]
                weighted_sum += val * w
                weight_total += w

        return weighted_sum / weight_total if weight_total > 0 else 50.0

    def _map_signal(self, score: float) -> str:
        for threshold, label in self.SIGNAL_MAP:
            if score >= threshold:
                return label
        return "大凶"

    def _build_reasons(self, market_score, stock_score, scores, character_type) -> list[str]:
        reasons = []
        if market_score >= 60:
            reasons.append("大盘环境偏暖，有利于操作")
        elif market_score < 40:
            reasons.append("大盘环境偏弱，注意风险")

        trend = scores.get("trend", 50)
        momentum = scores.get("momentum", 50)
        if trend >= 65:
            reasons.append("趋势稳健，均线多头排列")
        elif trend < 35:
            reasons.append("趋势偏弱，均线空头")

        if momentum >= 65:
            reasons.append("动量充足，近期表现强势")
        elif momentum < 35:
            reasons.append("动量不足，涨幅有限")

        flow = scores.get("flow")
        if flow is not None and flow >= 65:
            reasons.append("资金持续流入")
        elif flow is not None and flow < 35:
            reasons.append("资金流出明显")

        return reasons[:3]
