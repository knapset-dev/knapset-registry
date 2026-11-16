"""
PC Domain Extension.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightRegistry
from extensions.base import BaseDomainExtension, BaseSearchInstruction, BaseSorterExtension
from extensions.pc.layout import create_pc_layout
from extensions.pc.search import get_pc_criteria, pc_search_instruction, print_pc_search_results, search_pc
from extensions.pc.sorter import pc_sorter
from extensions.pc.weights import create_pc_scorer, create_pc_weights_registry
from provider_template import BaseMarketProvider


class PCDomainExtension(BaseDomainExtension):
    """Extension for synthesizing balanced PC builds."""

    domain_id = "pc"
    domain_aliases = ("hardware_pc", "pc-builder", "pc-prebuilt", "pc_builder", "pc_prebuilt", "hardware", "computer")
    title = "PC Build"
    description = "Combinatorial PC build synthesizer matching GPU, CPU, Motherboard, RAM, and Power Supply."

    def __init__(self):
        self._layout = create_pc_layout()
        self._weights_reg = create_pc_weights_registry()
        self._scorer = create_pc_scorer()
        self._search_instruction = pc_search_instruction
        self._sorter = pc_sorter

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
        return get_pc_criteria(section_id)

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
        return search_pc(
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
        print_pc_search_results(
            results=results,
            section_id=section_id,
            layout=self._layout,
            mode=mode,
        )

    def run_cli(self, argv: List[str]) -> None:
        from extensions.pc.cli import main as pc_cli_main
        pc_cli_main(argv)

    def evaluate_prebuilt(
        self,
        listing_a: str,
        listing_b: Optional[str] = None,
        mode: str = "sweet-spot",
    ) -> Dict[str, Any]:
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from extensions.pc.prebuilt_evaluator import PrebuiltEvaluator

        evaluator = PrebuiltEvaluator()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            if listing_b and str(listing_b).strip():
                rep = evaluator.compare_duo(str(listing_a), str(listing_b), mode=mode)
                return {
                    "type": "duo_comparison",
                    "mode": rep.get("mode_name"),
                    "winner": rep.get("winner"),
                    "winner_reason": rep.get("winner_reason"),
                    "score_a": rep.get("score_a"),
                    "score_b": rep.get("score_b"),
                    "matchups": rep.get("matchups"),
                }
            rep = evaluator.evaluate(str(listing_a), mode=mode)
            return {
                "type": "single_evaluation",
                "verdict": rep.get("verdict"),
                "mode": rep.get("mode"),
                "valuation": rep.get("valuation"),
                "risks": rep.get("risks"),
                "recommendation": rep.get("recommendation"),
            }

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "knapset_evaluate_prebuilt_pc",
                "description": "Evaluate a ready-made PC listing or compare two prebuilt PC offers head-to-head against market fair value and DIY alternatives.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "listing_a": {
                            "type": "string",
                            "description": "First PC listing text or URL (e.g. 'Ryzen 5 5600, RTX 3060 12GB, B550, 16GB DDR4, 650W, 450 USDT').",
                        },
                        "listing_b": {
                            "type": "string",
                            "description": "Optional second PC listing text for a head-to-head comparison duel.",
                        },
                        "mode": {
                            "type": "string",
                            "description": "Optimization mode for scoring (default: 'sweet-spot').",
                        },
                        "currency": {
                            "type": "string",
                            "description": "Active currency code (default: USDT).",
                        },
                    },
                    "required": ["listing_a"],
                },
            }
        ]

    def execute_mcp_tool(self, name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if name != "knapset_evaluate_prebuilt_pc":
            return None
        import json

        listing_a = str(arguments.get("listing_a", ""))
        listing_b = arguments.get("listing_b")
        mode = str(arguments.get("mode") or "sweet-spot")
        summary = self.evaluate_prebuilt(listing_a, listing_b=listing_b, mode=mode)
        return {
            "content": [{"type": "text", "text": json.dumps(summary, indent=2, ensure_ascii=False, default=str)}],
            "isError": False,
        }

