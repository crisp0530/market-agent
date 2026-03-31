"""Tests for QuantMetrics."""

import pandas as pd
import numpy as np
import pytest

from market_analyst.processors.strength_calculator import StrengthCalculator
from market_analyst.processors.quant_metrics import QuantMetrics


@pytest.fixture
def strength_df(sample_raw_df, sample_config):
    """Pre-compute strength DataFrame for quant metric tests."""
    calc = StrengthCalculator(sample_config)
    return calc.calculate(sample_raw_df)


class TestQuantMetricsCalculateAll:
    """Tests for QuantMetrics.calculate_all()."""

    def test_adds_expected_columns(self, sample_raw_df, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, strength_df)

        expected_new_cols = [
            "ann_return", "ann_vol", "sharpe",
            "max_drawdown", "max_dd_date",
            "calmar_ratio", "variance_drag",
        ]
        for col in expected_new_cols:
            assert col in result.columns, f"Missing expected column: {col}"

    def test_sharpe_is_numeric_and_reasonable(self, sample_raw_df, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, strength_df)

        sharpe_vals = result["sharpe"].dropna()
        assert len(sharpe_vals) > 0, "No Sharpe values computed"
        assert sharpe_vals.between(-10, 10).all(), (
            f"Sharpe out of range: min={sharpe_vals.min()}, max={sharpe_vals.max()}"
        )

    def test_max_drawdown_between_minus1_and_0(self, sample_raw_df, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, strength_df)

        dd_vals = result["max_drawdown"].dropna()
        assert len(dd_vals) > 0, "No max_drawdown values computed"
        # max_drawdown is stored as percentage (e.g. -5.23 means -5.23%)
        assert (dd_vals <= 0).all(), "max_drawdown should be <= 0"
        assert (dd_vals >= -100).all(), "max_drawdown should be >= -100%"

    def test_volatility_is_positive(self, sample_raw_df, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, strength_df)

        vol_vals = result["ann_vol"].dropna()
        assert len(vol_vals) > 0, "No volatility values computed"
        assert (vol_vals >= 0).all(), "Annualized volatility should be non-negative"

    def test_preserves_original_columns(self, sample_raw_df, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, strength_df)

        for col in strength_df.columns:
            assert col in result.columns, f"Original column '{col}' lost after merge"

    def test_empty_raw_df_returns_strength_df_unchanged(self, strength_df):
        qm = QuantMetrics()
        result = qm.calculate_all(pd.DataFrame(), strength_df)

        pd.testing.assert_frame_equal(result, strength_df)

    def test_empty_strength_df_returns_empty(self, sample_raw_df):
        qm = QuantMetrics()
        result = qm.calculate_all(sample_raw_df, pd.DataFrame())

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_symbol_with_insufficient_data(self, sample_config):
        """Symbol with < 10 data points gets NaN metrics."""
        # Create raw data with only 8 points
        rows = []
        for i in range(8):
            rows.append({
                'symbol': 'SHORT', 'name': 'SHORT', 'sector': 'equity',
                'date': f'2024-01-{i+10}', 'market': 'us',
                'open': 100, 'high': 101, 'low': 99,
                'close': 100 + i * 0.5, 'volume': 1000000,
            })
        raw_df = pd.DataFrame(rows)

        # Create a minimal strength_df with this symbol
        strength_df = pd.DataFrame([{
            'symbol': 'SHORT', 'name': 'SHORT', 'market': 'us',
            'close': 103.5, 'roc_5d': 1.0, 'roc_20d': 0.5,
            'composite_score': 50.0, 'tier': 'T2',
        }])

        qm = QuantMetrics()
        result = qm.calculate_all(raw_df, strength_df)

        row = result[result['symbol'] == 'SHORT'].iloc[0]
        assert pd.isna(row['sharpe']), "Sharpe should be NaN for insufficient data"
        assert pd.isna(row['max_drawdown']), "max_drawdown should be NaN for insufficient data"

    def test_constant_price_zero_volatility(self, sample_config):
        """Symbol with constant price should have 0 Sharpe (0 vol → 0 sharpe)."""
        rows = []
        for i in range(30):
            rows.append({
                'symbol': 'FLAT', 'name': 'FLAT', 'sector': 'equity',
                'date': f'2024-01-{i+1:02d}' if i < 28 else f'2024-02-{i-27:02d}',
                'market': 'us',
                'open': 100, 'high': 100, 'low': 100,
                'close': 100, 'volume': 1000000,
            })
        raw_df = pd.DataFrame(rows)

        strength_df = pd.DataFrame([{
            'symbol': 'FLAT', 'name': 'FLAT', 'market': 'us',
            'close': 100, 'roc_5d': 0.0, 'roc_20d': 0.0,
            'composite_score': 50.0, 'tier': 'T2',
        }])

        qm = QuantMetrics()
        result = qm.calculate_all(raw_df, strength_df)

        row = result[result['symbol'] == 'FLAT'].iloc[0]
        assert row['ann_vol'] == 0.0 or pd.isna(row['ann_vol']), (
            "Constant price should have 0 volatility"
        )
        assert row['sharpe'] == 0.0, "Constant price should have 0 Sharpe"


class TestQuantMetricsWealthIndex:
    """Tests for QuantMetrics.compute_wealth_index()."""

    def test_returns_expected_columns(self, sample_raw_df):
        result = QuantMetrics.compute_wealth_index(sample_raw_df, "SPY")

        assert not result.empty
        for col in ["date", "wealth", "drawdown", "previous_peak"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_single_data_point_returns_empty(self):
        df = pd.DataFrame([{
            'symbol': 'X', 'date': '2024-01-01', 'close': 100,
        }])
        result = QuantMetrics.compute_wealth_index(df, "X")
        assert result.empty


class TestQuantMetricsReturnSeries:
    """Tests for QuantMetrics.compute_return_series()."""

    def test_returns_expected_columns(self, sample_raw_df):
        result = QuantMetrics.compute_return_series(sample_raw_df, "SPY")

        assert not result.empty
        for col in ["date", "return"]:
            assert col in result.columns

    def test_single_data_point_returns_empty(self):
        df = pd.DataFrame([{
            'symbol': 'X', 'date': '2024-01-01', 'close': 100,
        }])
        result = QuantMetrics.compute_return_series(df, "X")
        assert result.empty
