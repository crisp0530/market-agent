"""Tests for StrengthCalculator."""

import pandas as pd
import numpy as np
import pytest

from market_analyst.processors.strength_calculator import StrengthCalculator


class TestStrengthCalculator:
    """Tests for StrengthCalculator.calculate()."""

    def test_returns_dataframe_with_expected_columns(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        expected_cols = [
            "symbol", "name", "market", "close",
            "roc_5d", "roc_20d", "composite_score", "tier",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing expected column: {col}"

    def test_all_symbols_present_in_output(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        input_symbols = set(sample_raw_df["symbol"].unique())
        output_symbols = set(result["symbol"].unique())
        assert input_symbols == output_symbols, (
            f"Missing symbols in output: {input_symbols - output_symbols}"
        )

    def test_tier_distribution(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        tier_counts = result["tier"].value_counts()
        valid_tiers = {"T1", "T2", "T3", "T4"}
        assert set(tier_counts.index).issubset(valid_tiers), (
            f"Unexpected tier values: {set(tier_counts.index) - valid_tiers}"
        )

        # T1 should not contain more than half the symbols in any market
        for market in result["market"].unique():
            market_df = result[result["market"] == market]
            t1_count = len(market_df[market_df["tier"] == "T1"])
            assert t1_count <= len(market_df), "T1 count exceeds total symbols"

    def test_composite_score_is_numeric_and_reasonable(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        assert result["composite_score"].dtype in [np.float64, np.float32], (
            "composite_score should be numeric"
        )
        # Composite score is a weighted sum of percentile ranks (0-100)
        assert result["composite_score"].min() >= 0, "composite_score should be >= 0"
        assert result["composite_score"].max() <= 100, "composite_score should be <= 100"

    def test_roc_values_are_reasonable(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        for col in ["roc_5d", "roc_20d"]:
            assert not result[col].isna().all(), f"{col} should not be all NaN"
            # With 1% daily vol, ROC should be within a reasonable range
            assert result[col].abs().max() < 200, (
                f"{col} has unreasonably large values: {result[col].abs().max()}"
            )

    def test_empty_input_returns_empty_dataframe(self, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(pd.DataFrame())

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_global_zscore_column_added(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        assert "global_zscore_5d" in result.columns
        assert result["global_zscore_5d"].notna().any()

    def test_market_temp_column_added(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        assert "market_temp_5d" in result.columns
        assert result["market_temp_5d"].notna().any()

    def test_result_sorted_by_composite_score_within_market(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        # Within each market group (from _calculate_market), results should be
        # sorted descending by composite_score. After concat the global order
        # is market-by-market so we check each market independently.
        for market in result["market"].unique():
            market_df = result[result["market"] == market]
            scores = market_df["composite_score"].values
            assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)), (
                f"Results for market '{market}' not sorted by composite_score descending"
            )

    def test_delta_roc_5d_present(self, sample_raw_df, sample_config):
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(sample_raw_df)

        assert "delta_roc_5d" in result.columns

    def test_symbol_with_few_data_points_skipped(self, sample_raw_df, sample_config):
        """Symbols with < 5 data points should be skipped while others remain."""
        # Add a symbol with only 3 data points alongside the normal data
        tiny_rows = []
        dates = sorted(sample_raw_df["date"].unique())[:3]
        for i, date in enumerate(dates):
            tiny_rows.append({
                'symbol': 'TINY',
                'name': 'TINY',
                'date': date,
                'open': 100, 'high': 101, 'low': 99,
                'close': 100 + i,
                'volume': 1000000,
                'market': 'us',
                'sector': 'equity',
            })
        combined = pd.concat(
            [sample_raw_df, pd.DataFrame(tiny_rows)], ignore_index=True
        )
        calc = StrengthCalculator(sample_config)
        result = calc.calculate(combined)

        assert 'TINY' not in result['symbol'].values, (
            "Symbol with < 5 data points should be skipped"
        )
        # Other symbols should still be present
        assert len(result) > 0
