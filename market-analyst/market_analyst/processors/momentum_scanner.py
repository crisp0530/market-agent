"""Market-wide multi-day momentum scanner.

Scans US and CN markets via TradingView Screener for stocks with
strong multi-day momentum (5d >15% or monthly >30%), independent
of ETF tier rankings.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

try:
    from tvscreener import Market, StockField, StockScreener
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False


class MomentumScanner:
    """Scan for multi-day momentum surges across entire markets."""

    def __init__(self, config: dict = None):
        cfg = (config or {}).get("momentum_scan", {})
        self.enabled = cfg.get("enabled", True) and TV_AVAILABLE

        us_cfg = cfg.get("us", {})
        self.us_min_cap = float(us_cfg.get("min_market_cap", 3e9))
        self.us_min_avg_vol = float(us_cfg.get("min_avg_volume", 300000))

        cn_cfg = cfg.get("cn", {})
        self.cn_min_cap = float(cn_cfg.get("min_market_cap", 3e9))
        self.cn_min_avg_vol = float(cn_cfg.get("min_avg_volume", 100000))

        thresholds = cfg.get("thresholds", {})
        self.threshold_5d = thresholds.get("perf_5d", 15)
        self.threshold_20d = thresholds.get("perf_20d", 30)

        self.max_results = cfg.get("max_results", 20)

        # A股过滤：科创板(688)需50万、创业板(300)需10万门槛
        cn_cfg_filter = cn_cfg.get("exclude_prefixes", ["688", "300"])
        self.cn_exclude_prefixes = tuple(cn_cfg_filter)

    def scan(self) -> dict:
        """Scan US and CN markets for momentum surges.

        Returns: {"us_momentum": [...], "cn_momentum": [...]}
        """
        if not self.enabled:
            logger.info("Momentum scan: disabled")
            return {"us_momentum": [], "cn_momentum": []}

        us = self._scan_market(
            Market.AMERICA, self.us_min_cap, self.us_min_avg_vol, "us"
        )
        cn = self._scan_market(
            Market.CHINA, self.cn_min_cap, self.cn_min_avg_vol, "cn"
        )

        logger.info(
            f"Momentum scan: {len(us)} US + {len(cn)} CN surges"
        )
        return {"us_momentum": us, "cn_momentum": cn}

    def _scan_market(
        self, tv_market, min_cap: float, min_avg_vol: float, market_label: str
    ) -> list[dict]:
        """Query TradingView for momentum stocks in one market."""
        try:
            # 5-day momentum scan
            results_5d = self._query_tv(
                tv_market, min_cap, min_avg_vol,
                StockField.PERF_5D, self.threshold_5d
            )
            # Monthly momentum scan
            results_1m = self._query_tv(
                tv_market, min_cap, min_avg_vol,
                StockField.MONTHLY_PERFORMANCE, self.threshold_20d
            )

            # Merge and deduplicate by symbol
            merged = {}
            for row in results_5d:
                sym = row["symbol"]
                row["_hit_5d"] = True
                merged[sym] = row

            for row in results_1m:
                sym = row["symbol"]
                if sym in merged:
                    merged[sym]["_hit_20d"] = True
                    # Update 20d value if available from this query
                    if row.get("perf_20d") and not merged[sym].get("perf_20d"):
                        merged[sym]["perf_20d"] = row["perf_20d"]
                else:
                    row["_hit_20d"] = True
                    merged[sym] = row

            # Filter CN restricted boards
            if market_label == "cn" and self.cn_exclude_prefixes:
                before = len(merged)
                merged = {
                    sym: item for sym, item in merged.items()
                    if not sym.startswith(self.cn_exclude_prefixes)
                }
                filtered = before - len(merged)
                if filtered:
                    logger.debug(f"Momentum: filtered {filtered} CN restricted stocks (688/300)")

            # Classify triggers and build output
            output = []
            for sym, item in merged.items():
                perf_5d = item.get("perf_5d", 0) or 0
                perf_20d = item.get("perf_20d", 0) or 0
                trigger = self._classify_trigger(perf_5d, perf_20d)
                if trigger is None:
                    continue
                item["trigger"] = trigger
                item["market"] = market_label
                # Clean internal keys
                item.pop("_hit_5d", None)
                item.pop("_hit_20d", None)
                output.append(item)

            # Sort by 5d performance descending
            output.sort(key=lambda x: x.get("perf_5d", 0), reverse=True)
            return output[: self.max_results]

        except Exception as e:
            logger.warning(f"Momentum scan ({market_label}) failed: {e}")
            return []

    def _query_tv(
        self, tv_market, min_cap: float, min_avg_vol: float,
        perf_field, threshold: float
    ) -> list[dict]:
        """Execute a single TradingView screener query."""
        ss = StockScreener()
        ss.set_markets(tv_market)
        ss.set_range(0, 50)
        ss.select(
            StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
            StockField.PERF_5D, StockField.MONTHLY_PERFORMANCE,
            StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
            StockField.CHAIKIN_MONEY_FLOW_20,
            StockField.MARKET_CAPITALIZATION,
            StockField.SECTOR, StockField.INDUSTRY,
            StockField.AVERAGE_VOLUME_30_DAY,
        )
        ss.where(StockField.MARKET_CAPITALIZATION > min_cap)
        ss.where(StockField.AVERAGE_VOLUME_30_DAY > min_avg_vol)
        ss.where(perf_field > threshold)

        df = ss.get()
        if df.empty:
            return []

        # Filter out OTC
        df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]

        is_cn = (tv_market == Market.CHINA)
        results = []
        for _, r in df.iterrows():
            sym = str(r.get("Symbol", "")).split(":")[-1]
            cap = float(r.get("Market Capitalization", 0))
            cap_display = round(cap / 1e8, 1) if is_cn else round(cap / 1e9, 1)
            results.append({
                "symbol": sym,
                "name": r.get("Name", sym),
                "price": round(float(r.get("Price", 0)), 2),
                "change_pct": round(float(r.get("Change %", 0)), 2),
                "perf_5d": round(float(r.get("Perf 5d", 0)), 2),
                "perf_20d": round(float(r.get("Monthly Performance", 0)), 2),
                "rel_volume": round(float(r.get("Relative Volume", 0)), 2),
                "rsi": round(float(r.get("Relative Strength Index (14)", 0)), 1),
                "cmf": round(float(r.get("Chaikin Money Flow (20)", 0)), 3),
                "market_cap_b": cap_display,
                "market_cap_unit": "亿" if is_cn else "B",
                "sector": str(r.get("Sector", "")),
                "industry": str(r.get("Industry", "")),
            })
        return results

    def _classify_trigger(self, perf_5d: float, perf_20d: float) -> str | None:
        """Classify which threshold was triggered."""
        hit_5d = perf_5d >= self.threshold_5d
        hit_20d = perf_20d >= self.threshold_20d
        if hit_5d and hit_20d:
            return "both"
        if hit_5d:
            return "5d"
        if hit_20d:
            return "20d"
        return None
