"""Market Analyst Agent entrypoint."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from loguru import logger


def setup_logging(log_dir: str = "logs") -> None:
    """Configure console + file logging."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add(
        os.path.join(log_dir, "market_analyst_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
    )


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_etf_universe(universe_path: str) -> dict:
    with open(universe_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    """Drop symbols with suspicious price jumps."""
    if df.empty:
        return df

    bad_symbols: set[str] = set()

    for symbol in df["symbol"].unique():
        sym_df = df[df["symbol"] == symbol].sort_values("date")
        if len(sym_df) < 2:
            continue

        is_global = sym_df.iloc[0].get("market", "") == "global"
        daily_threshold = 0.80 if is_global else 0.35
        total_threshold = 5.0 if is_global else 2.0

        closes = sym_df["close"].values
        prev_closes = np.where(closes[:-1] == 0, 1e-10, closes[:-1])
        daily_returns = np.diff(closes) / prev_closes

        max_daily = float(np.max(np.abs(daily_returns)))
        if max_daily > daily_threshold:
            bad_symbols.add(symbol)
            name = sym_df.iloc[0].get("name", symbol)
            logger.warning(f"Removed dirty data: {name}({symbol}) max daily move {max_daily:.1%}")
            continue

        total_return = float(closes[-1] / closes[0] - 1)
        if abs(total_return) > total_threshold:
            bad_symbols.add(symbol)
            name = sym_df.iloc[0].get("name", symbol)
            logger.warning(f"Removed dirty data: {name}({symbol}) total return {total_return:.1%}")

    if bad_symbols:
        logger.info(f"Data cleaning removed {len(bad_symbols)} symbols")
        df = df[~df["symbol"].isin(bad_symbols)]
    else:
        logger.info("Data cleaning passed all symbols")

    return df


def run(config_path: str | None = None, skip_ai: bool = False, skip_search: bool = False, us_only: bool = False):
    """Execute the end-to-end pipeline."""
    base_dir = Path(__file__).parent.parent
    if config_path is None:
        config_path = str(base_dir / "config" / "config.yaml")

    env_path = base_dir / "config" / ".env"
    if env_path.exists():
        load_dotenv(str(env_path))

    config = load_config(config_path)
    universe = load_etf_universe(str(base_dir / "config" / "etf_universe.yaml"))

    setup_logging(str(base_dir / config.get("general", {}).get("log_dir", "logs")))
    logger.info("=" * 60)
    logger.info("Market Analyst Agent started")
    logger.info("=" * 60)

    lookback = config.get("data", {}).get("lookback_days", 60)

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    from market_analyst.collectors.cn_etf_collector import CNETFCollector
    from market_analyst.collectors.global_index_collector import GlobalIndexCollector
    from market_analyst.collectors.us_etf_collector import USETFCollector
    from market_analyst.exporters.obsidian_exporter import ObsidianExporter
    from market_analyst.exporters.json_exporter import JsonExporter
    from market_analyst.processors.anomaly_detector import AnomalyDetector
    from market_analyst.processors.cycle_analyzer import CycleAnalyzer
    from market_analyst.processors.market_analyzer import MarketAnalyzer
    from market_analyst.processors.signal_generator import SignalGenerator
    from market_analyst.processors.strength_calculator import StrengthCalculator
    from market_analyst.utils.cache import DataCache
    from market_analyst.utils.web_search import WebSearcher

    cache = DataCache(str(base_dir / config.get("general", {}).get("cache_dir", "data/cache")))

    logger.info("Step 1/6: collecting data...")
    all_data: list[pd.DataFrame] = []

    if config.get("data", {}).get("us_market", True):
        us_collector = USETFCollector()
        us_symbols = universe.get("us_etfs", [])
        us_data = cache.get_or_fetch(
            f"us_etf_{datetime.now().strftime('%Y%m%d')}",
            lambda: us_collector.collect(us_symbols, lookback),
            max_age_hours=8,
        )
        all_data.append(us_data)
        logger.info(f"  US ETFs: {us_data['symbol'].nunique() if not us_data.empty else 0}")

    if config.get("data", {}).get("cn_market", True) and not us_only:
        cn_collector = CNETFCollector()
        cn_symbols = universe.get("cn_etfs", [])
        cn_data = cache.get_or_fetch(
            f"cn_etf_{datetime.now().strftime('%Y%m%d')}",
            lambda: cn_collector.collect(cn_symbols, lookback),
            max_age_hours=8,
        )
        all_data.append(cn_data)
        logger.info(f"  CN ETFs: {cn_data['symbol'].nunique() if not cn_data.empty else 0}")

    if config.get("data", {}).get("global_indices", True):
        global_collector = GlobalIndexCollector()
        global_symbols = universe.get("global_indices", [])
        global_data = cache.get_or_fetch(
            f"global_idx_{datetime.now().strftime('%Y%m%d')}",
            lambda: global_collector.collect(global_symbols, lookback),
            max_age_hours=8,
        )
        all_data.append(global_data)
        logger.info(f"  Global indices: {global_data['symbol'].nunique() if not global_data.empty else 0}")

    valid_dfs = [d for d in all_data if d is not None and not d.empty]
    if not valid_dfs:
        logger.error("No data returned from all data sources, exiting")
        return None

    raw_df = pd.concat(valid_dfs, ignore_index=True)
    logger.info(f"  Total: {raw_df['symbol'].nunique()} symbols, {len(raw_df)} rows")

    logger.info("Step 1.5: cleaning data...")
    raw_df = clean_raw_data(raw_df)
    if raw_df.empty:
        logger.error("No valid data after cleaning, exiting")
        return None

    logger.info("Step 2/6: calculating strength...")
    calculator = StrengthCalculator(config)
    strength_df = calculator.calculate(raw_df)
    logger.info(f"  Strength ranking completed: {len(strength_df)} symbols")

    logger.info("Step 2.5: calculating quant metrics...")
    from market_analyst.processors.quant_metrics import QuantMetrics

    qm = QuantMetrics(periods_per_year=252)
    strength_df = qm.calculate_all(raw_df, strength_df)
    logger.info("  Quant metrics completed")

    if config.get("tradingview", {}).get("enabled", True):
        logger.info("Step 2.6: collecting TradingView indicators...")
        from market_analyst.collectors.tv_indicator_collector import TVIndicatorCollector

        tv_collector = TVIndicatorCollector(config)
        strength_df = tv_collector.collect_for_extremes(strength_df)

    if config.get("premarket", {}).get("enabled", True):
        logger.info("Step 2.7: collecting premarket data...")
        from market_analyst.collectors.premarket_collector import PremarketCollector

        pm_collector = PremarketCollector(config)
        strength_df = pm_collector.collect(strength_df)

    if config.get("fear_score", {}).get("enabled", True):
        logger.info("Step 2.8: calculating fear/bottom score...")
        from market_analyst.processors.fear_score_calculator import FearScoreCalculator

        fear_calc = FearScoreCalculator(config)
        strength_df = fear_calc.calculate_all(raw_df, strength_df)

    logger.info("Step 3/6: detecting anomalies...")
    detector = AnomalyDetector(config)
    anomalies = detector.detect(strength_df, raw_df)
    logger.info(f"  Detected anomalies: {len(anomalies)}")

    logger.info("Step 3.5: cycle analysis...")
    cycle_analyzer = CycleAnalyzer(config)
    strength_df = cycle_analyzer.analyze(raw_df, strength_df)

    signal_gen = SignalGenerator(config)
    cycle_signals = signal_gen.generate(strength_df, raw_df)
    logger.info(f"  Cycle signals: {len(cycle_signals)}")

    lead_lag = []
    if config.get("cycle", {}).get("lead_lag_enabled", False):
        lead_lag = cycle_analyzer.detect_lead_lag(raw_df)
        logger.info(f"  Lead-lag pairs: {len(lead_lag)}")
    else:
        logger.info("  Lead-lag disabled")

    search_results = []
    if not skip_search and config.get("web_search", {}).get("enabled", True):
        logger.info("Step 4/6: web verification...")
        searcher = WebSearcher(config)
        search_results = searcher.verify_anomalies(anomalies)
        logger.info(f"  Verified anomalies: {len(search_results)}")
    else:
        logger.info("Step 4/6: skipped web verification")

    analysis_text = ""
    if not skip_ai and config.get("analysis", {}).get("enabled", True):
        logger.info("Step 5/6: AI analysis...")
        analyzer = MarketAnalyzer(config)
        analysis_text = analyzer.analyze(strength_df, anomalies, search_results, cycle_signals, lead_lag)
        logger.info(f"  AI analysis length: {len(analysis_text)} chars")
    else:
        logger.info("Step 5/6: skipped AI analysis")

    stock_picks: dict = {}
    if config.get("sector_scan", {}).get("enabled", True):
        logger.info("Step 5.5: sector stock scan...")
        from market_analyst.collectors.sector_scanner import SectorScanner

        scanner = SectorScanner(config)
        stock_picks = scanner.scan(strength_df)

    momentum_data: dict = {}
    if config.get("momentum_scan", {}).get("enabled", True):
        logger.info("Step 5.6: momentum scan...")
        from market_analyst.processors.momentum_scanner import MomentumScanner

        mom_scanner = MomentumScanner(config)
        momentum_data = mom_scanner.scan()

    portfolio_advice: dict = {}
    portfolio_path = base_dir / "config" / "portfolio.yaml"
    if portfolio_path.exists():
        logger.info("Step 5.7: portfolio advice...")
        from market_analyst.processors.portfolio_advisor import PortfolioAdvisor

        advisor = PortfolioAdvisor(str(portfolio_path), config)
        portfolio_advice = advisor.analyze()
        if portfolio_advice.get("items"):
            logger.info(f"  Portfolio: {len(portfolio_advice['items'])} items analyzed")
        else:
            logger.info("  Portfolio: no items configured")

    logger.info("Step 6/6: exporting report...")
    exporter = ObsidianExporter(config)
    filepath = exporter.export(
        strength_df,
        anomalies,
        analysis_text,
        search_results,
        cycle_signals=cycle_signals,
        lead_lag=lead_lag,
        stock_picks=stock_picks,
        momentum_data=momentum_data,
        portfolio_advice=portfolio_advice,
    )
    logger.info(f"  Report exported: {filepath}")

    # JSON export for web dashboard
    json_exporter = JsonExporter(str(base_dir / "data"))
    json_path = json_exporter.export(
        strength_df, anomalies, analysis_text,
        cycle_signals, stock_picks, config,
        momentum_data=momentum_data,
        portfolio_advice=portfolio_advice,
    )
    logger.info(f"  JSON exported: {json_path}")

    logger.info("=" * 60)
    logger.info("Market Analyst Agent completed")
    logger.info("=" * 60)
    return filepath


def main() -> None:
    parser = argparse.ArgumentParser(description="AI market analyst agent")
    parser.add_argument("--config", type=str, help="Path to config file")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI analysis")
    parser.add_argument("--skip-search", action="store_true", help="Skip web verification")
    parser.add_argument("--us-only", action="store_true", help="Only collect US market data")

    args = parser.parse_args()

    result = run(
        config_path=args.config,
        skip_ai=args.skip_ai,
        skip_search=args.skip_search,
        us_only=args.us_only,
    )

    if result:
        print(f"\nReport generated: {result}")
    else:
        print("\nReport generation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
