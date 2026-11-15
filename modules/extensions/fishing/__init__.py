"""
Fishing Tackle Set Domain Extension.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightRegistry
from extensions.base import BaseDomainExtension, BaseSearchInstruction, BaseSorterExtension
from extensions.fishing.layout import create_fishing_layout
from extensions.fishing.market_data import get_sample_fishing_market
from extensions.fishing.search import fishing_search_instruction, get_fishing_criteria, print_fishing_search_results, search_fishing
from extensions.fishing.sorter import fishing_sorter
from extensions.fishing.weights import create_fishing_scorer, create_fishing_weights_registry
from provider_template import BaseMarketProvider


class FishingDomainExtension(BaseDomainExtension):
    """Extension for synthesizing balanced fishing tackle sets."""

    domain_id = "fishing"
    domain_aliases = ("fishing_tackle", "fishing-tackle")
    title = "Fishing Tackle Set"
    description = "Combinatorial fishing tackle set synthesizer matching rods, reels, lines, baits, and tackle accessories."

    def __init__(self):
        self._layout = create_fishing_layout()
        self._weights_reg = create_fishing_weights_registry()
        self._scorer = create_fishing_scorer()
        self._search_instruction = fishing_search_instruction
        self._sorter = fishing_sorter

    def get_layout(self) -> DomainLayout:
        return self._layout

    def get_weights_registry(self) -> WeightRegistry:
        return self._weights_reg

    def get_scorer(self) -> DomainScorer:
        return self._scorer

    def get_search_instruction(self) -> BaseSearchInstruction:
        return self._search_instruction

    def get_sorter(self) -> BaseSorterExtension:
        return self._sorter

    def load_candidates(
        self,
        budget: float,
        refresh: bool = False,
        provider: Optional[BaseMarketProvider] = None,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return self._search_instruction.instruct_load_all(
            provider=provider,
            budget=budget,
            refresh=refresh,
            **kwargs,
        )

    def get_supported_criteria(self, section_id: Optional[str] = None) -> Dict[str, str]:
        return get_fishing_criteria(section_id)

    def search(
        self,
        section_id: str,
        query: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        criteria: Optional[Dict[str, Any]] = None,
        mode: Optional[str] = None,
        limit: int = 15,
        provider: Optional[BaseMarketProvider] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return search_fishing(
            section_id=section_id,
            query=query,
            min_price=min_price,
            max_price=max_price,
            criteria=criteria,
            mode=mode,
            limit=limit,
            scorer=self._scorer,
            weights_reg=self._weights_reg,
            provider=provider,
        )

    def print_search_results(
        self,
        results: List[Dict[str, Any]],
        section_id: str,
        mode: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        print_fishing_search_results(
            results=results,
            section_id=section_id,
            layout=self._layout,
            mode=mode,
        )

    def run_cli(self, argv: List[str]) -> None:
        from extensions.fishing.cli import main as fishing_cli_main
        fishing_cli_main(argv)
