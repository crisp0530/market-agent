"""Stock characterization: classify as 游资票/机构票/机游合力票/普通票."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from market_analyst.schemas_retail import StockCharacterization


class StockCharacterizer:
    """Classify a stock's trading character based on multi-dimensional scoring."""

    MIN_DAYS = 10

    def __init__(self, config: dict):
        cfg = config.get("characterization", {})
        self.turnover_high = cfg.get("turnover_high_threshold", 8.0)
        self.turnover_low = cfg.get("turnover_low_threshold", 3.0)
        self.cap_small = cfg.get("market_cap_small", 200)
        self.cap_large = cfg.get("market_cap_large", 500)
        self.hot_threshold = cfg.get("hot_money_threshold", 65)
        self.inst_threshold = cfg.get("institutional_threshold", 65)
        self.weights = cfg.get("weights", {
            "turnover": 0.25, "volatility": 0.20, "volume_pattern": 0.20,
            "limit_up_freq": 0.15, "institutional_holding": 0.10,
            "market_cap": 0.10,
        })
        self.optional_dims = {"institutional_holding", "market_cap"}

    def characterize(
        self,
        symbol: str,
        raw_df: pd.DataFrame,
        market: str,
        market_cap: float | None = None,
        institutional_pct: float | None = None,
    ) -> StockCharacterization:
        name = raw_df.iloc[0]["name"] if not raw_df.empty and "name" in raw_df.columns else symbol

        if raw_df.empty or len(raw_df) < self.MIN_DAYS:
            return self._default_result(symbol, name, market)

        closes = raw_df["close"].values.astype(float)
        highs = raw_df["high"].values.astype(float)
        lows = raw_df["low"].values.astype(float)
        volumes = raw_df["volume"].values.astype(float)

        dims: dict[str, float] = {}
        dims["turnover"] = self._score_turnover(volumes, closes, market_cap)
        dims["volatility"] = self._score_volatility(closes, highs, lows)
        dims["volume_pattern"] = self._score_volume_pattern(volumes)
        dims["limit_up_freq"] = self._score_limit_up_frequency(closes, market)

        if institutional_pct is not None:
            dims["institutional_holding"] = self._score_institutional(institutional_pct)
        if market_cap is not None:
            dims["market_cap"] = self._score_market_cap(market_cap)

        available = list(dims.keys())

        active_weights = {k: self.weights[k] for k in available if k in self.weights}
        total_w = sum(active_weights.values())
        if total_w <= 0:
            return self._default_result(symbol, name, market)
        norm_weights = {k: v / total_w for k, v in active_weights.items()}

        hot_money = sum(
            (dims[k] if k not in ("institutional_holding", "market_cap") else (100 - dims[k]))
            * norm_weights[k]
            for k in available if k in norm_weights
        )
        institutional = sum(
            ((100 - dims[k]) if k not in ("institutional_holding", "market_cap") else dims[k])
            * norm_weights[k]
            for k in available if k in norm_weights
        )

        hot_money = float(np.clip(hot_money, 0, 100))
        institutional = float(np.clip(institutional, 0, 100))

        character_type = self._classify(hot_money, institutional)
        evidence = self._build_evidence(dims, market_cap, institutional_pct, market)
        tips = self._get_tips(character_type)

        return StockCharacterization(
            symbol=symbol, name=name, market=market,
            character_type=character_type,
            hot_money_score=round(hot_money, 1),
            institutional_score=round(institutional, 1),
            available_dimensions=available,
            key_evidence=evidence, analysis_tips=tips,
        )

    def _score_turnover(self, volumes: np.ndarray, closes: np.ndarray, market_cap: float | None) -> float:
        if market_cap is None or market_cap <= 0:
            return 50.0
        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        avg_close = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
        daily_turnover_pct = (avg_vol * avg_close) / (market_cap * 1e8) * 100
        return float(np.clip(daily_turnover_pct / 15 * 100, 0, 100))

    def _score_volatility(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        if len(closes) < 5:
            return 50.0
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        atr_pct = atr / closes[-1] * 100 if closes[-1] > 0 else 0
        return float(np.clip(atr_pct / 8 * 100, 0, 100))

    def _score_volume_pattern(self, volumes: np.ndarray) -> float:
        if len(volumes) < 10:
            return 50.0
        avg_vol = np.mean(volumes)
        if avg_vol <= 0:
            return 50.0
        volume_ratios = volumes / avg_vol
        spike_count = np.sum(volume_ratios > 2.0)
        cv = np.std(volumes) / avg_vol if avg_vol > 0 else 0
        spike_score = float(np.clip(spike_count / 6 * 100, 0, 100))
        cv_score = float(np.clip(cv / 0.8 * 100, 0, 100))
        return (spike_score * 0.6 + cv_score * 0.4)

    def _score_limit_up_frequency(self, closes: np.ndarray, market: str) -> float:
        if len(closes) < 5:
            return 50.0
        daily_returns = np.diff(closes) / closes[:-1] * 100
        threshold = 9.5 if market == "cn" else 8.0
        big_days_all = np.sum(daily_returns >= threshold)
        big_days_high = np.sum(daily_returns >= 7.0) if market == "cn" else np.sum(daily_returns >= 5.0)
        score = big_days_all * 25.0 + big_days_high * 8.0
        return float(np.clip(score, 0, 100))

    def _score_institutional(self, institutional_pct: float | None) -> float:
        if institutional_pct is None:
            return 50.0
        return float(np.clip(institutional_pct / 60 * 100, 0, 100))

    def _score_market_cap(self, market_cap: float | None) -> float:
        if market_cap is None:
            return 50.0
        return float(np.clip(market_cap / 2000 * 100, 0, 100))

    def _classify(self, hot: float, inst: float) -> str:
        if hot > self.hot_threshold and inst < (100 - self.hot_threshold):
            return "游资票"
        if inst > self.inst_threshold and hot < (100 - self.inst_threshold):
            return "机构票"
        if hot > 45 and inst > 45:
            return "机游合力票"
        return "普通票"

    def _build_evidence(self, dims: dict, market_cap, inst_pct, market) -> list[str]:
        evidence = []
        turnover = dims.get("turnover", 50)
        volatility = dims.get("volatility", 50)
        limit_up = dims.get("limit_up_freq", 50)
        if turnover > 70:
            evidence.append("换手率活跃，游资参与度高")
        elif turnover < 30:
            evidence.append("换手率低，持仓稳定")
        if volatility > 70:
            evidence.append("波动率大，短线资金博弈明显")
        elif volatility < 30:
            evidence.append("波动率低，走势稳健")
        if limit_up > 50:
            evidence.append("近期有涨停或大阳线，辨识度高")
        if market_cap is not None:
            if market_cap < 200:
                evidence.append(f"总市值{market_cap:.0f}亿，偏小盘")
            elif market_cap > 500:
                evidence.append(f"总市值{market_cap:.0f}亿，大盘股")
        if inst_pct is not None:
            if inst_pct > 30:
                evidence.append(f"机构持仓{inst_pct:.1f}%，机构参与度高")
            elif inst_pct < 10:
                evidence.append(f"机构持仓{inst_pct:.1f}%，散户为主")
        return evidence[:5]

    def _get_tips(self, character_type: str) -> str:
        tips_map = {
            "游资票": "关注市场辨识度、情绪周期、板块梯队位置，快进快出",
            "机构票": "关注基本面、业绩预期、估值水平，波段持有",
            "机游合力票": "兼顾基本面和情绪面，关注放量突破信号",
            "普通票": "无明显主力特征，建议观望或小仓位参与",
        }
        return tips_map.get(character_type, tips_map["普通票"])

    def _default_result(self, symbol: str, name: str, market: str) -> StockCharacterization:
        return StockCharacterization(
            symbol=symbol, name=name, market=market,
            character_type="普通票", hot_money_score=50.0, institutional_score=50.0,
            available_dimensions=[],
            key_evidence=["数据不足，无法准确定性"], analysis_tips="数据不足，建议观望",
        )
