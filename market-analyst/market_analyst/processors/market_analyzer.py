"""多模型 AI 市场分析 — 支持 Gemini / Claude / OpenAI"""
import os
from typing import Optional
import pandas as pd
from loguru import logger


SYSTEM_PROMPT = """你是一个专业的全球市场分析师。你的任务是基于 88 个板块 ETF 的相对强弱数据，进行全局逻辑推理和分析。

## 分析框架
1. **先看全局温度**：VIX/美元/黄金/原油 → 判断市场整体风险偏好
2. **再看板块轮动**：哪些板块在 T1（最强），哪些在 T4（最弱），中间梯队的变化方向
3. **重视异常 > 正常**：异常信号是最有信息量的部分
4. **分析传导链路**：美元→美股→A股→黄金，找到跨市场逻辑
5. **全部 88 个板块都要覆盖**，中间梯队（T2/T3）的变化方向往往更有信息量
6. **关注周期阶段**：Stage3(底部积累)是最有交易价值的阶段，Stage4(突破)是入场时机，Stage5(抛物线)需要警惕回调
7. **Lead-Lag 传导**：黄金常领先大盘，美股领先A股，关注领先指标的阶段变化对后续市场的预示
8. **恐慌与底部**：Fear Score 和 Bottom Score 是综合评分，关注高恐慌(>60)+高底部(>40)的交叉标的

## 输出结构（约 3000 字）
1. **全局温度计**：一段话概括市场温度（risk-on/risk-off/混合）
2. **异常信号解读**：逐条解读异常，给出可能的原因和含义
3. **美股板块全景**：T1→T4 展开，找每个梯队的共同逻辑
4. **A股板块全景**：同上结构
5. **主线传导逻辑**：美元→美股→A股→黄金的传导路径
6. **周期阶段判断**：各资产当前所处的周期阶段(Stage1-5)及其含义，哪些处于积累/突破阶段
7. **关注清单**：5-7 个值得持续跟踪的逻辑线索（优先包含 Stage3→4 转换中的标的）
8. **恐慌与底部洞察**：Fear Score 极端值标的是重要信号，结合 Bottom Score 和 Streak 判断是否存在逆向机会

## 反循环论证规则
- 禁止用"X涨了所以X强势"的同义反复，必须找到X上涨的独立驱动因子
- 每个因果推断必须有不同维度的数据支撑（如：用利差解释美元，用VIX解释股市，不能用美元解释美元）
- 如果无法找到独立因子验证，请明确标注"[待验证] 缺少独立因子，仅为相关性观察"
- 区分"描述现象"和"解释原因"：如果只能描述现象就说清楚，不要伪装成因果解释
- 对自己的每个关键判断，考虑历史上是否存在反例（如2020.3月VIX飙升但美元走强）

## 注意事项
- 你是研究助手，只做分析，不做投资建议
- 数据说什么就说什么，不要编造
- 不确定的地方标注"待验证"
- 用数据支撑每一个判断"""


class MarketAnalyzer:
    """多模型市场分析器 — 支持 gemini / claude / openai"""

    def __init__(self, config: dict):
        self.config = config.get("analysis", {})
        self.provider = self.config.get("provider", "gemini")  # gemini / claude / openai
        self.model = self.config.get("model", self._default_model())
        self.max_tokens = self.config.get("max_tokens", 4096)
        self.temperature = self.config.get("temperature", 0.3)
        self.client = None
        self._init_client()

    def _default_model(self) -> str:
        defaults = {
            "gemini": "gemini-2.5-flash",
            "claude": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
        }
        return defaults.get(self.provider, "gemini-2.5-flash")

    @staticmethod
    def _sanitize_error(error: Exception) -> str:
        """Mask any API key that might appear in exception messages"""
        msg = str(error)
        # Mask anything that looks like an API key (long alphanumeric strings)
        import re
        return re.sub(r'(sk-[a-zA-Z0-9]{8})[a-zA-Z0-9]+', r'\1***', msg)

    def _init_client(self):
        """根据 provider 初始化对应的客户端"""
        try:
            if self.provider == "gemini":
                self._init_gemini()
            elif self.provider == "claude":
                self._init_claude()
            elif self.provider == "openai":
                self._init_openai()
            else:
                logger.error(f"未知 provider: {self.provider}")
        except Exception as e:
            logger.error(f"{self.provider} 初始化失败: {self._sanitize_error(e)}")
            self.client = None

    def _init_gemini(self):
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY 未设置")
            return
        self.client = genai.Client(api_key=api_key)
        logger.info(f"Gemini 初始化成功 (model={self.model})")

    def _init_claude(self):
        from anthropic import Anthropic
        # 三层 key 优先级
        api_key = (
            os.environ.get("CLAUDE_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if not api_key or not api_key.strip():
            logger.error("ANTHROPIC_API_KEY not set, AI analysis will be skipped")
            return
        base_url = os.environ.get("CLAUDE_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        logger.info(f"Claude 初始化成功 (model={self.model})")

    def _init_openai(self):
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        if not api_key:
            logger.error("OPENAI_API_KEY 未设置")
            return
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        logger.info(f"OpenAI 初始化成功 (model={self.model})")

    # === 分析入口 ===

    def analyze(
        self,
        strength_df: pd.DataFrame,
        anomalies: list,
        search_results: list = None,
        cycle_signals: list = None,
        lead_lag: list = None,
    ) -> str:
        if self.client is None:
            logger.warning(f"{self.provider} 不可用，降级为纯数据报告")
            return self._fallback_analysis(strength_df, anomalies)

        data_text = self._build_data_text(strength_df, anomalies, search_results, cycle_signals, lead_lag)

        try:
            if self.provider == "gemini":
                analysis_text = self._call_gemini(data_text)
            elif self.provider == "claude":
                analysis_text = self._call_claude(data_text)
            elif self.provider == "openai":
                analysis_text = self._call_openai(data_text)
            else:
                analysis_text = None

            # Devil's Advocate: 默认关闭，config 中 challenge_enabled 为 true 时启用
            if (
                self.config.get("challenge_enabled", False)
                and analysis_text
                and "（AI 分析不可用" not in analysis_text
            ):
                challenge = self._challenge_analysis(analysis_text)
                if challenge:
                    analysis_text += "\n\n## AI 自我审查\n\n" + challenge

            return analysis_text
        except Exception as e:
            logger.error(f"{self.provider} API 调用失败: {self._sanitize_error(e)}")
            if "auth" in str(e).lower() or "key" in str(e).lower() or "401" in str(e) or "403" in str(e):
                logger.error("API Key 可能已过期，请更新 token")
            return self._fallback_analysis(strength_df, anomalies)

    def _call_gemini(self, data_text: str) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=f"{SYSTEM_PROMPT}\n\n---\n\n{data_text}",
            config={
                "max_output_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
        )
        text = resp.text
        logger.info(f"Gemini 分析完成，{len(text)} 字")
        return text

    def _call_claude(self, data_text: str) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": data_text}],
        )
        text = message.content[0].text
        logger.info(f"Claude 分析完成，{len(text)} 字")
        return text

    def _call_openai(self, data_text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": data_text},
            ],
        )
        text = resp.choices[0].message.content
        logger.info(f"OpenAI 分析完成，{len(text)} 字")
        return text

    # === 数据组装 ===

    def _build_data_text(self, strength_df: pd.DataFrame, anomalies: list, search_results: list = None, cycle_signals: list = None, lead_lag: list = None) -> str:
        sections = []

        # 盘前数据（如果有）
        if "pm_price" in strength_df.columns:
            pm_df = strength_df[strength_df["pm_price"].notna()]
            if not pm_df.empty:
                sections.append("## 盘前异动数据")
                for _, row in pm_df.sort_values("pm_gap", key=abs, ascending=False).iterrows():
                    sections.append(
                        f"- {row.get('name', row['symbol'])}({row['symbol']}): "
                        f"昨收={row['close']:.2f}, 盘前={row['pm_price']:.2f}, "
                        f"盘前涨跌={row['pm_gap']:+.2f}%"
                    )
                sections.append("")

        # 全局指标
        global_df = strength_df[strength_df["market"] == "global"]
        if not global_df.empty:
            sections.append("## 全局宏观指标")
            for _, row in global_df.iterrows():
                sections.append(
                    f"- {row['name']}({row['symbol']}): 收盘={row['close']:.2f}, "
                    f"5dROC={row['roc_5d']:.2f}%, 20dROC={row['roc_20d']:.2f}%, 60dROC={row['roc_60d']:.2f}%"
                )

        # 美股
        us_df = strength_df[strength_df["market"] == "us"].sort_values("composite_score", ascending=False)
        if not us_df.empty:
            sections.append("\n## 美股板块强弱排名（按综合得分降序）")
            sections.append("| 排名 | 板块 | 代码 | 梯队 | 综合分 | 5dROC% | 20dROC% | 60dROC% |")
            sections.append("|------|------|------|------|--------|--------|---------|---------|")
            for i, (_, row) in enumerate(us_df.iterrows(), 1):
                # 基础列
                line = (
                    f"| {i} | {row['name']} | {row['symbol']} | {row['tier']} | "
                    f"{row['composite_score']:.1f} | {row['roc_5d']:.2f} | {row['roc_20d']:.2f} | {row['roc_60d']:.2f} |"
                )
                # 追加量化指标（如果存在）
                extra = ""
                if "sharpe" in row and pd.notna(row.get("sharpe")):
                    extra += f" Sharpe={row['sharpe']:.2f}"
                if "delta_roc_5d" in row and pd.notna(row.get("delta_roc_5d")):
                    extra += f" Δ5d={row['delta_roc_5d']:+.2f}"
                if "global_zscore_5d" in row and pd.notna(row.get("global_zscore_5d")):
                    extra += f" GZ={row['global_zscore_5d']:+.2f}"
                # TradingView 独立指标（仅 T1/T4 有）
                if "tv_rsi" in row and pd.notna(row.get("tv_rsi")):
                    extra += f" RSI={row['tv_rsi']:.1f}"
                if "tv_macd_hist" in row and pd.notna(row.get("tv_macd_hist")):
                    extra += f" MACD柱={row['tv_macd_hist']:+.3f}"
                if "tv_cmf" in row and pd.notna(row.get("tv_cmf")):
                    extra += f" CMF={row['tv_cmf']:+.3f}"
                if "tv_rel_volume" in row and pd.notna(row.get("tv_rel_volume")):
                    extra += f" 相对量={row['tv_rel_volume']:.2f}"
                # 恐慌/底部分数
                if "fear_score" in row and pd.notna(row.get("fear_score")):
                    extra += f" Fear={row['fear_score']:.0f}"
                if "bottom_score" in row and pd.notna(row.get("bottom_score")):
                    extra += f" Bottom={row['bottom_score']:.0f}"
                if "streak" in row and pd.notna(row.get("streak")):
                    s = int(row['streak'])
                    extra += f" Streak={s:+d}d"
                if extra:
                    line += extra
                sections.append(line)

        # A股
        cn_df = strength_df[strength_df["market"] == "cn"].sort_values("composite_score", ascending=False)
        if not cn_df.empty:
            sections.append("\n## A股板块强弱排名（按综合得分降序）")
            sections.append("| 排名 | 板块 | 代码 | 梯队 | 综合分 | 5dROC% | 20dROC% | 60dROC% |")
            sections.append("|------|------|------|------|--------|--------|---------|---------|")
            for i, (_, row) in enumerate(cn_df.iterrows(), 1):
                # 基础列
                line = (
                    f"| {i} | {row['name']} | {row['symbol']} | {row['tier']} | "
                    f"{row['composite_score']:.1f} | {row['roc_5d']:.2f} | {row['roc_20d']:.2f} | {row['roc_60d']:.2f} |"
                )
                # 追加量化指标（如果存在）
                extra = ""
                if "sharpe" in row and pd.notna(row.get("sharpe")):
                    extra += f" Sharpe={row['sharpe']:.2f}"
                if "delta_roc_5d" in row and pd.notna(row.get("delta_roc_5d")):
                    extra += f" Δ5d={row['delta_roc_5d']:+.2f}"
                if "global_zscore_5d" in row and pd.notna(row.get("global_zscore_5d")):
                    extra += f" GZ={row['global_zscore_5d']:+.2f}"
                # TradingView 独立指标（仅 T1/T4 有）
                if "tv_rsi" in row and pd.notna(row.get("tv_rsi")):
                    extra += f" RSI={row['tv_rsi']:.1f}"
                if "tv_macd_hist" in row and pd.notna(row.get("tv_macd_hist")):
                    extra += f" MACD柱={row['tv_macd_hist']:+.3f}"
                if "tv_cmf" in row and pd.notna(row.get("tv_cmf")):
                    extra += f" CMF={row['tv_cmf']:+.3f}"
                if "tv_rel_volume" in row and pd.notna(row.get("tv_rel_volume")):
                    extra += f" 相对量={row['tv_rel_volume']:.2f}"
                # 恐慌/底部分数
                if "fear_score" in row and pd.notna(row.get("fear_score")):
                    extra += f" Fear={row['fear_score']:.0f}"
                if "bottom_score" in row and pd.notna(row.get("bottom_score")):
                    extra += f" Bottom={row['bottom_score']:.0f}"
                if "streak" in row and pd.notna(row.get("streak")):
                    s = int(row['streak'])
                    extra += f" Streak={s:+d}d"
                if extra:
                    line += extra
                sections.append(line)

        # 异常
        if anomalies:
            sections.append(f"\n## 检测到的异常信号 ({len(anomalies)} 个)")
            for i, a in enumerate(anomalies, 1):
                sections.append(f"{i}. [{a['severity'].upper()}] {a['description']}")

        # Web 搜索验证
        if search_results:
            sections.append("\n## Web 搜索验证结果")
            for sr in search_results:
                sections.append(f"### 搜索: {sr['query']}")
                for r in sr.get("results", [])[:3]:
                    sections.append(f"- {r['title']}: {r.get('snippet', '')[:200]}")

        # 周期阶段分布
        if "cycle_stage" in strength_df.columns:
            sections.append("\n## 周期阶段分布")
            for market, mname in [("us", "美股"), ("cn", "A股")]:
                mdf = strength_df[strength_df["market"] == market]
                if mdf.empty:
                    continue
                dist = mdf["cycle_stage"].value_counts().to_dict()
                sections.append(f"### {mname}: {dist}")
                # 列出 Stage3(积累) 和 Stage4(突破) 标的 — 最有交易价值
                for stage_name in ["Stage3", "Stage4", "Stage5"]:
                    stage_df = mdf[mdf["cycle_stage"] == stage_name]
                    if not stage_df.empty:
                        names = ", ".join(f"{r['name']}({r['cycle_position']:.0%})" for _, r in stage_df.iterrows())
                        sections.append(f"- {stage_name}: {names}")

        # 周期信号
        if cycle_signals:
            sections.append(f"\n## 周期信号 ({len(cycle_signals)} 个)")
            for s in cycle_signals:
                sections.append(f"- [{s['confidence'].upper()}] {s['signal_type']}: {s['description']}")

        # Lead-Lag 关系
        if lead_lag:
            sections.append(f"\n## Lead-Lag 关系 ({len(lead_lag)} 对)")
            for ll in lead_lag:
                sections.append(f"- {ll['pair_name']}: {ll['description']} (r={ll['correlation']:.3f})")

        # 恐慌/底部概览
        if "fear_score" in strength_df.columns:
            sections.append("\n## 恐慌/底部评分概览")
            for market, mname in [("us", "美股"), ("cn", "A股")]:
                mdf = strength_df[strength_df["market"] == market]
                if mdf.empty or "fear_score" not in mdf.columns:
                    continue
                fear_med = mdf["fear_score"].median()
                sections.append(f"- {mname}恐慌中位数: {fear_med:.0f}")

            # 交叉信号：高恐慌 + 底部信号
            has_fear = "fear_score" in strength_df.columns
            has_bottom = "bottom_score" in strength_df.columns
            if has_fear and has_bottom:
                cross = strength_df[
                    (strength_df["fear_score"] >= 60) &
                    (strength_df["bottom_score"] >= 40)
                ]
                if not cross.empty:
                    sections.append("\n### 恐慌中的机会（高恐慌+底部信号）")
                    for _, r in cross.iterrows():
                        streak_val = int(r.get("streak", 0)) if pd.notna(r.get("streak")) else 0
                        sections.append(
                            f"- {r.get('name', '')}({r['symbol']}): "
                            f"Fear={r['fear_score']:.0f} + Bottom={r['bottom_score']:.0f}, "
                            f"Streak={streak_val:+d}d"
                        )

        return "\n".join(sections)

    # === Devil's Advocate 质疑 ===

    def _challenge_analysis(self, analysis_text: str) -> str:
        """用同一个 provider 发第二轮请求，以审查员视角质疑分析结果"""
        challenge_prompt = (
            "你是一位严谨的金融分析审查员。你的任务是审查以下市场分析报告，"
            "按照以下 checklist 逐条检查并给出审查意见（300-500字）：\n\n"
            "1. **循环论证**：有没有用结果解释结果？（如'涨了所以强势'）\n"
            "2. **忽略反面证据**：有没有选择性引用数据、忽略不利信号？\n"
            "3. **超出数据范围的推断**：有没有数据不支撑的因果判断？\n"
            "4. **关键判断置信度**：对报告中每个关键判断标注置信度（高/中/低）\n\n"
            "请直接输出审查意见，不要重复原文。语言简洁，有问题就指出，没问题也说明理由。"
        )
        try:
            if self.provider == "gemini":
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{challenge_prompt}\n\n---\n\n以下是待审查的分析报告：\n\n{analysis_text}",
                    config={
                        "max_output_tokens": 1024,
                        "temperature": self.temperature,
                    },
                )
                text = resp.text
            elif self.provider == "claude":
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    temperature=self.temperature,
                    system=challenge_prompt,
                    messages=[{"role": "user", "content": f"以下是待审查的分析报告：\n\n{analysis_text}"}],
                )
                text = message.content[0].text
            elif self.provider == "openai":
                resp = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=1024,
                    temperature=self.temperature,
                    messages=[
                        {"role": "system", "content": challenge_prompt},
                        {"role": "user", "content": f"以下是待审查的分析报告：\n\n{analysis_text}"},
                    ],
                )
                text = resp.choices[0].message.content
            else:
                return ""
            logger.info(f"Devil's Advocate 审查完成，{len(text)} 字")
            return text
        except Exception as e:
            logger.warning(f"Devil's Advocate 审查失败: {self._sanitize_error(e)}")
            return ""

    def _fallback_analysis(self, strength_df: pd.DataFrame, anomalies: list) -> str:
        lines = ["*（AI 分析不可用，以下为纯数据摘要）*\n"]

        for market in ["us", "cn"]:
            market_df = strength_df[strength_df["market"] == market]
            if market_df.empty:
                continue
            market_name = "美股" if market == "us" else "A股"
            tier_dist = market_df["tier"].value_counts().to_dict()
            lines.append(f"### {market_name}梯队分布")
            lines.append(f"T1(强): {tier_dist.get('T1', 0)} | T2: {tier_dist.get('T2', 0)} | T3: {tier_dist.get('T3', 0)} | T4(弱): {tier_dist.get('T4', 0)}")

            if len(market_df) >= 3:
                lines.append(f"\n**最强 3 个板块**: {', '.join(market_df.head(3)['name'].tolist())}")
                lines.append(f"**最弱 3 个板块**: {', '.join(market_df.tail(3)['name'].tolist())}")
            lines.append("")

        if anomalies:
            lines.append("### 异常信号")
            for a in anomalies:
                lines.append(f"- [{a['severity']}] {a['description']}")

        return "\n".join(lines)
