"""Anomaly detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from .strength_calculator import StrengthCalculator


class AnomalyDetector:
    """Detect market anomalies from ranked strength data."""

    def __init__(self, config: dict):
        self.config = config
        anomaly_cfg = config.get("anomaly", {})
        self.zscore_threshold = anomaly_cfg.get("zscore_threshold", 2.0)
        self.tier_jump_days = anomaly_cfg.get("tier_jump_days", 20)
        self.cluster_threshold = anomaly_cfg.get("cluster_threshold", 0.4)
        self.momentum_threshold = anomaly_cfg.get("momentum_reversal_threshold", 3.0)

    def detect(self, strength_df: pd.DataFrame, raw_df: pd.DataFrame) -> list:
        """Return a sorted list of anomaly dictionaries."""
        anomalies: list[dict] = []

        if strength_df is None or strength_df.empty:
            return anomalies

        anomalies.extend(self._detect_zscore(strength_df))
        anomalies.extend(self._detect_divergence(strength_df))
        anomalies.extend(self._detect_tier_jump(strength_df, raw_df))
        anomalies.extend(self._detect_cross_market(strength_df))
        anomalies.extend(self._detect_clustering(strength_df))
        anomalies.extend(self._detect_momentum_reversal(strength_df))

        severity_order = {"high": 0, "medium": 1, "low": 2}
        anomalies.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))
        logger.info(f"Detected {len(anomalies)} anomalies")
        return anomalies

    def _detect_zscore(self, df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        for market in df["market"].dropna().unique():
            market_df = df[df["market"] == market]
            if len(market_df) < 5:
                continue

            mean = market_df["roc_5d"].mean()
            std = market_df["roc_5d"].std()
            if pd.isna(std) or std == 0:
                continue

            zscores = (market_df["roc_5d"] - mean) / std
            extreme_mask = zscores.abs() > self.zscore_threshold
            for _, row in market_df[extreme_mask].iterrows():
                zscore = float((row["roc_5d"] - mean) / std)
                severity = "high" if abs(zscore) > 3.0 else "medium"
                direction = "surge" if zscore > 0 else "drop"
                anomalies.append(
                    {
                        "type": "zscore",
                        "severity": severity,
                        "symbols": [row["symbol"]],
                        "description": (
                            f"{row.get('name', row['symbol'])}({row['symbol']}) 5d {direction} "
                            f"outlier: z={zscore:.2f}, roc_5d={row['roc_5d']:.2f}%"
                        ),
                        "data": {
                            "zscore": round(zscore, 2),
                            "roc_5d": round(float(row["roc_5d"]), 2),
                            "market": market,
                        },
                    }
                )

        return anomalies

    def _detect_divergence(self, df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        vix_rows = df[df["symbol"] == "^VIX"]
        qqq_rows = df[df["symbol"] == "QQQ"]
        if vix_rows.empty or qqq_rows.empty:
            return anomalies

        vix_row = vix_rows.iloc[0]
        qqq_row = qqq_rows.iloc[0]
        vix_roc = float(vix_row.get("roc_5d", 0.0))
        qqq_roc = float(qqq_row.get("roc_5d", 0.0))

        vix_close = vix_row.get("close")
        if pd.notna(vix_close):
            if vix_close < 15:
                vix_level = "low_fear"
            elif vix_close <= 25:
                vix_level = "normal"
            elif vix_close <= 35:
                vix_level = "high_fear"
            else:
                vix_level = "extreme_fear"
        else:
            vix_level = "unknown"

        usd_rows = df[df["symbol"].isin(["UUP", "DX-Y.NYB"])]
        usd_roc = float(usd_rows.iloc[0]["roc_5d"]) if not usd_rows.empty else 0.0
        usd_direction = "up" if usd_roc > 0.5 else ("down" if usd_roc < -0.5 else "flat")

        vix_up = vix_roc > 1
        vix_down = vix_roc < -1
        qqq_up = qqq_roc > 1
        qqq_down = qqq_roc < -1

        base_data = {
            "vix_roc": round(vix_roc, 2),
            "qqq_roc": round(qqq_roc, 2),
            "usd_roc": round(usd_roc, 2),
            "vix_close": round(float(vix_close), 2) if pd.notna(vix_close) else None,
            "vix_level": vix_level,
            "usd_direction": usd_direction,
        }

        if vix_up and usd_direction == "up":
            severity = "high" if vix_level in ("high_fear", "extreme_fear") else "medium"
            anomalies.append(
                {
                    "type": "divergence",
                    "severity": severity,
                    "symbols": ["^VIX"] + ([usd_rows.iloc[0]["symbol"]] if not usd_rows.empty else []),
                    "description": (
                        f"Risk-off mode: VIX +{vix_roc:.2f}% ({vix_level}) with USD +{usd_roc:.2f}%"
                    ),
                    "data": base_data,
                }
            )

        if vix_up and usd_direction == "down":
            anomalies.append(
                {
                    "type": "divergence",
                    "severity": "high",
                    "symbols": ["^VIX"] + ([usd_rows.iloc[0]["symbol"]] if not usd_rows.empty else []),
                    "description": (
                        f"Global stress: VIX +{vix_roc:.2f}% but USD {usd_roc:.2f}% (non-USD hedges may lead)"
                    ),
                    "data": base_data,
                }
            )

        if vix_down and qqq_down:
            anomalies.append(
                {
                    "type": "divergence",
                    "severity": "medium",
                    "symbols": ["^VIX", "QQQ"],
                    "description": (
                        f"Fear easing but QQQ still weak: VIX {vix_roc:.2f}%, QQQ {qqq_roc:.2f}%"
                    ),
                    "data": base_data,
                }
            )

        if vix_up and qqq_up:
            severity = "high" if vix_level in ("high_fear", "extreme_fear") else "medium"
            anomalies.append(
                {
                    "type": "divergence",
                    "severity": severity,
                    "symbols": ["^VIX", "QQQ"],
                    "description": (
                        f"VIX and QQQ rising together: VIX +{vix_roc:.2f}%, QQQ +{qqq_roc:.2f}%"
                    ),
                    "data": base_data,
                }
            )

        return anomalies

    def _detect_tier_jump(self, strength_df: pd.DataFrame, raw_df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        if raw_df is None or raw_df.empty:
            return anomalies

        unique_dates = sorted(pd.to_datetime(raw_df["date"].dropna().unique()))
        if len(unique_dates) <= self.tier_jump_days:
            return anomalies

        cutoff_date = unique_dates[-(self.tier_jump_days + 1)]
        hist_raw = raw_df[pd.to_datetime(raw_df["date"]) <= cutoff_date].copy()
        if hist_raw.empty:
            return anomalies

        hist_strength = StrengthCalculator(self.config).calculate(hist_raw)
        if hist_strength.empty or strength_df.empty:
            return anomalies

        tier_to_num = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
        hist_map = (
            hist_strength[["symbol", "tier"]]
            .drop_duplicates(subset=["symbol"])
            .set_index("symbol")["tier"]
            .to_dict()
        )

        for _, row in strength_df.iterrows():
            symbol = row["symbol"]
            prev_tier = hist_map.get(symbol)
            curr_tier = row.get("tier")
            if not prev_tier or prev_tier == curr_tier:
                continue

            prev_num = tier_to_num.get(prev_tier)
            curr_num = tier_to_num.get(curr_tier)
            if prev_num is None or curr_num is None:
                continue

            jump_size = abs(curr_num - prev_num)
            if jump_size < 2:
                continue

            severity = "high" if jump_size >= 3 else "medium"
            direction = "up" if curr_num < prev_num else "down"
            anomalies.append(
                {
                    "type": "tier_jump",
                    "severity": severity,
                    "symbols": [symbol],
                    "description": (
                        f"{row.get('name', symbol)}({symbol}) {self.tier_jump_days}d tier jump: "
                        f"{prev_tier} -> {curr_tier} ({direction})"
                    ),
                    "data": {
                        "from_tier": prev_tier,
                        "to_tier": curr_tier,
                        "jump_size": jump_size,
                        "days": self.tier_jump_days,
                    },
                }
            )

        return anomalies

    def _detect_cross_market(self, df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        cross_market_checks = [
            (["UUP", "DX-Y.NYB"], ["GLD", "GC=F", "518880"], "up", "up", "USD and gold rising together", "high"),
            (["UUP", "DX-Y.NYB"], ["USO", "CL=F"], "up", "up", "USD and oil rising together", "high"),
            (["TLT"], ["SPY"], "down", "down", "Stock-bond selloff", "high"),
            (["GLD", "GC=F"], ["TLT"], "up", "up", "Gold and long bonds rising", "medium"),
            (["GLD", "GC=F"], ["TLT"], "up", "down", "Gold up while long bonds down", "medium"),
        ]

        for symbols_a, symbols_b, dir_a, dir_b, description, severity in cross_market_checks:
            rows_a = df[df["symbol"].isin(symbols_a)]
            rows_b = df[df["symbol"].isin(symbols_b)]
            if rows_a.empty or rows_b.empty:
                continue

            roc_a = float(rows_a.iloc[0]["roc_5d"])
            roc_b = float(rows_b.iloc[0]["roc_5d"])
            sym_a = rows_a.iloc[0]["symbol"]
            sym_b = rows_b.iloc[0]["symbol"]

            a_match = (dir_a == "up" and roc_a > 1) or (dir_a == "down" and roc_a < -1)
            b_match = (dir_b == "up" and roc_b > 1) or (dir_b == "down" and roc_b < -1)
            if not (a_match and b_match):
                continue

            anomalies.append(
                {
                    "type": "cross_market",
                    "severity": severity,
                    "symbols": [sym_a, sym_b],
                    "description": f"{description} ({sym_a}: {roc_a:+.2f}%, {sym_b}: {roc_b:+.2f}%)",
                    "data": {
                        "symbol_a": sym_a,
                        "roc_a": round(roc_a, 2),
                        "symbol_b": sym_b,
                        "roc_b": round(roc_b, 2),
                    },
                }
            )

        return anomalies

    def _detect_clustering(self, df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        for market in df["market"].dropna().unique():
            if market == "global":
                continue

            market_df = df[df["market"] == market]
            total = len(market_df)
            if total < 5:
                continue

            tier_counts = market_df["tier"].value_counts()
            for tier, count in tier_counts.items():
                ratio = count / total
                if ratio <= self.cluster_threshold:
                    continue

                if tier in ["T1", "T2"]:
                    desc = f"{market} concentration in {tier}: {count}/{total} ({ratio:.0%})"
                    severity = "medium" if tier == "T2" else "high"
                else:
                    desc = f"{market} concentration in {tier}: {count}/{total} ({ratio:.0%})"
                    severity = "medium" if tier == "T3" else "high"

                anomalies.append(
                    {
                        "type": "clustering",
                        "severity": severity,
                        "symbols": market_df[market_df["tier"] == tier]["symbol"].tolist(),
                        "description": desc,
                        "data": {
                            "market": market,
                            "tier": tier,
                            "count": int(count),
                            "total": int(total),
                            "ratio": round(ratio, 2),
                        },
                    }
                )

        return anomalies

    def _detect_momentum_reversal(self, df: pd.DataFrame) -> list:
        anomalies: list[dict] = []

        if "delta_roc_5d" not in df.columns:
            return anomalies

        for _, row in df.iterrows():
            delta = row.get("delta_roc_5d")
            if pd.isna(delta):
                continue

            symbol = row["symbol"]
            name = row.get("name", symbol)
            tier = row.get("tier", "")
            roc_5d = float(row.get("roc_5d", 0))
            delta = float(delta)

            if tier == "T1" and delta < -self.momentum_threshold:
                anomalies.append(
                    {
                        "type": "momentum_reversal",
                        "severity": "medium",
                        "symbols": [symbol],
                        "description": (
                            f"{name}({symbol}) is T1 but momentum is decelerating "
                            f"(delta_roc_5d={delta:.2f}, roc_5d={roc_5d:.2f}%)"
                        ),
                        "data": {
                            "tier": tier,
                            "roc_5d": round(roc_5d, 2),
                            "delta_roc_5d": round(delta, 2),
                        },
                    }
                )
            elif tier == "T4" and delta > self.momentum_threshold:
                anomalies.append(
                    {
                        "type": "momentum_reversal",
                        "severity": "medium",
                        "symbols": [symbol],
                        "description": (
                            f"{name}({symbol}) is T4 but momentum is improving quickly "
                            f"(delta_roc_5d=+{delta:.2f}, roc_5d={roc_5d:.2f}%)"
                        ),
                        "data": {
                            "tier": tier,
                            "roc_5d": round(roc_5d, 2),
                            "delta_roc_5d": round(delta, 2),
                        },
                    }
                )

        return anomalies
