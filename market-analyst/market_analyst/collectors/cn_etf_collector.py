"""A股 ETF 数据收集器 - yfinance 为主，AKShare 为备"""
import pandas as pd
import yfinance as yf
from .base_collector import BaseCollector
from loguru import logger


class CNETFCollector(BaseCollector):
    """A股 ETF 数据收集器"""

    def __init__(self):
        super().__init__(name="cn_etf")

    @staticmethod
    def _to_yfinance_symbol(code: str) -> str:
        """将A股代码转换为 yfinance 格式
        沪市 (51xxxx, 58xxxx, 56xxxx, 510xxx, 512xxx, 513xxx, 515xxx, 516xxx, 518xxx) → .SS
        深市 (15xxxx, 16xxxx) → .SZ
        """
        if code.startswith(("51", "58", "56")):
            return f"{code}.SS"
        elif code.startswith(("15", "16")):
            return f"{code}.SZ"
        else:
            # 默认尝试沪市
            return f"{code}.SS"

    def _fetch_data(self, symbols: list, lookback_days: int) -> pd.DataFrame:
        """
        symbols: [{"symbol": "510300", "name": "沪深300ETF", "sector": "宽基指数"}, ...]
        使用 yfinance 批量下载A股ETF数据
        """
        # 构建 yfinance 格式的代码映射
        yf_to_info = {}
        ticker_list = []
        for s in symbols:
            yf_sym = self._to_yfinance_symbol(s["symbol"])
            yf_to_info[yf_sym] = s
            ticker_list.append(yf_sym)

        # 批量下载
        period = f"{lookback_days + 10}d"
        raw = yf.download(ticker_list, period=period, group_by="ticker", progress=False, threads=True)

        rows = []
        for yf_sym, sym_info in yf_to_info.items():
            try:
                if len(ticker_list) == 1:
                    df_sym = raw
                else:
                    df_sym = raw[yf_sym] if yf_sym in raw.columns.get_level_values(0) else None

                if df_sym is None or df_sym.empty:
                    logger.warning(f"无数据: {sym_info['symbol']} ({sym_info['name']})")
                    continue

                df_sym = df_sym.dropna(subset=["Close"]).tail(lookback_days)

                for date, row in df_sym.iterrows():
                    rows.append({
                        "symbol": sym_info["symbol"],  # 保留原始A股代码
                        "name": sym_info["name"],
                        "sector": sym_info["sector"],
                        "market": "cn",
                        "date": pd.Timestamp(date),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })
            except Exception as e:
                logger.warning(f"yfinance failed for {sym_info['symbol']} ({sym_info['name']}): {e}. Falling back to AKShare.")
                continue

        if rows:
            logger.info(f"yfinance 获取 {len(set(r['symbol'] for r in rows))} 个A股ETF")
        else:
            logger.warning("yfinance failed for all symbols: no data returned. Falling back to AKShare.")
            rows = self._fetch_via_akshare(symbols, lookback_days)
            if rows:
                logger.info(f"Successfully fetched {len(set(r['symbol'] for r in rows))} symbols via AKShare fallback")
            else:
                logger.error("AKShare fallback also failed: no data returned for any symbol")

        return pd.DataFrame(rows)

    def _fetch_via_akshare(self, symbols: list, lookback_days: int) -> list:
        """AKShare 备用方案"""
        import time
        from datetime import datetime, timedelta

        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare 未安装，跳过备用方案")
            return []

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y%m%d")

        rows = []
        for i, sym_info in enumerate(symbols):
            sym = sym_info["symbol"]
            if i > 0:
                time.sleep(1.5)
            try:
                df_raw = ak.fund_etf_hist_em(
                    symbol=sym, period="daily",
                    start_date=start_date, end_date=end_date, adjust="qfq",
                )
                if df_raw is None or df_raw.empty:
                    continue

                df_raw = df_raw.tail(lookback_days)
                for _, row in df_raw.iterrows():
                    rows.append({
                        "symbol": sym, "name": sym_info["name"],
                        "sector": sym_info["sector"], "market": "cn",
                        "date": pd.Timestamp(row["日期"]),
                        "open": float(row["开盘"]), "high": float(row["最高"]),
                        "low": float(row["最低"]), "close": float(row["收盘"]),
                        "volume": float(row["成交量"]),
                    })
                logger.info(f"Successfully fetched {sym} ({sym_info['name']}) via AKShare fallback: {len(df_raw)} days")
            except Exception as e:
                logger.error(f"AKShare also failed for {sym} ({sym_info['name']}): {e}")
                continue

        return rows
