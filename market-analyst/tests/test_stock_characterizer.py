"""Tests for stock characterization processor."""
import pytest
import pandas as pd
import numpy as np

from market_analyst.processors.stock_characterizer import StockCharacterizer
from market_analyst.schemas_retail import StockCharacterization


class TestStockCharacterizer:
    def test_hot_money_stock(self, sample_stock_df_hot_money, sample_characterization_config):
        """High turnover, volatile stock should be classified as 游资票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234",
            raw_df=sample_stock_df_hot_money,
            market="cn",
            market_cap=50.0,
            institutional_pct=5.0,
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type == "游资票"
        assert result.hot_money_score > result.institutional_score

    def test_institutional_stock(self, sample_stock_df_institutional, sample_characterization_config):
        """Low turnover, stable, large-cap stock should be classified as 机构票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="600519",
            raw_df=sample_stock_df_institutional,
            market="cn",
            market_cap=21000.0,
            institutional_pct=45.0,
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type == "机构票"
        assert result.institutional_score > result.hot_money_score

    def test_mixed_stock(self, sample_stock_df_hot_money, sample_characterization_config):
        """Moderate indicators should produce 机游合力票 or 普通票."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="000001",
            raw_df=sample_stock_df_hot_money,
            market="cn",
            market_cap=3000.0,
            institutional_pct=35.0,
        )
        assert isinstance(result, StockCharacterization)
        assert result.character_type in ("机游合力票", "普通票")

    def test_scores_in_range(self, sample_stock_df_hot_money, sample_characterization_config):
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert 0 <= result.hot_money_score <= 100
        assert 0 <= result.institutional_score <= 100

    def test_key_evidence_not_empty(self, sample_stock_df_hot_money, sample_characterization_config):
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert len(result.key_evidence) >= 2

    def test_available_dimensions_tracked(self, sample_stock_df_hot_money, sample_characterization_config):
        """Should track which dimensions were used in scoring."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=50.0, institutional_pct=5.0,
        )
        assert "turnover" in result.available_dimensions
        assert "volatility" in result.available_dimensions
        assert "institutional_holding" in result.available_dimensions

    def test_missing_dimensions_renormalized(self, sample_stock_df_hot_money, sample_characterization_config):
        """Missing optional dimensions should be excluded and weights renormalized."""
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(
            symbol="301234", raw_df=sample_stock_df_hot_money, market="cn",
            market_cap=None,
            institutional_pct=None,
        )
        assert "institutional_holding" not in result.available_dimensions
        assert "market_cap" not in result.available_dimensions
        assert 0 <= result.hot_money_score <= 100
        assert 0 <= result.institutional_score <= 100

    def test_insufficient_data_returns_normal(self, sample_characterization_config):
        """Very short data should default to 普通票."""
        df = pd.DataFrame({
            "symbol": ["X"] * 3, "close": [100.0, 101.0, 99.0],
            "high": [101.0, 102.0, 100.0], "low": [99.0, 100.0, 98.0],
            "volume": [1000.0, 1200.0, 900.0], "date": ["2026-03-25", "2026-03-26", "2026-03-27"],
            "name": ["X"] * 3, "market": ["cn"] * 3, "sector": ["Tech"] * 3,
            "open": [100.0, 101.0, 99.0],
        })
        charzer = StockCharacterizer(sample_characterization_config)
        result = charzer.characterize(symbol="X", raw_df=df, market="cn", market_cap=100.0, institutional_pct=10.0)
        assert result.character_type == "普通票"
