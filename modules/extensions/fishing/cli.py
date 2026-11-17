#!/usr/bin/env python3
"""
Fishing Tackle Domain CLI.

Standalone and embedded CLI for fishing equipment discovery and set synthesis:
- build : Synthesize optimal fishing tackle combinations under budget
- rod   : Search & filter fishing rods by power class, test, brand, price
- reel  : Search & filter reels by spool size, drag power, brand, price
- line  : Search & filter fishing lines by weave (PE 4x/8x), test (kg), diameter
- bait  : Search & filter lures and feeder cages by type, weight, target species
- tackle: Search & filter accessory kits, tools, and nets
- modes : List available fishing optimization modes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from extensions.fishing.layout import create_fishing_layout
from extensions.fishing.search import print_fishing_search_results, search_fishing
from extensions.fishing.weights import create_fishing_scorer, create_fishing_weights_registry
from set_synthesizer import print_domain_sets, synthesize_domain_sets


def _cli_prog() -> str:
    exe = Path(sys.argv[0]).name if sys.argv else ""
    return exe if exe in ("ks", "knapset") else "python3 main.py"


def _run_build(argv: List[str]) -> None:
    from currency import canonical_currency, convert_currency, get_active_currency

    active_curr = get_active_currency()
    default_budget = 150.0 if canonical_currency(active_curr) in ("USDT", "USD") else convert_currency(150.0, "USDT", active_curr)

    parser = argparse.ArgumentParser(
        prog=f"{_cli_prog()} fishing build",
        description="Synthesize balanced fishing tackle sets under budget",
    )
    parser.add_argument("--domain", "-D", type=str, default="fishing", help="Domain identifier (default: fishing)")
    parser.add_argument("--budget", "-b", type=float, default=default_budget, help=f"Total budget in {active_curr} (default: {default_budget:,.0f} {active_curr})")
    parser.add_argument("--mode", "-M", type=str, default="spinning-light", help="Optimization mode (default: spinning-light)")
    parser.add_argument("--top", "-n", type=int, default=5, help="Number of distinct sets to show (default: 5)")
    parser.add_argument("--weights", "-w", type=str, default=None, help="Custom weights string (e.g. 'casting=0.4,lightness=0.4,value=0.2')")
    parser.add_argument("--provider", "-p", type=str, default="sample", help="Marketplace information provider (default: sample)")
    args = parser.parse_args(argv)

    import time
    t0 = time.perf_counter()

    layout = create_fishing_layout()
    weights_reg = create_fishing_weights_registry()
    scorer = create_fishing_scorer()
    profile = weights_reg.resolve_profile(args.mode, weights_override=args.weights)

    from provider_template import get_market_provider
    from extensions.fishing.search import fishing_search_instruction
    from extensions.fishing.sorter import fishing_sorter

    prov = get_market_provider(args.provider)
    candidates = fishing_search_instruction.instruct_load_all(provider=prov, budget=args.budget)

    counts = [f"{sec.label}s={len(candidates.get(sec.id, []))}" for sec in layout.sections]
    print(f"\n   Synthesizing {layout.title}")
    print(f"   Candidate pool: {' | '.join(counts)}")

    sets = fishing_sorter.sort_and_synthesize(
        layout=layout,
        scorer=scorer,
        profile=profile,
        candidate_pool=candidates,
        budget=args.budget,
        top_n=args.top,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print_domain_sets(layout, profile, sets, elapsed_ms=elapsed_ms)


def _run_search_category(section_id: str, argv: List[str]) -> None:
    layout = create_fishing_layout()
    weights_reg = create_fishing_weights_registry()
    scorer = create_fishing_scorer()
    sec_obj = layout.get_section(section_id)
    sec_title = sec_obj.name if sec_obj else section_id.upper()

    parser = argparse.ArgumentParser(
        prog=f"{_cli_prog()} fishing {section_id}",
        description=f"Search and filter {sec_title}",
    )
    parser.add_argument("--query", "-q", type=str, default=None, help="Keyword query (model, brand, title)")
    parser.add_argument("--brand", type=str, default=None, help="Brand filter (Favorite, Daiwa, Shimano, Flagman, Brain, Select)")
    parser.add_argument("--min-price", type=float, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=float, default=None, help="Maximum price in UAH")
    parser.add_argument("--mode", "-M", type=str, default=None, help="Score and rank results using mode profile")
    parser.add_argument("--limit", "-n", type=int, default=15, help="Maximum results to display (default: 15)")

    # Section-specific natural arguments
    if section_id == "rod":
        parser.add_argument("--power", type=str, default=None, help="Power class (Ultralight, Light, Medium-Light, Medium, Heavy)")
        parser.add_argument("--test-min", type=float, default=None, help="Minimum test in grams")
        parser.add_argument("--test-max", type=float, default=None, help="Maximum test in grams")
    elif section_id == "reel":
        parser.add_argument("--spool", type=int, default=None, help="Spool size (1000, 2000, 2500, 3000, 4000, 5000)")
        parser.add_argument("--min-drag", type=float, default=None, help="Minimum front drag in kg")
    elif section_id == "line":
        parser.add_argument("--type", type=str, default=None, help="Weave type (PE 4x, PE 8x, Mono)")
        parser.add_argument("--min-kg", type=float, default=None, help="Minimum breaking strength in kg")
    elif section_id == "bait":
        parser.add_argument("--type", type=str, default=None, help="Bait type (MicroJig, Wobbler, FeederCage, HeavyCage)")
        parser.add_argument("--target", type=str, default=None, help="Target fish species (Perch, Pike, Zander, Bream, Carp)")
    elif section_id == "tackle":
        parser.add_argument("--type", type=str, default=None, help="Accessory type (Terminal, Net, Feeder, Tools)")

    args = parser.parse_args(argv)

    # Build criteria map from parsed domain arguments
    crit: dict = {}
    if args.brand:
        crit["brand"] = args.brand

    if section_id == "rod":
        if args.power:
            crit["power"] = args.power
        if args.test_min is not None:
            crit["test_min"] = args.test_min
        if args.test_max is not None:
            crit["test_max"] = args.test_max
    elif section_id == "reel":
        if args.spool is not None:
            crit["spool"] = args.spool
        if args.min_drag is not None:
            crit["min_drag"] = args.min_drag
    elif section_id == "line":
        if args.type:
            crit["type"] = args.type
        if args.min_kg is not None:
            crit["min_kg"] = args.min_kg
    elif section_id == "bait":
        if args.type:
            crit["type"] = args.type
        if args.target:
            crit["target"] = args.target
    elif section_id == "tackle":
        if args.type:
            crit["type"] = args.type

    results = search_fishing(
        section_id=section_id,
        query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        criteria=crit,
        mode=args.mode,
        limit=args.limit,
        scorer=scorer,
        weights_reg=weights_reg,
    )
    print_fishing_search_results(
        results=results,
        section_id=section_id,
        layout=layout,
        mode=args.mode,
    )


def _run_modes(argv: List[str]) -> None:
    parser = argparse.ArgumentParser(
        prog=f"{_cli_prog()} fishing modes",
        description="List fishing optimization modes and weights",
    )
    parser.add_argument("--inspect", "-i", type=str, default=None, help="Inspect weights of a specific mode")
    args = parser.parse_args(argv)

    weights_reg = create_fishing_weights_registry()
    print("\nOptimization Modes for Fishing Tackle Set")
    print("─" * 82)
    print(f"  {'Mode':<18} │ {'Title':<28} │ Key Criteria")
    print("─" * 82)
    for prof in weights_reg.list_profiles().values():
        top_weights = sorted(prof.weights.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = ", ".join(f"{k}:{v:.2f}" for k, v in top_weights)
        print(f"  {prof.name:<18} │ {prof.title:<28} │ {top_str}")
    print("─" * 82)
    print(f"Total modes available: {len(weights_reg.list_profiles())}\n")

    if args.inspect:
        prof = weights_reg.resolve_profile(args.inspect)
        print(f"Mode Details: {prof.name} ({prof.title})")
        print(f"   Description       : {prof.description}")
        if prof.constraints:
            print(f"   Constraints       : {prof.constraints}")
        print(f"   Normalized Weights: {prof.weights}\n")


def print_help() -> None:
    prog = _cli_prog()
    print("\nFishing Tackle Set Synthesizer & Explorer\n")
    print(f"Usage: {prog} fishing <command> [options]\n")
    print("Commands:")
    print("  build    Synthesize optimal tackle sets under budget (spinning, feeder, carp)")
    print("  rod      Search and filter fishing rods (power, test range, brand, price)")
    print("  reel     Search and filter reels (spool size, drag power, brand, price)")
    print("  line     Search and filter lines (PE 4x/8x, breaking test kg, diameter)")
    print("  bait     Search and filter lures/cages (type, target fish, weight)")
    print("  tackle   Search and filter accessory kits and nets")
    print("  deals    Inspect verified historical seller price drops in SQLite MarketStore (alias: history)")
    print("  modes    List available optimization modes and weights")
    print("\nExamples:")
    print(f"  {prog} fishing build -b 150 -M spinning-light")
    print(f"  {prog} fishing build -b 200 -M feeder-distance")
    print(f"  {prog} fishing rod --power Light -q Favorite")
    print(f"  {prog} fishing reel --spool 2000")
    print(f"  {prog} fishing bait --type MicroJig")
    print(f"  {prog} fishing line --type 'PE 4x'")
    print(f"  {prog} fishing modes -i feeder-distance\n")


def main(argv: Optional[List[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return

    cmd = args[0].lower()
    extra = args[1:]

    if cmd == "build":
        _run_build(extra)
    elif cmd in ("search", "find"):
        from extensions.fishing import FishingDomainExtension
        FishingDomainExtension().run_cli_search(extra)
    elif cmd in ("rod", "reel", "line", "bait", "tackle"):
        _run_search_category(cmd, extra)
    elif cmd in ("modes", "mods"):
        _run_modes(extra)
    else:
        print(f"Error: Unknown fishing command '{cmd}'\n", file=sys.stderr)
        print_help()
        return


if __name__ == "__main__":
    main()
