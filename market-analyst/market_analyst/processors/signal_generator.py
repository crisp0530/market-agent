"""信号生成器 — 只生成突破(breakout)和抛物线(parabolic)信号

瘦身版：去掉 caution/reversal（与梯队系统重叠），只保留有独立价值的信号。
"""
import pandas as pd
import numpy as np
from loguru import logger


class SignalGenerator:
    """基于 Stage4/5 生成突破和抛物线信号"""

    def __init__(self, config: dict):
        cycle_cfg = config.get("cycle", {})
        self.enabled = cycle_cfg.get("signals_enabled", True)
        self.parabolic_roc = cycle_cfg.get("parabolic_roc_threshold", 10.0)
        self.breakout_roc = cycle_cfg.get("breakout_roc_threshold", 3.0)

    def generate(self, strength_df: pd.DataFrame, raw_df: pd.DataFrame) -> list:
        """扫描 Stage4/5 标的，生成信号列表"""
        if not self.enabled or "cycle_stage" not in strength_df.columns:
            return []

        signals = []

        for _, row in strength_df.iterrows():
            stage_num = int(row.get("cycle_stage_num", 0))
            if stage_num not in (4, 5):
                continue
            signal = self._build_signal(row)
            if signal:
                signals.append(signal)

        # breakout 优先于 parabolic
        signals.sort(key=lambda s: 0 if s["signal_type"] == "breakout" else 1)

        if signals:
            logger.info(f"信号: {len(signals)} 个 — {[s['signal_type'] for s in signals]}")

        return signals

    def _build_signal(self, row: pd.Series) -> dict | None:
        g = lambda key, default=0: self._safe_get(row, key, default)

        symbol = row["symbol"]
        name = g("name", symbol)
        stage_num = int(g("cycle_stage_num", 0))
        position = g("cycle_position", 0.5)
        range_high = g("cycle_range_high", 0)
        range_low = g("cycle_range_low", 0)
        range_mid = g("cycle_range_mid", 0)
        roc_5d = g("roc_5d", 0)
        roc_20d = g("roc_20d", 0)
        close = g("close", 0)
        sma_short = g("cycle_sma_short", 0)
        trend_up = bool(g("cycle_trend_up", False))

        range_span = range_high - range_low if range_high > range_low else 1

        if stage_num == 4:
            confidence = "high" if (trend_up and abs(roc_5d) > self.breakout_roc and position > 0.45) else "medium"
            return {
                "symbol": symbol,
                "name": name,
                "signal_type": "breakout",
                "confidence": confidence,
                "key_level": round(range_mid, 2),
                "invalidation": round(range_low + range_span * 0.2, 2),
                "close": round(close, 2),
                "description": f"{name} 突破60日区间中点({range_mid:.2f})，趋势翻转确认中",
            }

        if stage_num == 5:
            confidence = "high" if (roc_20d > self.parabolic_roc and position > 0.95 and trend_up) else "medium"
            inv = sma_short if sma_short > 0 else range_mid
            return {
                "symbol": symbol,
                "name": name,
                "signal_type": "parabolic",
                "confidence": confidence,
                "key_level": round(range_high, 2),
                "invalidation": round(inv, 2),
                "close": round(close, 2),
                "description": f"{name} 抛物线加速，20日涨幅{roc_20d:.1f}%，位置{position:.0%}",
            }

        return None

    @staticmethod
    def _safe_get(row: pd.Series, key: str, default=0):
        val = row.get(key, default)
        return default if pd.isna(val) else val
