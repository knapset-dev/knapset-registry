#!/usr/bin/env python3
"""
Automated Multi-Category Hardware Verification Audit Pipeline.

Ranks clean OLX-Delivery candidates across all 5 component categories (GPU, CPU,
Motherboard, RAM, PSU) using any Optimization Mode ('best', 'sweet-spot', 'safe',
etc.), fetches full descriptions in a single concurrent batch, runs Multi-Provider
AI semantic inspection (with persistent AuditLedger memoization), and exports
`data/ai_verified_components.json`.
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_providers import list_provider_names
from analyzer_core import fmt_deal_pct, make_terminal_link
from audit_ledger import ledger
from currency import format_price, get_active_currency, normalize_listing_price
from extensions.pc.cpu_ai_inspector import CPUAIInspector
from extensions.pc.cpu_database import identify_cpu
from extensions.pc.cpu_scam_detector import CPUScamDetector
from extensions.pc.gpu_ai_inspector import GPUAIInspector
from extensions.pc.gpu_database import identify_gpu
from extensions.pc.gpu_scam_detector import GPUScamDetector
from market_client import INTEL_DATA_DIR, MarketClient, check_delivery_refusal, load_market_cache
from extensions.pc.mobo_ai_inspector import MotherboardAIInspector
from extensions.pc.mobo_database import identify_motherboard
from extensions.pc.mobo_scam_detector import MotherboardScamDetector
from extensions.pc.modes import (
    compute_market_discount_pct,
    get_mode_names,
    is_listing_disqualified,
    resolve_mode,
    score_component,
)
from extensions.pc.psu_ai_inspector import PSUAIInspector
from extensions.pc.psu_database import identify_psu
from extensions.pc.psu_scam_detector import PSUScamDetector
from extensions.pc.ram_ai_inspector import RAMAIInspector
from extensions.pc.ram_database import identify_ram
from extensions.pc.ram_scam_detector import RAMScamDetector

DATA_DIR = INTEL_DATA_DIR
ALL_CATEGORIES = ("gpu", "cpu", "mobo", "ram", "psu")


def _pick_diverse_finalists(candidates: List[Dict[str, Any]], spec_key: str, limit: int) -> List[Dict[str, Any]]:
    """Picks top-ranked clean candidates while limiting max 2 listings per identical hardware model."""
    picked: List[Dict[str, Any]] = []
    per_model: Dict[str, int] = defaultdict(int)
    for c in candidates:
        if is_listing_disqualified(c.get("heuristic"), c.get("ai_eval")):
            continue
        model = c[spec_key]["model"]
        if per_model[model] >= 2:
            continue
        per_model[model] += 1
        picked.append(c)
        if len(picked) >= limit:
            break
    return picked


def run_audit_pipeline(
    mode: str = "best",
    weights: Optional[str] = None,
    categories: Optional[List[str]] = None,
    top_per_category: int = 5,
    min_confidence: int = 70,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    re_audit: bool = False,
    refresh: bool = False,
    output_path: Optional[Path] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    t0 = time.perf_counter()
    profile = resolve_mode(mode, default="best", weights_override=weights)
    active_cats = [c.lower() for c in (categories or list(ALL_CATEGORIES)) if c.lower() in ALL_CATEGORIES]
    client = MarketClient()

    inspectors = {
        "gpu": GPUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url),
        "cpu": CPUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url),
        "mobo": MotherboardAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url),
        "ram": RAMAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url),
        "psu": PSUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url),
    }
    detectors = {
        "gpu": GPUScamDetector(),
        "cpu": CPUScamDetector(),
        "mobo": MotherboardScamDetector(),
        "ram": RAMScamDetector(),
        "psu": PSUScamDetector(),
    }

    any_cat = active_cats[0] if active_cats else "gpu"
    print(
        f"\nMulti-Category AI Audit Pipeline │ Mode: {profile.name.upper()} ({profile.title}) │ "
        f"AI: {inspectors[any_cat].provider_label}"
    )

    finalists_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    all_finalist_ids: List[str] = []

    for cat in active_cats:
        if refresh:
            offers = client.harvest_category(cat, max_pages=20, deep=False)
        else:
            offers, _, _ = load_market_cache(cat)

        cands: List[Dict[str, Any]] = []
        active_curr = get_active_currency()
        for raw_off in offers:
            if not raw_off.get("has_olx_delivery") or check_delivery_refusal(raw_off.get("description", "")):
                continue
            raw_uah_price = float(raw_off.get("price", 0))
            if raw_uah_price < 600:
                continue
            off = dict(raw_off)
            normalize_listing_price(off, target_currency=active_curr)
            price = float(off.get("price", 0.0))
            title = off.get("title", "")
            desc = off.get("description", "")

            # 1. Hardware Specification Identification (Modular Component Analyser -> Legacy DB fallback)
            spec = None
            try:
                from component_analyser import get_component_registry
                comp_mod = get_component_registry().get(cat)
                if comp_mod:
                    spec = comp_mod.identify(title, desc)
            except Exception:
                spec = None

            if not spec:
                if cat == "gpu":
                    spec = identify_gpu(title)
                elif cat == "cpu":
                    spec = identify_cpu(title, desc)
                elif cat == "mobo":
                    spec = identify_motherboard(title, desc)
                elif cat == "ram":
                    spec = identify_ram(title, desc)
                elif cat == "psu":
                    spec = identify_psu(title, desc)

            if not spec:
                continue

            # Category-specific threshold filters
            if cat == "gpu" and spec.get("fps_1440p", 0) < 35:
                continue
            elif cat == "cpu" and spec.get("fps_gaming", 0) < 75:
                continue
            elif cat == "mobo" and spec.get("is_bundle"):
                continue
            elif cat == "ram" and (spec.get("form_factor") not in ("UDIMM", "UNKNOWN", "ECC_UDIMM") or spec.get("total_gb", 0) < 16):
                continue
            elif cat == "psu" and (spec.get("wattage", 0) < 550 or spec.get("vrm_tier") == "Tier D"):
                continue

            # 2. Defect & Scam Analysis (Modular Scam Analyser -> Legacy Detector fallback)
            heur = None
            try:
                from scam_analyser import get_scam_registry
                scam_mod = get_scam_registry().get(cat)
                if scam_mod:
                    scam_res = scam_mod.analyze(off, off.get("raw") or {}, spec)
                    heur = scam_res.to_dict()
            except Exception:
                heur = None

            if not heur:
                det = detectors.get(cat)
                if det:
                    heur = det.analyze_listing(off, off.get("raw") or {}, spec)
                else:
                    heur = {"risk_score": 20, "red_flags": [], "warnings": []}
            has_deliv = off.get("has_olx_delivery", True)
            cached = None if re_audit else ledger.get_audit(
                str(off.get("id")),
                title=title,
                price=price,
                description=desc,
                has_delivery=has_deliv,
            )

            entry: Dict[str, Any] = {
                "summary": off,
                cat: spec,
                "spec": spec,
                "price": price,
                "currency": active_curr,
                "heuristic": heur,
                "ai_eval": cached,
                "discount_pct": compute_market_discount_pct(price, spec, price_currency=active_curr, spec_currency="UAH"),
                "uah_per_fps": round(price / max(1.0, spec.get("fps_1440p", spec.get("fps_gaming", 1.0))), 1),
                "uah_per_gb": round(price / max(1, spec.get("total_gb", 1)), 1),
            }
            if cat == "gpu":
                entry["fps_1440p"] = spec["fps_1440p"]
                entry["fps_1080p"] = spec["fps_1080p"]
            elif cat == "cpu":
                entry["fps_gaming"] = spec["fps_gaming"]

            entry["mode_score"] = score_component(cat, entry, profile)
            cands.append(entry)

        cands.sort(key=lambda x: (-x["mode_score"], x["price"]))
        picked = _pick_diverse_finalists(cands, cat, limit=top_per_category + 2)
        finalists_by_cat[cat] = picked
        all_finalist_ids.extend(str(x["summary"]["id"]) for x in picked)

    # Single concurrent batch fetch across all categories!
    details_map = client.get_batch_details(all_finalist_ids) if all_finalist_ids else {}

    verified_dataset: Dict[str, List[Dict[str, Any]]] = {}
    for cat in active_cats:
        picked = finalists_by_cat.get(cat, [])
        det = detectors[cat]
        for c in picked:
            oid = str(c["summary"]["id"])
            c["detail"] = details_map.get(oid) or c["summary"].get("raw") or {"description": c["summary"].get("description", "")}
            c["heuristic"] = det.analyze_listing(c["summary"], c["detail"], c[cat])

        ai_res = inspectors[cat].inspect_and_rank_batch(picked, sort_by=profile.name, re_audit=re_audit)
        approved = [
            x for x in ai_res.get("approved", [])
            if x.get("ai_eval", {}).get("confidence_score", 0) >= min_confidence
            and not is_listing_disqualified(x.get("heuristic"), x.get("ai_eval"))
        ][:top_per_category]

        verified_dataset[f"{cat}s"] = approved
        print(f"\nApproved {cat.upper()}s ({len(approved)}):")
        for item in approved:
            ai_e = item.get("ai_eval", {})
            spec = item[cat]
            link = make_terminal_link(item["summary"].get("url", ""), "[Open Ad ↗]")
            deal_s = fmt_deal_pct(item["discount_pct"])
            p_str = format_price(item["price"], item.get("currency"))
            print(
                f"  • {spec['model']:<24} {p_str:>10} ({deal_s}) │ "
                f"Score: {item['mode_score']:>5.1f} │ Conf: {ai_e.get('confidence_score', 0)}% │ {link}"
            )
            for reason in (ai_e.get("reasons") or [])[:2]:
                print(f"      └─ {reason}")

    out_file = output_path or (DATA_DIR / "ai_verified_components.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(verified_dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - t0
    total_ok = sum(len(v) for v in verified_dataset.values())
    print(f"\nAudited & verified {total_ok} components across {len(active_cats)} categories in {elapsed:.2f}s -> {out_file}")
    return verified_dataset


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-Category Hardware AI Audit Pipeline")
    parser.add_argument("--mode", "-M", type=str, default="best", help=f"Optimization mode ({', '.join(get_mode_names())})")
    parser.add_argument("--weights", type=str, default=None, help="Custom weight overrides")
    parser.add_argument(
        "--categories",
        type=str,
        default="gpu,cpu,mobo,ram,psu",
        help="Comma-separated categories to audit (default: gpu,cpu,mobo,ram,psu)",
    )
    parser.add_argument("--top", "-n", type=int, default=5, help="Approved finalists to keep per category (default: 5)")
    parser.add_argument("--min-confidence", type=int, default=70, help="Minimum AI confidence threshold (default: 70)")
    parser.add_argument("--ai-provider", choices=list_provider_names(), default=None, help="AI provider backend")
    parser.add_argument("--ai-model", type=str, default=None, help="Override AI model name")
    parser.add_argument("--ai-base-url", type=str, default=None, help="Custom base URL for local/OpenAI-compatible endpoint")
    parser.add_argument("--re-audit", action="store_true", help="Ignore cached AuditLedger verdicts")
    parser.add_argument("--refresh", action="store_true", help="Refresh OLX caches before auditing")
    parser.add_argument("--output", type=str, default=None, help="Custom output JSON path")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    out_p = Path(args.output) if args.output else None
    run_audit_pipeline(
        mode=args.mode,
        weights=args.weights,
        categories=cats,
        top_per_category=args.top,
        min_confidence=args.min_confidence,
        ai_provider=args.ai_provider,
        ai_model=args.ai_model,
        ai_base_url=args.ai_base_url,
        re_audit=args.re_audit,
        refresh=args.refresh,
        output_path=out_p,
    )


if __name__ == "__main__":
    main()
