"""Cross-validate capital flow using CMF score and tvscreener MFI."""

from __future__ import annotations

from market_analyst.schemas_retail import CapitalFlowSignal


class CapitalFlowDetector:
    """Cross-validate capital flow using CMF score and tvscreener MFI."""

    def __init__(self, config: dict):
        cfg = config.get("capital_flow", {})
        self.strong_inflow_cmf = cfg.get("strong_inflow_cmf", 60)
        self.strong_inflow_mfi = cfg.get("strong_inflow_mfi", 70)
        self.strong_inflow_volume = cfg.get("strong_inflow_volume", 1.5)
        self.mild_inflow_threshold = cfg.get("mild_inflow_threshold", 55)
        self.outflow_threshold = cfg.get("outflow_threshold", 40)
        self.strong_outflow_threshold = cfg.get("strong_outflow_threshold", 30)
        self.strong_outflow_volume = cfg.get("strong_outflow_volume", 1.5)
        self.single_source_inflow = cfg.get("single_source_inflow", 65)
        self.single_source_outflow = cfg.get("single_source_outflow", 35)

    def detect(
        self,
        cmf_score: float | None,
        mfi_score: float | None = None,
        relative_volume: float | None = None,
    ) -> CapitalFlowSignal:
        """Detect capital flow signal.

        Args:
            cmf_score: Diagnostor CMF score 0-100 (from _score_flow)
            mfi_score: tvscreener MFI 0-100 (None if tvscreener unavailable)
            relative_volume: tvscreener relative volume (None if unavailable)
        """
        dual_source = mfi_score is not None

        if not dual_source:
            return self._single_source(cmf_score)

        # Priority-ordered detection (first match wins)
        vol = relative_volume or 0.0
        cmf = cmf_score if cmf_score is not None else 50.0

        # Priority 1: Strong inflow
        if cmf > self.strong_inflow_cmf and mfi_score > self.strong_inflow_mfi and vol > self.strong_inflow_volume:
            return CapitalFlowSignal(
                signal="大幅流入",
                cmf_score=cmf,
                mfi_score=mfi_score,
                relative_volume=relative_volume,
                description="资金大幅流入，主力积极介入",
                dual_source=True,
            )

        # Priority 2: Strong outflow
        if (
            cmf < self.strong_outflow_threshold
            and mfi_score < self.strong_outflow_threshold
            and vol > self.strong_outflow_volume
        ):
            return CapitalFlowSignal(
                signal="大幅流出",
                cmf_score=cmf,
                mfi_score=mfi_score,
                relative_volume=relative_volume,
                description="放量资金流出，主力撤离",
                dual_source=True,
            )

        # Priority 3: Mild inflow (CMF > 55 AND MFI > 45 for dual-source)
        if cmf > self.mild_inflow_threshold and mfi_score > 45:
            return CapitalFlowSignal(
                signal="小幅流入",
                cmf_score=cmf,
                mfi_score=mfi_score,
                relative_volume=relative_volume,
                description="资金小幅流入",
                dual_source=True,
            )

        # Priority 4: Outflow
        if cmf < self.outflow_threshold and mfi_score < self.outflow_threshold:
            return CapitalFlowSignal(
                signal="流出",
                cmf_score=cmf,
                mfi_score=mfi_score,
                relative_volume=relative_volume,
                description="资金流出，注意风险",
                dual_source=True,
            )

        # Priority 5: Neutral (catch-all)
        return CapitalFlowSignal(
            signal="中性",
            cmf_score=cmf,
            mfi_score=mfi_score,
            relative_volume=relative_volume,
            description="资金流向不明确",
            dual_source=True,
        )

    def _single_source(self, cmf_score: float | None) -> CapitalFlowSignal:
        """Single-source fallback using only CMF score."""
        cmf = cmf_score if cmf_score is not None else 50.0

        if cmf > self.single_source_inflow:
            signal, desc = "小幅流入", "资金小幅流入（单源判断）"
        elif cmf < self.single_source_outflow:
            signal, desc = "流出", "资金流出，注意风险（单源判断）"
        else:
            signal, desc = "中性", "资金流向不明确"

        return CapitalFlowSignal(
            signal=signal,
            cmf_score=cmf,
            mfi_score=None,
            relative_volume=None,
            description=desc,
            dual_source=False,
        )
