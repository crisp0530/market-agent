"""On-demand individual stock data collector."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import akshare as ak
except ImportError:
    ak = None


class StockCollector:
    """Collects OHLCV data for individual stocks on demand."""

    def collect_single(
        self,
        symbol: str,
        market: str = "us",
        lookback_days: int = 60,
    ) -> pd.DataFrame:
        """Fetch OHLCV for a single stock.

        Args:
            symbol: Stock ticker (e.g. "AAPL", "600519")
            market: "us" or "cn"
            lookback_days: Number of trading days to fetch

        Returns:
            DataFrame with columns: symbol, name, sector, market, date, open, high, low, close, volume
        """
        try:
            if market == "cn":
                return self._fetch_cn(symbol, lookback_days)
            else:
                return self._fetch_us(symbol, lookback_days)
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")
            return pd.DataFrame()

    def _fetch_us(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        if yf is None:
            logger.error("yfinance not installed")
            return pd.DataFrame()

        ticker = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=int(lookback_days * 1.5))
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if hist.empty:
            return pd.DataFrame()

        name = ticker.info.get("shortName", symbol)
        sector = ticker.info.get("sector", "个股")

        df = pd.DataFrame({
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "market": "us",
            "date": hist.index.strftime("%Y-%m-%d"),
            "open": hist["Open"].values,
            "high": hist["High"].values,
            "low": hist["Low"].values,
            "close": hist["Close"].values,
            "volume": hist["Volume"].values,
        })
        return df.tail(lookback_days)

    def _fetch_cn(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        if ak is None:
            logger.error("akshare not installed")
            return pd.DataFrame()

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime("%Y%m%d")

        raw = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start, end_date=end, adjust="qfq",
        )
        if raw.empty:
            return pd.DataFrame()

        df = pd.DataFrame({
            "symbol": symbol,
            "name": symbol,  # akshare doesn't always return name
            "sector": "个股",
            "market": "cn",
            "date": pd.to_datetime(raw["日期"]).dt.strftime("%Y-%m-%d"),
            "open": raw["开盘"].values,
            "high": raw["最高"].values,
            "low": raw["最低"].values,
            "close": raw["收盘"].values,
            "volume": raw["成交量"].values,
        })
        return df.tail(lookback_days)
