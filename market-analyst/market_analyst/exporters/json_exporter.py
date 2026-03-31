"""Export analysis results to JSON for web dashboard."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger


class JsonExporter:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, strength_df: pd.DataFrame, anomalies: list,
               analysis_text: str, cycle_signals: list,
               stock_picks: dict, config: dict,
               momentum_data: dict | None = None,
               portfolio_advice: dict | None = None) -> Path:
        """Export all analysis data to a dated JSON file."""
        today = datetime.now().strftime("%Y-%m-%d")
        data = {
            "date": today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self._build_summary(strength_df, anomalies),
            "strength": self._df_to_records(strength_df),
            "anomalies": anomalies,
            "cycle_signals": cycle_signals,
            "stock_picks": stock_picks,
            "momentum_surge": momentum_data or {},
            "portfolio_advice": portfolio_advice or {},
            "analysis_text": analysis_text or "",
        }

        filepath = self.output_dir / f"{today}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"JSON exported: {filepath} ({filepath.stat().st_size / 1024:.1f} KB)")
        self._cleanup_old_files(max_days=30)
        return filepath

    def _build_summary(self, df: pd.DataFrame, anomalies: list) -> dict:
        summary = {
            "total_symbols": int(df["symbol"].nunique()) if not df.empty else 0,
            "anomaly_count": len(anomalies),
            "tier_distribution": {},
        }

        if not df.empty:
            # Tier distribution
            if "tier" in df.columns:
                summary["tier_distribution"] = df["tier"].value_counts().to_dict()

            # Market temperatures (from market_temp_5d numeric field)
            if "market_temp_5d" in df.columns:
                for market in ["us", "cn"]:
                    market_df = df[df["market"] == market]
                    if not market_df.empty:
                        temps = market_df["market_temp_5d"].dropna()
                        if not temps.empty:
                            avg_temp = float(temps.mean())
                            summary[f"{market}_temperature"] = self._temp_to_label(avg_temp)
                            summary[f"{market}_temp_value"] = round(avg_temp, 2)

            # VIX
            vix_rows = df[df["symbol"] == "^VIX"]
            if not vix_rows.empty:
                vix_row = vix_rows.iloc[0]
                summary["vix_close"] = round(float(vix_row.get("close", 0)), 2)
                summary["vix_roc_5d"] = round(float(vix_row.get("roc_5d", 0)), 2)

        return summary

    @staticmethod
    def _temp_to_label(temp_value: float) -> str:
        """Convert market_temp_5d numeric value to human-readable label."""
        if temp_value > 1.0:
            return "强势"
        elif temp_value > 0.3:
            return "偏强"
        elif temp_value > -0.3:
            return "震荡"
        elif temp_value > -1.0:
            return "偏弱"
        else:
            return "弱势"

    def _df_to_records(self, df: pd.DataFrame) -> list:
        """Convert DataFrame to list of dicts, handling NaN/Inf."""
        if df is None or df.empty:
            return []
        records = df.to_dict(orient="records")
        # Clean each record: replace NaN/Inf with None, round floats
        import math
        cleaned = []
        for record in records:
            clean_record = {}
            for k, v in record.items():
                if v is None:
                    clean_record[k] = None
                elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    clean_record[k] = None
                elif isinstance(v, float):
                    clean_record[k] = round(v, 4)
                else:
                    clean_record[k] = v
            cleaned.append(clean_record)
        return cleaned

    def _cleanup_old_files(self, max_days: int = 30):
        """Delete JSON files older than max_days."""
        cutoff = datetime.now() - timedelta(days=max_days)
        removed = 0
        for f in self.output_dir.glob("*.json"):
            try:
                # Parse date from filename (YYYY-MM-DD.json)
                date_str = f.stem
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        if removed:
            logger.info(f"Cleaned up {removed} old JSON files (>{max_days} days)")
