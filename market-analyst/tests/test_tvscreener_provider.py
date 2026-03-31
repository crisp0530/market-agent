"""Tests for TvScreenerProvider."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from market_analyst.providers.tvscreener_provider import TvScreenerData, TvScreenerProvider


@pytest.fixture
def provider(tmp_path: Path) -> TvScreenerProvider:
    """Create a TvScreenerProvider with a temp scripts dir containing a dummy script."""
    script = tmp_path / "query_symbol.py"
    script.write_text("# dummy")
    return TvScreenerProvider(scripts_dir=tmp_path, timeout=10)


@pytest.fixture
def provider_no_script(tmp_path: Path) -> TvScreenerProvider:
    """Provider whose scripts_dir has no query_symbol.py."""
    return TvScreenerProvider(scripts_dir=tmp_path, timeout=10)


# ── _map_symbol ──────────────────────────────────────────────────────────────

class TestMapSymbol:
    def test_cn_6_prefix_shse(self, provider: TvScreenerProvider):
        assert provider._map_symbol("601866", "cn") == "SHSE:601866"

    def test_cn_9_prefix_shse(self, provider: TvScreenerProvider):
        assert provider._map_symbol("900901", "cn") == "SHSE:900901"

    def test_cn_0_prefix_szse(self, provider: TvScreenerProvider):
        assert provider._map_symbol("000001", "cn") == "SZSE:000001"

    def test_cn_3_prefix_szse(self, provider: TvScreenerProvider):
        assert provider._map_symbol("300750", "cn") == "SZSE:300750"

    def test_cn_2_prefix_szse(self, provider: TvScreenerProvider):
        assert provider._map_symbol("200001", "cn") == "SZSE:200001"

    def test_cn_4_prefix_bse_none(self, provider: TvScreenerProvider):
        assert provider._map_symbol("430047", "cn") is None

    def test_cn_8_prefix_bse_none(self, provider: TvScreenerProvider):
        assert provider._map_symbol("830799", "cn") is None

    def test_us_nasdaq(self, provider: TvScreenerProvider):
        assert provider._map_symbol("AAPL", "us") == "NASDAQ:AAPL"


# ── _map_market ──────────────────────────────────────────────────────────────

class TestMapMarket:
    def test_cn_to_china(self, provider: TvScreenerProvider):
        assert provider._map_market("cn") == "CHINA"

    def test_us_to_america(self, provider: TvScreenerProvider):
        assert provider._map_market("us") == "AMERICA"

    def test_other_to_america(self, provider: TvScreenerProvider):
        assert provider._map_market("hk") == "AMERICA"


# ── _parse ───────────────────────────────────────────────────────────────────

class TestParse:
    def test_full_data(self, provider: TvScreenerProvider):
        data = {
            "Symbol": "SHSE:601866",
            "Name": "601866",
            "Price": 8.5,
            "Relative Volume": 0.85,
            "Chaikin Money Flow (20)": 0.1,
            "Money Flow (14)": 48.2,
            "Relative Strength Index (14)": 55.0,
            "MACD Histogram": 0.03,
            "Recommendation Mark": "Buy",
            "Simple Moving Average (20)": 8.3,
            "Simple Moving Average (50)": 8.1,
            "Simple Moving Average (200)": 7.9,
            "Bollinger Upper Band (20)": 9.0,
            "Bollinger Lower Band (20)": 7.8,
        }
        result = provider._parse(data)
        assert result.price == 8.5
        assert result.relative_volume == 0.85
        assert result.mfi_14 == 48.2
        assert result.rsi_14 == 55.0
        assert result.macd_hist == 0.03
        assert result.recommendation == "Buy"
        assert result.sma_20 == 8.3
        assert result.sma_50 == 8.1
        assert result.sma_200 == 7.9
        assert result.bollinger_upper == 9.0
        assert result.bollinger_lower == 7.8
        # CMF 0.1 → (0.1 + 0.5) * 100 = 60.0
        assert result.cmf_20 == 60.0

    def test_partial_data(self, provider: TvScreenerProvider):
        data = {"Price": 100.0, "Recommendation Mark": "Strong Buy"}
        result = provider._parse(data)
        assert result.price == 100.0
        assert result.recommendation == "Strong Buy"
        assert result.relative_volume is None
        assert result.cmf_20 is None

    def test_empty_data(self, provider: TvScreenerProvider):
        result = provider._parse({})
        assert result.price is None
        assert result.recommendation is None
        assert result.relative_volume is None

    def test_empty_string_values_ignored(self, provider: TvScreenerProvider):
        data = {"Price": "", "Recommendation Mark": ""}
        result = provider._parse(data)
        assert result.price is None
        assert result.recommendation is None


# ── CMF conversion ───────────────────────────────────────────────────────────

class TestCmfConversion:
    def test_cmf_positive(self, provider: TvScreenerProvider):
        """Raw CMF 0.1 → (0.1 + 0.5) * 100 = 60.0"""
        data = {"Chaikin Money Flow (20)": 0.1}
        result = provider._parse(data)
        assert result.cmf_20 == pytest.approx(60.0)

    def test_cmf_min(self, provider: TvScreenerProvider):
        """Raw CMF -0.5 → (-0.5 + 0.5) * 100 = 0.0"""
        data = {"Chaikin Money Flow (20)": -0.5}
        result = provider._parse(data)
        assert result.cmf_20 == pytest.approx(0.0)

    def test_cmf_max(self, provider: TvScreenerProvider):
        """Raw CMF 0.5 → (0.5 + 0.5) * 100 = 100.0"""
        data = {"Chaikin Money Flow (20)": 0.5}
        result = provider._parse(data)
        assert result.cmf_20 == pytest.approx(100.0)

    def test_cmf_clamped_above(self, provider: TvScreenerProvider):
        """Raw CMF > 0.5 gets clamped to 100."""
        data = {"Chaikin Money Flow (20)": 0.8}
        result = provider._parse(data)
        assert result.cmf_20 == 100.0

    def test_cmf_clamped_below(self, provider: TvScreenerProvider):
        """Raw CMF < -0.5 gets clamped to 0."""
        data = {"Chaikin Money Flow (20)": -0.8}
        result = provider._parse(data)
        assert result.cmf_20 == 0.0


# ── fetch ────────────────────────────────────────────────────────────────────

class TestFetch:
    def test_fetch_success(self, provider: TvScreenerProvider):
        stdout = json.dumps({
            "Symbol": "SHSE:601866",
            "Price": 8.5,
            "Recommendation Mark": "Buy",
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=stdout, stderr=""
            )
            result = provider.fetch("601866", "cn")
        assert result is not None
        assert result.price == 8.5
        assert result.recommendation == "Buy"

    def test_fetch_failure_returncode(self, provider: TvScreenerProvider):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error"
            )
            result = provider.fetch("601866", "cn")
        assert result is None

    def test_fetch_timeout(self, provider: TvScreenerProvider):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)
            result = provider.fetch("601866", "cn")
        assert result is None

    def test_fetch_not_found(self, provider: TvScreenerProvider):
        stdout = json.dumps({"found": False})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=stdout, stderr=""
            )
            result = provider.fetch("601866", "cn")
        assert result is None

    def test_fetch_script_not_found(self, provider_no_script: TvScreenerProvider):
        result = provider_no_script.fetch("601866", "cn")
        assert result is None

    def test_fetch_bse_symbol_returns_none(self, provider: TvScreenerProvider):
        """BSE symbols (4xx/8xx) should return None without calling subprocess."""
        with patch("subprocess.run") as mock_run:
            result = provider.fetch("430047", "cn")
        assert result is None
        mock_run.assert_not_called()
