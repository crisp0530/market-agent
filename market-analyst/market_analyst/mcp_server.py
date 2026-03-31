"""Market Analyst MCP Server — FastMCP entry point."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from dotenv import load_dotenv
from loguru import logger
from fastmcp import FastMCP

from market_analyst.schemas import (
    AnomalySignal,
    CommentaryData,
    CycleSignal,
    FearScoreResult,
    MarketOverview,
    MomentumItem,
    NewsItem,
    ReportResult,
    SectorStrength,
    SectorStrengthItem,
    StockDiagnosis,
    ToolError,
)

# ---------------------------------------------------------------------------
# Globals (lazy-loaded)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
_strength_df: pd.DataFrame | None = None
_raw_df: pd.DataFrame | None = None
_config: dict | None = None
_universe: dict | None = None

mcp = FastMCP(
    "market-analyst",
    instructions="市场分析引擎：板块强弱、个股诊断、恐慌评分、异常检测",
)


def _load_config() -> dict:
    global _config, _universe
    if _config is None:
        env_path = BASE_DIR / "config" / ".env"
        if env_path.exists():
            load_dotenv(str(env_path))
        config_path = BASE_DIR / "config" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    if _universe is None:
        universe_path = BASE_DIR / "config" / "etf_universe.yaml"
        with open(universe_path, "r", encoding="utf-8") as f:
            _universe = yaml.safe_load(f)
    return _config


def _ensure_data(market: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load or refresh the core pipeline data (strength_df + raw_df)."""
    global _strength_df, _raw_df

    if _strength_df is not None and _raw_df is not None:
        if market and market != "all":
            mask = _strength_df["market"] == market
            return _strength_df[mask], _raw_df[_raw_df["symbol"].isin(_strength_df[mask]["symbol"])]
        return _strength_df, _raw_df

    config = _load_config()
    from market_analyst.utils.cache import DataCache
    cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    cached_strength = cache.get("_strength", max_age_hours=8)

    if cached_strength is not None and not cached_strength.empty:
        _strength_df = cached_strength
        raw_parts = []
        for prefix in ["us_etf", "cn_etf", "global_idx"]:
            part = cache.get(f"{prefix}_{today}", max_age_hours=8)
            if part is not None and not part.empty:
                raw_parts.append(part)
        _raw_df = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    else:
        logger.info("No cached data, running pipeline...")
        from market_analyst.collectors.us_etf_collector import USETFCollector
        from market_analyst.collectors.cn_etf_collector import CNETFCollector
        from market_analyst.collectors.global_index_collector import GlobalIndexCollector
        from market_analyst.processors.strength_calculator import StrengthCalculator
        from market_analyst.processors.quant_metrics import QuantMetrics
        from market_analyst.processors.fear_score_calculator import FearScoreCalculator

        lookback = config.get("data", {}).get("lookback_days", 60)
        all_data = []

        if config.get("data", {}).get("us_market", True):
            us = cache.get_or_fetch(
                f"us_etf_{today}",
                lambda: USETFCollector().collect(_universe.get("us_etfs", []), lookback),
                max_age_hours=8,
            )
            all_data.append(us)

        if config.get("data", {}).get("cn_market", True):
            cn = cache.get_or_fetch(
                f"cn_etf_{today}",
                lambda: CNETFCollector().collect(_universe.get("cn_etfs", []), lookback),
                max_age_hours=8,
            )
            all_data.append(cn)

        if config.get("data", {}).get("global_indices", True):
            gl = cache.get_or_fetch(
                f"global_idx_{today}",
                lambda: GlobalIndexCollector().collect(_universe.get("global_indices", []), lookback),
                max_age_hours=8,
            )
            all_data.append(gl)

        valid = [d for d in all_data if d is not None and not d.empty]
        if not valid:
            _raw_df = pd.DataFrame()
            _strength_df = pd.DataFrame()
        else:
            _raw_df = pd.concat(valid, ignore_index=True)
            calc = StrengthCalculator(config)
            _strength_df = calc.calculate(_raw_df)

            qm = QuantMetrics(periods_per_year=252)
            _strength_df = qm.calculate_all(_raw_df, _strength_df)

            if config.get("fear_score", {}).get("enabled", True):
                fc = FearScoreCalculator(config)
                _strength_df = fc.calculate_all(_raw_df, _strength_df)

            cache.set("_strength", _strength_df)

    if market and market != "all":
        mask = _strength_df["market"] == market
        return _strength_df[mask], _raw_df[_raw_df["symbol"].isin(_strength_df[mask]["symbol"])]
    return _strength_df, _raw_df


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fear_label(score: float | None) -> str | None:
    """Convert fear score (0-100) to Chinese label."""
    if score is None:
        return None
    if score < 25:
        return "极贪婪"
    if score < 40:
        return "贪婪"
    if score < 60:
        return "中性"
    if score < 75:
        return "恐慌"
    return "极恐慌"


def _extract_key_indices(strength_df: pd.DataFrame) -> dict[str, float]:
    """Extract key macro indices from global symbols in strength_df."""
    key_symbols = {"^VIX": "VIX", "DX-Y.NYB": "DXY", "GC=F": "黄金", "CL=F": "原油"}
    indices = {}
    for sym, label in key_symbols.items():
        row = strength_df[strength_df["symbol"] == sym]
        if not row.empty and "close" in row.columns:
            indices[label] = round(float(row.iloc[0]["close"]), 2)
    return indices


# ---------------------------------------------------------------------------
# Tool implementations (pure functions, testable without MCP)
# ---------------------------------------------------------------------------

def _get_fear_score_impl(
    strength_df: pd.DataFrame,
    symbol: str | None = None,
    market: str | None = None,
) -> FearScoreResult | ToolError:
    """Pure implementation of get_fear_score."""
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data loaded")

    dim_cols = ["fear_rsi_dim", "fear_drawdown_dim", "fear_streak_dim", "fear_momentum_dim"]

    if symbol:
        row = strength_df[strength_df["symbol"] == symbol]
        if row.empty:
            return ToolError(error="symbol_not_found", message=f"Symbol {symbol} not found")
        r = row.iloc[0]
        dims = {c: float(r[c]) for c in dim_cols if c in r and pd.notna(r[c])}
        return FearScoreResult(
            symbol=symbol,
            market=str(r.get("market", "")),
            fear_score=float(r["fear_score"]) if pd.notna(r.get("fear_score")) else None,
            fear_label=str(r.get("fear_label", "")),
            bottom_score=float(r["bottom_score"]) if pd.notna(r.get("bottom_score")) else None,
            bottom_label=str(r.get("bottom_label", "")),
            dimensions=dims,
        )
    else:
        mkt = market or "all"
        df = strength_df if mkt == "all" else strength_df[strength_df["market"] == mkt]
        if df.empty:
            return ToolError(error="no_data_for_market", message=f"No data for market={mkt}")
        avg_fear = float(df["fear_score"].mean()) if "fear_score" in df.columns else None
        avg_bottom = float(df["bottom_score"].mean()) if "bottom_score" in df.columns else None

        return FearScoreResult(
            market=mkt,
            fear_score=round(avg_fear, 1) if avg_fear else None,
            fear_label=_fear_label(avg_fear),
            bottom_score=round(avg_bottom, 1) if avg_bottom else None,
        )


def _get_market_overview_impl(
    strength_df: pd.DataFrame,
    market: str = "all",
) -> MarketOverview | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data")

    df = strength_df if market == "all" else strength_df[strength_df["market"] == market]
    if df.empty:
        return ToolError(error="no_data_for_market", message=f"No data for {market}")

    t1 = df[df["tier"] == "T1"].sort_values("composite_score", ascending=False)
    t4 = df[df["tier"] == "T4"].sort_values("composite_score", ascending=True)
    advancing = int((df["roc_5d"] > 0).sum())
    declining = int((df["roc_5d"] < 0).sum())

    avg_fear = float(df["fear_score"].mean()) if "fear_score" in df.columns else None

    temp = float(df["market_temp_5d"].iloc[0]) if "market_temp_5d" in df.columns else None

    return MarketOverview(
        market=market,
        market_temp_5d=temp,
        advancing=advancing,
        declining=declining,
        t1_sectors=[
            {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
            for _, r in t1.head(10).iterrows()
        ],
        t4_sectors=[
            {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
            for _, r in t4.head(10).iterrows()
        ],
        fear_score=round(avg_fear, 1) if avg_fear else None,
        fear_label=_fear_label(avg_fear),
        key_indices=_extract_key_indices(strength_df),
    )


def _get_sector_strength_impl(
    strength_df: pd.DataFrame,
    market: str = "all",
    top_n: int = 50,
) -> SectorStrength | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No data")

    df = strength_df if market == "all" else strength_df[strength_df["market"] == market]
    df = df.sort_values("composite_score", ascending=False).head(top_n)

    items = []
    for _, r in df.iterrows():
        items.append(SectorStrengthItem(
            symbol=r["symbol"], name=r["name"], sector=r.get("sector", ""),
            market=r["market"], close=round(float(r["close"]), 2),
            roc_5d=round(float(r["roc_5d"]), 2),
            roc_20d=round(float(r["roc_20d"]), 2),
            roc_60d=round(float(r["roc_60d"]), 2),
            composite_score=round(float(r["composite_score"]), 1),
            tier=r["tier"],
            delta_roc_5d=round(float(r["delta_roc_5d"]), 2) if pd.notna(r.get("delta_roc_5d")) else None,
        ))

    return SectorStrength(market=market, items=items)


def _get_anomalies_impl(
    anomalies: list[dict],
    severity: str = "all",
) -> list[AnomalySignal]:
    results = []
    for a in anomalies:
        if severity != "all" and a.get("severity") != severity:
            continue
        results.append(AnomalySignal(
            type=a["type"],
            severity=a["severity"],
            symbols=a.get("symbols", []),
            description=a.get("description", ""),
            data=a.get("data", {}),
        ))
    return results


def _get_cycle_signals_impl(signals: list[dict]) -> list[CycleSignal]:
    return [
        CycleSignal(
            symbol=s["symbol"],
            name=s.get("name", s["symbol"]),
            signal_type=s["signal_type"],
            confidence=s.get("confidence", "medium"),
            details={k: v for k, v in s.items()
                     if k not in ("symbol", "name", "signal_type", "confidence")},
        )
        for s in signals
    ]


def _get_commentary_impl(
    strength_df: pd.DataFrame,
    anomalies: list[dict],
    commentary_type: str = "closing",
) -> CommentaryData | ToolError:
    if strength_df.empty:
        return ToolError(error="data_unavailable", message="No market data")

    sorted_df = strength_df.sort_values("roc_5d", ascending=False)
    top = sorted_df.head(5)
    worst = sorted_df.tail(5)

    top_movers = [
        {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
        for _, r in top.iterrows()
    ]
    worst_movers = [
        {"symbol": r["symbol"], "name": r["name"], "roc_5d": round(float(r["roc_5d"]), 2)}
        for _, r in worst.iterrows()
    ]

    market_temp = {}
    for mkt in strength_df["market"].unique():
        mkt_df = strength_df[strength_df["market"] == mkt]
        if "market_temp_5d" in mkt_df.columns and not mkt_df.empty:
            market_temp[mkt] = round(float(mkt_df["market_temp_5d"].iloc[0]), 2)

    anomaly_summaries = [
        a.get("description", "") for a in anomalies
        if a.get("severity") == "high"
    ][:5]

    avg_fear = float(strength_df["fear_score"].mean()) if "fear_score" in strength_df.columns else None

    key_indices_change = {}
    key_symbols = {"^VIX": "VIX", "DX-Y.NYB": "DXY", "GC=F": "黄金", "CL=F": "原油"}
    for sym, label in key_symbols.items():
        row = strength_df[strength_df["symbol"] == sym]
        if not row.empty and "roc_5d" in row.columns:
            key_indices_change[label] = round(float(row.iloc[0]["roc_5d"]), 2)

    return CommentaryData(
        type=commentary_type,
        market_temp=market_temp,
        top_movers=top_movers,
        worst_movers=worst_movers,
        anomalies_summary=anomaly_summaries,
        key_indices_change=key_indices_change,
        fear_score=round(avg_fear, 1) if avg_fear else None,
        fear_label=_fear_label(avg_fear),
    )


def _scan_momentum_impl(
    momentum_data: dict,
    market: str = "us",
) -> list[MomentumItem]:
    items = momentum_data.get(f"{market}_momentum", [])
    return [
        MomentumItem(
            symbol=i["symbol"], name=i.get("name", i["symbol"]),
            market=market,
            perf_5d=i.get("perf_5d"), perf_20d=i.get("perf_20d"),
            trigger=i.get("trigger"), avg_volume=i.get("avg_volume"),
        )
        for i in items
    ]


def _search_news_impl(raw_results: list[dict]) -> list[NewsItem]:
    items = []
    for r in raw_results:
        snippet = r.get("snippet", "")
        summary = snippet[:200] + "..." if len(snippet) > 200 else snippet
        items.append(NewsItem(
            title=r.get("title", ""),
            url=r.get("url", ""),
            summary=summary or None,
        ))
    return items


def _import_and_run_pipeline(skip_ai: bool = False, skip_search: bool = False) -> str | None:
    """Wrapper around main.run() for mocking in tests."""
    from market_analyst.main import run
    return run(skip_ai=skip_ai, skip_search=skip_search)


def _run_full_report_impl(skip_ai: bool = False) -> ReportResult:
    """Synchronous full report generation."""
    try:
        filepath = _import_and_run_pipeline(skip_ai=skip_ai)
        if filepath:
            return ReportResult(status="completed", filepath=str(filepath))
        else:
            return ReportResult(status="failed", message="Pipeline returned no result")
    except Exception as e:
        return ReportResult(status="failed", message=str(e))


def _diagnose_stock_impl(
    stock_df: pd.DataFrame,
    symbol: str,
    name: str,
    market: str,
) -> StockDiagnosis | ToolError:
    if stock_df.empty:
        return ToolError(error="data_unavailable", message=f"No data for {symbol}")

    from market_analyst.processors.stock_diagnostor import StockDiagnostor
    diag = StockDiagnostor()
    result = diag.diagnose(stock_df)

    if result is None:
        return ToolError(error="insufficient_data", message=f"Not enough data for {symbol}")

    return StockDiagnosis(
        symbol=symbol,
        name=name,
        market=market,
        scores={k: result[k] for k in ["trend", "momentum", "sentiment", "volatility", "flow"]},
        rating=result["rating"],
        available_dimensions=result["available_dimensions"],
    )


# ---------------------------------------------------------------------------
# MCP Tool registrations
# ---------------------------------------------------------------------------

@mcp.tool()
def get_fear_score(symbol: Optional[str] = None, market: Optional[str] = None) -> str:
    """获取恐慌/抄底评分。

    指定 symbol 返回单只标的评分，指定 market ("us"/"cn") 返回市场平均评分。

    Args:
        symbol: 股票/ETF 代码，如 "SPY", "510300"
        market: 市场筛选 "us" / "cn" / "all"
    """
    try:
        strength_df, _ = _ensure_data(market)
        result = _get_fear_score_impl(strength_df, symbol=symbol, market=market)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_fear_score error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_market_overview(market: Optional[str] = "all") -> str:
    """获取市场全局概览：温度、涨跌统计、强弱板块、恐慌评分。

    Args:
        market: "us" / "cn" / "all"
    """
    try:
        strength_df, _ = _ensure_data(market)
        result = _get_market_overview_impl(strength_df, market=market or "all")
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_market_overview error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_sector_strength(market: Optional[str] = "all", top_n: Optional[int] = 50) -> str:
    """获取板块/ETF 强弱排名。

    Args:
        market: "us" / "cn" / "all"
        top_n: 返回前 N 个
    """
    try:
        strength_df, _ = _ensure_data(market)
        result = _get_sector_strength_impl(strength_df, market=market or "all", top_n=top_n or 50)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_sector_strength error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_anomalies(market: Optional[str] = "all", severity: Optional[str] = "all") -> str:
    """获取异常信号列表。

    Args:
        market: "us" / "cn" / "all"
        severity: "high" / "all"
    """
    try:
        config = _load_config()
        strength_df, raw_df = _ensure_data(market)
        if strength_df.empty:
            return json.dumps([])

        from market_analyst.processors.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(config)
        anomalies = detector.detect(strength_df, raw_df)

        results = _get_anomalies_impl(anomalies, severity=severity or "all")
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"get_anomalies error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_cycle_signals(market: Optional[str] = "all") -> str:
    """获取周期突破和抛物线加速信号。

    Args:
        market: "us" / "cn" / "all"
    """
    try:
        config = _load_config()
        strength_df, raw_df = _ensure_data(market)
        if strength_df.empty:
            return json.dumps([])

        from market_analyst.processors.cycle_analyzer import CycleAnalyzer
        from market_analyst.processors.signal_generator import SignalGenerator

        cycle = CycleAnalyzer(config)
        strength_df = cycle.analyze(raw_df, strength_df)
        gen = SignalGenerator(config)
        signals = gen.generate(strength_df, raw_df)

        if market and market != "all":
            market_symbols = set(strength_df[strength_df["market"] == market]["symbol"])
            signals = [s for s in signals if s["symbol"] in market_symbols]

        results = _get_cycle_signals_impl(signals)
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"get_cycle_signals error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_market_commentary(type: str = "closing") -> str:
    """获取结构化市场数据摘要，供 agent 合成极简解盘文本。

    Args:
        type: "morning" / "midday" / "closing"
    """
    try:
        config = _load_config()
        strength_df, raw_df = _ensure_data()
        if strength_df.empty:
            return ToolError(error="data_unavailable", message="No data").model_dump_json()

        from market_analyst.processors.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(config)
        anomalies = detector.detect(strength_df, raw_df)

        result = _get_commentary_impl(strength_df, anomalies, commentary_type=type)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_market_commentary error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def diagnose_stock(symbol: str, market: Optional[str] = None) -> str:
    """个股/ETF多维度诊断：趋势、动量、情绪、波动、资金流五维评分 + 综合星级。

    Args:
        symbol: 股票代码，如 "AAPL", "600519", "SPY"
        market: "us" 或 "cn"，不传则自动推断
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        strength_df, raw_df = _ensure_data()
        etf_data = raw_df[raw_df["symbol"] == symbol] if not raw_df.empty else pd.DataFrame()

        if not etf_data.empty:
            name = etf_data.iloc[0].get("name", symbol)
            result = _diagnose_stock_impl(etf_data, symbol, name, market)
        else:
            from market_analyst.collectors.stock_collector import StockCollector
            from market_analyst.utils.cache import DataCache
            config = _load_config()
            cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

            stock_df = cache.get_or_fetch(
                f"stock_{market}_{symbol}",
                lambda: StockCollector().collect_single(symbol, market=market),
                max_age_hours=4,
            )
            name = stock_df.iloc[0]["name"] if not stock_df.empty else symbol
            result = _diagnose_stock_impl(stock_df, symbol, name, market)

        return result.model_dump_json()
    except Exception as e:
        logger.error(f"diagnose_stock error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def scan_momentum(market: Optional[str] = "us", min_return_5d: Optional[float] = None) -> str:
    """扫描多日动量飙升的个股。

    Args:
        market: "us" 或 "cn"
        min_return_5d: 最小 5 日涨幅过滤 (%)
    """
    try:
        config = _load_config()
        from market_analyst.processors.momentum_scanner import MomentumScanner
        scanner = MomentumScanner(config)
        raw_data = scanner.scan()
        results = _scan_momentum_impl(raw_data, market=market or "us")
        if min_return_5d is not None:
            results = [r for r in results if r.perf_5d and r.perf_5d >= min_return_5d]
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"scan_momentum error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def search_market_news(query: str, max_results: Optional[int] = 5) -> str:
    """搜索市场新闻并生成通俗摘要。

    Args:
        query: 搜索关键词
        max_results: 最大返回条数
    """
    try:
        config = _load_config()
        from market_analyst.utils.web_search import WebSearcher
        searcher = WebSearcher(config)
        raw = searcher._search_tavily(query) if config.get("web_search", {}).get("provider") == "tavily" \
            else searcher._search_ddg(query)
        raw = raw[:max_results] if max_results else raw
        results = _search_news_impl(raw)
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    except Exception as e:
        logger.error(f"search_market_news error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def run_full_report(market: Optional[str] = "all", skip_ai: Optional[bool] = False) -> str:
    """触发全量市场分析报告。同步执行，耗时约 1-5 分钟。

    Args:
        market: "us" / "cn" / "all"
        skip_ai: 跳过 AI 分析
    """
    try:
        result = _run_full_report_impl(skip_ai=skip_ai)
        return result.model_dump_json()
    except Exception as e:
        return ReportResult(status="failed", message=str(e)).model_dump_json()


# ---------------------------------------------------------------------------
# Retail investor tools — helpers
# ---------------------------------------------------------------------------

def _fetch_market_cap(symbol: str, market: str) -> float | None:
    """Best-effort market cap fetch (亿元/亿美元)."""
    try:
        if market == "us":
            import yfinance as yf
            info = yf.Ticker(symbol).info
            cap = info.get("marketCap", 0)
            return cap / 1e8 if cap else None
        else:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=symbol)
            if not df.empty:
                row = df[df["item"] == "总市值"]
                if not row.empty:
                    return float(row.iloc[0]["value"]) / 1e8
    except Exception as e:
        logger.debug(f"market_cap fetch failed for {symbol}: {e}")
    return None


def _fetch_institutional_pct(symbol: str, market: str) -> float | None:
    """Best-effort institutional holding percentage."""
    try:
        if market == "cn":
            import akshare as ak
            df = ak.stock_fund_stock_holder(symbol=symbol)
            if not df.empty:
                # Constrain to latest reporting period to avoid double-counting
                period_col = [c for c in df.columns if "日期" in c or "截止日期" in c or "报告期" in c]
                if period_col:
                    latest_period = df[period_col[0]].iloc[0]
                    df = df[df[period_col[0]] == latest_period]
                pct_col = [c for c in df.columns if "占流通" in c or "持股比例" in c or "占总股本" in c]
                if pct_col:
                    return min(float(df[pct_col[0]].sum()), 100.0)
        else:
            import yfinance as yf
            holders = yf.Ticker(symbol).institutional_holders
            if holders is not None and not holders.empty and "pctHeld" in holders.columns:
                return float(holders["pctHeld"].sum() * 100)
    except Exception as e:
        logger.debug(f"institutional_pct fetch failed for {symbol}: {e}")
    return None


# ---------------------------------------------------------------------------
# Retail investor tools
# ---------------------------------------------------------------------------

@mcp.tool()
def characterize_stock(symbol: str, market: Optional[str] = None) -> str:
    """个股定性：判断是游资票、机构票、机游合力票还是普通票。

    Args:
        symbol: 股票代码，如 "AAPL", "600519"
        market: "us" 或 "cn"，不传则自动推断
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        from market_analyst.collectors.stock_collector import StockCollector
        from market_analyst.processors.stock_characterizer import StockCharacterizer
        from market_analyst.utils.cache import DataCache

        config = _load_config()
        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))

        stock_df = cache.get_or_fetch(
            f"stock_{market}_{symbol}",
            lambda: StockCollector().collect_single(symbol, market=market),
            max_age_hours=4,
        )

        market_cap = _fetch_market_cap(symbol, market)
        inst_pct = _fetch_institutional_pct(symbol, market)

        charzer = StockCharacterizer(config)
        result = charzer.characterize(
            symbol=symbol, raw_df=stock_df, market=market,
            market_cap=market_cap, institutional_pct=inst_pct,
        )
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"characterize_stock error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_trade_signal(symbol: str, market: Optional[str] = None) -> str:
    """加减仓建议：综合大盘+个股+定性，给出大吉/小吉/平/小凶/大凶判定。

    Args:
        symbol: 股票代码
        market: "us" 或 "cn"
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        config = _load_config()

        # 1. Market overview score
        strength_df, raw_df = _ensure_data()
        overview = _get_market_overview_impl(strength_df, market=market)
        market_score = max(0, min(100, overview.market_temp_5d if overview.market_temp_5d is not None else 50))

        # 2. Stock diagnosis
        from market_analyst.collectors.stock_collector import StockCollector
        from market_analyst.processors.stock_diagnostor import StockDiagnostor
        from market_analyst.utils.cache import DataCache
        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
        stock_df = cache.get_or_fetch(
            f"stock_{market}_{symbol}",
            lambda: StockCollector().collect_single(symbol, market=market),
            max_age_hours=4,
        )
        diag = StockDiagnostor().diagnose(stock_df)
        if diag is None:
            return ToolError(error="insufficient_data", message=f"个股数据不足: {symbol}").model_dump_json()

        # 3. Characterization (best effort fallback)
        try:
            from market_analyst.processors.stock_characterizer import StockCharacterizer
            market_cap = _fetch_market_cap(symbol, market)
            inst_pct = _fetch_institutional_pct(symbol, market)
            char_result = StockCharacterizer(config).characterize(
                symbol=symbol, raw_df=stock_df, market=market,
                market_cap=market_cap, institutional_pct=inst_pct,
            )
            character_type = char_result.character_type
        except Exception:
            character_type = "普通票"

        # 4. Generate signal
        from market_analyst.processors.trade_signal_generator import TradeSignalGenerator
        name = stock_df.iloc[0]["name"] if not stock_df.empty and "name" in stock_df.columns else symbol
        gen = TradeSignalGenerator(config)
        result = gen.generate(
            symbol=symbol, name=name, market=market,
            market_score=market_score, stock_scores=diag,
            character_type=character_type,
        )
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_trade_signal error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def analyze_earnings(symbol: str, market: Optional[str] = None) -> str:
    """财报解读：拉取最近财报，判断超预期/不及预期，标记ST/减持/质押等风险。

    Args:
        symbol: 股票代码
        market: "us" 或 "cn"
    """
    try:
        clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
        if market is None:
            market = "cn" if clean_symbol.isdigit() else "us"
        symbol = clean_symbol

        config = _load_config()
        from market_analyst.collectors.earnings_collector import EarningsCollector
        from market_analyst.processors.earnings_analyzer import EarningsAnalyzer
        from market_analyst.utils.cache import DataCache

        cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
        data = cache.get_or_fetch_json(
            f"earnings_{market}_{symbol}",
            lambda: EarningsCollector(config).collect(symbol, market=market),
            max_age_hours=24,
        )

        analyzer = EarningsAnalyzer(config)
        result = analyzer.analyze(symbol, market, data)
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"analyze_earnings error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


@mcp.tool()
def get_trading_strategies(symbol: Optional[str] = None, market: Optional[str] = None) -> str:
    """交易策略推荐：结合个股行情推荐适用策略，附盈亏比教育。不传symbol则返回通用策略。

    Args:
        symbol: 股票代码（可选）
        market: "us" 或 "cn"
    """
    try:
        config = _load_config()
        from market_analyst.processors.strategy_matcher import StrategyMatcher
        matcher = StrategyMatcher(config)

        if symbol is None:
            # General mode
            strength_df, raw_df = _ensure_data()
            overview = _get_market_overview_impl(strength_df, market=market or "all")
            market_score = max(0, min(100, overview.market_temp_5d if overview.market_temp_5d is not None else 50))
            fear = overview.fear_score if overview.fear_score is not None else 50
            result = matcher.match_general(market_score=market_score, fear_score=fear)
        else:
            clean_symbol = symbol.split(".")[0] if "." in symbol else symbol
            if market is None:
                market = "cn" if clean_symbol.isdigit() else "us"
            symbol = clean_symbol

            from market_analyst.collectors.stock_collector import StockCollector
            from market_analyst.processors.stock_diagnostor import StockDiagnostor
            from market_analyst.utils.cache import DataCache
            cache = DataCache(str(BASE_DIR / config.get("general", {}).get("cache_dir", "data/cache")))
            stock_df = cache.get_or_fetch(
                f"stock_{market}_{symbol}",
                lambda: StockCollector().collect_single(symbol, market=market),
                max_age_hours=4,
            )

            diag = StockDiagnostor().diagnose(stock_df)
            if diag is None:
                diag = {"trend": 50, "momentum": 50, "sentiment": 50, "volatility": 50}

            try:
                from market_analyst.processors.stock_characterizer import StockCharacterizer
                market_cap = _fetch_market_cap(symbol, market)
                inst_pct = _fetch_institutional_pct(symbol, market)
                char_result = StockCharacterizer(config).characterize(
                    symbol=symbol, raw_df=stock_df, market=market,
                    market_cap=market_cap, institutional_pct=inst_pct,
                )
                character_type = char_result.character_type
            except Exception:
                character_type = "普通票"

            strength_df, _ = _ensure_data()
            fear_result = _get_fear_score_impl(strength_df, market=market)
            fear = fear_result.fear_score if hasattr(fear_result, 'fear_score') and fear_result.fear_score is not None else 50

            name = stock_df.iloc[0]["name"] if not stock_df.empty and "name" in stock_df.columns else symbol
            result = matcher.match(
                symbol=symbol, name=name, market=market,
                character_type=character_type, diagnosis=diag,
                fear_score=fear, sector_tier=None,
            )

        return result.model_dump_json()
    except Exception as e:
        logger.error(f"get_trading_strategies error: {e}")
        return ToolError(error="internal_error", message=str(e)).model_dump_json()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server via stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
