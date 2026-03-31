"""TradingView 技术指标补充收集器 — 为 T1/T4 极端标的拉取独立技术指标

只对梯队排名最强(T1)和最弱(T4)的标的调用 tvscreener，
补充 RSI/MACD/CMF/MFI/相对成交量/TradingView综合评级等独立因子。
这些指标由 TradingView 独立计算，与我们的 ROC 体系互为交叉验证。
"""
from typing import Optional
import pandas as pd
from loguru import logger

try:
    from tvscreener import Market, StockField, StockScreener, SymbolType
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False
    logger.warning("tvscreener 未安装，跳过 TradingView 指标补充")


# 我们需要的字段
TV_FIELDS = [
    StockField.NAME,
    StockField.PRICE,
    StockField.RELATIVE_VOLUME,
    StockField.CHAIKIN_MONEY_FLOW_20,
    StockField.MONEY_FLOW_14,
    StockField.RELATIVE_STRENGTH_INDEX_14,
    StockField.MACD_LEVEL_12_26,
    StockField.MACD_SIGNAL_12_26,
    StockField.MACD_HIST,
    StockField.MOVING_AVERAGES_RATING,
    StockField.RECOMMENDATION_MARK,
] if TV_AVAILABLE else []


class TVIndicatorCollector:
    """从 TradingView 补充技术指标（仅对 T1/T4 标的）"""

    def __init__(self, config: dict = None):
        self.enabled = TV_AVAILABLE

    def collect_for_extremes(self, strength_df: pd.DataFrame) -> pd.DataFrame:
        """对 T1/T4 标的查询 TradingView 技术指标，合并到 strength_df。"""
        if not self.enabled:
            logger.info("TradingView 指标: 不可用（tvscreener 未安装）")
            return strength_df

        extreme_df = strength_df[strength_df["tier"].isin(["T1", "T4"])]
        if extreme_df.empty:
            return strength_df

        logger.info(f"TradingView 指标: 查询 {len(extreme_df)} 个 T1/T4 标的...")

        results = []

        # 按市场批量查询
        for market in extreme_df["market"].unique():
            market_symbols = extreme_df[extreme_df["market"] == market]["symbol"].tolist()
            tv_market = self._resolve_market(market)
            if tv_market is None:
                continue
            batch_results = self._query_batch(market_symbols, tv_market, market)
            results.extend(batch_results)

        if not results:
            logger.warning("TradingView 指标: 未获取到任何数据")
            return strength_df

        tv_df = pd.DataFrame(results)
        logger.info(f"TradingView 指标: 成功获取 {len(tv_df)} 个标的")

        existing_tv = [c for c in strength_df.columns if c.startswith("tv_")]
        if existing_tv:
            strength_df = strength_df.drop(columns=existing_tv)

        result = strength_df.merge(tv_df, on="symbol", how="left")
        return result

    def _query_batch(self, symbols: list, tv_market, market: str) -> list:
        """批量查询一个市场的所有标的，在本地按 Symbol 列匹配"""
        try:
            ss = StockScreener()
            ss.set_markets(tv_market)
            ss.set_range(0, 3000)
            ss.set_symbol_types(SymbolType.ETF)
            ss.select(*TV_FIELDS)
            df = ss.get()

            if df.empty:
                return []

            # 从 Symbol 列提取 ticker（格式: "AMEX:SPY" → "SPY"）
            df["_ticker"] = df["Symbol"].apply(
                lambda x: str(x).split(":")[-1] if pd.notna(x) else ""
            )

            results = []
            for sym in symbols:
                match_token = self._to_tv_token(sym)
                matched = df[df["_ticker"] == match_token]
                if matched.empty:
                    # 尝试包含匹配（A股等场景）
                    matched = df[df["_ticker"].str.contains(match_token, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    results.append({
                        "symbol": sym,
                        "tv_rsi": self._safe_float(row, "Relative Strength Index (14)"),
                        "tv_macd": self._safe_float(row, "MACD Level (12, 26)"),
                        "tv_macd_signal": self._safe_float(row, "MACD Signal (12, 26)"),
                        "tv_macd_hist": self._safe_float(row, "MACD Hist"),
                        "tv_cmf": self._safe_float(row, "Chaikin Money Flow (20)"),
                        "tv_mfi": self._safe_float(row, "Money Flow (14)"),
                        "tv_rel_volume": self._safe_float(row, "Relative Volume"),
                        "tv_ma_rating": self._safe_float(row, "Moving Averages Rating"),
                        "tv_recommendation": self._safe_str(row, "Analyst Rating"),
                    })

            return results
        except (ValueError, KeyError, ConnectionError, Exception) as e:
            # tvscreener 网络请求或数据解析都可能失败，保留 Exception 兜底
            logger.debug(f"TradingView 批量查询 {market} 失败: {e}")
            return []

    @staticmethod
    def _resolve_market(market: str) -> Optional["Market"]:
        """将 market-analyst 的市场标识映射到 tvscreener 的 Market 枚举"""
        if not TV_AVAILABLE:
            return None
        mapping = {
            "us": Market.AMERICA,
            "cn": Market.CHINA,
        }
        return mapping.get(market)

    @staticmethod
    def _to_tv_token(symbol: str) -> str:
        """将 market-analyst 的 symbol 转为 TradingView Symbol 列的 ticker 部分"""
        # 美股: SPY, QQQ 等直接用
        # A股: 510300 直接用
        # 全局: ^VIX → VIX, GC=F → GCF
        return symbol.replace("^", "").replace("=", "")

    @staticmethod
    def _safe_float(row, col: str) -> Optional[float]:
        try:
            val = row.get(col)
            if val is not None and pd.notna(val):
                return round(float(val), 4)
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _safe_str(row, col: str) -> Optional[str]:
        try:
            val = row.get(col)
            if val is not None and pd.notna(val):
                return str(val)
        except (ValueError, TypeError):
            pass
        return None
