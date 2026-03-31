"""Pydantic schemas for retail investor features."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StockCharacterization(BaseModel):
    """个股定性结果：游资票/机构票/机游合力票/普通票。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    hot_money_score: float = Field(ge=0, le=100, description="游资倾向 0-100")
    institutional_score: float = Field(ge=0, le=100, description="机构倾向 0-100")
    available_dimensions: list[str] = Field(description="实际参与评分的维度")
    key_evidence: list[str] = Field(description="3-5条关键依据")
    analysis_tips: str = Field(description="针对该类型的分析建议")
    stale: bool = False


class TradeSignal(BaseModel):
    """加减仓信号：大吉/小吉/平/小凶/大凶。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    signal: Literal["大吉", "小吉", "平", "小凶", "大凶"]
    score: float = Field(ge=0, le=100, description="综合分")
    market_score: float = Field(ge=0, le=100, description="大盘分")
    stock_score: float = Field(ge=0, le=100, description="个股原始均分")
    character_score: float = Field(ge=0, le=100, description="定性修正分")
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"]
    score_breakdown: dict[str, float] = Field(description="各维度明细")
    reasons: list[str] = Field(description="2-3条简明理由")
    risk_warnings: list[str] = Field(default_factory=list)
    stale: bool = False


class QuarterlyMetric(BaseModel):
    """单季度财务指标。"""

    quarter: str
    revenue: float
    revenue_yoy: float | None = None
    profit: float
    profit_yoy: float | None = None


class RiskFlag(BaseModel):
    """风险标记。"""

    type: Literal["ST风险", "减持风险", "质押风险", "亏损风险", "营收萎缩"]
    level: Literal["high", "medium"]
    detail: str


class EarningsAnalysis(BaseModel):
    """财报解读结果。"""

    symbol: str
    name: str
    market: Literal["us", "cn"]
    latest_quarter: str
    revenue: float
    net_profit: float
    revenue_yoy: float
    profit_yoy: float
    expectation_basis: Literal["consensus", "yoy_fallback", "none"]
    expectation: Literal[
        "大幅超预期", "小幅超预期", "符合预期", "小幅不及预期", "大幅不及预期", "无预期数据"
    ]
    deviation_pct: float | None = None
    quarterly_trend: list[QuarterlyMetric]
    trend_summary: Literal["连续增长", "拐点向上", "拐点向下", "持续下滑", "波动"]
    risks: list[RiskFlag] = Field(default_factory=list)
    plain_summary: str = Field(max_length=300, description="≤300字通俗解读")
    stale: bool = False


class StrategyItem(BaseModel):
    """单个推荐策略。"""

    name: str
    match_reason: str
    description: str
    entry_rule: str
    exit_rule: str
    stop_loss: str
    risk_reward: str
    difficulty: Literal["新手", "进阶", "高阶"]


class TradingStrategies(BaseModel):
    """交易策略推荐结果。"""

    symbol: str | None = None
    name: str | None = None
    market: Literal["us", "cn"] | None = None
    character_type: Literal["游资票", "机构票", "机游合力票", "普通票"] | None = None
    current_situation: str
    recommended: list[StrategyItem]
    risk_reward_lesson: str
    stale: bool = False
