"""Portfolio-based action recommendations.

Reads portfolio.yaml, fetches current prices and EMA levels,
computes structured metrics, then optionally generates natural
language advice via AI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf
from loguru import logger


class PortfolioAdvisor:
    """Generate action recommendations for user's holdings and watchlist."""

    def __init__(self, portfolio_path: str, config: dict):
        self.portfolio_path = Path(portfolio_path)
        self.config = config

        if self.portfolio_path.exists():
            with open(self.portfolio_path, "r", encoding="utf-8") as f:
                self.portfolio = yaml.safe_load(f) or {}
        else:
            self.portfolio = {}

        settings = self.portfolio.get("settings", {})
        self.ema_periods = settings.get("ema_periods", [20, 50, 100, 200])
        self.proximity_threshold = settings.get("proximity_threshold", 4)

    def analyze(self) -> dict:
        """Run portfolio analysis. Returns {"items": [...], "advice_text": str}."""
        if not self.portfolio or (
            not self.portfolio.get("holdings") and not self.portfolio.get("watchlist")
        ):
            return {"items": [], "advice_text": ""}

        metrics = self._compute_metrics()
        if not metrics:
            return {"items": [], "advice_text": ""}

        advice_text = self._generate_advice(metrics)
        return {"items": metrics, "advice_text": advice_text}

    def _compute_metrics(self) -> list[dict]:
        """Compute structured metrics for all portfolio items."""
        all_items = []
        for item in self.portfolio.get("holdings", []):
            all_items.append({**item, "_type": "holding"})
        for item in self.portfolio.get("watchlist", []):
            all_items.append({**item, "_type": "watchlist"})

        if not all_items:
            return []

        price_data = self._fetch_price_data(all_items)
        results = []

        for item in all_items:
            symbol = item["symbol"]
            hist = price_data.get(symbol)
            if hist is None or hist.empty:
                logger.warning(f"Portfolio: no data for {symbol}")
                continue

            closes = hist["Close"]
            current_price = round(float(closes.iloc[-1]), 2)
            daily_change = round(float(closes.iloc[-1] / closes.iloc[-2] - 1) * 100, 2) if len(closes) > 1 else 0

            # Calculate EMAs
            emas = {}
            for period in self.ema_periods:
                if len(closes) >= period:
                    ema_val = round(float(closes.ewm(span=period, adjust=False).mean().iloc[-1]), 2)
                    emas[f"ema_{period}"] = ema_val

            # RSI 14
            rsi = self._calc_rsi(closes, 14)

            # CMF 20
            cmf = self._calc_cmf(hist, 20)

            # Distance to key EMAs
            distance_to_ema200_pct = None
            if "ema_200" in emas and emas["ema_200"]:
                distance_to_ema200_pct = round((current_price / emas["ema_200"] - 1) * 100, 2)

            target_buy = item.get("target_buy")
            target_sell = item.get("target_sell")

            distance_to_target = None
            if target_buy:
                distance_to_target = round((current_price / target_buy - 1) * 100, 2)

            status = self._classify_status(current_price, target_buy)
            strength = self._signal_strength(current_price, target_buy)

            result = {
                "symbol": symbol,
                "name": item.get("name", symbol),
                "type": item["_type"],
                "current_price": current_price,
                "daily_change_pct": daily_change,
                "avg_cost": item.get("avg_cost"),
                "target_buy": target_buy,
                "target_sell": target_sell,
                "distance_to_target_pct": distance_to_target,
                "distance_to_ema200_pct": distance_to_ema200_pct,
                "rsi": rsi,
                "cmf": cmf,
                "status": status,
                "signal_strength": strength,
                "notes": item.get("notes", ""),
                "logic": item.get("logic", ""),
                "position_plan": item.get("position_plan", ""),
            }
            result.update(emas)
            results.append(result)

        return results

    def _fetch_price_data(self, items: list[dict]) -> dict[str, pd.DataFrame]:
        """Fetch historical price data for all symbols."""
        symbols = [item["symbol"] for item in items]
        max_period = max(self.ema_periods) + 50  # Extra buffer for EMA warmup
        data = {}
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period=f"{max_period}d")
                if not hist.empty:
                    data[sym] = hist
            except Exception as e:
                logger.warning(f"Portfolio: failed to fetch {sym}: {e}")
        return data

    def _classify_status(self, current: float, target_buy: float | None) -> str:
        if target_buy is None:
            return "holding"
        if current <= target_buy:
            return "in_zone"
        pct_above = (current / target_buy - 1) * 100
        if pct_above < self.proximity_threshold:
            return "approaching"
        return "away"

    def _signal_strength(self, current: float, target_buy: float | None) -> str:
        if target_buy is None:
            return "none"
        pct_above = (current / target_buy - 1) * 100
        if pct_above <= 0:
            return "strong"
        if pct_above < self.proximity_threshold:
            return "medium"
        return "weak"

    def _generate_advice(self, metrics: list[dict]) -> str:
        """Generate AI advice from metrics, with fallback to data-only."""
        analysis_cfg = self.config.get("analysis", {})
        if not analysis_cfg.get("enabled", True):
            return ""

        prompt = self._build_prompt(metrics)
        try:
            return self._call_ai(prompt, analysis_cfg)
        except Exception as e:
            logger.warning(f"Portfolio AI advice failed: {e}")
            if analysis_cfg.get("fallback_to_data_only", True):
                return ""
            return ""

    def _build_prompt(self, metrics: list[dict]) -> str:
        lines = [
            "You are a concise trading advisor. Based on the following portfolio data, "
            "generate action recommendations in Chinese.",
            "",
            "For each item, output:",
            "- Status icon: ✅ (in zone) / 🟡 (approaching) / ❌ (hold/away)",
            "- Item name — one-line summary",
            "- Current state (price, target, EMA distances)",
            "- Logic (2-3 sentences using the provided notes/logic)",
            "- Action instruction (specific price levels and position sizing)",
            "",
            "End with a priority ranking of actionable items.",
            "",
            "Portfolio data:",
            "```json",
        ]

        import json
        lines.append(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        return "\n".join(lines)

    def _call_ai(self, prompt: str, analysis_cfg: dict) -> str:
        """Call configured AI provider."""
        provider = analysis_cfg.get("provider", "gemini")
        model = analysis_cfg.get("model", "gemini-3.1-pro-preview")
        max_tokens = analysis_cfg.get("max_tokens", 4096)
        temperature = analysis_cfg.get("temperature", 0.3)

        if provider == "gemini":
            from google import genai
            import os
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return response.text or ""

        elif provider == "claude":
            import anthropic
            import os
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif provider == "openai":
            import openai
            import os
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""

        return ""

    @staticmethod
    def _calc_rsi(closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(window=period).mean()
        loss = (-delta.clip(upper=0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 1)

    @staticmethod
    def _calc_cmf(hist: pd.DataFrame, period: int = 20) -> float:
        """Chaikin Money Flow over given period."""
        if len(hist) < period or "Volume" not in hist.columns:
            return 0.0
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        volume = hist["Volume"]
        hl_range = high - low
        hl_range = hl_range.replace(0, 1e-10)
        mfm = ((close - low) - (high - close)) / hl_range
        mfv = mfm * volume
        cmf = mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, 1e-10)
        return round(float(cmf.iloc[-1]), 3)
