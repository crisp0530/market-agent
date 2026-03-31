#!/usr/bin/env python3
"""Query a single stock symbol from TradingView screener."""
import argparse
import json
import sys

from tvscreener import Market, StockField, StockScreener


# Market name aliases for convenience
MARKET_ALIASES = {
    "HK": "HONGKONG",
    "CN": "CHINA",
    "US": "AMERICA",
    "JP": "JAPAN",
    "UK": "UK",
}


def resolve_market(name: str) -> Market:
    resolved = MARKET_ALIASES.get(name.upper(), name.upper())
    try:
        return getattr(Market, resolved)
    except AttributeError:
        raise ValueError(f"Invalid market: {name}. Available: HONGKONG, CHINA, AMERICA, JAPAN, UK, etc.")


def main() -> int:
    p = argparse.ArgumentParser(description="Query one stock symbol from tvscreener")
    p.add_argument("--symbol", default="HKEX:700", help="e.g. HKEX:700, NASDAQ:AAPL, SHSE:600519")
    p.add_argument("--market", default="HONGKONG", help="Market: HONGKONG/HK, CHINA/CN, AMERICA/US, JAPAN/JP, UK")
    p.add_argument("--csv", default="", help="Optional CSV output path")
    args = p.parse_args()

    try:
        market = resolve_market(args.market)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    ss = StockScreener()
    ss.set_markets(market)
    ss.set_range(0, 500)
    ss.select(
        StockField.NAME,
        StockField.PRICE,
        StockField.CHANGE_PERCENT,
        # Volume & liquidity
        StockField.VOLUME,
        StockField.AVERAGE_VOLUME_10_DAY,
        StockField.AVERAGE_VOLUME_30_DAY,
        StockField.AVERAGE_VOLUME_60_DAY,
        StockField.RELATIVE_VOLUME,
        StockField.CHAIKIN_MONEY_FLOW_20,
        StockField.MONEY_FLOW_14,
        StockField.VWAP_60,
        # Momentum
        StockField.RELATIVE_STRENGTH_INDEX_14,
        StockField.MACD_LEVEL_12_26,
        StockField.MACD_SIGNAL_12_26,
        StockField.MACD_HIST,
        # Moving averages
        StockField.SIMPLE_MOVING_AVERAGE_20,
        StockField.SIMPLE_MOVING_AVERAGE_50,
        StockField.SIMPLE_MOVING_AVERAGE_200,
        StockField.EXPONENTIAL_MOVING_AVERAGE_20,
        StockField.EXPONENTIAL_MOVING_AVERAGE_50,
        StockField.EXPONENTIAL_MOVING_AVERAGE_200,
        # Volatility
        StockField.BOLLINGER_UPPER_BAND_20,
        StockField.BOLLINGER_LOWER_BAND_20,
        StockField.STOCHASTIC_PERCENTK_14_3_3,
        StockField.STOCHASTIC_PERCENTD_14_3_3,
        StockField.AVERAGE_TRUE_RANGE_14,
        # Ratings
        StockField.MOVING_AVERAGES_RATING,
        StockField.RECOMMENDATION_MARK,
    )

    # Server-side filter by ticker to avoid missing symbols outside top-N page.
    token = args.symbol.split(":")[-1]
    ss.where(StockField.NAME == token)
    df = ss.get()

    row = df[df["Symbol"] == args.symbol]
    if row.empty:
        # Exchange prefix may differ (e.g. SHSE:600519 vs SSE:600519), fallback by token.
        row = df[df["Name"].astype(str) == token]

    if row.empty:
        print(json.dumps({"symbol": args.symbol, "found": False}, ensure_ascii=False))
        return 1

    payload = row.iloc[0].to_dict()
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))

    if args.csv:
        row.to_csv(args.csv, index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
