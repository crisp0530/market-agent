"""On-demand individual stock data collector."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

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

    CN_FETCH_RETRIES = 2

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
        prefixed_symbol = self._to_akshare_symbol(symbol)
        name = self._fetch_cn_name(symbol)

        raw = self._fetch_with_retries(
            lambda: ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=start, end_date=end, adjust="qfq",
            ),
            source=f"stock_zh_a_hist:{symbol}",
        )
        if raw is not None and not raw.empty:
            return self._normalize_cn_hist(raw, symbol=symbol, name=name, lookback_days=lookback_days)

        raw_daily = self._fetch_with_retries(
            lambda: ak.stock_zh_a_daily(symbol=prefixed_symbol),
            source=f"stock_zh_a_daily:{prefixed_symbol}",
        )
        if raw_daily is not None and not raw_daily.empty:
            return self._normalize_cn_daily(raw_daily, symbol=symbol, name=name, lookback_days=lookback_days)

        raw_tx = self._fetch_with_retries(
            lambda: ak.stock_zh_a_hist_tx(
                symbol=prefixed_symbol,
                start_date=start,
                end_date=end,
                adjust="qfq",
            ),
            source=f"stock_zh_a_hist_tx:{prefixed_symbol}",
        )
        if raw_tx is not None and not raw_tx.empty:
            return self._normalize_cn_tx(raw_tx, symbol=symbol, name=name, lookback_days=lookback_days)

        return pd.DataFrame()

    def _fetch_with_retries(self, fetcher: Callable[[], pd.DataFrame], source: str) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.CN_FETCH_RETRIES + 1):
            try:
                data = fetcher()
                if data is not None and not data.empty:
                    return data
            except Exception as exc:
                last_error = exc
                logger.warning(f"{source} attempt {attempt}/{self.CN_FETCH_RETRIES} failed: {exc}")
        if last_error is not None:
            logger.warning(f"{source} exhausted retries: {last_error}")
        return pd.DataFrame()

    @staticmethod
    def _to_akshare_symbol(symbol: str) -> str:
        if symbol.startswith(("sh", "sz", "bj")):
            return symbol
        if symbol.startswith(("6", "9")):
            return f"sh{symbol}"
        if symbol.startswith(("0", "2", "3")):
            return f"sz{symbol}"
        if symbol.startswith(("4", "8")):
            return f"bj{symbol}"
        return symbol

    def _fetch_cn_name(self, symbol: str) -> str:
        try:
            info = ak.stock_individual_info_em(symbol=symbol)
            if not info.empty:
                row = info[info["item"] == "股票简称"]
                if not row.empty:
                    return str(row.iloc[0]["value"])
        except Exception as exc:
            logger.debug(f"Failed to fetch CN stock name for {symbol}: {exc}")
        return symbol

    @staticmethod
    def _normalize_cn_hist(raw: pd.DataFrame, symbol: str, name: str, lookback_days: int) -> pd.DataFrame:
        df = pd.DataFrame({
            "symbol": symbol,
            "name": name,
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

    @staticmethod
    def _normalize_cn_daily(raw: pd.DataFrame, symbol: str, name: str, lookback_days: int) -> pd.DataFrame:
        df = pd.DataFrame({
            "symbol": symbol,
            "name": name,
            "sector": "个股",
            "market": "cn",
            "date": pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d"),
            "open": raw["open"].values,
            "high": raw["high"].values,
            "low": raw["low"].values,
            "close": raw["close"].values,
            "volume": raw["volume"].values,
        })
        return df.tail(lookback_days)

    @staticmethod
    def _normalize_cn_tx(raw: pd.DataFrame, symbol: str, name: str, lookback_days: int) -> pd.DataFrame:
        df = pd.DataFrame({
            "symbol": symbol,
            "name": name,
            "sector": "个股",
            "market": "cn",
            "date": pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d"),
            "open": raw["open"].values,
            "high": raw["high"].values,
            "low": raw["low"].values,
            "close": raw["close"].values,
            "volume": raw["amount"].values,
        })
        return df.tail(lookback_days)
