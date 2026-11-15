"""
Value Composer Sample Module.
Domain: hardware_pc
"""

from typing import Any, Dict, List, Optional
from build_composer.base import BaseBuildComposer, ComposerSetResult


class ValueComposer(BaseBuildComposer):
    name = "value_composer"
    title = "Value FPS Composer"
    version = "1.0.0"
    author = "HardwareCommunity"
    description = "Build synthesizer focused on maximum FPS per budget unit"
    min_app_version = "1.0.0"
    domain = "hardware_pc"
    tags = ["pc", "build", "value", "fps"]

    def compose(
        self,
        candidate_pool: Dict[str, List[Dict[str, Any]]],
        budget: float,
        mode: str = "value",
        weights: Optional[Dict[str, float]] = None,
        top_n: int = 5,
    ) -> List[ComposerSetResult]:
        components = {
            "gpu": {"model": "RX 6600", "price": 7500.0},
            "cpu": {"model": "Ryzen 5 3600", "price": 2800.0},
            "mobo": {"model": "B450M", "price": 2200.0},
            "ram": {"model": "16GB DDR4", "price": 1200.0},
            "psu": {"model": "550W Bronze", "price": 1800.0},
        }
        total = sum(c["price"] for c in components.values())
        return [
            ComposerSetResult(
                domain=self.domain,
                mode=mode,
                total_cost=total,
                budget=budget,
                surplus=budget - total,
                score=92.5,
                components=components,
                metrics={"fps_1080p": 75, "value_ratio": 4.05},
            )
        ]
