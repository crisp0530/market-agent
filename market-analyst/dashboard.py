"""Market Analyst Dashboard v2 — Dark Terminal Edition

包含 9 个 Tab：全局概览、恐慌/底部、盘前异动、异常信号、突破/抛物线、
个股机会、板块热力图、量化面板、个股详情
"""
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import yaml
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))


# ============================================================
# Design System — Colors
# ============================================================

COLORS = {
    "bg_primary": "#0a0e17",
    "bg_secondary": "#111827",
    "bg_card": "rgba(255, 255, 255, 0.03)",
    "bg_card_hover": "rgba(255, 255, 255, 0.06)",
    "accent_gold": "#f0b90b",
    "accent_green": "#00d4aa",
    "accent_red": "#ff4757",
    "accent_blue": "#3b82f6",
    "accent_purple": "#a855f7",
    "accent_cyan": "#06b6d4",
    "text_primary": "#e0e0f0",
    "text_secondary": "#8888aa",
    "text_muted": "#555577",
    "border_subtle": "rgba(255, 255, 255, 0.06)",
}

TIER_COLORS = {
    "T1": "#00d4aa",
    "T2": "#3b82f6",
    "T3": "#f59e0b",
    "T4": "#ff4757",
}

FEAR_COLORS = {
    "极贪婪": "#00d4aa",
    "贪婪": "#4ade80",
    "中性": "#f0b90b",
    "恐慌": "#f97316",
    "极恐慌": "#ff4757",
}


# ============================================================
# Plotly Dark Template
# ============================================================

DARK_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            color="#a0a0b8",
            family="JetBrains Mono, Consolas, monospace",
            size=12,
        ),
        title=dict(font=dict(
            color="#e0e0f0",
            family="Outfit, sans-serif",
            size=16,
        )),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.08)",
            linecolor="rgba(255,255,255,0.08)",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.08)",
            linecolor="rgba(255,255,255,0.08)",
            tickfont=dict(size=10),
        ),
        colorway=[
            "#00d4aa", "#f0b90b", "#3b82f6", "#ff4757",
            "#a855f7", "#06b6d4", "#f59e0b", "#ec4899",
        ],
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(255,255,255,0.06)",
            font=dict(color="#8888aa", size=11),
        ),
        hoverlabel=dict(
            bgcolor="#1a1a2e",
            bordercolor="rgba(255,255,255,0.1)",
            font=dict(
                color="#e0e0f0",
                family="JetBrains Mono, monospace",
                size=12,
            ),
        ),
    )
)

pio.templates["dark_terminal"] = DARK_TEMPLATE
pio.templates.default = "dark_terminal"


# ============================================================
# Data Loading
# ============================================================

def load_data():
    """加载缓存数据并计算全部指标"""
    from market_analyst.utils.cache import DataCache
    from market_analyst.processors.strength_calculator import StrengthCalculator
    from market_analyst.processors.anomaly_detector import AnomalyDetector
    from market_analyst.processors.quant_metrics import QuantMetrics
    from market_analyst.processors.cycle_analyzer import CycleAnalyzer
    from market_analyst.processors.signal_generator import SignalGenerator
    from market_analyst.processors.fear_score_calculator import FearScoreCalculator

    base_dir = Path(__file__).parent
    config = yaml.safe_load(open(base_dir / "config" / "config.yaml", encoding="utf-8"))
    cache = DataCache(str(base_dir / "data" / "cache"))
    today = datetime.now().strftime("%Y%m%d")

    us = cache.get(f"us_etf_{today}", max_age_hours=24)
    cn = cache.get(f"cn_etf_{today}", max_age_hours=24)
    gl = cache.get(f"global_idx_{today}", max_age_hours=24)

    dfs = [d for d in [us, cn, gl] if d is not None and not d.empty]
    if not dfs:
        # No cache found — try live data collection
        logger.info("No cached data found, collecting fresh data...")
        import streamlit as _st
        _collect_errors = []

        with _st.spinner("首次加载，正在采集市场数据（约2-3分钟）..."):
            try:
                from market_analyst.collectors.us_etf_collector import USETFCollector
                from market_analyst.collectors.cn_etf_collector import CNETFCollector
                from market_analyst.collectors.global_index_collector import GlobalIndexCollector

                universe = yaml.safe_load(
                    open(base_dir / "config" / "etf_universe.yaml", encoding="utf-8")
                )
                lookback = config.get("data", {}).get("lookback_days", 60)
            except Exception as e:
                logger.error(f"Config/import failed: {e}")
                _collect_errors.append(f"配置加载失败: {e}")

            if not _collect_errors:
                if config.get("data", {}).get("us_market", True):
                    try:
                        us = cache.get_or_fetch(
                            f"us_etf_{today}",
                            lambda: USETFCollector().collect(universe.get("us_etfs", []), lookback),
                            max_age_hours=8,
                        )
                        logger.info(f"US data: {len(us) if us is not None else 0} rows")
                    except Exception as e:
                        _collect_errors.append(f"US 数据采集失败: {e}")
                        logger.error(f"US collection failed: {e}")

                if config.get("data", {}).get("cn_market", True):
                    try:
                        cn = cache.get_or_fetch(
                            f"cn_etf_{today}",
                            lambda: CNETFCollector().collect(universe.get("cn_etfs", []), lookback),
                            max_age_hours=8,
                        )
                        logger.info(f"CN data: {len(cn) if cn is not None else 0} rows")
                    except Exception as e:
                        _collect_errors.append(f"CN 数据采集失败: {e}")
                        logger.error(f"CN collection failed: {e}")

                if config.get("data", {}).get("global_indices", True):
                    try:
                        gl = cache.get_or_fetch(
                            f"global_idx_{today}",
                            lambda: GlobalIndexCollector().collect(universe.get("global_indices", []), lookback),
                            max_age_hours=8,
                        )
                        logger.info(f"Global data: {len(gl) if gl is not None else 0} rows")
                    except Exception as e:
                        _collect_errors.append(f"Global 数据采集失败: {e}")
                        logger.error(f"Global collection failed: {e}")

            dfs = [d for d in [us, cn, gl] if d is not None and not d.empty]

        if _collect_errors and not dfs:
            _st.error("数据采集失败，详细错误：")
            for err in _collect_errors:
                _st.code(err)
            return None, None, None, None, None, None
        elif _collect_errors:
            for err in _collect_errors:
                _st.warning(err)

        if not dfs:
            return None, None, None, None, None, None

    raw_df = pd.concat(dfs, ignore_index=True)

    # 数据清洗
    from main import clean_raw_data
    raw_df = clean_raw_data(raw_df)

    # 强弱排名
    calc = StrengthCalculator(config)
    strength_df = calc.calculate(raw_df)

    # 量化指标
    qm = QuantMetrics(periods_per_year=252)
    strength_df = qm.calculate_all(raw_df, strength_df)

    # TradingView 指标
    try:
        from market_analyst.collectors.tv_indicator_collector import TVIndicatorCollector
        tv = TVIndicatorCollector(config)
        strength_df = tv.collect_for_extremes(strength_df)
    except Exception as e:
        logger.warning(f"TradingView indicator enrichment failed in dashboard: {e}")

    # 盘前数据
    try:
        from market_analyst.collectors.premarket_collector import PremarketCollector
        pm = PremarketCollector(config)
        strength_df = pm.collect(strength_df)
    except Exception as e:
        logger.warning(f"Premarket enrichment failed in dashboard: {e}")

    # 恐慌/底部分数
    fear_calc = FearScoreCalculator(config)
    strength_df = fear_calc.calculate_all(raw_df, strength_df)

    # 异常检测
    detector = AnomalyDetector(config)
    anomalies = detector.detect(strength_df, raw_df)

    # 突破/抛物线
    cycle_analyzer = CycleAnalyzer(config)
    strength_df = cycle_analyzer.analyze(raw_df, strength_df)
    signal_gen = SignalGenerator(config)
    cycle_signals = signal_gen.generate(strength_df, raw_df)

    # 板块扫描
    stock_picks = {}
    try:
        from market_analyst.collectors.sector_scanner import SectorScanner
        scanner = SectorScanner(config)
        stock_picks = scanner.scan(strength_df)
    except Exception as e:
        logger.warning(f"Sector scanner failed in dashboard: {e}")

    return raw_df, strength_df, anomalies, config, cycle_signals, stock_picks


# ============================================================
# Page Config
# ============================================================

st.set_page_config(
    page_title="Market Analyst Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS Injection — Dark Terminal Theme
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');

/* ===== APP BACKGROUND ===== */
.stApp {
    background: linear-gradient(180deg, #0a0e17 0%, #0f1422 50%, #0a0e17 100%) !important;
}

/* ===== SIDEBAR ===== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d0d1f 0%, #080818 100%) !important;
    border-right: 1px solid rgba(240, 185, 11, 0.12) !important;
}

section[data-testid="stSidebar"] .stMarkdown p {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
}

/* ===== METRIC CARDS ===== */
[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 16px 20px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    backdrop-filter: blur(10px);
}

[data-testid="stMetric"]:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 185, 11, 0.25);
    box-shadow: 0 0 24px rgba(240, 185, 11, 0.08), 0 0 48px rgba(240, 185, 11, 0.04);
    transform: translateY(-2px);
}

[data-testid="stMetricLabel"] {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.5px !important;
    text-transform: uppercase !important;
    font-size: 0.72rem !important;
    color: #8888aa !important;
}

[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 1.4rem !important;
    color: #e0e0f0 !important;
}

[data-testid="stMetricDelta"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
}

[data-testid="stMetricDelta"][data-testid-direction="up"] {
    color: #00d4aa !important;
}

[data-testid="stMetricDelta"][data-testid-direction="down"] {
    color: #ff4757 !important;
}

/* ===== TABS ===== */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: rgba(255, 255, 255, 0.015);
    border-radius: 12px;
    padding: 4px 6px;
    border: 1px solid rgba(255, 255, 255, 0.05);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    color: #555577 !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500;
    font-size: 0.82rem;
    padding: 8px 14px;
    transition: all 0.2s ease;
    white-space: nowrap;
}

.stTabs [data-baseweb="tab"]:hover {
    color: #8888aa !important;
    background: rgba(255, 255, 255, 0.03);
}

.stTabs [aria-selected="true"] {
    background: rgba(240, 185, 11, 0.08) !important;
    color: #f0b90b !important;
}

/* Tab bottom indicator */
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #f0b90b !important;
    height: 2px !important;
    border-radius: 1px;
}

/* ===== DATAFRAMES ===== */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    overflow: hidden;
}

[data-testid="stDataFrame"] [data-testid="glideDataEditor"] {
    border-radius: 12px;
}

/* ===== EXPANDERS ===== */
[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px !important;
    margin-bottom: 8px;
    transition: all 0.2s ease;
    overflow: hidden;
}

[data-testid="stExpander"]:hover {
    border-color: rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.03);
}

[data-testid="stExpander"] summary {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500;
}

/* ===== HEADERS ===== */
h1, h2, h3 {
    font-family: 'Outfit', sans-serif !important;
    letter-spacing: -0.02em;
}

/* ===== DIVIDERS ===== */
hr {
    border-color: rgba(255, 255, 255, 0.05) !important;
    margin: 20px 0 !important;
}

/* ===== SELECT BOXES ===== */
[data-baseweb="select"] > div {
    font-family: 'JetBrains Mono', monospace !important;
    background: rgba(255, 255, 255, 0.03) !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
}

/* ===== MULTISELECT ===== */
[data-baseweb="tag"] {
    background: rgba(240, 185, 11, 0.15) !important;
    border: 1px solid rgba(240, 185, 11, 0.3) !important;
    border-radius: 6px !important;
    color: #f0b90b !important;
}

/* ===== ALERTS ===== */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-family: 'Outfit', sans-serif;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.15);
}

/* ===== PROGRESS COLUMNS ===== */
[data-testid="stDataFrame"] .gdg-progress-bar {
    border-radius: 4px;
}

/* ===== JSON VIEWER ===== */
[data-testid="stJson"] {
    background: rgba(0, 0, 0, 0.2) !important;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 12px;
}

/* ===== CUSTOM CLASSES ===== */
.terminal-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 0 20px;
}

.terminal-header h1 {
    margin: 0 !important;
    font-size: 1.8rem !important;
    color: #f0b90b !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
}

.terminal-header p {
    margin: 0 !important;
    color: #555577 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.05em;
}

.terminal-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

.badge-green {
    background: rgba(0, 212, 170, 0.12);
    color: #00d4aa;
    border: 1px solid rgba(0, 212, 170, 0.25);
}

.badge-red {
    background: rgba(255, 71, 87, 0.12);
    color: #ff4757;
    border: 1px solid rgba(255, 71, 87, 0.25);
}

.badge-gold {
    background: rgba(240, 185, 11, 0.12);
    color: #f0b90b;
    border: 1px solid rgba(240, 185, 11, 0.25);
}

.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 12px 0 20px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.section-header .icon {
    font-size: 1.3rem;
}

.section-header .title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.2rem;
    font-weight: 600;
    color: #e0e0f0;
    letter-spacing: -0.01em;
}

.section-header .subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: #555577;
    margin-left: 4px;
}

.signal-card {
    padding: 16px 20px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
}

.signal-card:hover {
    border-color: rgba(255, 255, 255, 0.12);
}

.signal-card .signal-title {
    font-family: 'Outfit', sans-serif;
    font-weight: 600;
    font-size: 0.95rem;
    color: #e0e0f0;
    margin-bottom: 4px;
}

.signal-card .signal-detail {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: #8888aa;
}

.footer-bar {
    text-align: center;
    padding: 20px 0 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
    margin-top: 32px;
}

.footer-bar .main-text {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: #555577;
    letter-spacing: 0.05em;
}

.footer-bar .sub-text {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: #333355;
    margin-top: 4px;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# Helper Functions
# ============================================================

def section_header(icon, title, subtitle=""):
    """Styled section header with icon and optional subtitle."""
    sub_html = f'<span class="subtitle">{subtitle}</span>' if subtitle else ""
    st.markdown(
        f'<div class="section-header">'
        f'<span class="icon">{icon}</span>'
        f'<span class="title">{title}</span>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def severity_badge(severity):
    """Return an HTML badge for anomaly severity."""
    style_map = {
        "high": ("badge-red", "HIGH"),
        "medium": ("badge-gold", "MED"),
        "low": ("badge-green", "LOW"),
    }
    cls, label = style_map.get(severity, ("badge-gold", severity.upper()))
    return f'<span class="terminal-badge {cls}">{label}</span>'


def fear_gauge_color(score):
    """Return the appropriate color for a fear score."""
    if score >= 75:
        return COLORS["accent_red"]
    elif score >= 60:
        return "#f97316"
    elif score >= 40:
        return COLORS["accent_gold"]
    elif score >= 25:
        return "#4ade80"
    return COLORS["accent_green"]


def fear_label(score):
    """Return the text label for a fear score."""
    if score >= 75:
        return "极恐慌"
    elif score >= 60:
        return "恐慌"
    elif score >= 40:
        return "中性"
    elif score >= 25:
        return "贪婪"
    return "极贪婪"


# ============================================================
# Data
# ============================================================

@st.cache_data(ttl=3600)
def cached_load():
    return load_data()


raw_df, strength_df, anomalies, config, cycle_signals, stock_picks = cached_load()

if strength_df is None or strength_df.empty:
    st.markdown(
        '<div style="text-align:center; padding: 60px 0;">'
        '<p style="font-size: 2rem; margin-bottom: 8px;">⚡</p>'
        '<p style="font-family: Outfit, sans-serif; font-size: 1.1rem; color: #8888aa;">'
        '无缓存数据</p>'
        '<p style="font-family: JetBrains Mono, monospace; font-size: 0.8rem; color: #555577;">'
        '数据采集失败，请检查网络连接或稍后重试</p></div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# Header
# ============================================================

st.markdown(
    '<div class="terminal-header">'
    '<div>'
    '<h1>⚡ Market Analyst</h1>'
    '<p>GLOBAL MARKET INTELLIGENCE TERMINAL</p>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# Sidebar
# ============================================================

st.sidebar.markdown(
    '<div style="text-align: center; padding: 12px 0 20px;">'
    '<div style="font-size: 1.8rem; margin-bottom: 6px;">⚡</div>'
    '<div style="font-family: Outfit, sans-serif; font-weight: 700; font-size: 1rem; '
    'color: #f0b90b; letter-spacing: 0.08em;">MARKET ANALYST</div>'
    '<div style="font-family: JetBrains Mono, monospace; font-size: 0.6rem; '
    'color: #555577; margin-top: 4px;">v2.0 &middot; TERMINAL EDITION</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.8rem; '
    'color: #8888aa; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px;">'
    'FILTERS</p>',
    unsafe_allow_html=True,
)

market_filter = st.sidebar.multiselect(
    "市场",
    options=["us", "cn", "global"],
    default=["us", "cn", "global"],
    format_func=lambda x: {"us": "US  美股", "cn": "CN  A股", "global": "GL  全球"}.get(x, x),
)
tier_filter = st.sidebar.multiselect(
    "梯队",
    options=["T1", "T2", "T3", "T4"],
    default=["T1", "T2", "T3", "T4"],
)

filtered_df = strength_df[
    strength_df["market"].isin(market_filter) & strength_df["tier"].isin(tier_filter + ["—"])
]

has_fear = "fear_score" in strength_df.columns
has_bottom = "bottom_score" in strength_df.columns
has_pm = "pm_price" in strength_df.columns

# Sidebar stats
st.sidebar.markdown("---")
st.sidebar.markdown(
    f'<div style="font-family: JetBrains Mono, monospace; font-size: 0.7rem; color: #555577; line-height: 1.8;">'
    f'ASSETS &nbsp;&nbsp;<span style="color: #8888aa;">{len(strength_df)}</span><br>'
    f'SIGNALS <span style="color: #8888aa;">{len(anomalies)}</span><br>'
    f'UPDATED <span style="color: #8888aa;">{datetime.now().strftime("%H:%M")}</span>'
    f'</div>',
    unsafe_allow_html=True,
)


# ============================================================
# Tabs
# ============================================================

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "🌡 概览", "😱 恐慌/底部", "⏰ 盘前", "⚠ 异常",
    "🔵 突破", "🎯 个股", "🗺 热力图", "📈 量化", "📉 详情",
])


# ===== Tab 1: 全局概览 =====
with tab1:
    section_header("🌡", "全局概览", "Global Indicators & Market Pulse")

    global_df = strength_df[strength_df["market"] == "global"]
    if not global_df.empty:
        cols = st.columns(4)
        for i, (label, sym, desc) in enumerate([
            ("VIX", "^VIX", "恐慌指数"),
            ("美元", "DX-Y.NYB", "美元指数"),
            ("黄金", "GC=F", "黄金期货"),
            ("原油", "CL=F", "原油期货"),
        ]):
            row = global_df[global_df["symbol"] == sym]
            if not row.empty:
                r = row.iloc[0]
                cols[i].metric(
                    label,
                    f"{r['close']:.2f}",
                    f"{r['roc_5d']:+.2f}% (5d)",
                    delta_color="inverse" if sym == "^VIX" else "normal",
                    help=desc,
                )

    # 市场恐慌温度 — Gauge Charts
    if has_fear:
        st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, (market, mname) in enumerate([("us", "🇺🇸 美股"), ("cn", "🇨🇳 A股")]):
            mdf = strength_df[(strength_df["market"] == market) & strength_df["fear_score"].notna()]
            if mdf.empty:
                continue
            with cols[i]:
                med = mdf["fear_score"].median()
                fl = fear_label(med)
                gc = fear_gauge_color(med)

                # Gauge
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=med,
                    title={
                        "text": f"{mname} 恐慌温度 · {fl}",
                        "font": {"size": 13, "color": COLORS["text_secondary"], "family": "Outfit, sans-serif"},
                    },
                    number={
                        "font": {"size": 36, "color": gc, "family": "JetBrains Mono, monospace"},
                    },
                    gauge={
                        "axis": {
                            "range": [0, 100],
                            "tickcolor": COLORS["text_muted"],
                            "tickwidth": 1,
                            "dtick": 25,
                            "tickfont": {"size": 9, "color": COLORS["text_muted"]},
                        },
                        "bar": {"color": gc, "thickness": 0.65},
                        "bgcolor": "rgba(255,255,255,0.02)",
                        "borderwidth": 0,
                        "steps": [
                            {"range": [0, 25], "color": "rgba(0, 212, 170, 0.06)"},
                            {"range": [25, 40], "color": "rgba(74, 222, 128, 0.06)"},
                            {"range": [40, 60], "color": "rgba(240, 185, 11, 0.06)"},
                            {"range": [60, 75], "color": "rgba(249, 115, 22, 0.06)"},
                            {"range": [75, 100], "color": "rgba(255, 71, 87, 0.06)"},
                        ],
                    },
                ))
                fig.update_layout(height=200, margin=dict(t=60, b=0, l=30, r=30))
                st.plotly_chart(fig, use_container_width=True)

                # 恐慌分布柱状图
                bins = [0, 25, 40, 60, 75, 100]
                labels_list = ["极贪婪", "贪婪", "中性", "恐慌", "极恐慌"]
                mdf_copy = mdf.copy()
                mdf_copy["fear_bin"] = pd.cut(mdf_copy["fear_score"], bins=bins, labels=labels_list, include_lowest=True)
                dist = mdf_copy["fear_bin"].value_counts().reindex(labels_list, fill_value=0)
                fig = px.bar(
                    x=dist.index, y=dist.values,
                    color=dist.index, color_discrete_map=FEAR_COLORS,
                    labels={"x": "", "y": "板块数"},
                )
                fig.update_layout(showlegend=False, height=200, margin=dict(t=8, b=30, l=40, r=8))
                fig.update_traces(marker_line_width=0, opacity=0.85)
                st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)

    # 梯队分布
    col1, col2 = st.columns(2)
    for col_ui, market, mname in [(col1, "us", "🇺🇸 美股梯队"), (col2, "cn", "🇨🇳 A股梯队")]:
        mdf = strength_df[strength_df["market"] == market]
        if mdf.empty:
            continue
        with col_ui:
            st.markdown(
                f'<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                f'color: {COLORS["text_primary"]}; margin-bottom: 8px;">{mname}</p>',
                unsafe_allow_html=True,
            )
            tc = mdf["tier"].value_counts().reindex(["T1", "T2", "T3", "T4"], fill_value=0)
            fig = px.bar(
                x=tc.index, y=tc.values,
                color=tc.index, color_discrete_map=TIER_COLORS,
                labels={"x": "梯队", "y": "板块数"},
            )
            fig.update_layout(showlegend=False, height=220, margin=dict(t=8, b=30, l=40, r=8))
            fig.update_traces(marker_line_width=0, opacity=0.85)
            st.plotly_chart(fig, use_container_width=True)

    # Top / Bottom 5
    section_header("🔥", "最强 / 最弱 Top 5")
    non_global = strength_df[strength_df["market"] != "global"].sort_values("composite_score", ascending=False)
    col1, col2 = st.columns(2)
    display = ["name", "symbol", "market", "tier", "composite_score", "roc_5d"]
    if has_fear:
        display += ["fear_score", "streak"]
    avail = [c for c in display if c in non_global.columns]
    with col1:
        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; color: #00d4aa; '
            'font-size: 0.85rem; margin-bottom: 6px;">💪 STRONGEST</p>',
            unsafe_allow_html=True,
        )
        st.dataframe(non_global.head(5)[avail].reset_index(drop=True), use_container_width=True)
    with col2:
        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; color: #ff4757; '
            'font-size: 0.85rem; margin-bottom: 6px;">📉 WEAKEST</p>',
            unsafe_allow_html=True,
        )
        st.dataframe(non_global.tail(5)[avail].reset_index(drop=True), use_container_width=True)


# ===== Tab 2: 恐慌/底部 =====
with tab2:
    section_header("😱", "恐慌 / 底部评分面板", "Fear & Bottom Score Analysis")

    if not has_fear:
        st.warning("恐慌分数未计算。请先运行 `python main.py`。")
    else:
        # 散点图: Fear vs Bottom
        if has_bottom:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #e0e0f0; margin: 12px 0 8px;">Fear vs Bottom 散点图</p>',
                unsafe_allow_html=True,
            )
            scatter = filtered_df[filtered_df["market"] != "global"].dropna(subset=["fear_score", "bottom_score"])
            if not scatter.empty:
                fig = px.scatter(
                    scatter, x="fear_score", y="bottom_score",
                    color="tier", size="composite_score",
                    hover_name="name",
                    hover_data=["symbol", "roc_5d", "streak"],
                    color_discrete_map=TIER_COLORS,
                    labels={
                        "fear_score": "Fear Score (越高越恐慌)",
                        "bottom_score": "Bottom Score (越高越接近底部)",
                    },
                )
                # 机会区（高恐慌 + 高底部）
                fig.add_shape(
                    type="rect", x0=60, y0=40, x1=100, y1=100,
                    fillcolor="rgba(0, 212, 170, 0.06)",
                    line=dict(color="rgba(0, 212, 170, 0.3)", dash="dash", width=1),
                )
                fig.add_annotation(
                    x=80, y=70, text="OPPORTUNITY ZONE",
                    showarrow=False,
                    font=dict(color="#00d4aa", size=12, family="Outfit, sans-serif"),
                    opacity=0.7,
                )
                fig.update_layout(height=500)
                fig.update_traces(marker=dict(line=dict(width=0), opacity=0.85))
                st.plotly_chart(fig, use_container_width=True)

        # 最恐慌标的
        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
            'color: #ff4757; margin: 16px 0 8px;">🔴 最恐慌标的 (Fear ≥ 60)</p>',
            unsafe_allow_html=True,
        )
        fear_top = strength_df[strength_df["fear_score"].notna() & (strength_df["fear_score"] >= 60)].copy()
        if not fear_top.empty:
            fear_top = fear_top.sort_values("fear_score", ascending=False)
            cols_show = [
                "name", "symbol", "market", "fear_score", "fear_label", "streak",
                "fear_rsi_dim", "fear_drawdown_dim", "fear_streak_dim", "fear_momentum_dim",
            ]
            avail_cols = [c for c in cols_show if c in fear_top.columns]
            st.dataframe(
                fear_top[avail_cols], use_container_width=True,
                column_config={
                    "fear_score": st.column_config.ProgressColumn("Fear", format="%.0f", min_value=0, max_value=100),
                },
            )
        else:
            st.info("当前无极恐慌标的")

        # 底部信号
        if has_bottom:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #00d4aa; margin: 16px 0 8px;">🟢 底部信号 (Bottom ≥ 40)</p>',
                unsafe_allow_html=True,
            )
            bottom_top = strength_df[strength_df["bottom_score"].notna() & (strength_df["bottom_score"] >= 40)].copy()
            if not bottom_top.empty:
                bottom_top = bottom_top.sort_values("bottom_score", ascending=False)
                cols_show = [
                    "name", "symbol", "market", "bottom_score", "bottom_label", "fear_score",
                    "bottom_rsi_dim", "bottom_drawdown_dim", "bottom_vol_dim", "bottom_flow_dim",
                ]
                avail_cols = [c for c in cols_show if c in bottom_top.columns]
                st.dataframe(
                    bottom_top[avail_cols], use_container_width=True,
                    column_config={
                        "bottom_score": st.column_config.ProgressColumn("Bottom", format="%.0f", min_value=0, max_value=100),
                    },
                )
            else:
                st.info("当前无底部信号标的")

        # 交叉信号
        if has_bottom:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #f0b90b; margin: 16px 0 8px;">⭐ 恐慌中的机会 (Fear≥60 + Bottom≥40)</p>',
                unsafe_allow_html=True,
            )
            cross = strength_df[
                (strength_df["fear_score"] >= 60) & (strength_df["bottom_score"] >= 40)
            ].sort_values("bottom_score", ascending=False)
            if not cross.empty:
                for _, r in cross.iterrows():
                    streak_val = int(r["streak"]) if pd.notna(r.get("streak")) else 0
                    streak_str = f"连跌{abs(streak_val)}天" if streak_val < 0 else f"连涨{streak_val}天"
                    st.markdown(
                        f'<div class="signal-card" style="border-left: 3px solid #f0b90b;">'
                        f'<div class="signal-title">{r.get("name", r["symbol"])}</div>'
                        f'<div class="signal-detail">'
                        f'Fear={r["fear_score"]:.0f} ({r.get("fear_label", "")}) · '
                        f'Bottom={r["bottom_score"]:.0f} ({r.get("bottom_label", "")}) · {streak_str}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("当前无交叉信号")


# ===== Tab 3: 盘前异动 =====
with tab3:
    section_header("⏰", "盘前异动", "Pre-Market Movers")

    if not has_pm:
        st.warning("无盘前数据。请在美股盘前时段运行 `python main.py`。")
    else:
        pm_df = strength_df[strength_df["pm_price"].notna()].copy()
        if pm_df.empty:
            st.info("当前无盘前报价")
        else:
            pm_df = pm_df.sort_values("pm_gap", key=abs, ascending=False)

            # 大幅异动高亮
            big = pm_df[pm_df["pm_gap"].abs() > 5]
            if not big.empty:
                big_cols = st.columns(min(len(big), 4))
                for idx, (_, r) in enumerate(big.iterrows()):
                    if idx >= 4:
                        break
                    color = COLORS["accent_green"] if r["pm_gap"] > 0 else COLORS["accent_red"]
                    arrow = "▲" if r["pm_gap"] > 0 else "▼"
                    with big_cols[idx]:
                        st.markdown(
                            f'<div style="background: rgba(255,255,255,0.025); border: 1px solid {color}33; '
                            f'border-radius: 12px; padding: 16px; text-align: center;">'
                            f'<div style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.85rem; '
                            f'color: {COLORS["text_primary"]}; margin-bottom: 6px;">'
                            f'{r.get("name", r["symbol"])}</div>'
                            f'<div style="font-family: JetBrains Mono, monospace; font-size: 1.5rem; '
                            f'font-weight: 700; color: {color};">{arrow} {r["pm_gap"]:+.2f}%</div>'
                            f'<div style="font-family: JetBrains Mono, monospace; font-size: 0.75rem; '
                            f'color: {COLORS["text_muted"]}; margin-top: 4px;">'
                            f'${r["pm_price"]:.2f} vs ${r["close"]:.2f}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)

            # 完整表格
            cols_show = ["name", "symbol", "close", "pm_price", "pm_gap", "tier"]
            avail_cols = [c for c in cols_show if c in pm_df.columns]
            st.dataframe(
                pm_df[avail_cols], use_container_width=True,
                column_config={
                    "pm_gap": st.column_config.NumberColumn("盘前涨跌%", format="%.2f%%"),
                },
            )


# ===== Tab 4: 异常信号 =====
with tab4:
    n_high = sum(1 for a in anomalies if a["severity"] == "high")
    n_med = sum(1 for a in anomalies if a["severity"] == "medium")
    n_low = sum(1 for a in anomalies if a["severity"] == "low")
    section_header("⚠", f"异常信号 ({len(anomalies)})", f"HIGH:{n_high}  MED:{n_med}  LOW:{n_low}")

    if not anomalies:
        st.info("未检测到异常信号")
    else:
        # Sort by severity
        sev_order = {"high": 0, "medium": 1, "low": 2}
        sorted_anomalies = sorted(anomalies, key=lambda a: sev_order.get(a["severity"], 3))

        for a in sorted_anomalies:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(a["severity"], "⚪")
            border_color = {
                "high": COLORS["accent_red"],
                "medium": COLORS["accent_gold"],
                "low": COLORS["accent_green"],
            }.get(a["severity"], "#555577")

            with st.expander(
                f"{icon} [{a['severity'].upper()}] {a['description']}",
                expanded=(a["severity"] == "high"),
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("类型", a["type"])
                c2.metric("严重度", a["severity"].upper())
                c3.metric("标的", ", ".join(a.get("symbols", [])))
                if a.get("data"):
                    st.json(a["data"])


# ===== Tab 5: 突破/抛物线 =====
with tab5:
    section_header("🔵", "突破 & 抛物线检测", "Breakout & Parabolic Detection")

    detected = (
        strength_df[strength_df.get("cycle_stage_num", pd.Series(dtype=int)) > 0]
        if "cycle_stage_num" in strength_df.columns
        else pd.DataFrame()
    )
    if not detected.empty:
        cols_show = ["name", "symbol", "market", "cycle_stage", "cycle_position", "cycle_confidence", "composite_score"]
        avail_cols = [c for c in cols_show if c in detected.columns]
        st.dataframe(
            detected[avail_cols], use_container_width=True,
            column_config={
                "cycle_position": st.column_config.ProgressColumn("位置", format="%.0f%%", min_value=0, max_value=1),
            },
        )
    else:
        st.info("当前无突破/抛物线信号")

    if cycle_signals:
        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
            'color: #e0e0f0; margin: 16px 0 8px;">活跃信号</p>',
            unsafe_allow_html=True,
        )
        for s in cycle_signals:
            signal_colors = {"breakout": COLORS["accent_blue"], "parabolic": COLORS["accent_purple"]}
            signal_icons = {"breakout": "🔵 突破", "parabolic": "🟣 抛物线"}
            sc = signal_colors.get(s["signal_type"], COLORS["accent_gold"])
            si = signal_icons.get(s["signal_type"], s["signal_type"])

            with st.expander(f"{si} | {s['confidence'].upper()} | {s['name']}", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.metric("当前价", f"{s['close']:.2f}")
                c2.metric("关键价位", f"{s['key_level']:.2f}")
                c3.metric("失效价位", f"{s['invalidation']:.2f}")
                st.markdown(
                    f'<p style="font-family: JetBrains Mono, monospace; font-size: 0.8rem; '
                    f'color: {COLORS["text_secondary"]}; margin-top: 8px;">{s["description"]}</p>',
                    unsafe_allow_html=True,
                )


# ===== Tab 6: 个股机会 =====
with tab6:
    section_header("🎯", "个股机会", "Sector Drill-Down & Market Movers")

    if not stock_picks:
        st.warning("板块扫描未运行。请先运行 `python main.py`。")
    else:
        # 板块个股
        sector_picks = stock_picks.get("sector_picks", [])
        if sector_picks:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #e0e0f0; margin-bottom: 8px;">热门板块放量个股</p>',
                unsafe_allow_html=True,
            )
            for sp in sector_picks:
                etfs = ", ".join(sp["source_etfs"])
                with st.expander(f"📂 {sp['sector']}（来源: {etfs}）— {len(sp['stocks'])} 只", expanded=False):
                    sp_df = pd.DataFrame(sp["stocks"])
                    if not sp_df.empty:
                        st.dataframe(
                            sp_df, use_container_width=True,
                            column_config={
                                "rel_volume": st.column_config.NumberColumn("相对量", format="%.2f"),
                                "rsi": st.column_config.NumberColumn("RSI", format="%.0f"),
                                "cmf": st.column_config.NumberColumn("CMF", format="%.3f"),
                                "market_cap_b": st.column_config.NumberColumn("市值(B)", format="%.0f"),
                            },
                        )

        # 暴涨暴跌
        col1, col2 = st.columns(2)
        big_up = stock_picks.get("big_movers_up", [])
        big_down = stock_picks.get("big_movers_down", [])

        with col1:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #00d4aa; margin-bottom: 6px;">🟢 暴涨 (&gt;8%)</p>',
                unsafe_allow_html=True,
            )
            if big_up:
                st.dataframe(pd.DataFrame(big_up), use_container_width=True)
            else:
                st.info("无")

        with col2:
            st.markdown(
                '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
                'color: #ff4757; margin-bottom: 6px;">🔴 暴跌 (&lt;-8%)</p>',
                unsafe_allow_html=True,
            )
            if big_down:
                st.dataframe(pd.DataFrame(big_down), use_container_width=True)
            else:
                st.info("无")


# ===== Tab 7: 热力图 =====
with tab7:
    section_header("🗺", "板块相对强弱热力图", "Sector Relative Strength Treemap")

    for market, mname in [("us", "🇺🇸 美股"), ("cn", "🇨🇳 A股")]:
        mdf = filtered_df[filtered_df["market"] == market].sort_values("composite_score", ascending=False)
        if mdf.empty:
            continue
        st.markdown(
            f'<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
            f'color: {COLORS["text_primary"]}; margin: 12px 0 8px;">{mname}</p>',
            unsafe_allow_html=True,
        )
        hover = ["symbol", "roc_5d", "roc_20d", "roc_60d", "composite_score"]
        if has_fear:
            hover += ["fear_score", "bottom_score", "streak"]
        avail_hover = [c for c in hover if c in mdf.columns]
        fig = px.treemap(
            mdf, path=["tier", "name"], values="composite_score",
            color="roc_5d",
            color_continuous_scale=[
                [0, COLORS["accent_red"]],
                [0.5, "#1a1a2e"],
                [1, COLORS["accent_green"]],
            ],
            color_continuous_midpoint=0,
            hover_data=avail_hover,
        )
        fig.update_layout(
            height=500,
            margin=dict(t=8, b=8, l=8, r=8),
            coloraxis_colorbar=dict(
                title=dict(text="5d ROC", font=dict(size=11)),
                tickfont=dict(size=10),
            ),
        )
        fig.update_traces(
            textfont=dict(family="Outfit, sans-serif", size=12),
            marker=dict(cornerradius=4),
        )
        st.plotly_chart(fig, use_container_width=True)


# ===== Tab 8: 量化面板 =====
with tab8:
    section_header("📈", "量化指标面板", "Quantitative Metrics")
    has_quant = "sharpe" in filtered_df.columns and filtered_df["sharpe"].notna().any()

    if not has_quant:
        st.warning("量化指标未计算。")
    else:
        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
            'color: #e0e0f0; margin-bottom: 8px;">Sharpe vs 最大回撤</p>',
            unsafe_allow_html=True,
        )
        scatter = filtered_df[filtered_df["market"] != "global"].dropna(subset=["sharpe", "max_drawdown"])
        if not scatter.empty:
            fig = px.scatter(
                scatter, x="max_drawdown", y="sharpe",
                color="tier", size="composite_score",
                hover_name="name",
                hover_data=["symbol", "ann_return", "ann_vol"],
                color_discrete_map=TIER_COLORS,
                labels={"max_drawdown": "最大回撤 (%)", "sharpe": "Sharpe"},
            )
            # Sharpe = 0 reference line
            fig.add_hline(
                y=0, line_dash="dash", line_color="rgba(255,255,255,0.15)",
                annotation_text="Sharpe = 0",
                annotation_font=dict(size=10, color=COLORS["text_muted"]),
            )
            fig.update_layout(height=500)
            fig.update_traces(marker=dict(line=dict(width=0), opacity=0.85))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.95rem; '
            'color: #e0e0f0; margin: 16px 0 8px;">完整数据</p>',
            unsafe_allow_html=True,
        )
        cols = [
            "name", "symbol", "market", "tier", "composite_score",
            "roc_5d", "roc_20d", "roc_60d", "delta_roc_5d",
            "ann_return", "ann_vol", "sharpe", "max_drawdown",
        ]
        if has_fear:
            cols += ["fear_score", "bottom_score", "streak"]
        avail = [c for c in cols if c in filtered_df.columns]
        st.dataframe(
            filtered_df[avail].sort_values("composite_score", ascending=False),
            use_container_width=True,
            height=600,
        )


# ===== Tab 9: 个股详情 =====
with tab9:
    section_header("📉", "个股详情 & 走势", "Single Asset Deep Dive")

    all_symbols = strength_df[["symbol", "name", "market"]].drop_duplicates()
    all_symbols["label"] = all_symbols.apply(
        lambda r: f"{r['name']} ({r['symbol']}) [{r['market']}]", axis=1,
    )
    selected_label = st.selectbox("选择标的", all_symbols["label"].tolist())

    if selected_label:
        sel_sym = all_symbols[all_symbols["label"] == selected_label].iloc[0]["symbol"]
        sym_info = strength_df[strength_df["symbol"] == sel_sym]

        if not sym_info.empty:
            r = sym_info.iloc[0]

            # 基础指标卡片
            metric_cols = st.columns(8)
            metric_cols[0].metric("梯队", r.get("tier", "—"))
            metric_cols[1].metric("综合分", f"{r['composite_score']:.1f}")
            metric_cols[2].metric("5日%", f"{r['roc_5d']:+.2f}%")
            metric_cols[3].metric("20日%", f"{r['roc_20d']:+.2f}%")
            if pd.notna(r.get("sharpe")):
                metric_cols[4].metric("Sharpe", f"{r['sharpe']:.3f}")
            if has_fear and pd.notna(r.get("fear_score")):
                metric_cols[5].metric("Fear", f"{r['fear_score']:.0f}", r.get("fear_label", ""))
            if has_bottom and pd.notna(r.get("bottom_score")):
                metric_cols[6].metric("Bottom", f"{r['bottom_score']:.0f}", r.get("bottom_label", ""))
            if pd.notna(r.get("streak")):
                s_val = int(r["streak"])
                metric_cols[7].metric("Streak", f"{s_val:+d}d")

            # 盘前数据
            if has_pm and pd.notna(r.get("pm_price")):
                pm_color = COLORS["accent_green"] if r["pm_gap"] >= 0 else COLORS["accent_red"]
                st.markdown(
                    f'<div style="background: rgba(255,255,255,0.02); border: 1px solid {pm_color}33; '
                    f'border-radius: 8px; padding: 10px 16px; margin: 8px 0; '
                    f'font-family: JetBrains Mono, monospace; font-size: 0.85rem;">'
                    f'<span style="color: {COLORS["text_secondary"]};">⏰ 盘前价:</span> '
                    f'<span style="color: {COLORS["text_primary"]}; font-weight: 600;">${r["pm_price"]:.2f}</span> '
                    f'<span style="color: {pm_color}; font-weight: 600;">({r["pm_gap"]:+.2f}%)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # TradingView 指标
            tv_cols_list = ["tv_rsi", "tv_macd_hist", "tv_cmf", "tv_rel_volume", "tv_ma_rating"]
            tv_available = [c for c in tv_cols_list if c in r.index and pd.notna(r.get(c))]
            if tv_available:
                st.markdown(
                    '<p style="font-family: Outfit, sans-serif; font-weight: 600; font-size: 0.85rem; '
                    'color: #8888aa; margin: 12px 0 6px;">TRADINGVIEW INDICATORS</p>',
                    unsafe_allow_html=True,
                )
                tv_data = {c: r[c] for c in tv_available}
                st.json(tv_data)

        # 价格走势
        sym_raw = raw_df[raw_df["symbol"] == sel_sym].sort_values("date") if raw_df is not None else pd.DataFrame()
        if not sym_raw.empty:
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=sym_raw["date"], y=sym_raw["close"],
                    name="收盘价",
                    line=dict(width=2, color=COLORS["accent_gold"]),
                    fill="tonexty" if False else None,
                ))
                closes = sym_raw["close"].values
                dates = sym_raw["date"].values
                sma20 = pd.Series(closes).rolling(20).mean().values
                sma50 = pd.Series(closes).rolling(50).mean().values
                fig.add_trace(go.Scatter(
                    x=dates, y=sma20, name="SMA20",
                    line=dict(dash="dash", width=1, color=COLORS["accent_cyan"]),
                ))
                fig.add_trace(go.Scatter(
                    x=dates, y=sma50, name="SMA50",
                    line=dict(dash="dot", width=1, color=COLORS["accent_purple"]),
                ))
                fig.update_layout(
                    title=dict(text="价格走势", font=dict(size=14)),
                    height=400,
                    margin=dict(t=40, b=30, l=50, r=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                from market_analyst.processors.quant_metrics import QuantMetrics
                wi = QuantMetrics.compute_wealth_index(raw_df, sel_sym)
                if not wi.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=wi["date"], y=wi["drawdown"],
                        name="回撤",
                        fill="tozeroy",
                        fillcolor="rgba(255, 71, 87, 0.1)",
                        line=dict(width=1.5, color=COLORS["accent_red"]),
                    ))
                    fig.add_hline(
                        y=wi["drawdown"].min(),
                        line_dash="dash",
                        line_color="rgba(255, 71, 87, 0.5)",
                        annotation_text=f"最大: {wi['drawdown'].min():.2%}",
                        annotation_font=dict(size=10, color=COLORS["accent_red"]),
                    )
                    fig.update_layout(
                        title=dict(text="回撤曲线", font=dict(size=14)),
                        height=400,
                        margin=dict(t=40, b=30, l=50, r=20),
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Footer
# ============================================================

st.markdown(
    f'<div class="footer-bar">'
    f'<div class="main-text">'
    f'DATA UPDATED {datetime.now().strftime("%Y-%m-%d %H:%M")} &middot; MARKET ANALYST v2.0 &middot; TERMINAL EDITION'
    f'</div>'
    f'<div class="sub-text">'
    f'{len(strength_df)} ASSETS &middot; {len(anomalies)} SIGNALS &middot; '
    f'{"FEAR DATA ✓" if has_fear else "NO FEAR DATA"} &middot; '
    f'{"PREMARKET ✓" if has_pm else "NO PM DATA"}'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)
