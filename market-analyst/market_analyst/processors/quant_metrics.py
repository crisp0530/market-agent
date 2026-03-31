"""量化指标计算 — Sharpe / 最大回撤 / 年化收益 / 年化波动率 / 财富指数"""
import numpy as np
import pandas as pd
from loguru import logger


class QuantMetrics:
    """为 ETF 数据计算量化风险/回报指标"""

    def __init__(self, periods_per_year: int = 252):
        """
        periods_per_year: 每年交易日数
        - 日线数据: 252
        - 月线数据: 12
        """
        self.periods_per_year = periods_per_year

    def calculate_all(self, raw_df: pd.DataFrame, strength_df: pd.DataFrame) -> pd.DataFrame:
        """
        为每个 symbol 计算完整量化指标，合并到 strength_df 中

        raw_df: 原始日线数据 (symbol, date, close, ...)
        strength_df: 已有的强弱排名数据

        新增列: ann_return, ann_vol, sharpe, max_drawdown, max_dd_date, calmar_ratio, variance_drag
        """
        if raw_df.empty or strength_df.empty:
            return strength_df

        metrics_rows = []

        for symbol in strength_df["symbol"].unique():
            sym_df = raw_df[raw_df["symbol"] == symbol].sort_values("date")

            if len(sym_df) < 10:
                # 数据太少，跳过
                metrics_rows.append({
                    "symbol": symbol,
                    "ann_return": np.nan,
                    "ann_vol": np.nan,
                    "sharpe": np.nan,
                    "max_drawdown": np.nan,
                    "max_dd_date": None,
                    "calmar_ratio": np.nan,
                    "variance_drag": np.nan,
                })
                continue

            prices = sym_df["close"].values

            # 防止除零
            safe_prices = np.where(prices[:-1] == 0, 1e-10, prices[:-1])
            returns = np.diff(prices) / safe_prices

            # 年化收益率
            compound_growth = np.prod(1 + returns)
            n_periods = len(returns)
            ann_return = compound_growth ** (self.periods_per_year / n_periods) - 1

            # 年化波动率
            ann_vol = np.std(returns, ddof=1) * np.sqrt(self.periods_per_year)

            # Sharpe 比率 (raw, 无风险利率=0)
            sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

            # 最大回撤
            wealth_index = np.cumprod(1 + returns)
            previous_peaks = np.maximum.accumulate(wealth_index)
            drawdowns = (wealth_index - previous_peaks) / previous_peaks
            max_drawdown = np.min(drawdowns)
            max_dd_idx = np.argmin(drawdowns)
            max_dd_date = sym_df["date"].iloc[max_dd_idx + 1] if max_dd_idx + 1 < len(sym_df) else None

            # Calmar 比率 (年化收益 / |最大回撤|)
            calmar = ann_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

            # 方差损耗 ≈ σ²/2
            variance_drag = (ann_vol ** 2) / 2

            metrics_rows.append({
                "symbol": symbol,
                "ann_return": round(ann_return * 100, 2),       # 百分比
                "ann_vol": round(ann_vol * 100, 2),             # 百分比
                "sharpe": round(sharpe, 3),
                "max_drawdown": round(max_drawdown * 100, 2),   # 百分比 (负数)
                "max_dd_date": max_dd_date,
                "calmar_ratio": round(calmar, 3),
                "variance_drag": round(variance_drag * 100, 2), # 百分比
            })

        metrics_df = pd.DataFrame(metrics_rows)

        # 合并到 strength_df
        result = strength_df.merge(metrics_df, on="symbol", how="left")

        logger.info(f"量化指标计算完成: {len(metrics_rows)} 个标的")
        return result

    @staticmethod
    def compute_wealth_index(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        计算单个 symbol 的财富指数（用于绘图）
        返回 DataFrame: date, wealth, drawdown, previous_peak
        """
        sym_df = raw_df[raw_df["symbol"] == symbol].sort_values("date").copy()
        if len(sym_df) < 2:
            return pd.DataFrame()

        prices = sym_df["close"].values
        returns = np.diff(prices) / prices[:-1]

        wealth = np.cumprod(1 + returns)
        peaks = np.maximum.accumulate(wealth)
        dd = (wealth - peaks) / peaks

        result = pd.DataFrame({
            "date": sym_df["date"].iloc[1:].values,
            "wealth": wealth,
            "drawdown": dd,
            "previous_peak": peaks,
        })

        return result

    @staticmethod
    def compute_return_series(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """计算单个 symbol 的收益率序列（用于绘图）"""
        sym_df = raw_df[raw_df["symbol"] == symbol].sort_values("date").copy()
        if len(sym_df) < 2:
            return pd.DataFrame()

        prices = sym_df["close"].values
        returns = np.diff(prices) / prices[:-1]

        return pd.DataFrame({
            "date": sym_df["date"].iloc[1:].values,
            "return": returns,
        })
