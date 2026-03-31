"""Multi-dimensional stock scoring for retail investor diagnosis."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


class StockDiagnostor:
    """Computes 5-dimension scores (0-100) and 1-5 star rating."""

    MIN_DAYS = 14  # Minimum data points for RSI calculation

    def diagnose(self, df: pd.DataFrame) -> dict | None:
        """Score a single stock across multiple dimensions.

        Args:
            df: OHLCV DataFrame for one stock, sorted by date.

        Returns:
            Dict with keys: trend, momentum, sentiment, volatility, flow (nullable),
            rating (1-5), available_dimensions.
            Returns None if insufficient data.
        """
        if df.empty or len(df) < self.MIN_DAYS:
            return None

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float) if "high" in df.columns else closes
        lows = df["low"].values.astype(float) if "low" in df.columns else closes
        volumes = df["volume"].values.astype(float) if "volume" in df.columns else None

        trend = self._score_trend(closes)
        momentum = self._score_momentum(closes)
        sentiment = self._score_sentiment(closes)
        volatility = self._score_volatility(closes, highs, lows)
        flow = self._score_flow(closes, highs, lows, volumes) if volumes is not None else None

        available = ["trend", "momentum", "sentiment", "volatility"]
        scores = [trend, momentum, sentiment, volatility]
        if flow is not None:
            available.append("flow")
            scores.append(flow)

        avg = np.mean(scores)
        rating = max(1, min(5, int(round(avg / 20))))

        return {
            "trend": round(float(trend), 1),
            "momentum": round(float(momentum), 1),
            "sentiment": round(float(sentiment), 1),
            "volatility": round(float(volatility), 1),
            "flow": round(float(flow), 1) if flow is not None else None,
            "rating": rating,
            "available_dimensions": available,
        }

    def _score_trend(self, closes: np.ndarray) -> float:
        """Trend score: SMA position + direction. 100 = strong uptrend."""
        sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
        sma60 = np.mean(closes[-60:]) if len(closes) >= 60 else np.mean(closes)
        current = closes[-1]

        score = 50.0
        # Price vs SMA20: +/- 25
        if sma20 > 0:
            pct_above_20 = (current - sma20) / sma20
            score += np.clip(pct_above_20 * 500, -25, 25)  # 5% above = +25

        # SMA20 vs SMA60: +/- 25
        if sma60 > 0:
            sma_spread = (sma20 - sma60) / sma60
            score += np.clip(sma_spread * 500, -25, 25)

        return np.clip(score, 0, 100)

    def _score_momentum(self, closes: np.ndarray) -> float:
        """Momentum score: ROC percentile. 100 = strong acceleration."""
        if len(closes) < 5:
            return 50.0

        roc_5d = (closes[-1] / closes[-5] - 1) * 100
        roc_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else roc_5d

        # Map 5d ROC [-10%, +10%] → [0, 100]
        score_5d = np.clip((roc_5d + 10) / 20 * 100, 0, 100)
        # Map 20d ROC [-20%, +20%] → [0, 100]
        score_20d = np.clip((roc_20d + 20) / 40 * 100, 0, 100)

        return float(score_5d * 0.6 + score_20d * 0.4)

    def _score_sentiment(self, closes: np.ndarray) -> float:
        """Sentiment score based on RSI. 50 = neutral, 100 = overbought (bullish momentum)."""
        rsi = self._calc_rsi(closes, 14)
        # RSI naturally ranges 0-100, map to our score
        return float(rsi)

    def _score_volatility(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        """Volatility score. 100 = low vol (stable), 0 = high vol (risky)."""
        if len(closes) < 5:
            return 50.0

        # ATR-based
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        atr_pct = atr / closes[-1] * 100 if closes[-1] > 0 else 0

        # Map ATR% [0%, 5%] → [100, 0] (lower vol = higher score)
        score = np.clip((5 - atr_pct) / 5 * 100, 0, 100)
        return float(score)

    def _score_flow(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray) -> float:
        """Money flow score using CMF-like calculation. 100 = strong inflow."""
        if len(closes) < 5 or volumes is None:
            return 50.0

        hl_range = highs - lows
        hl_range = np.where(hl_range == 0, 1e-10, hl_range)
        mf_multiplier = ((closes - lows) - (highs - closes)) / hl_range
        mf_volume = mf_multiplier * volumes

        cmf_20 = np.sum(mf_volume[-20:]) / np.sum(volumes[-20:]) if len(closes) >= 20 else 0

        # Map CMF [-0.5, +0.5] → [0, 100]
        score = np.clip((cmf_20 + 0.5) * 100, 0, 100)
        return float(score)

    @staticmethod
    def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - 100 / (1 + rs))
