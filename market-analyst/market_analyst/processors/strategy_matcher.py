"""Strategy matching engine: recommend 2-3 trading strategies based on stock state."""
from __future__ import annotations

from market_analyst.schemas_retail import StrategyItem, TradingStrategies


# Built-in strategy knowledge base
STRATEGIES = {
    "龙头战法": StrategyItem(
        name="龙头战法",
        match_reason="",
        description="做板块最强辨识度票，打板或低吸首阴，快进快出",
        entry_rule="板块启动，个股辨识度最高，首板或2板确认",
        exit_rule="分歧日（竞价低于预期）或板块退潮",
        stop_loss="-5~7%，次日不及预期即出",
        risk_reward="3:1",
        difficulty="高阶",
    ),
    "波段持股": StrategyItem(
        name="波段持股",
        match_reason="",
        description="沿20日均线持股，享受趋势红利",
        entry_rule="站上20日均线且均线向上",
        exit_rule="收盘跌破20日均线",
        stop_loss="跌破20日均线即离场",
        risk_reward="2:1",
        difficulty="进阶",
    ),
    "低吸反弹": StrategyItem(
        name="低吸反弹",
        match_reason="",
        description="恐慌超跌后分批低吸，等待反弹",
        entry_rule="恐慌指数>70，个股超跌>20%",
        exit_rule="反弹15-20%止盈",
        stop_loss="-8%",
        risk_reward="2.5:1",
        difficulty="进阶",
    ),
    "趋势突破": StrategyItem(
        name="趋势突破",
        match_reason="",
        description="长期横盘后放量突破关键阻力位",
        entry_rule="放量突破前高/平台，量比>2",
        exit_rule="回落至突破位下方",
        stop_loss="回落至突破位下方即出",
        risk_reward="3:1",
        difficulty="进阶",
    ),
    "高抛低吸": StrategyItem(
        name="高抛低吸",
        match_reason="",
        description="在明确的震荡箱体内高卖低买",
        entry_rule="触及箱体下沿",
        exit_rule="触及箱体上沿",
        stop_loss="跌破箱体下沿",
        risk_reward="1.5:1",
        difficulty="新手",
    ),
    "打板战法": StrategyItem(
        name="打板战法",
        match_reason="",
        description="涨停板买入，博次日溢价",
        entry_rule="封板坚决，板上买入",
        exit_rule="次日竞价或盘中高点卖出",
        stop_loss="次日低开或炸板即出",
        risk_reward="3:1",
        difficulty="高阶",
    ),
    "定投策略": StrategyItem(
        name="定投策略",
        match_reason="",
        description="定期定额买入宽基ETF，穿越牛熊",
        entry_rule="定期（周/月）定额买入",
        exit_rule="持有3年以上或牛市高估值时分批卖出",
        stop_loss="无固定止损，坚持定投纪律",
        risk_reward="长期2:1以上",
        difficulty="新手",
    ),
}

RISK_REWARD_LESSON = (
    "盈亏比是长期盈利的核心。假设盈亏比3:1，即使胜率只有40%，"
    "长期也能稳定盈利。关键是每笔交易严守止损纪律，让利润奔跑。"
    "赚大亏小，而非追求高胜率。"
)


class StrategyMatcher:
    """Match trading strategies to stock conditions."""

    def __init__(self, config: dict):
        cfg = config.get("strategies", {})
        self.max_recs = cfg.get("max_recommendations", 3)

    def match(
        self,
        symbol: str,
        name: str,
        market: str,
        character_type: str,
        diagnosis: dict[str, float],
        fear_score: float,
        sector_tier: str | None = None,
    ) -> TradingStrategies:
        candidates = []

        trend = diagnosis.get("trend", 50)
        momentum = diagnosis.get("momentum", 50)
        sentiment = diagnosis.get("sentiment", 50)

        is_hot = character_type == "游资票"
        is_inst = character_type == "机构票"
        is_oversold = trend < 30 and momentum < 30
        is_high_fear = fear_score > 70
        is_uptrend = trend > 60
        is_strong_momentum = momentum > 70

        if is_hot and is_strong_momentum:
            reason = "游资票+动量强"
            if sector_tier in ("T1", "T2"):
                reason += "+板块领先"
            candidates.append(self._with_reason("龙头战法", reason))
            candidates.append(self._with_reason("打板战法", "游资票+强情绪周期"))

        if is_oversold and is_high_fear:
            candidates.append(self._with_reason("低吸反弹", f"超跌+恐慌指数{fear_score:.0f}"))

        if is_inst and is_uptrend:
            candidates.append(self._with_reason("波段持股", "机构票+趋势向上"))

        if is_uptrend and is_strong_momentum and not is_hot:
            candidates.append(self._with_reason("趋势突破", "趋势向上+动量充足"))

        if 35 <= trend <= 65 and 35 <= momentum <= 65:
            candidates.append(self._with_reason("高抛低吸", "震荡区间，适合箱体操作"))

        if not candidates:
            if is_inst:
                candidates.append(self._with_reason("波段持股", "机构票，波段操作为主"))
            else:
                candidates.append(self._with_reason("高抛低吸", "当前无明确趋势，箱体操作"))

        seen = set()
        unique = []
        for c in candidates:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)
        unique = unique[: self.max_recs]

        situation = self._describe_situation(character_type, trend, momentum, fear_score)

        return TradingStrategies(
            symbol=symbol, name=name, market=market,
            character_type=character_type,
            current_situation=situation,
            recommended=unique,
            risk_reward_lesson=RISK_REWARD_LESSON,
        )

    def match_general(self, market_score: float, fear_score: float) -> TradingStrategies:
        """No-symbol mode: general market strategies."""
        candidates = []

        if fear_score > 70:
            candidates.append(self._with_reason("低吸反弹", f"市场恐慌（{fear_score:.0f}），超跌机会"))
            candidates.append(self._with_reason("定投策略", "恐慌区域，适合定投布局"))
        elif market_score > 60:
            candidates.append(self._with_reason("趋势突破", "大盘偏暖，关注突破机会"))
            candidates.append(self._with_reason("波段持股", "趋势向上，持股待涨"))
        else:
            candidates.append(self._with_reason("定投策略", "市场不明朗，定投最稳妥"))
            candidates.append(self._with_reason("高抛低吸", "震荡市，高抛低吸"))

        situation = f"大盘评分{market_score:.0f}，恐慌指数{fear_score:.0f}"

        return TradingStrategies(
            symbol=None, name=None, market=None, character_type=None,
            current_situation=situation,
            recommended=candidates[: self.max_recs],
            risk_reward_lesson=RISK_REWARD_LESSON,
        )

    def _with_reason(self, strategy_name: str, reason: str) -> StrategyItem:
        base = STRATEGIES[strategy_name]
        return base.model_copy(update={"match_reason": reason})

    def _describe_situation(self, char_type, trend, momentum, fear) -> str:
        parts = [char_type]
        if trend > 60:
            parts.append("趋势向上")
        elif trend < 40:
            parts.append("趋势偏弱")
        if momentum > 60:
            parts.append("动量充足")
        elif momentum < 40:
            parts.append("动量不足")
        if fear > 70:
            parts.append("恐慌情绪高")
        elif fear < 30:
            parts.append("情绪贪婪")
        return "，".join(parts)
