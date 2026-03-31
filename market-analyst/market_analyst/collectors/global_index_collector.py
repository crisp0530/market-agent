"""全球宏观指标收集器 - DXY/VIX/黄金/日经/A股大盘等"""
import pandas as pd
import yfinance as yf
from .base_collector import BaseCollector
from loguru import logger


class GlobalIndexCollector(BaseCollector):
    """全球宏观指标收集器"""

    def __init__(self):
        super().__init__(name="global_index")

    def _fetch_data(self, symbols: list, lookback_days: int) -> pd.DataFrame:
        """
        symbols: [{"symbol": "^VIX", "name": "VIX恐慌指数", "sector": "宏观指标"}, ...]
        使用 yfinance 逐个下载（因为指数符号特殊，批量可能有问题）。

        NOTE: yf.download(symbol_list, ...) 可以批量下载提升速度，但一个坏符号会导致
        整个批次失败。当前逐个下载的方式更健壮——单个符号失败不影响其余。
        如果符号列表稳定且全部可靠，可考虑切换到批量模式。
        """
        rows = []
        period = f"{lookback_days + 10}d"

        for sym_info in symbols:
            sym = sym_info["symbol"]
            try:
                ticker = yf.Ticker(sym)
                df_raw = ticker.history(period=period)

                if df_raw is None or df_raw.empty:
                    logger.warning(f"无数据: {sym} ({sym_info['name']})")
                    continue

                df_raw = df_raw.dropna(subset=["Close"]).tail(lookback_days)

                for date, row in df_raw.iterrows():
                    rows.append({
                        "symbol": sym,
                        "name": sym_info["name"],
                        "sector": sym_info.get("sector", "宏观指标"),
                        "market": "global",
                        "date": pd.Timestamp(date).tz_localize(None),  # 去掉时区
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })

                logger.debug(f"✓ {sym} ({sym_info['name']}): {len(df_raw)} 天")

            except (ValueError, KeyError, Exception) as e:
                # yfinance 没有专用异常类，保留 Exception 兜底
                logger.warning(f"获取 {sym} ({sym_info['name']}) 失败: {e}")
                continue

        return pd.DataFrame(rows)
