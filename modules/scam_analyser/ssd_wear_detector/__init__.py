"""
SSD Controller and NAND Flash Wear / Scam Analyser (Directory Package Sample).
Demonstrates reading local JSON data packaged together with the module.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from scam_analyser.base import BaseScamAnalyser, ScamAnalysisResult


class SSDWearDetector(BaseScamAnalyser):
    name = "ssd_wear_detector"
    title = "SSD Controller & Wear Analyser"
    version = "1.0.0"
    author = "HardwareCommunity"
    description = "Analyzes counterfeit SSD controllers and fake NAND capacity"
    min_app_version = "1.0.0"
    category = "storage"
    domain = "hardware_pc"
    tags = ["storage", "ssd", "scam", "nand"]

    def __init__(self) -> None:
        super().__init__()
        data_path = Path(__file__).resolve().parent / "flash_chips.json"
        self._fake_chips = []
        self._risky_vendors = []
        if data_path.exists():
            try:
                content = json.loads(data_path.read_text(encoding="utf-8"))
                self._fake_chips = content.get("fake_chips", [])
                self._risky_vendors = content.get("risky_vendors", [])
            except Exception:
                pass

    def analyze(
        self,
        item: Dict[str, Any],
        detail: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> ScamAnalysisResult:
        desc = (item.get("description") or "").lower()
        title = (item.get("title") or "").lower()
        text = f"{title} {desc}"

        flags = []
        for vendor in self._risky_vendors:
            if vendor.lower() in text:
                flags.append(f"Detected suspicious/counterfeit SSD brand: '{vendor}'")

        risk_score = 90 if flags else 5
        return ScamAnalysisResult(
            category="storage",
            risk_score=risk_score,
            red_flags=flags,
            warnings=["Verify SMART health status and TBW limits"] if not flags else [],
            trust_signals=["Known reputable storage vendor"] if not flags else [],
            is_defective=len(flags) > 0,
        )
