# market_analyst/schemas.py
"""Pydantic output models for all MCP tools."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from market_analyst.schemas_retail import (
    ActionSignal,
    CapitalFlowSignal,
    EarningsAnalysis,
    QuarterlyMetric,
    RiskFlag,
    StockCharacterization,
    StrategyItem,
    TradeSignal,
    TradingStrategies,
)


class ToolError(BaseModel):
    """Returned when a tool cannot produce results."""
    error: str
    message: str


class MarketOverview(BaseModel):
    market: Literal["us", "cn", "all"]
    market_temp_5d: float | None = None
    advancing: int = 0
    declining: int = 0
    t1_sectors: list[dict] = Field(default_factory=list)
    t4_sectors: list[dict] = Field(default_factory=list)
    fear_score: float | None = None
    fear_label: str | None = None
    key_indices: dict[str, float] = Field(default_factory=dict)
    stale: bool = False


class SectorStrengthItem(BaseModel):
    symbol: str
    name: str
    sector: str
    market: str
    close: float
    roc_5d: float
    roc_20d: float
    roc_60d: float
    composite_score: float
    tier: str
    delta_roc_5d: float | None = None


class SectorStrength(BaseModel):
    market: str
    items: list[SectorStrengthItem]
    stale: bool = False


class StockDiagnosis(BaseModel):
    symbol: str
    name: str
    market: Literal["us", "cn"]
    scores: dict[str, float | None]
    rating: int = Field(ge=1, le=5)
    available_dimensions: list[str]
    capital_flow: CapitalFlowSignal | None = None
    action: ActionSignal | None = None
    stale: bool = False


class FearScoreResult(BaseModel):
    symbol: str | None = None
    market: str | None = None
    fear_score: float | None = None
    fear_label: str | None = None
    bottom_score: float | None = None
    bottom_label: str | None = None
    dimensions: dict[str, float] = Field(default_factory=dict)
    stale: bool = False


class AnomalySignal(BaseModel):
    type: str
    severity: Literal["high", "medium", "low"]
    symbols: list[str]
    description: str
    data: dict = Field(default_factory=dict)


class CycleSignal(BaseModel):
    symbol: str
    name: str
    signal_type: str  # "breakout" or "parabolic"
    confidence: str
    details: dict = Field(default_factory=dict)


class CommentaryData(BaseModel):
    """Structured data for the agent to compose commentary."""
    type: Literal["morning", "midday", "closing"]
    market_temp: dict[str, float] = Field(default_factory=dict)
    top_movers: list[dict] = Field(default_factory=list)
    worst_movers: list[dict] = Field(default_factory=list)
    anomalies_summary: list[str] = Field(default_factory=list)
    key_indices_change: dict[str, float] = Field(default_factory=dict)
    fear_score: float | None = None
    fear_label: str | None = None


class MomentumItem(BaseModel):
    symbol: str
    name: str
    market: str
    perf_5d: float | None = None
    perf_20d: float | None = None
    trigger: str | None = None  # "5d" / "20d" / "both"
    avg_volume: float | None = None


class NewsItem(BaseModel):
    title: str
    url: str
    summary: str | None = None
    related_sectors: list[str] = Field(default_factory=list)


class ReportResult(BaseModel):
    status: Literal["completed", "running", "failed"]
    filepath: str | None = None
    job_id: str | None = None
    message: str | None = None


# Retail investor schemas are imported above for shared typing/export.
