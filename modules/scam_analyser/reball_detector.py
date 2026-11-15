"""
Reball / Oven-Baked GPU Scam Analyser Module.
Domain: hardware_pc
"""

from typing import Any, Dict, Optional
from scam_analyser.base import BaseScamAnalyser, ScamAnalysisResult


class ReballDetectorAnalyser(BaseScamAnalyser):
    name = "reball_detector"
    title = "GPU Reball & Oven-Baking Detector"
    version = "1.0.0"
    author = "HardwareCommunity"
    description = "Detects oven-baked, reballed, or damaged GPUs recovered after mining"
    min_app_version = "1.0.0"
    category = "gpu"
    domain = "hardware_pc"
    tags = ["gpu", "scam", "reball", "safety"]

    def analyze(
        self,
        item: Dict[str, Any],
        detail: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> ScamAnalysisResult:
        desc = (item.get("description") or "").lower()
        title = (item.get("title") or "").lower()
        combined = f"{title} {desc}"

        suspicious_words = [
            "reballed", "reball", "baked", "oven", "artifacts",
            "for repair", "as is", "no warranty", "warming", "overheated", "glitched"
        ]

        flags = []
        for word in suspicious_words:
            if word in combined:
                flags.append(f"Detected suspicious reball/repair marker: '{word}'")

        risk_score = 85 if flags else 5
        return ScamAnalysisResult(
            category="gpu",
            risk_score=risk_score,
            red_flags=flags,
            warnings=["FurMark stress testing recommended"] if not flags else [],
            trust_signals=["Original factory warranty seals intact"] if not flags else [],
            is_defective=len(flags) > 0,
        )
