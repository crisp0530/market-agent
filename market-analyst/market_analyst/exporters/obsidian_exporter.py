"""Export analysis results to Obsidian markdown."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger


class ObsidianExporter:
    """Write market analysis markdown reports into an Obsidian vault."""

    def __init__(self, config: dict):
        obs_config = config.get("obsidian", {})
        self.vault_path = Path(obs_config.get("vault_path", str(Path.home())))
        self.output_path = obs_config.get("output_path", "03_output/market-analysis")
        self.tags = obs_config.get("tags", ["market-analysis", "daily", "auto-generated"])

    def export(
        self,
        strength_df: pd.DataFrame,
        anomalies: list,
        analysis_text: str,
        search_results: list | None = None,
        date: datetime | None = None,
        cycle_signals: list | None = None,
        lead_lag: list | None = None,
        stock_picks: dict | None = None,
        momentum_data: dict | None = None,
        portfolio_advice: dict | None = None,
    ) -> str:
        """Generate and save a markdown report, returning its absolute path."""
        if date is None:
            date = datetime.now()

        output_dir = self.vault_path / self.output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{date.strftime('%Y-%m-%d')}_market_analysis.md"
        filepath = output_dir / filename

        content = self._generate_markdown(
            strength_df,
            anomalies,
            analysis_text,
            search_results or [],
            date,
            cycle_signals or [],
            lead_lag or [],
            stock_picks or {},
            momentum_data=momentum_data or {},
            portfolio_advice=portfolio_advice or {},
        )

        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Report written: {filepath}")
        return str(filepath)

    def _generate_markdown(
        self,
        strength_df: pd.DataFrame,
        anomalies: list,
        analysis_text: str,
        search_results: list,
        date: datetime,
        cycle_signals: list,
        lead_lag: list,
        stock_picks: dict,
        momentum_data: dict | None = None,
        portfolio_advice: dict | None = None,
    ) -> str:
        sections: list[str] = []
        sections.append(self._frontmatter(date, strength_df, anomalies))
        sections.append(f"# Global Market Analysis - {date.strftime('%Y-%m-%d')}\n")
        sections.append(self._section_global_temp(strength_df))
        sections.append(self._section_anomalies(anomalies, search_results))
        sections.append(self._section_fear_bottom(strength_df))
        sections.append(self._section_premarket(strength_df))
        sections.append(self._section_cycle(strength_df, cycle_signals, lead_lag))

        if analysis_text:
            sections.append("## AI Analysis\n")
            sections.append(analysis_text)
            sections.append("")

        if stock_picks:
            sections.append(self._section_stock_picks(stock_picks))

        if momentum_data:
            sections.append(self._section_momentum(momentum_data))

        if portfolio_advice and portfolio_advice.get("items"):
            sections.append(self._section_portfolio(portfolio_advice))

        sections.append(self._section_market_strength(strength_df, "us", "US"))
        sections.append(self._section_market_strength(strength_df, "cn", "CN"))
        sections.append(self._footer(date))
        return "\n".join(sections)

    def _frontmatter(self, date: datetime, strength_df: pd.DataFrame, anomalies: list) -> str:
        tags_str = "\n".join(f"  - {tag}" for tag in self.tags)
        us_count = len(strength_df[strength_df.get("market") == "us"]) if not strength_df.empty else 0
        cn_count = len(strength_df[strength_df.get("market") == "cn"]) if not strength_df.empty else 0
        return (
            "---\n"
            f"date: {date.strftime('%Y-%m-%d')}\n"
            "type: market-analysis\n"
            "tags:\n"
            f"{tags_str}\n"
            f"us_etfs: {us_count}\n"
            f"cn_etfs: {cn_count}\n"
            f"anomalies: {len(anomalies)}\n"
            "---\n"
        )

    def _section_global_temp(self, df: pd.DataFrame) -> str:
        lines = ["## 1. Macro Snapshot\n"]
        global_df = df[df["market"] == "global"] if not df.empty else pd.DataFrame()
        if global_df.empty:
            lines.append("*No global index data*\n")
            return "\n".join(lines)

        lines.append("| Index | Last | 5d % | 20d % | 60d % |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, row in global_df.iterrows():
            lines.append(
                f"| {row.get('name', row['symbol'])} | {row.get('close', 0):.2f} | "
                f"{self._fmt_pct(row.get('roc_5d'))} | {self._fmt_pct(row.get('roc_20d'))} | {self._fmt_pct(row.get('roc_60d'))} |"
            )
        lines.append("")
        return "\n".join(lines)

    def _section_anomalies(self, anomalies: list, search_results: list) -> str:
        lines = ["## 2. Anomalies\n"]
        if not anomalies:
            lines.append("*No significant anomaly detected*\n")
            return "\n".join(lines)

        search_map = {sr.get("anomaly_key", ""): sr for sr in search_results}

        for i, a in enumerate(anomalies, 1):
            severity = a.get("severity", "low").upper()
            lines.append(f"### {i}. [{severity}] {a.get('description', '')}\n")
            anomaly_key = f"{a.get('type', '')}:{','.join(a.get('symbols', []))}"
            sr = search_map.get(anomaly_key)
            if sr and sr.get("results"):
                lines.append("**Web verification:**")
                for r in sr["results"][:2]:
                    lines.append(f"- {r.get('title', '')}: {r.get('snippet', '')[:150]}")
                lines.append("")
            elif a.get("severity") == "high":
                lines.append("*Unverified*\n")

        return "\n".join(lines)

    def _section_market_strength(self, df: pd.DataFrame, market: str, market_name: str) -> str:
        market_df = df[df["market"] == market].sort_values("composite_score", ascending=False) if not df.empty else pd.DataFrame()
        if market_df.empty:
            return f"## {market_name} Strength\n\n*No data*\n"

        lines = [f"## {market_name} Strength\n"]
        tier_counts = market_df["tier"].value_counts()
        lines.append(
            f"**Tier distribution**: T1={tier_counts.get('T1', 0)} | T2={tier_counts.get('T2', 0)} | "
            f"T3={tier_counts.get('T3', 0)} | T4={tier_counts.get('T4', 0)}\n"
        )

        has_delta_roc = "delta_roc_5d" in market_df.columns
        has_sharpe = "sharpe" in market_df.columns
        has_fear = "fear_score" in market_df.columns

        for tier in ["T1", "T2", "T3", "T4"]:
            tier_df = market_df[market_df["tier"] == tier]
            if tier_df.empty:
                continue

            lines.append(f"### {tier}\n")
            header = "| Name | Symbol | Close | 5d % | 20d % | 60d % |"
            sep = "|---|---|---:|---:|---:|---:|"
            if has_delta_roc:
                header += " dROC |"
                sep += "---:|"
            if has_sharpe:
                header += " Sharpe |"
                sep += "---:|"
            if has_fear:
                header += " Fear | Bottom | Streak |"
                sep += "---:|---:|---:|"
            header += " Score |"
            sep += "---:|"
            lines.append(header)
            lines.append(sep)

            for _, row in tier_df.iterrows():
                row_str = (
                    f"| {row.get('name', row['symbol'])} | {row['symbol']} | {row.get('close', 0):.2f} | "
                    f"{self._fmt_pct(row.get('roc_5d'))} | {self._fmt_pct(row.get('roc_20d'))} | "
                    f"{self._fmt_pct(row.get('roc_60d'))} |"
                )
                if has_delta_roc:
                    row_str += f" {row.get('delta_roc_5d', 0):+.1f} |"
                if has_sharpe:
                    row_str += f" {row.get('sharpe', 0):.2f} |"
                if has_fear:
                    fear_val = int(row["fear_score"]) if pd.notna(row.get("fear_score")) else "—"
                    bottom_val = int(row["bottom_score"]) if pd.notna(row.get("bottom_score")) else "—"
                    streak_val = f"{int(row['streak']):+d}d" if pd.notna(row.get("streak")) else "—"
                    row_str += f" {fear_val} | {bottom_val} | {streak_val} |"
                row_str += f" {row.get('composite_score', 0):.1f} |"
                lines.append(row_str)

            lines.append("")

        return "\n".join(lines)

    def _section_fear_bottom(self, strength_df: pd.DataFrame) -> str:
        if "fear_score" not in strength_df.columns:
            return ""

        lines = ["## Fear / Bottom Scores\n"]
        lines.append("### Market Fear Snapshot\n")
        lines.append("| Market | Fear Median | Extreme Fear | Fear | Neutral | Greed | Extreme Greed |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")

        for market, label in [("us", "US"), ("cn", "CN")]:
            mdf = strength_df[strength_df["market"] == market]
            if mdf.empty:
                continue
            scores = mdf["fear_score"].dropna()
            if scores.empty:
                continue

            median_val = scores.median()
            if "fear_label" in mdf.columns:
                label_counts = mdf["fear_label"].value_counts()
                extreme_fear = int(label_counts.get("极恐慌", 0))
                fear = int(label_counts.get("恐慌", 0))
                neutral = int(label_counts.get("中性", 0))
                greed = int(label_counts.get("贪婪", 0))
                extreme_greed = int(label_counts.get("极贪婪", 0))
            else:
                extreme_fear = int((scores >= 75).sum())
                fear = int(((scores >= 60) & (scores < 75)).sum())
                neutral = int(((scores >= 40) & (scores < 60)).sum())
                greed = int(((scores >= 25) & (scores < 40)).sum())
                extreme_greed = int((scores < 25).sum())

            lines.append(
                f"| {label} | {median_val:.0f} | {extreme_fear} | {fear} | {neutral} | {greed} | {extreme_greed} |"
            )
        lines.append("")

        has_bottom = "bottom_score" in strength_df.columns
        if has_bottom:
            bottom_df = strength_df[strength_df["bottom_score"].notna() & (strength_df["bottom_score"] >= 40)].copy()
            if not bottom_df.empty:
                bottom_df = bottom_df.sort_values("bottom_score", ascending=False).head(10)
                lines.append("### Bottom Signals\n")
                lines.append("| Name | Symbol | Bottom | Fear | RSI Dim | DD Dim | Vol Dim | Flow Dim | Label |")
                lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
                for _, row in bottom_df.iterrows():
                    bottom_dd_val = row.get("bottom_drawdown_dim")
                    if pd.isna(bottom_dd_val):
                        bottom_dd_val = row.get("bottom_dd_dim")

                    rsi_dim = f"{int(row['bottom_rsi_dim'])}/25" if pd.notna(row.get("bottom_rsi_dim")) else "—"
                    dd_dim = f"{int(bottom_dd_val)}/25" if pd.notna(bottom_dd_val) else "—"
                    vol_dim = f"{int(row['bottom_vol_dim'])}/25" if pd.notna(row.get("bottom_vol_dim")) else "—"
                    flow_dim = f"{int(row['bottom_flow_dim'])}/25" if pd.notna(row.get("bottom_flow_dim")) else "—"
                    fear_val = int(row["fear_score"]) if pd.notna(row.get("fear_score")) else "—"
                    lines.append(
                        f"| {row.get('name', row['symbol'])} | {row['symbol']} | {int(row['bottom_score'])} | {fear_val} | "
                        f"{rsi_dim} | {dd_dim} | {vol_dim} | {flow_dim} | {row.get('bottom_label', '—')} |"
                    )
                lines.append("")

        return "\n".join(lines)

    def _section_premarket(self, df: pd.DataFrame) -> str:
        if "pm_price" not in df.columns:
            return ""

        pm_df = df[df["pm_price"].notna()].copy()
        if pm_df.empty:
            return ""

        pm_df = pm_df.sort_values("pm_gap", key=abs, ascending=False)
        lines = ["## Premarket Moves\n"]
        lines.append("| Name | Symbol | Prev Close | Premarket | Gap % | Tier |")
        lines.append("|---|---|---:|---:|---:|---|")

        for _, row in pm_df.iterrows():
            lines.append(
                f"| {row.get('name', row['symbol'])} | {row['symbol']} | {row.get('close', 0):.2f} | "
                f"{row.get('pm_price', 0):.2f} | {self._fmt_pct(row.get('pm_gap'))} | {row.get('tier', '—')} |"
            )

        big_movers = pm_df[pm_df["pm_gap"].abs() > 5]
        if not big_movers.empty:
            lines.append("")
            for _, row in big_movers.iterrows():
                direction = "surge" if row["pm_gap"] > 0 else "drop"
                lines.append(f"> **{row.get('name', row['symbol'])}** premarket {direction} {row['pm_gap']:+.2f}%")

        lines.append("")
        return "\n".join(lines)

    def _section_stock_picks(self, stock_picks: dict) -> str:
        lines = ["## Stock Picks\n"]
        sector_picks = stock_picks.get("sector_picks", [])
        us_picks = [sp for sp in sector_picks if sp.get("market") != "cn"]
        cn_picks = [sp for sp in sector_picks if sp.get("market") == "cn"]

        if us_picks:
            lines.append("### US Sector Picks\n")
            lines.extend(self._render_sector_picks(us_picks, currency="$", cap_unit="B"))

        if cn_picks:
            lines.append("### CN Sector Picks\n")
            lines.extend(self._render_sector_picks(cn_picks, currency="¥", cap_unit="亿"))

        big_up = stock_picks.get("big_movers_up", [])
        big_down = stock_picks.get("big_movers_down", [])
        if big_up:
            lines.extend(self._render_big_movers(big_up, "US Gainers (>8%)", "$", "B"))
        if big_down:
            lines.extend(self._render_big_movers(big_down, "US Losers (<-8%)", "$", "B"))

        cn_up = stock_picks.get("cn_big_movers_up", [])
        cn_down = stock_picks.get("cn_big_movers_down", [])
        if cn_up:
            lines.extend(self._render_big_movers(cn_up, "CN Gainers (>5%)", "¥", "亿"))
        if cn_down:
            lines.extend(self._render_big_movers(cn_down, "CN Losers (<-5%)", "¥", "亿"))

        if not (sector_picks or big_up or big_down or cn_up or cn_down):
            lines.append("*No notable stock opportunities today*\n")

        return "\n".join(lines)

    def _render_sector_picks(self, picks: list, currency: str = "$", cap_unit: str = "B") -> list[str]:
        lines: list[str] = []
        for sp in picks:
            etfs = ", ".join(sp.get("source_etfs", []))
            lines.append(f"#### {sp.get('sector', 'Unknown')} (source: {etfs})\n")
            lines.append("| Symbol | Price | Chg % | RelVol | RSI | CMF | MktCap | Industry |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
            for s in sp.get("stocks", []):
                unit = s.get("market_cap_unit", cap_unit)
                lines.append(
                    f"| {s.get('symbol', '')} | {currency}{s.get('price', 0):.2f} | {self._fmt_pct(s.get('change_pct'))} | "
                    f"{s.get('rel_volume', 0):.2f}x | {s.get('rsi', 0):.0f} | {s.get('cmf', 0):+.3f} | "
                    f"{s.get('market_cap_b', 0):.0f}{unit} | {str(s.get('industry', ''))[:18]} |"
                )
            lines.append("")
        return lines

    def _render_big_movers(self, movers: list, title: str, currency: str = "$", cap_unit: str = "B") -> list[str]:
        lines = [f"### {title}\n"]
        lines.append("| Symbol | Price | Chg % | RelVol | RSI | MktCap | Industry |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for s in movers[:10]:
            unit = s.get("market_cap_unit", cap_unit)
            lines.append(
                f"| {s.get('symbol', '')} | {currency}{s.get('price', 0):.2f} | **{self._fmt_pct(s.get('change_pct'))}** | "
                f"{s.get('rel_volume', 0):.2f}x | {s.get('rsi', 0):.0f} | {s.get('market_cap_b', 0):.0f}{unit} | "
                f"{str(s.get('industry', ''))[:18]} |"
            )
        lines.append("")
        return lines

    def _section_momentum(self, momentum_data: dict) -> str:
        lines = ["## Momentum Surges\n"]

        for market_key, label, currency, cap_unit in [
            ("us_momentum", "US Momentum (5d >15% or 1M >30%)", "$", "B"),
            ("cn_momentum", "CN Momentum (5d >15% or 1M >30%)", "¥", "亿"),
        ]:
            items = momentum_data.get(market_key, [])
            if not items:
                continue
            lines.append(f"### {label}\n")
            lines.append("| Name | Symbol | Price | Day % | 5d % | 1M % | Trigger | RSI | RelVol | MktCap | Industry |")
            lines.append("|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|")
            for s in items:
                unit = s.get("market_cap_unit", cap_unit)
                lines.append(
                    f"| {s.get('name', '')} | {s['symbol']} | {currency}{s.get('price', 0):.2f} | "
                    f"{self._fmt_pct(s.get('change_pct'))} | {self._fmt_pct(s.get('perf_5d'))} | "
                    f"{self._fmt_pct(s.get('perf_20d'))} | {s.get('trigger', '')} | "
                    f"{s.get('rsi', 0):.0f} | {s.get('rel_volume', 0):.2f}x | "
                    f"{s.get('market_cap_b', 0):.0f}{unit} | {str(s.get('industry', ''))[:20]} |"
                )
            lines.append("")

        if not any(momentum_data.get(k) for k in ("us_momentum", "cn_momentum")):
            lines.append("*No multi-day momentum surges detected*\n")

        return "\n".join(lines)

    def _section_portfolio(self, portfolio_advice: dict) -> str:
        lines = ["## Portfolio Action Plan\n"]

        items = portfolio_advice.get("items", [])
        advice_text = portfolio_advice.get("advice_text", "")

        if advice_text:
            lines.append(advice_text)
            lines.append("")
        else:
            # Fallback: structured table
            holdings = [i for i in items if i["type"] == "holding"]
            watchlist = [i for i in items if i["type"] == "watchlist"]

            if holdings:
                lines.append("### Holdings\n")
                lines.append("| Name | Symbol | Cost | Current | P/L % | Status | Notes |")
                lines.append("|---|---|---:|---:|---:|---|---|")
                for h in holdings:
                    pnl = ""
                    if h.get("avg_cost") and h.get("current_price"):
                        pnl_val = (h["current_price"] / h["avg_cost"] - 1) * 100
                        pnl = f"{pnl_val:+.1f}"
                    lines.append(
                        f"| {h['name']} | {h['symbol']} | ${h.get('avg_cost', '—')} | "
                        f"${h.get('current_price', '—')} | {pnl} | {h.get('status', '')} | "
                        f"{h.get('notes', '')} |"
                    )
                lines.append("")

            if watchlist:
                lines.append("### Watchlist\n")
                lines.append("| Name | Symbol | Target | Current | Distance | Status | Signal |")
                lines.append("|---|---|---:|---:|---:|---|---|")
                for w in watchlist:
                    lines.append(
                        f"| {w['name']} | {w['symbol']} | ${w.get('target_buy', '—')} | "
                        f"${w.get('current_price', '—')} | {w.get('distance_to_target_pct', '—')}% | "
                        f"{w.get('status', '')} | {w.get('signal_strength', '')} |"
                    )
                lines.append("")

        return "\n".join(lines)

    def _section_cycle(self, strength_df: pd.DataFrame, cycle_signals: list, lead_lag: list) -> str:
        lines = ["## Breakout / Parabolic Signals\n"]

        if "cycle_stage" in strength_df.columns:
            detected = strength_df[strength_df["cycle_stage_num"] > 0].copy()
            if not detected.empty:
                detected = detected.sort_values("cycle_stage_num", ascending=False)
                lines.append("| Name | Symbol | Market | Stage | Position | Confidence |")
                lines.append("|---|---|---|---|---:|---|")
                for _, row in detected.iterrows():
                    lines.append(
                        f"| {row.get('name', row['symbol'])} | {row['symbol']} | {row.get('market', '')} | "
                        f"{row.get('cycle_stage', '')} | {row.get('cycle_position', 0):.0%} | {row.get('cycle_confidence', '')} |"
                    )
                lines.append("")
            else:
                lines.append("*No breakout/parabolic trigger today*\n")

        if cycle_signals:
            lines.append("### Active Signals\n")
            for s in cycle_signals:
                lines.append(f"#### [{s.get('confidence', '').upper()}] {s.get('name', '')} - {s.get('signal_type', '')}\n")
                lines.append(f"- **Description**: {s.get('description', '')}")
                lines.append(
                    f"- **Close**: {s.get('close', 0)} | **Key level**: {s.get('key_level', 0)} | "
                    f"**Invalidation**: {s.get('invalidation', 0)}"
                )
                lines.append("")
        else:
            lines.append("*No active cycle signal*\n")

        if lead_lag:
            lines.append("### Lead-Lag\n")
            for ll in lead_lag:
                lines.append(
                    f"- {ll.get('pair_name', '')}: {ll.get('description', '')} (r={ll.get('correlation', 0):.3f})"
                )
            lines.append("")

        return "\n".join(lines)

    def _footer(self, date: datetime) -> str:
        return f"\n---\n*Generated at {date.strftime('%Y-%m-%d %H:%M')} | Market Analyst Agent*\n"

    @staticmethod
    def _fmt_pct(val) -> str:
        if pd.isna(val):
            return "—"
        if val > 0:
            return f"+{val:.2f}"
        return f"{val:.2f}"
