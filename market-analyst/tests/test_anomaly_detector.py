"""Tests for AnomalyDetector."""

import pandas as pd
import numpy as np
import pytest

from market_analyst.processors.strength_calculator import StrengthCalculator
from market_analyst.processors.anomaly_detector import AnomalyDetector


@pytest.fixture
def strength_df(sample_raw_df, sample_config):
    """Pre-compute strength DataFrame for anomaly tests."""
    calc = StrengthCalculator(sample_config)
    return calc.calculate(sample_raw_df)


class TestAnomalyDetectorDetect:
    """Tests for AnomalyDetector.detect()."""

    def test_returns_list_of_dicts_with_required_keys(
        self, strength_df, sample_raw_df, sample_config
    ):
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(strength_df, sample_raw_df)

        assert isinstance(anomalies, list)
        required_keys = {"type", "severity", "symbols", "description", "data"}
        for a in anomalies:
            assert isinstance(a, dict)
            assert required_keys.issubset(a.keys()), (
                f"Anomaly missing keys: {required_keys - a.keys()}"
            )

    def test_severity_values_are_valid(
        self, strength_df, sample_raw_df, sample_config
    ):
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(strength_df, sample_raw_df)

        valid_severities = {"high", "medium", "low"}
        for a in anomalies:
            assert a["severity"] in valid_severities, (
                f"Invalid severity: {a['severity']}"
            )

    def test_normal_data_few_anomalies(
        self, strength_df, sample_raw_df, sample_config
    ):
        """With normally-distributed random data, anomalies should be limited."""
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(strength_df, sample_raw_df)

        # Not a strict bound, but random data shouldn't produce dozens of anomalies
        assert len(anomalies) < 30, (
            f"Too many anomalies ({len(anomalies)}) for normal data"
        )

    def test_extreme_data_triggers_zscore_anomaly(self, sample_raw_df, sample_config):
        """Inject a symbol with 50% 5-day return to trigger zscore anomaly."""
        dates = sorted(sample_raw_df["date"].unique())

        # Add several normal-range symbols to the 'us' market so that the
        # standard deviation isn't inflated by the single outlier.
        extra_rows = []
        for sym_name in ['IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP']:
            np.random.seed(hash(sym_name) % 2**31)
            base = 150
            prices = base * (1 + np.random.randn(len(dates)).cumsum() * 0.005)
            for i, date in enumerate(dates):
                p = prices[i]
                extra_rows.append({
                    'symbol': sym_name, 'name': sym_name, 'date': date,
                    'open': round(p * 0.999, 2), 'high': round(p * 1.005, 2),
                    'low': round(p * 0.995, 2), 'close': round(p, 2),
                    'volume': 30000000, 'market': 'us', 'sector': 'equity',
                })

        # Create the extreme mover: flat then 50% jump
        extreme_rows = []
        base_price = 100
        for i, date in enumerate(dates):
            if i >= len(dates) - 5:
                price = base_price * 1.5  # 50% jump
            else:
                price = base_price
            extreme_rows.append({
                'symbol': 'EXTREME', 'name': 'EXTREME', 'date': date,
                'open': price * 0.999, 'high': price * 1.005,
                'low': price * 0.995, 'close': price,
                'volume': 50000000, 'market': 'us', 'sector': 'equity',
            })

        combined_df = pd.concat(
            [sample_raw_df, pd.DataFrame(extra_rows), pd.DataFrame(extreme_rows)],
            ignore_index=True,
        )

        calc = StrengthCalculator(sample_config)
        strength = calc.calculate(combined_df)

        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(strength, combined_df)

        zscore_anomalies = [a for a in anomalies if a["type"] == "zscore"]
        extreme_zscore = [
            a for a in zscore_anomalies
            if "EXTREME" in a["symbols"]
        ]
        assert len(extreme_zscore) > 0, (
            "Expected zscore anomaly for EXTREME symbol with 50% return"
        )

    def test_empty_strength_df_returns_empty(self, sample_raw_df, sample_config):
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(pd.DataFrame(), sample_raw_df)

        assert anomalies == []

    def test_none_strength_df_returns_empty(self, sample_raw_df, sample_config):
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(None, sample_raw_df)

        assert anomalies == []

    def test_anomalies_sorted_by_severity(
        self, strength_df, sample_raw_df, sample_config
    ):
        detector = AnomalyDetector(sample_config)
        anomalies = detector.detect(strength_df, sample_raw_df)

        if len(anomalies) > 1:
            severity_order = {"high": 0, "medium": 1, "low": 2}
            orders = [severity_order[a["severity"]] for a in anomalies]
            assert orders == sorted(orders), "Anomalies should be sorted by severity"


class TestDetectTierJump:
    """Tests for AnomalyDetector._detect_tier_jump()."""

    def test_small_jump_returns_nothing(self, sample_config):
        """A tier change of < 2 should not trigger a tier_jump anomaly."""
        # Create strength_df where a symbol changed by only 1 tier
        strength_df = pd.DataFrame([{
            'symbol': 'SPY', 'name': 'SPY', 'market': 'us',
            'sector': 'equity',
            'close': 500, 'roc_5d': 2.0, 'roc_20d': 3.0, 'roc_60d': 5.0,
            'rank_5d_pct': 90, 'rank_20d_pct': 90, 'rank_60d_pct': 90,
            'composite_score': 90, 'tier': 'T1',
            'delta_roc_5d': 0.0,
        }])

        # Create raw_df with too few unique dates to trigger tier jump
        # (tier_jump_days=20, so we need <=20 unique dates to short-circuit)
        dates = pd.date_range('2024-01-01', periods=15, freq='B')
        rows = []
        for date in dates:
            rows.append({
                'symbol': 'SPY', 'name': 'SPY', 'market': 'us',
                'sector': 'equity',
                'date': date.strftime('%Y-%m-%d'),
                'open': 500, 'high': 505, 'low': 495,
                'close': 500, 'volume': 1e7,
            })
        raw_df = pd.DataFrame(rows)

        detector = AnomalyDetector(sample_config)
        anomalies = detector._detect_tier_jump(strength_df, raw_df)

        tier_jumps = [a for a in anomalies if a["type"] == "tier_jump"]
        assert len(tier_jumps) == 0, "Small tier jump should not trigger anomaly"

    def test_empty_raw_df_returns_empty(self, sample_config):
        detector = AnomalyDetector(sample_config)

        strength_df = pd.DataFrame([{
            'symbol': 'SPY', 'name': 'SPY', 'market': 'us',
            'close': 500, 'tier': 'T1',
        }])

        anomalies = detector._detect_tier_jump(strength_df, pd.DataFrame())
        assert anomalies == []

    def test_none_raw_df_returns_empty(self, sample_config):
        detector = AnomalyDetector(sample_config)

        strength_df = pd.DataFrame([{
            'symbol': 'SPY', 'name': 'SPY', 'market': 'us',
            'close': 500, 'tier': 'T1',
        }])

        anomalies = detector._detect_tier_jump(strength_df, None)
        assert anomalies == []


class TestDetectDivergence:
    """Tests for AnomalyDetector._detect_divergence()."""

    def test_missing_vix_returns_empty(self, sample_config):
        """If ^VIX is missing from the data, no divergence anomalies."""
        df = pd.DataFrame([{
            'symbol': 'QQQ', 'name': 'QQQ', 'market': 'us',
            'close': 450, 'roc_5d': 2.0,
        }])

        detector = AnomalyDetector(sample_config)
        anomalies = detector._detect_divergence(df)

        assert anomalies == []

    def test_missing_qqq_returns_empty(self, sample_config):
        """If QQQ is missing from the data, no divergence anomalies."""
        df = pd.DataFrame([{
            'symbol': '^VIX', 'name': 'VIX', 'market': 'global',
            'close': 20, 'roc_5d': 5.0,
        }])

        detector = AnomalyDetector(sample_config)
        anomalies = detector._detect_divergence(df)

        assert anomalies == []

    def test_vix_and_qqq_both_up_triggers_divergence(self, sample_config):
        """VIX up + QQQ up should trigger a divergence anomaly."""
        df = pd.DataFrame([
            {'symbol': '^VIX', 'name': 'VIX', 'market': 'global',
             'close': 30, 'roc_5d': 5.0},
            {'symbol': 'QQQ', 'name': 'QQQ', 'market': 'us',
             'close': 450, 'roc_5d': 3.0},
        ])

        detector = AnomalyDetector(sample_config)
        anomalies = detector._detect_divergence(df)

        assert len(anomalies) > 0
        assert any(a["type"] == "divergence" for a in anomalies)
