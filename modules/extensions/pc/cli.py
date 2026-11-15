#!/usr/bin/env python3
"""
PC Domain CLI.

Standalone and embedded CLI for computer hardware discovery and PC build synthesis:
- build : Synthesize optimal PC builds under budget
- gpu   : Analyze GPU market dynamics, % vs median deals, and cost/FPS
- cpu   : Analyze CPU market data, X3D/multi-core tiers, and gaming valuation
- mobo  : Analyze Motherboards, chipset VRM tiers, and socket compatibility
- ram   : Analyze RAM kits, DDR4/DDR5 latency (ns), and cost/GB density
- psu   : Analyze Power Supplies with Cultists Tier & fire-hazard protection
- modes : List available PC optimization modes
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

def print_help() -> None:
    print("\nPC Hardware Intelligence & System Optimization Suite\n")
    print("Usage: python main.py pc <command> [options]\n")
    print("Commands:")
    print("  build    Synthesize optimal 5-part PC builds under budget")
    print("  compare  Head-to-head comparison duel of prebuilt listings vs alternatives or other prebuilts (aliases: eval, vs)")
    print("  eval     Evaluate ready-made PC listings or offers against market fair value")
    print("  vs       Alias for 'compare'")
    print("  gpu      Analyze GPU market dynamics, % vs median deals, and cost/FPS")
    print("  cpu      Analyze CPU market data, X3D/multi-core tiers, and gaming valuation")
    print("  mobo     Analyze Motherboards, chipset VRM tiers, and socket compatibility")
    print("  ram      Analyze RAM kits, DDR4/DDR5 latency (ns), and cost/GB density")
    print("  psu      Analyze Power Supplies with Cultists Tier & fire-hazard protection")
    print("  deals    Inspect verified historical seller price drops in SQLite MarketStore (alias: history)")
    print("  audit    AI-verify top candidates across all component categories")
    print("  modes    List available PC optimization modes and weights\n")
    print("Examples:")
    print("  python main.py pc build -b 850 -M sweet-spot")
    print("  python main.py pc compare 'Ryzen 5 3600, RTX 2060, 450 USDT' vs 'i5 10400F, RTX 3060, 500 USDT' -M sweet-spot")
    print("  python main.py pc compare 'Ryzen 5 3600, RTX 2060 Super, 450 USDT' -M value")
    print("  python main.py pc eval 'Ryzen 5 3600, RTX 2060 Super, 450 USDT'")
    print("  python main.py pc vs 'https://www.olx.ua/d/uk/obyavlenie/...'")
    print("  python main.py pc gpu -q '3080' --no-ai")
    print("  python main.py pc cpu --socket AM5 -t 16 --no-ai\n")


def main(argv: Optional[List[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return

    cmd = args[0].lower()
    extra = args[1:]

    if cmd == "build":
        import extensions.pc.build_optimizer as build_optimizer
        build_optimizer.main(extra)
    elif cmd in ("search", "find"):
        from extensions.pc import PCDomainExtension
        PCDomainExtension().run_cli_search(extra)
    elif cmd in ("eval", "vs", "compare"):
        from extensions.pc.prebuilt_evaluator import main as eval_main
        eval_main(extra, prog=f"python main.py pc {cmd}")
    elif cmd == "audit":
        import extensions.pc.audit_pipeline as audit_pipeline
        audit_pipeline.main(extra)
    elif cmd == "gpu":
        import extensions.pc.gpu_analyzer as gpu_analyzer
        gpu_analyzer.main(extra)
    elif cmd == "cpu":
        import extensions.pc.cpu_analyzer as cpu_analyzer
        cpu_analyzer.main(extra)
    elif cmd == "mobo":
        import extensions.pc.mobo_analyzer as mobo_analyzer
        mobo_analyzer.main(extra)
    elif cmd == "ram":
        import extensions.pc.ram_analyzer as ram_analyzer
        ram_analyzer.main(extra)
    elif cmd == "psu":
        import extensions.pc.psu_analyzer as psu_analyzer
        psu_analyzer.main(extra)
    elif cmd in ("modes", "mods"):
        from extensions.pc.modes import print_modes_table, resolve_mode
        if extra and extra[0] in ("-i", "--inspect") and len(extra) > 1:
            prof = resolve_mode(extra[1])
            print(f"Mode Details: {prof.name} ({prof.title})")
            print(f"   Description      : {prof.description}")
            print(f"   Normalized Weights: {prof.weights}\n")
        else:
            print_modes_table()
    else:
        print(f"Error: Unknown PC command '{cmd}'\n", file=sys.stderr)
        print_help()
        return


if __name__ == "__main__":
    main()
