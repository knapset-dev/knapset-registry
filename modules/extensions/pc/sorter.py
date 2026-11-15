"""
PC Domain Sorter / Optimizer Extension.

Operates strictly according to the DomainLayout template and Weights.
Knows ZERO about web scraping or providers; receives candidate pools from
the Search Instruction and performs combinatorial synthesis.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightProfile
from extensions.base import BaseSorterExtension


class PCSorter(BaseSorterExtension):
    """
    Combinatorial PC Build Sorter / Synthesizer.
    Decoupled from data providers; operates purely on candidate pools and template rules.
    """

    domain_id = "pc"

    def sort_and_synthesize(
        self,
        *args: Any,
        candidate_pool: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        budget: Optional[float] = None,
        layout: Optional[DomainLayout] = None,
        scorer: Optional[DomainScorer] = None,
        profile: Optional[WeightProfile] = None,
        mode: Optional[str] = None,
        top_n: int = 5,
        **kwargs: Any,
    ) -> List[Any]:
        # Unpack positional arguments if supplied
        if args:
            if isinstance(args[0], DomainLayout):
                layout = args[0]
                if len(args) > 1 and isinstance(args[1], DomainScorer):
                    scorer = args[1]
                if len(args) > 2 and isinstance(args[2], WeightProfile):
                    profile = args[2]
                if len(args) > 3 and isinstance(args[3], dict):
                    candidate_pool = args[3]
                if len(args) > 4:
                    budget = float(args[4])
                if len(args) > 5:
                    top_n = int(args[5])
            elif isinstance(args[0], dict):
                candidate_pool = args[0]
                if len(args) > 1:
                    budget = float(args[1])
                if len(args) > 2:
                    top_n = int(args[2])

        from extensions.pc.build_optimizer import run_build_optimizer

        target_budget = float(budget or kwargs.pop("budget", 20000.0))
        target_mode = profile.name if profile is not None else (mode or kwargs.pop("mode", "value"))
        target_pool = candidate_pool if candidate_pool is not None else kwargs.pop("candidate_pool", {})
        target_top_n = kwargs.pop("top_builds", kwargs.pop("max_proposals", top_n))

        return run_build_optimizer(
            budget=target_budget,
            candidate_pool=target_pool,
            top_builds=target_top_n,
            domain="pc",
            mode=target_mode,
            **kwargs,
        )


pc_sorter = PCSorter()
