"""
NVMe SSD Component Analyser Module.
Domain: hardware_pc
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from component_analyser.base import BaseComponentAnalyser


class NVMeSSDAnalyser(BaseComponentAnalyser):
    """Identifies popular NVMe M.2 SSD models, PCIe generation, and capacity."""

    name: str = "nvme_ssd_analyser"
    title: str = "NVMe SSD Spec Analyser"
    domain: str = "hardware_pc"
    version: str = "1.0.0"
    author: str = "knapset-dev"
    min_app_version: str = "1.0.0"
    category: str = "hardware_spec"
    tags: List[str] = ["pc", "storage", "ssd", "nvme", "specs"]
    description: str = "Identifies NVMe M.2 SSD models, capacities, read speeds, and PCIe interfaces from listings."

    _MODEL_PATTERNS = [
        (re.compile(r"\b(?:samsung\s*990\s*pro|990\s*pro)\b", re.IGNORECASE), "Samsung 990 Pro", 7450, "PCIe 4.0 x4"),
        (re.compile(r"\b(?:samsung\s*980\s*pro|980\s*pro)\b", re.IGNORECASE), "Samsung 980 Pro", 7000, "PCIe 4.0 x4"),
        (re.compile(r"\b(?:kingston\s*kc3000|kc3000)\b", re.IGNORECASE), "Kingston KC3000", 7000, "PCIe 4.0 x4"),
        (re.compile(r"\b(?:wd\s*black\s*sn850x|sn850x)\b", re.IGNORECASE), "WD Black SN850X", 7300, "PCIe 4.0 x4"),
        (re.compile(r"\b(?:crucial\s*p3\s*plus|p3\s*plus)\b", re.IGNORECASE), "Crucial P3 Plus", 5000, "PCIe 4.0 x4"),
        (re.compile(r"\b(?:crucial\s*p3)\b", re.IGNORECASE), "Crucial P3", 3500, "PCIe 3.0 x4"),
    ]
    _CAPACITY_RE = re.compile(r"\b(500\s*gb|512\s*gb|1\s*tb|2\s*tb|4\s*tb)\b", re.IGNORECASE)

    def identify(self, title: str, description: str = "") -> Optional[Dict[str, Any]]:
        """Extracts normalized NVMe SSD model, capacity, and interface specs."""
        text = f"{title} {description}"
        for pattern, model_name, read_speed_mb, interface in self._MODEL_PATTERNS:
            if pattern.search(text):
                cap_match = self._CAPACITY_RE.search(text)
                cap_str = cap_match.group(1).upper().replace(" ", "") if cap_match else "1TB"
                cap_gb = (
                    500 if ("500" in cap_str or "512" in cap_str)
                    else (2000 if "2TB" in cap_str else (4000 if "4TB" in cap_str else 1000))
                )
                return {
                    "model": f"{model_name} {cap_str}",
                    "base_model": model_name,
                    "category": "ssd",
                    "capacity_gb": cap_gb,
                    "read_speed_mb": read_speed_mb,
                    "interface": interface,
                    "form_factor": "M.2 2280 NVMe",
                }
        return None
