"""突破/抛物线检测器 — 只检测 Stage4(突破) 和 Stage5(抛物线)

瘦身版：60天数据只够可靠检测这两种极端状态。
Stage1/2/3 判定需要更长数据窗口(180天+)和成交量数据，暂不实现。
Lead-Lag 同理，已禁用。
"""
import numpy as np
import pandas as pd
from loguru import logger


STAGE_DESCRIPTIONS = {
    4: "突破 — 穿越60日中点，趋势翻转确认",
    5: "抛物线 — 极端强势，加速上涨",
}

STAGE_COLORS = {
    4: "#3b82f6",  # 蓝 — 突破
    5: "#a855f7",  # 紫 — 抛物线
}


class CycleAnalyzer:
    """只检测 Stage4(突破) 和 Stage5(抛物线)"""

    def __init__(self, config: dict):
        cycle_cfg = config.get("cycle", {})
        self.sma_short = cycle_cfg.get("sma_short", 20)
        self.sma_long = cycle_cfg.get("sma_long", 50)
        self.parabolic_roc_threshold = cycle_cfg.get("parabolic_roc_threshold", 10.0)

    def analyze(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """对每个标的检测是否处于突破或抛物线阶段，追加 cycle_* 列"""
        if raw_df.empty or strength_df.empty:
            return strength_df

        cycle_rows = []

        for symbol in strength_df["symbol"].unique():
            sym_raw = raw_df[raw_df["symbol"] == symbol].sort_values("date")
            if len(sym_raw) < 10:
                cycle_rows.append(self._empty_row(symbol))
                continue

            cycle_rows.append(self._detect(sym_raw, symbol))

        if not cycle_rows:
            return strength_df

        cycle_df = pd.DataFrame(cycle_rows)

        # 清除已有的 cycle_ 列
        existing = [c for c in strength_df.columns if c.startswith("cycle_")]
        if existing:
            strength_df = strength_df.drop(columns=existing)

        result = strength_df.merge(cycle_df, on="symbol", how="left")
        result["cycle_stage"] = result["cycle_stage"].fillna("—")
        result["cycle_stage_num"] = result["cycle_stage_num"].fillna(0).astype(int)

        detected = result[result["cycle_stage_num"] > 0]
        if not detected.empty:
            dist = detected["cycle_stage"].value_counts().to_dict()
            logger.info(f"突破/抛物线检测: {dist}")
        else:
            logger.info("突破/抛物线检测: 无触发")

        return result

    def _detect(self, sym_df: pd.DataFrame, symbol: str) -> dict:
        """检测单个标的是否处于突破或抛物线阶段"""
        closes = sym_df["close"].values
        highs = sym_df["high"].values if "high" in sym_df.columns else closes
        lows = sym_df["low"].values if "low" in sym_df.columns else closes
        current = closes[-1]

        # 关键价位
        range_high = float(np.max(highs))
        range_low = float(np.min(lows))
        range_span = range_high - range_low
        range_mid = (range_high + range_low) / 2
        position = (current - range_low) / range_span if range_span > 0 else 0.5

        # 趋势
        sma_s = self._sma(closes, self.sma_short)
        sma_l = self._sma(closes, self.sma_long)
        trend_up = (sma_s > sma_l) and (current > sma_s)

        # ROC
        roc_20d = self._roc(closes, 20)

        # 波动率
        prev_closes = np.where(closes[:-1] == 0, 1e-10, closes[:-1])
        returns = np.diff(closes) / prev_closes
        recent_vol = float(np.std(returns[-10:])) if len(returns) >= 10 else float(np.std(returns))
        avg_vol = float(np.std(returns))
        vol_expanding = recent_vol > avg_vol * 1.3 if avg_vol > 0 else False

        # 中点穿越（近5日）
        recent_closes = closes[-min(5, len(closes)):]
        cross_mid = any(c < range_mid for c in recent_closes[:-1]) and current >= range_mid

        # === 检测（只有两种结果）===
        stage, stage_num = "—", 0

        if position > 0.92 and trend_up and roc_20d > self.parabolic_roc_threshold and vol_expanding:
            stage, stage_num = "Stage5", 5
        elif cross_mid and trend_up:
            stage, stage_num = "Stage4", 4

        return {
            "symbol": symbol,
            "cycle_stage": stage,
            "cycle_stage_num": stage_num,
            "cycle_confidence": "high" if stage_num > 0 else "none",
            "cycle_position": round(position, 4),
            "cycle_range_high": round(range_high, 4),
            "cycle_range_low": round(range_low, 4),
            "cycle_range_mid": round(range_mid, 4),
            "cycle_trend_up": trend_up,
            "cycle_vol_contracting": False,
            "cycle_sma_short": round(sma_s, 4),
            "cycle_sma_long": round(sma_l, 4),
            "cycle_description": STAGE_DESCRIPTIONS.get(stage_num, ""),
        }

    def detect_lead_lag(self, raw_df: pd.DataFrame, pairs: list = None) -> list:
        """Placeholder for future lead-lag detection. Returns empty list.

        Lead-Lag analysis requires 180+ days of data which exceeds the current
        60-day window. Gated by config ``cycle.lead_lag_enabled`` (default False)
        in main.py, so this stub is only called when explicitly enabled.
        """
        return []

    @staticmethod
    def _sma(data: np.ndarray, period: int) -> float:
        if len(data) < period:
            return float(np.mean(data))
        return float(np.mean(data[-period:]))

    @staticmethod
    def _roc(data: np.ndarray, days: int) -> float:
        if len(data) < days + 1:
            return (data[-1] / data[0] - 1) * 100 if len(data) >= 2 else 0.0
        return (data[-1] / data[-days - 1] - 1) * 100

    @staticmethod
    def _empty_row(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "cycle_stage": "—",
            "cycle_stage_num": 0,
            "cycle_confidence": "none",
            "cycle_position": 0.0,
            "cycle_range_high": 0.0,
            "cycle_range_low": 0.0,
            "cycle_range_mid": 0.0,
            "cycle_trend_up": False,
            "cycle_vol_contracting": False,
            "cycle_sma_short": 0.0,
            "cycle_sma_long": 0.0,
            "cycle_description": "",
        }
