"""TvScreenerProvider: wraps tvscreener CLI scripts to fetch real-time technical indicators."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class TvScreenerData:
    relative_volume: float | None = None
    cmf_20: float | None = None       # Converted to 0-100 score (from raw CMF [-0.5, +0.5])
    mfi_14: float | None = None       # Raw 0-100
    rsi_14: float | None = None       # Raw 0-100
    macd_hist: float | None = None    # Raw value
    recommendation: str | None = None  # e.g. "Buy", "Strong Buy", "Sell"
    price: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None


class TvScreenerProvider:
    """Wraps tvscreener CLI scripts to fetch real-time technical indicators."""

    # tvscreener JSON field names → TvScreenerData field name
    FIELD_ALIASES = {
        "relative_volume": ["Relative Volume"],
        "cmf_20": ["Chaikin Money Flow (20)"],
        "mfi_14": ["Money Flow (14)"],
        "rsi_14": ["Relative Strength Index (14)"],
        "macd_hist": ["MACD Histogram", "MACD Hist"],
        "recommendation": ["Recommendation Mark", "Analyst Rating"],
        "price": ["Price"],
        "sma_20": ["Simple Moving Average (20)"],
        "sma_50": ["Simple Moving Average (50)"],
        "sma_200": ["Simple Moving Average (200)"],
        "bollinger_upper": ["Bollinger Upper Band (20)"],
        "bollinger_lower": ["Bollinger Lower Band (20)"],
    }

    def __init__(self, scripts_dir: str | Path, timeout: int = 15):
        self.scripts_dir = Path(scripts_dir)
        self.timeout = timeout

    def fetch(self, symbol: str, market: str) -> TvScreenerData | None:
        """Fetch real-time indicators. Returns None on any failure."""
        tv_symbol = self._map_symbol(symbol, market)
        if tv_symbol is None:
            return None
        tv_market = self._map_market(market)

        script = self.scripts_dir / "query_symbol.py"
        if not script.exists():
            logger.warning(f"tvscreener script not found: {script}")
            return None

        try:
            result = subprocess.run(
                [sys.executable, str(script), "--symbol", tv_symbol, "--market", tv_market],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if result.returncode != 0:
                logger.warning(f"tvscreener query failed for {tv_symbol}: {result.stderr}")
                return None
            data = json.loads(result.stdout)
            if data.get("found") is False:
                logger.info(f"tvscreener: symbol not found: {tv_symbol}")
                return None
            return self._parse(data)
        except subprocess.TimeoutExpired:
            logger.warning(f"tvscreener timeout for {tv_symbol}")
            return None
        except Exception as e:
            logger.warning(f"tvscreener error for {tv_symbol}: {e}")
            return None

    def _map_symbol(self, symbol: str, market: str) -> str | None:
        """Map stock symbol to tvscreener format."""
        if market == "cn":
            if symbol.startswith(("6", "9")):
                return f"SHSE:{symbol}"
            elif symbol.startswith(("0", "2", "3")):
                return f"SZSE:{symbol}"
            elif symbol.startswith(("4", "8")):
                # 北交所 not supported by tvscreener
                return None
            return f"SHSE:{symbol}"
        else:
            # US stocks: try NASDAQ first (handled by tvscreener fallback)
            return f"NASDAQ:{symbol}"

    def _map_market(self, market: str) -> str:
        return "CHINA" if market == "cn" else "AMERICA"

    def _parse(self, data: dict) -> TvScreenerData:
        """Parse tvscreener JSON output to TvScreenerData."""
        kwargs = {}
        for field_name, aliases in self.FIELD_ALIASES.items():
            val = None
            for alias in aliases:
                candidate = data.get(alias)
                if candidate is not None and candidate != "":
                    val = candidate
                    break

            if val is None:
                continue

            try:
                if field_name == "recommendation":
                    kwargs[field_name] = self._normalize_recommendation(val)
                else:
                    kwargs[field_name] = float(val)
            except (ValueError, TypeError):
                pass

        # Convert raw CMF [-0.5, +0.5] to 0-100 score
        if kwargs.get("cmf_20") is not None:
            raw_cmf = kwargs["cmf_20"]
            kwargs["cmf_20"] = max(0.0, min(100.0, (raw_cmf + 0.5) * 100))

        return TvScreenerData(**kwargs)

    @staticmethod
    def _normalize_recommendation(value) -> str | None:
        """Normalize TradingView recommendation payloads to text labels."""
        if isinstance(value, str):
            text = value.strip()
            return text or None

        numeric = float(value)
        if numeric >= 1:
            return "Strong Buy"
        if numeric >= 0.5:
            return "Buy"
        if numeric <= -1:
            return "Strong Sell"
        if numeric <= -0.5:
            return "Sell"
        return "Neutral"
