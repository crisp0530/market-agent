"""美股 ETF 数据收集器 - 使用 yfinance"""
import pandas as pd
import yfinance as yf
from .base_collector import BaseCollector
from loguru import logger


class USETFCollector(BaseCollector):
    """美股 ETF 数据收集器"""

    def __init__(self):
        super().__init__(name="us_etf")

    def _fetch_data(self, symbols: list, lookback_days: int) -> pd.DataFrame:
        """
        symbols 是 list of dict: [{"symbol": "SPY", "name": "S&P 500", "sector": "大盘指数"}, ...]
        使用 yfinance.download 批量下载（一次 API 调用），比逐个下载快得多。
        """
        ticker_list = [s["symbol"] for s in symbols]
        symbol_map = {s["symbol"]: s for s in symbols}

        # 批量下载
        period = f"{lookback_days + 10}d"  # 多取几天防止不够
        raw = yf.download(
            ticker_list,
            period=period,
            group_by="ticker",
            progress=False,
            threads=True,
        )

        rows = []
        for sym_info in symbols:
            sym = sym_info["symbol"]
            try:
                if len(ticker_list) == 1:
                    df_sym = raw  # 单个标的时 yfinance 返回格式不同
                else:
                    df_sym = (
                        raw[sym]
                        if sym in raw.columns.get_level_values(0)
                        else None
                    )

                if df_sym is None or df_sym.empty:
                    logger.warning(f"无数据: {sym}")
                    continue

                df_sym = df_sym.dropna(subset=["Close"]).tail(lookback_days)

                for date, row in df_sym.iterrows():
                    rows.append({
                        "symbol": sym,
                        "name": sym_info["name"],
                        "sector": sym_info["sector"],
                        "market": "us",
                        "date": pd.Timestamp(date),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })
            except Exception as e:
                logger.warning(f"处理 {sym} 失败: {e}")
                continue

        return pd.DataFrame(rows)
