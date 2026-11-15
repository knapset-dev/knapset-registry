"""
Fishing Domain Sorter Extension.

Operates strictly according to the DomainLayout template and Weights.
Knows ZERO about providers or websites; receives candidate pools from
the Fishing Search Instruction and synthesizes optimal tackle kits.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightProfile
from extensions.base import BaseSorterExtension
from set_synthesizer import synthesize_domain_sets


class FishingSorter(BaseSorterExtension):
    """
    Combinatorial Fishing Tackle Set Sorter / Synthesizer.
    Decoupled from data providers; operates purely on candidate pools and template rules.
    """

    domain_id = "fishing"

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
        excluded_ids: Optional[set] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
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

        if layout is None:
            from extensions.fishing.layout import create_fishing_layout
            layout = create_fishing_layout()
        if scorer is None:
            from extensions.fishing.weights import create_fishing_scorer
            scorer = create_fishing_scorer()
        if profile is None:
            from extensions.fishing.weights import create_fishing_weights_registry
            profile = create_fishing_weights_registry().resolve_profile(mode or "spinning-light")

        target_budget = float(budget or kwargs.get("budget") or layout.default_budget or 150.0)
        target_pool = candidate_pool if candidate_pool is not None else {}

        return synthesize_domain_sets(
            layout=layout,
            scorer=scorer,
            profile=profile,
            candidate_pool=target_pool,
            budget=target_budget,
            top_n=top_n,
            excluded_ids=excluded_ids,
        )


fishing_sorter = FishingSorter()
