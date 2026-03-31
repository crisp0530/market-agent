"""
Fear Score Calculator
计算 Streak（连涨/连跌）、Fear Score（恐慌分数）、Bottom Score（底部评分）
"""

import numpy as np
import pandas as pd
from loguru import logger


class FearScoreCalculator:
    """恐慌分数与底部评分计算器"""

    def __init__(self, config: dict):
        cfg = config.get("fear_score", {})

        # 权重（每维度满分 25，总分 100）
        self.weights = cfg.get("weights", {
            "rsi": 25, "drawdown": 25, "streak": 25, "momentum": 25
        })

        # Fear 分档阈值 — 支持中英文 key
        raw_fear = cfg.get("fear_labels", {})
        FEAR_KEY_MAP = {
            "extreme_greed": "极贪婪", "greed": "贪婪", "neutral": "中性",
            "fear": "恐慌", "extreme_fear": "极恐慌",
        }
        self.fear_labels_cfg = {
            FEAR_KEY_MAP.get(k, k): v for k, v in raw_fear.items()
        } if raw_fear else {"极贪婪": 25, "贪婪": 40, "中性": 60, "恐慌": 75, "极恐慌": 100}

        # Bottom 分档阈值 — 支持中英文 key
        raw_bottom = cfg.get("bottom_labels", {})
        BOTTOM_KEY_MAP = {
            "none": "无迹象", "early": "早期", "signs": "有迹象",
            "strong": "强信号", "confirmed": "确认",
        }
        self.bottom_labels_cfg = {
            BOTTOM_KEY_MAP.get(k, k): v for k, v in raw_bottom.items()
        } if raw_bottom else {"无迹象": 20, "早期": 40, "有迹象": 60, "强信号": 80, "确认": 100}

    # ──────────────────────────── 入口 ────────────────────────────

    def calculate_all(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """入口方法：依次计算 streak → fear_score → bottom_score"""
        if raw_df is None or strength_df is None or raw_df.empty or strength_df.empty:
            return strength_df

        strength_df = self._calculate_streak(raw_df, strength_df)
        strength_df = self._calculate_fear_score(raw_df, strength_df)
        strength_df = self._calculate_bottom_score(raw_df, strength_df)

        return strength_df

    # ──────────────────────────── Streak ────────────────────────────

    def _calculate_streak(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """计算每个标的的连涨/连跌天数"""
        streaks = {}
        for symbol in strength_df["symbol"].unique():
            sym_data = raw_df[raw_df["symbol"] == symbol].sort_values("date")
            if len(sym_data) < 2:
                streaks[symbol] = 0
                continue

            diffs = sym_data["close"].diff().dropna().values
            if len(diffs) == 0:
                streaks[symbol] = 0
                continue

            last_diff = diffs[-1]
            if last_diff == 0:
                streaks[symbol] = 0
                continue

            # 从最后一天往前找连续同号
            sign = np.sign(last_diff)
            count = 0
            for d in reversed(diffs):
                if np.sign(d) == sign:
                    count += 1
                else:
                    break
            streaks[symbol] = int(count * sign)

        strength_df["streak"] = strength_df["symbol"].map(streaks).fillna(0).astype(int)
        logger.info(f"Streak 计算完成 | 最长连涨: {strength_df['streak'].max()} | 最长连跌: {strength_df['streak'].min()}")
        return strength_df

    # ──────────────────────────── Fear Score ────────────────────────────

    def _calculate_fear_score(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """计算恐慌分数（0-100），越高越恐慌"""
        # 预计算 roc_5d 全市场百分位排名（用于 fallback）
        if "roc_5d" in strength_df.columns:
            valid_roc = strength_df["roc_5d"].dropna()
            if len(valid_roc) > 0:
                strength_df["_roc_5d_pct"] = strength_df["roc_5d"].rank(pct=True) * 100
            else:
                strength_df["_roc_5d_pct"] = 50.0
        else:
            strength_df["_roc_5d_pct"] = 50.0

        fear_rsi = []
        fear_dd = []
        fear_streak = []
        fear_mom = []

        # NOTE: iterrows used intentionally due to complex branching
        # (_fear_dim_drawdown filters raw_df per symbol internally)
        for _, row in strength_df.iterrows():
            roc_5d_pct = row.get("_roc_5d_pct", 50.0)
            if pd.isna(roc_5d_pct):
                roc_5d_pct = 50.0

            fear_rsi.append(self._fear_dim_rsi(row, roc_5d_pct))
            fear_dd.append(self._fear_dim_drawdown(row, raw_df))
            fear_streak.append(self._fear_dim_streak(row.get("streak", 0)))
            fear_mom.append(self._fear_dim_momentum(row))

        strength_df["fear_rsi_dim"] = fear_rsi
        strength_df["fear_drawdown_dim"] = fear_dd
        strength_df["fear_streak_dim"] = fear_streak
        strength_df["fear_momentum_dim"] = fear_mom
        w = self.weights
        w_rsi = w.get("rsi", 25)
        w_dd = w.get("drawdown", 25)
        w_str = w.get("streak", 25)
        w_mom = w.get("momentum", 25)
        total_w = w_rsi + w_dd + w_str + w_mom
        if total_w == 0:
            total_w = 100
        strength_df["fear_score"] = np.clip(
            (strength_df["fear_rsi_dim"] / 25 * w_rsi +
             strength_df["fear_drawdown_dim"] / 25 * w_dd +
             strength_df["fear_streak_dim"] / 25 * w_str +
             strength_df["fear_momentum_dim"] / 25 * w_mom) * (100 / total_w),
            0, 100
        )
        strength_df["fear_label"] = strength_df["fear_score"].apply(self._fear_label)

        # 清理临时列
        strength_df.drop(columns=["_roc_5d_pct"], inplace=True, errors="ignore")

        logger.info(
            f"Fear Score 计算完成 | 均值: {strength_df['fear_score'].mean():.1f} | "
            f"分布: {strength_df['fear_label'].value_counts().to_dict()}"
        )
        return strength_df

    def _fear_dim_rsi(self, row, roc_5d_pct: float) -> float:
        """RSI 维度（0-25）：RSI 越低越恐慌"""
        tv_rsi = row.get("tv_rsi", None)
        if tv_rsi is not None and pd.notna(tv_rsi):
            return float(np.interp(tv_rsi, [20, 30, 50, 70, 80], [25, 20, 12, 5, 0]))
        # fallback: 用 roc_5d 绝对值（不用百分位，避免全市场下跌时被稀释）
        # roc_5d = -10% → 高恐慌, roc_5d = 0 → 中性, roc_5d = +10% → 低恐慌
        roc_5d = row.get("roc_5d", 0)
        if pd.isna(roc_5d):
            roc_5d = 0
        return float(np.interp(roc_5d, [-15, -8, -3, 0, 3, 8, 15], [25, 22, 18, 12, 8, 3, 0]))

    def _fear_dim_drawdown(self, row, raw_df: pd.DataFrame) -> float:
        """回撤维度（0-25）：当前价格距 60 日最高点的距离，越远越恐慌
        始终从 raw_df 计算，不用 max_drawdown（那是历史最大回撤，不反映当前恐慌）"""
        symbol = row.get("symbol", "")
        sym_data = raw_df[raw_df["symbol"] == symbol].sort_values("date")
        if len(sym_data) < 2:
            return 0.0
        recent = sym_data.tail(60)
        high_60 = recent["close"].max()
        if high_60 <= 0:
            return 0.0
        dd_pct = abs((recent["close"].iloc[-1] - high_60) / high_60 * 100)
        return float(np.interp(dd_pct, [0, 3, 8, 15, 25, 40], [0, 3, 8, 15, 22, 25]))

    def _fear_dim_streak(self, streak_val) -> float:
        """连跌维度（0-25）：连跌天数越多越恐慌"""
        if pd.isna(streak_val):
            streak_val = 0
        neg = abs(min(int(streak_val), 0))
        return float(np.interp(neg, [0, 1, 3, 5, 7, 10], [0, 5, 10, 15, 20, 25]))

    def _fear_dim_momentum(self, row) -> float:
        """动量维度（0-25）：动量恶化越多越恐慌"""
        delta = row.get("delta_roc_5d", None)
        if delta is None or pd.isna(delta):
            return 12.5
        return float(np.interp(delta, [-10, -5, 0, 5, 10], [25, 20, 12, 5, 0]))

    def _fear_label(self, score: float) -> str:
        """恐慌分数分档"""
        thresholds = self.fear_labels_cfg
        if score < thresholds.get("极贪婪", 25):
            return "极贪婪"
        elif score < thresholds.get("贪婪", 40):
            return "贪婪"
        elif score < thresholds.get("中性", 60):
            return "中性"
        elif score < thresholds.get("恐慌", 75):
            return "恐慌"
        else:
            return "极恐慌"

    # ──────────────────────────── Bottom Score ────────────────────────────

    def _calculate_bottom_score(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """计算底部评分（0-100），越高越接近底部"""
        # 预计算 roc_5d 全市场百分位
        if "roc_5d" in strength_df.columns:
            valid_roc = strength_df["roc_5d"].dropna()
            if len(valid_roc) > 0:
                strength_df["_roc_5d_pct"] = strength_df["roc_5d"].rank(pct=True) * 100
            else:
                strength_df["_roc_5d_pct"] = 50.0
        else:
            strength_df["_roc_5d_pct"] = 50.0

        bottom_rsi = []
        bottom_dd = []
        bottom_vol = []
        bottom_flow = []

        # NOTE: iterrows used intentionally due to complex branching
        # (_bottom_dim_drawdown, _bottom_dim_volatility, _bottom_dim_flow all filter raw_df per symbol)
        for _, row in strength_df.iterrows():
            symbol = row.get("symbol", "")
            roc_5d_pct = row.get("_roc_5d_pct", 50.0)
            if pd.isna(roc_5d_pct):
                roc_5d_pct = 50.0

            bottom_rsi.append(self._bottom_dim_rsi(row, roc_5d_pct))
            bottom_dd.append(self._bottom_dim_drawdown(row, raw_df))
            bottom_vol.append(self._bottom_dim_volatility(raw_df, symbol))
            bottom_flow.append(self._bottom_dim_flow(row, raw_df, symbol))

        strength_df["bottom_rsi_dim"] = bottom_rsi
        strength_df["bottom_drawdown_dim"] = bottom_dd
        # Backward compatibility for downstream code that still reads the old field name.
        strength_df["bottom_dd_dim"] = strength_df["bottom_drawdown_dim"]
        strength_df["bottom_vol_dim"] = bottom_vol
        strength_df["bottom_flow_dim"] = bottom_flow
        strength_df["bottom_score"] = np.clip(
            strength_df["bottom_rsi_dim"] + strength_df["bottom_drawdown_dim"] +
            strength_df["bottom_vol_dim"] + strength_df["bottom_flow_dim"],
            0, 100
        )
        strength_df["bottom_label"] = strength_df["bottom_score"].apply(self._bottom_label)

        # 清理临时列
        strength_df.drop(columns=["_roc_5d_pct"], inplace=True, errors="ignore")

        logger.info(
            f"Bottom Score 计算完成 | 均值: {strength_df['bottom_score'].mean():.1f} | "
            f"分布: {strength_df['bottom_label'].value_counts().to_dict()}"
        )
        return strength_df

    def _bottom_dim_rsi(self, row, roc_5d_pct: float) -> float:
        """RSI 超卖维度（0-25）：越超卖越可能见底"""
        tv_rsi = row.get("tv_rsi", None)
        if tv_rsi is not None and pd.notna(tv_rsi):
            return float(np.interp(tv_rsi, [20, 30, 40, 50, 60], [25, 20, 10, 5, 0]))
        # fallback: 用 roc_5d 绝对值（跌得越多越可能超卖）
        roc_5d = row.get("roc_5d", 0)
        if pd.isna(roc_5d):
            roc_5d = 0
        return float(np.interp(roc_5d, [-15, -8, -3, 0, 5], [25, 20, 10, 5, 0]))

    def _bottom_dim_drawdown(self, row, raw_df: pd.DataFrame) -> float:
        """回撤深度维度（0-25）：始终从 raw_df 计算距 60 日高点的跌幅"""
        symbol = row.get("symbol", "")
        sym_data = raw_df[raw_df["symbol"] == symbol].sort_values("date")
        if len(sym_data) < 2:
            return 0.0
        recent = sym_data.tail(60)
        high_60 = recent["close"].max()
        if high_60 <= 0:
            return 0.0
        dd_pct = (recent["close"].iloc[-1] - high_60) / high_60 * 100
        return float(np.interp(abs(dd_pct), [0, 5, 10, 20, 30], [0, 5, 15, 20, 25]))

    def _bottom_dim_volatility(self, raw_df: pd.DataFrame, symbol: str) -> float:
        """波动收窄维度（0-25）：近期波动率相对全区间收窄 → 可能在筑底"""
        sym_data = raw_df[raw_df["symbol"] == symbol].sort_values("date")
        if len(sym_data) < 10:
            return 0.0

        returns = sym_data["close"].pct_change().dropna()
        if len(returns) < 10:
            return 0.0

        recent_std = returns.tail(10).std()
        full_std = returns.std()
        if full_std == 0 or pd.isna(full_std):
            return 0.0

        vol_ratio = recent_std / full_std
        return float(np.interp(vol_ratio, [0.3, 0.5, 0.7, 0.9, 1.2], [25, 20, 10, 0, 0]))

    def _bottom_dim_flow(self, row, raw_df: pd.DataFrame, symbol: str) -> float:
        """资金流向维度（0-25）：资金流入 → 可能在吸筹"""
        tv_cmf = row.get("tv_cmf", None)
        if tv_cmf is not None and pd.notna(tv_cmf):
            return float(np.interp(tv_cmf, [-0.2, 0, 0.1, 0.2, 0.3], [0, 0, 10, 20, 25]))

        # fallback: 近 5 日成交量 vs 全区间均值
        sym_data = raw_df[raw_df["symbol"] == symbol].sort_values("date")
        if "volume" not in sym_data.columns or len(sym_data) < 5:
            return 0.0

        recent_vol = sym_data["volume"].tail(5).mean()
        full_vol = sym_data["volume"].mean()
        if full_vol == 0 or pd.isna(full_vol):
            return 0.0

        vol_ratio = recent_vol / full_vol
        return float(np.interp(vol_ratio, [0.5, 0.8, 1.0, 1.5, 2.0], [0, 0, 5, 15, 25]))

    def _bottom_label(self, score: float) -> str:
        """底部评分分档"""
        thresholds = self.bottom_labels_cfg
        if score < thresholds.get("无迹象", 20):
            return "无迹象"
        elif score < thresholds.get("早期", 40):
            return "早期"
        elif score < thresholds.get("有迹象", 60):
            return "有迹象"
        elif score < thresholds.get("强信号", 80):
            return "强信号"
        else:
            return "确认"
