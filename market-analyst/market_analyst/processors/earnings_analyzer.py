"""Earnings analysis: expectation verdict + risk flags + plain-language summary."""
from __future__ import annotations

from loguru import logger

from market_analyst.schemas_retail import (
    EarningsAnalysis,
    QuarterlyMetric,
    RiskFlag,
)


class EarningsAnalyzer:
    """Analyze earnings data and produce retail-friendly output."""

    def __init__(self, config: dict):
        cfg = config.get("earnings", {})
        self.beat_large = cfg.get("beat_large_threshold", 10)
        self.beat_small = cfg.get("beat_small_threshold", 3)
        self.pledge_alert = cfg.get("pledge_alert_ratio", 50)

    def analyze(self, symbol: str, market: str, data: dict) -> EarningsAnalysis:
        meta = data.get("meta", {})
        name = meta.get("name", symbol)
        financials = data.get("financials", [])
        forecast = data.get("forecast", {})
        risk_data = data.get("risks", {})

        if not financials:
            return self._empty_result(symbol, name, market, risk_data)

        # Build quarterly trend with YoY
        quarterly = self._build_quarterly_trend(financials)
        latest = quarterly[0] if quarterly else None

        # Expectation vs consensus, with YoY fallback
        consensus = forecast.get("consensus_profit")
        if consensus and latest and consensus != 0:
            deviation = (latest.profit - consensus) / abs(consensus) * 100
            expectation = self._classify_deviation(deviation)
            expectation_basis = "consensus"
        elif latest and latest.profit_yoy is not None:
            deviation = None
            expectation = self._classify_yoy(latest.profit_yoy)
            expectation_basis = "yoy_fallback"
        else:
            deviation = None
            expectation = "无预期数据"
            expectation_basis = "none"

        # Trend summary
        trend_summary = self._determine_trend(quarterly)

        # Risk flags
        risks = self._detect_risks(risk_data, quarterly)

        # Plain summary
        plain = self._build_summary(name, latest, expectation, deviation, trend_summary, risks)

        return EarningsAnalysis(
            symbol=symbol, name=name, market=market,
            latest_quarter=latest.quarter if latest else "N/A",
            revenue=latest.revenue if latest else 0,
            net_profit=latest.profit if latest else 0,
            revenue_yoy=latest.revenue_yoy if latest.revenue_yoy is not None else 0,
            profit_yoy=latest.profit_yoy if latest.profit_yoy is not None else 0,
            expectation_basis=expectation_basis,
            expectation=expectation,
            deviation_pct=round(deviation, 1) if deviation is not None else None,
            quarterly_trend=quarterly,
            trend_summary=trend_summary,
            risks=risks,
            plain_summary=plain[:300],
        )

    def _build_quarterly_trend(self, financials: list[dict]) -> list[QuarterlyMetric]:
        """Convert raw financials to typed quarterly metrics with YoY calc."""
        metrics = []
        for i, f in enumerate(financials):
            profit_yoy = None
            revenue_yoy = None
            if i + 4 < len(financials):
                prev_profit = financials[i + 4].get("net_profit")
                if prev_profit and prev_profit != 0:
                    profit_yoy = round((f["net_profit"] - prev_profit) / abs(prev_profit) * 100, 1)
                prev_rev = financials[i + 4].get("revenue")
                if prev_rev and prev_rev != 0:
                    revenue_yoy = round((f["revenue"] - prev_rev) / abs(prev_rev) * 100, 1)

            metrics.append(QuarterlyMetric(
                quarter=f.get("quarter", ""),
                revenue=f.get("revenue", 0),
                revenue_yoy=revenue_yoy,
                profit=f.get("net_profit", 0),
                profit_yoy=profit_yoy,
            ))
        return metrics

    def _classify_deviation(self, deviation: float) -> str:
        if deviation > self.beat_large:
            return "大幅超预期"
        elif deviation > self.beat_small:
            return "小幅超预期"
        elif deviation > -self.beat_small:
            return "符合预期"
        elif deviation > -self.beat_large:
            return "小幅不及预期"
        else:
            return "大幅不及预期"

    def _classify_yoy(self, profit_yoy: float) -> str:
        if profit_yoy > 30:
            return "大幅超预期"
        elif profit_yoy > 10:
            return "小幅超预期"
        elif profit_yoy > -10:
            return "符合预期"
        elif profit_yoy > -30:
            return "小幅不及预期"
        else:
            return "大幅不及预期"

    def _determine_trend(self, quarterly: list[QuarterlyMetric]) -> str:
        if len(quarterly) < 2:
            return "波动"
        profits = [q.profit for q in quarterly]
        increasing = all(profits[i] >= profits[i + 1] for i in range(len(profits) - 1))
        decreasing = all(profits[i] <= profits[i + 1] for i in range(len(profits) - 1))

        if increasing:
            return "连续增长"
        elif decreasing:
            return "持续下滑"
        if len(profits) >= 3:
            if profits[0] > profits[1] and profits[1] < profits[2]:
                return "拐点向上"
            if profits[0] < profits[1] and profits[1] > profits[2]:
                return "拐点向下"
        return "波动"

    def _detect_risks(self, risk_data: dict, quarterly: list[QuarterlyMetric]) -> list[RiskFlag]:
        flags = []
        if risk_data.get("is_st"):
            flags.append(RiskFlag(type="ST风险", level="high", detail="当前为ST/*ST状态"))

        pledge = risk_data.get("pledge_ratio")
        if pledge is not None and pledge > self.pledge_alert:
            flags.append(RiskFlag(type="质押风险", level="medium", detail=f"质押比例{pledge:.1f}%"))

        reductions = risk_data.get("reductions", [])
        if reductions:
            flags.append(RiskFlag(type="减持风险", level="medium", detail=f"近期有{len(reductions)}笔减持记录"))

        if len(quarterly) >= 2 and all(q.profit < 0 for q in quarterly[:2]):
            flags.append(RiskFlag(type="亏损风险", level="high", detail="连续2季净利润为负"))

        if len(quarterly) >= 3:
            revs = [q.revenue for q in quarterly[:3]]
            if revs[0] < revs[1] < revs[2]:
                flags.append(RiskFlag(type="营收萎缩", level="medium", detail="连续2季营收下滑"))

        return flags

    def _build_summary(self, name, latest, expectation, deviation, trend, risks) -> str:
        parts = []
        if latest:
            parts.append(f"{name}{latest.quarter}营收{latest.revenue:.1f}亿，净利润{latest.profit:.1f}亿。")
        if expectation != "无预期数据" and deviation is not None:
            parts.append(f"业绩{expectation}（偏差{deviation:+.1f}%）。")
        parts.append(f"近期走势：{trend}。")
        if risks:
            risk_str = "、".join(r.type for r in risks)
            parts.append(f"风险提示：{risk_str}。")
        return "".join(parts)

    def _empty_result(self, symbol, name, market, risk_data) -> EarningsAnalysis:
        risks = self._detect_risks(risk_data, [])
        return EarningsAnalysis(
            symbol=symbol, name=name, market=market,
            latest_quarter="N/A", revenue=0, net_profit=0,
            revenue_yoy=0, profit_yoy=0,
            expectation_basis="none",
            expectation="无预期数据", deviation_pct=None,
            quarterly_trend=[], trend_summary="波动",
            risks=risks, plain_summary=f"{name}暂无可用的财务数据。",
        )
