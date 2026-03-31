"""Tests for CapitalFlowDetector."""

from __future__ import annotations

import pytest

from market_analyst.processors.capital_flow_detector import CapitalFlowDetector


@pytest.fixture
def detector() -> CapitalFlowDetector:
    return CapitalFlowDetector({})


class TestDualSource:
    """Tests with both CMF and MFI available (dual_source=True)."""

    def test_strong_inflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=65, mfi_score=75, relative_volume=1.8)
        assert result.signal == "大幅流入"
        assert result.dual_source is True
        assert result.cmf_score == 65
        assert result.mfi_score == 75
        assert result.relative_volume == 1.8

    def test_strong_outflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=25, mfi_score=25, relative_volume=2.0)
        assert result.signal == "大幅流出"
        assert result.dual_source is True

    def test_mild_inflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=58, mfi_score=50, relative_volume=0.9)
        assert result.signal == "小幅流入"
        assert result.dual_source is True

    def test_outflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=35, mfi_score=35, relative_volume=0.8)
        assert result.signal == "流出"
        assert result.dual_source is True

    def test_neutral(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=50, mfi_score=50, relative_volume=1.0)
        assert result.signal == "中性"
        assert result.dual_source is True

    def test_priority_outflow_not_strong_when_low_volume(self, detector: CapitalFlowDetector) -> None:
        """CMF=25, MFI=25, volume=0.5 -> '流出' not '大幅流出' because volume < 1.5."""
        result = detector.detect(cmf_score=25, mfi_score=25, relative_volume=0.5)
        assert result.signal == "流出"

    def test_edge_cmf_above_mild_but_mfi_below_45(self, detector: CapitalFlowDetector) -> None:
        """CMF=57 > 55, MFI=35 < 45 -> '中性' (doesn't match mild inflow)."""
        result = detector.detect(cmf_score=57, mfi_score=35)
        assert result.signal == "中性"


class TestSingleSource:
    """Tests with MFI=None (single source, dual_source=False)."""

    def test_single_source_inflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=70, mfi_score=None)
        assert result.signal == "小幅流入"
        assert result.dual_source is False

    def test_single_source_outflow(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=30, mfi_score=None)
        assert result.signal == "流出"
        assert result.dual_source is False

    def test_single_source_neutral(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=50, mfi_score=None)
        assert result.signal == "中性"
        assert result.dual_source is False

    def test_single_source_never_produces_strong_signals(self, detector: CapitalFlowDetector) -> None:
        """Single source should never produce '大幅流入' or '大幅流出'."""
        for cmf in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            result = detector.detect(cmf_score=cmf, mfi_score=None)
            assert result.signal not in ("大幅流入", "大幅流出"), (
                f"CMF={cmf} produced {result.signal} in single source mode"
            )


class TestDualSourceFlag:
    """Test dual_source flag correctness."""

    def test_dual_source_true_when_mfi_provided(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=50, mfi_score=50)
        assert result.dual_source is True

    def test_dual_source_false_when_mfi_none(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=50, mfi_score=None)
        assert result.dual_source is False


class TestAllNone:
    """Test when all inputs are None."""

    def test_all_none_defaults_to_neutral_single_source(self, detector: CapitalFlowDetector) -> None:
        result = detector.detect(cmf_score=None, mfi_score=None)
        assert result.signal == "中性"
        assert result.cmf_score == 50.0
        assert result.dual_source is False
