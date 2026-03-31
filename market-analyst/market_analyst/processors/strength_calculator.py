"""相对强弱计算器 — 纯数学，不消耗 API"""
import pandas as pd
import numpy as np
from loguru import logger


class StrengthCalculator:
    """计算 ETF 相对强弱排名"""

    def __init__(self, config: dict):
        weights = config.get("strength", {}).get("weights", {})
        self.w_5d = weights.get("roc_5d", 0.5)
        self.w_20d = weights.get("roc_20d", 0.3)
        self.w_60d = weights.get("roc_60d", 0.2)

        tiers = config.get("strength", {}).get("tiers", {})
        self.tier_thresholds = {
            "T1": tiers.get("T1", 80),
            "T2": tiers.get("T2", 60),
            "T3": tiers.get("T3", 40),
        }

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        输入: 原始数据 DataFrame (多天数据，多个symbol)
        输出: 每个symbol的最新强弱排名 DataFrame

        按 market(us/cn) 分别独立排名
        """
        if df.empty:
            return pd.DataFrame()

        results = []

        for market in df["market"].unique():
            market_df = df[df["market"] == market]
            market_result = self._calculate_market(market_df)
            results.append(market_result)

        if not results:
            return pd.DataFrame()

        result = pd.concat(results, ignore_index=True)

        # 全局 Z-score：跨市场可比指标，将 roc_5d 标准化为 z 分数
        std_5d = result["roc_5d"].std()
        if std_5d and std_5d > 0:
            result["global_zscore_5d"] = (result["roc_5d"] - result["roc_5d"].mean()) / std_5d
        else:
            result["global_zscore_5d"] = 0.0

        # 市场温度：每个市场的 5d ROC 中位数，反映市场整体热度
        for market in result["market"].unique():
            mask = result["market"] == market
            result.loc[mask, "market_temp_5d"] = result.loc[mask, "roc_5d"].median()

        return result

    def _calculate_market(self, df: pd.DataFrame) -> pd.DataFrame:
        """对单个市场的数据计算 ROC + 排名 + 梯队"""
        rows = []

        for symbol in df["symbol"].unique():
            sym_df = df[df["symbol"] == symbol].sort_values("date")

            if len(sym_df) < 5:
                logger.debug(f"数据不足(< 5天)，跳过: {symbol}")
                continue

            latest = sym_df.iloc[-1]
            close = latest["close"]

            # 计算 ROC
            roc_5d = self._calc_roc(sym_df, 5)
            roc_20d = self._calc_roc(sym_df, 20)
            roc_60d = self._calc_roc(sym_df, 60)

            # Delta ROC：当前 5d ROC 与 5 天前的 5d ROC 之差（动量加速度）
            # 数据不足（< 11 天）时默认为 0
            roc_5d_prev = self._calc_roc_at_offset(sym_df, period=5, offset=5)
            delta_roc_5d = roc_5d - roc_5d_prev if roc_5d_prev is not None else 0.0

            rows.append({
                "symbol": latest["symbol"],
                "name": latest["name"],
                "sector": latest["sector"],
                "market": latest["market"],
                "close": close,
                "roc_5d": roc_5d,
                "roc_20d": roc_20d,
                "roc_60d": roc_60d,
                "delta_roc_5d": delta_roc_5d,
            })

        result = pd.DataFrame(rows)
        if result.empty:
            return result

        # 百分位排名 (0-100)
        for period in ["5d", "20d", "60d"]:
            col = f"roc_{period}"
            rank_col = f"rank_{period}_pct"
            result[rank_col] = result[col].rank(pct=True) * 100

        # 综合得分
        result["composite_score"] = (
            self.w_5d * result["rank_5d_pct"] +
            self.w_20d * result["rank_20d_pct"] +
            self.w_60d * result["rank_60d_pct"]
        )

        # 梯队划分
        result["tier"] = result["composite_score"].apply(self._assign_tier)

        # 按综合得分降序
        result = result.sort_values("composite_score", ascending=False).reset_index(drop=True)

        return result

    def _calc_roc(self, df: pd.DataFrame, days: int) -> float:
        """计算 N 日变化率 (%)"""
        if len(df) < days + 1:
            if len(df) >= 2:
                base = df.iloc[0]["close"]
                if base == 0:
                    return 0.0
                return (df.iloc[-1]["close"] / base - 1) * 100
            return 0.0
        base = df.iloc[-days - 1]["close"]
        if base == 0:
            return 0.0
        return (df.iloc[-1]["close"] / base - 1) * 100

    def _calc_roc_at_offset(self, df: pd.DataFrame, period: int, offset: int) -> float | None:
        """计算历史某个偏移位置的 ROC (%)

        从末尾往前偏移 offset 天作为"当时的最新点"，再往前 period 天作为基准，
        计算该区间的变化率。数据不足时返回 None。

        例: period=5, offset=5 → 用倒数第6个点 vs 倒数第11个点，
        即"5天前的5日ROC"
        """
        # 需要至少 offset + period + 1 行数据
        if len(df) < offset + period + 1:
            return None
        end_price = df.iloc[-(offset + 1)]["close"]
        start_price = df.iloc[-(offset + period + 1)]["close"]
        if start_price == 0:
            return None
        return (end_price / start_price - 1) * 100

    def _assign_tier(self, score: float) -> str:
        if score >= self.tier_thresholds["T1"]:
            return "T1"
        elif score >= self.tier_thresholds["T2"]:
            return "T2"
        elif score >= self.tier_thresholds["T3"]:
            return "T3"
        else:
            return "T4"
