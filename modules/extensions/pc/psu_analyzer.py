#!/usr/bin/env python3
"""
PSU Market Intelligence, Multi-Mode Valuation & Multi-Provider AI Audit Engine.
"""

import argparse
import csv
from typing import Any, Dict, List, Optional

from analyzer_core import (
    add_common_mode_and_ai_args,
    fetch_category_offers,
    fmt_deal_pct,
    get_status_badge,
    make_terminal_link,
    prepare_entry_metadata,
    print_verbose_evaluations,
    render_box_table,
    run_laser_audit_loop,
    sort_entries,
)
from currency import canonical_currency, convert_currency, format_price, get_active_currency, normalize_listing_price
from market_client import MarketClient as OLXClient, check_delivery_refusal
from extensions.pc.modes import EFF_RANK, PSU_TIER_RANK, resolve_mode
from extensions.pc.psu_ai_inspector import PSUAIInspector
from extensions.pc.psu_database import identify_psu
from extensions.pc.psu_scam_detector import PSUScamDetector


def render_psu_table(items: List[Dict[str, Any]], max_rows: Optional[int] = None) -> None:
    cols = [
        ("#", 3, lambda i, c: f"#{i}"),
        ("Model", 21, lambda i, c: make_terminal_link(c["summary"]["url"], f"{c['psu']['model'][:21]:<21}")),
        ("Watts", 5, lambda i, c: f"{c['psu']['wattage']}W"),
        ("Eff", 8, lambda i, c: c["psu"]["efficiency"][:8]),
        ("Mod", 7, lambda i, c: c["psu"]["modularity"][:7]),
        ("Tier", 6, lambda i, c: c["psu"]["vrm_tier"]),
        ("Price", 8, lambda i, c: format_price(c['price'], c.get('currency'))),
        ("Cost/W", 4, lambda i, c: f"{c['uah_per_watt']:.1f}"),
        ("Deal", 5, lambda i, c: fmt_deal_pct(c.get("discount_pct", 0.0))),
        ("Status", 20, lambda i, c: get_status_badge(c)),
    ]
    render_box_table(items, cols, max_rows=max_rows)


def export_to_csv(file_path: str, items: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Model", "Watts", "Efficiency", "Modularity", "FormFactor", "ATX3_12VHPWR", "Tier", "Price", "Cost_Per_W", "Vs_Market_Pct", "Risk", "URL"])
        for idx, c in enumerate(items, 1):
            p = c["psu"]
            writer.writerow([
                idx, p["model"], p["wattage"], p["efficiency"], p["modularity"], p["form_factor"],
                p["has_12vhpwr"], p["vrm_tier"], c["price"], c["uah_per_watt"],
                c.get("discount_pct", 0.0), (c.get("heuristic") or {}).get("risk_score", 0), c["summary"]["url"],
            ])


def write_markdown_report(file_path: str, approved: List[Dict[str, Any]], sort_label: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# OLX Power Supply Units (Ranked by {sort_label})\n\n")
        f.write("| # | Model | Watts | Eff | Mod | Tier | Price | Cost/W | vs Mkt | AI |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for idx, c in enumerate(approved, 1):
            ai_eval = c.get("ai_eval") or {}
            conf_pct = f"{ai_eval.get('confidence_score', 85)}%"
            disc = int(round(c.get("discount_pct", 0.0)))
            disc_str = f"-{disc}%" if disc > 0 else f"+{abs(disc)}%"
            m = c["psu"]
            p_str = format_price(c["price"], c.get("currency"))
            f.write(
                f"| #{idx} | [{m['model']}]({c['summary']['url']}) | {m['wattage']}W | {m['efficiency']} | "
                f"{m['modularity']} | {m['vrm_tier']} | {p_str} | {c['uah_per_watt']:.1f} | {disc_str} | {conf_pct} |\n"
            )


def run_psu_analyzer(
    query: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_watts: Optional[int] = None,
    max_watts: Optional[int] = None,
    tier_filter: Optional[str] = None,
    eff_min: Optional[str] = None,
    modular_only: bool = False,
    sfx_only: bool = False,
    atx3_only: bool = False,
    brand_filter: Optional[str] = None,
    sort_criterion: str = "value",
    mode: Optional[str] = None,
    weights: Optional[str] = None,
    max_risk: Optional[int] = None,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    re_audit: bool = False,
    only_olx_delivery: bool = True,
    target_approved: int = 8,
    max_pages: int = 25,
    harvest: bool = False,
    deep: bool = False,
    refresh: bool = False,
    show_mega_table: bool = False,
    show_rejected: bool = False,
    use_ai: bool = True,
    human_review: bool = False,
    verbose: bool = False,
    output_md: Optional[str] = None,
    output_csv: Optional[str] = None,
) -> List[Dict[str, Any]]:
    mode_profile = resolve_mode(mode or ("custom" if weights else None), weights_override=weights, max_risk_override=max_risk) if (mode or weights) else None
    effective_max_risk = mode_profile.max_risk if mode_profile else max_risk
    if mode_profile and mode_profile.require_delivery:
        only_olx_delivery = True

    active_curr = get_active_currency()
    client = OLXClient()
    detector = PSUScamDetector()
    ai = PSUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url) if use_ai else None

    min_p_uah = int(convert_currency(float(min_price), active_curr, "UAH")) if (min_price and canonical_currency(active_curr) != "UAH") else min_price
    max_p_uah = int(convert_currency(float(max_price), active_curr, "UAH")) if (max_price and canonical_currency(active_curr) != "UAH") else max_price

    raw_offers = fetch_category_offers(
        client, "psu", client.search_psus,
        query=query, min_price=min_p_uah, max_price=max_p_uah,
        max_pages=max_pages, harvest=harvest, deep=deep, refresh=refresh,
    )

    matched_items: List[Dict[str, Any]] = []
    seen_ids = set()
    q_low = query.lower()

    for raw_item in raw_offers:
        oid = raw_item.get("id")
        if oid in seen_ids:
            continue
        seen_ids.add(oid)

        raw_uah_price = float(raw_item.get("price", 0))
        if raw_uah_price <= 150:
            continue

        item = dict(raw_item)
        normalize_listing_price(item, target_currency=active_curr)
        price = float(item.get("price", 0.0))

        if min_price and price < min_price:
            continue
        if max_price and price > max_price:
            continue

        title = item.get("title", "")
        if q_low and q_low not in title.lower():
            continue

        desc = item.get("description") or (item.get("raw") or {}).get("description", "")
        if only_olx_delivery and (not item.get("has_olx_delivery") or check_delivery_refusal(desc)):
            continue

        psu_info = identify_psu(title, desc)
        if not psu_info:
            continue

        w = psu_info["wattage"]
        if min_watts and w < min_watts:
            continue
        if max_watts and w > max_watts:
            continue
        if tier_filter:
            tier_req = f"Tier {tier_filter.upper().replace('TIER', '').strip()}"
            if psu_info["vrm_tier"] != tier_req:
                continue
        if eff_min and EFF_RANK.get(psu_info["efficiency"], 0) < EFF_RANK.get(eff_min, 0):
            continue
        if modular_only and psu_info["modularity"] not in ("Full", "Semi"):
            continue
        if sfx_only and psu_info["form_factor"] not in ("SFX", "SFX-L"):
            continue
        if atx3_only and not psu_info["has_12vhpwr"]:
            continue
        if brand_filter and brand_filter.lower() not in psu_info["brand"].lower():
            continue

        entry: Dict[str, Any] = {
            "summary": item,
            "psu": psu_info,
            "price": price,
            "currency": active_curr,
            "uah_per_watt": round(price / w, 2),
            "tier_rank": PSU_TIER_RANK.get(psu_info["vrm_tier"], 1),
            "eff_rank": EFF_RANK.get(psu_info["efficiency"], 0),
        }
        prepare_entry_metadata("psu", entry, psu_info, detector, re_audit=re_audit)
        matched_items.append(entry)

    if not matched_items:
        print("No Power Supply Units matched all requirements. Try widening thresholds.")
        return []

    def legacy_key(x: Dict[str, Any]) -> Any:
        if sort_criterion == "value":
            return (x["uah_per_watt"], -x["tier_rank"], x["price"])
        if sort_criterion == "watts":
            return (-x["psu"]["wattage"], -x["eff_rank"], x["price"])
        if sort_criterion == "tier":
            return (-x["tier_rank"], -x["eff_rank"], x["uah_per_watt"])
        return (x["price"], -x["tier_rank"])

    mode_label = sort_entries("psu", matched_items, mode_profile, legacy_key)
    active_label = mode_label or sort_criterion.upper()
    print(f"[2/3] Built Mega Table: {len(matched_items)} matching PSUs ranked by {active_label}.")

    if human_review:
        from extensions.pc.human_review import run_human_validation_review
        run_human_validation_review(
            psu_list=matched_items,
            budget=float(max_price or 40000.0),
            profile=mode_profile,
        )

    if output_csv:
        export_to_csv(output_csv, matched_items)
        print(f"Exported {len(matched_items)} listings to CSV: {output_csv}")

    if show_mega_table or not use_ai:
        print(f"\nMarket Overview (Top {min(len(matched_items), 30)} candidates — 0 AI tokens):\n")
        render_psu_table(matched_items, max_rows=30)
        if not use_ai:
            return matched_items

    all_approved, all_rejected = run_laser_audit_loop(
        matched_items, "psu", client, detector, ai,
        target_approved=target_approved,
        sort_label=(mode_profile.name if mode_profile else sort_criterion),
        max_risk=effective_max_risk,
        re_audit=re_audit,
    )

    sort_entries("psu", all_approved, mode_profile, legacy_key)
    all_approved = all_approved[:target_approved]
    print(f"Verified {len(all_approved)} top PSU recommendations!\n")

    table_items = (all_approved + all_rejected[:12]) if show_rejected else all_approved
    render_psu_table(table_items)

    if verbose:
        print_verbose_evaluations("psu", all_approved, all_rejected)
    if output_md:
        write_markdown_report(output_md, all_approved, active_label)
        print(f"Saved report to: {output_md}")
    return all_approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX PSU Multi-Mode Valuation & Multi-Provider AI Analyzer")
    parser.add_argument("--query", "-q", type=str, default="", help="Search keyword (e.g. 'seasonic', 'rm750x', 'gold')")
    parser.add_argument("--min-watts", type=int, default=None, help="Minimum continuous wattage (e.g. 650, 750, 850)")
    parser.add_argument("--max-watts", type=int, default=None, help="Maximum continuous wattage")
    parser.add_argument("--tier", type=str, default=None, help="Filter by Cultists Tier (A, B, C)")
    parser.add_argument("--gold", action="store_true", help="Filter to 80 PLUS Gold or higher")
    parser.add_argument("--platinum", action="store_true", help="Filter to 80 PLUS Platinum or Titanium")
    parser.add_argument("--bronze", action="store_true", help="Filter to 80 PLUS Bronze or higher")
    parser.add_argument("--modular", action="store_true", help="Filter to Full or Semi modular PSUs")
    parser.add_argument("--sfx", action="store_true", help="Filter strictly to SFX / SFX-L compact form factor")
    parser.add_argument("--atx3", action="store_true", help="Filter strictly to ATX 3.0/3.1 with 12VHPWR / 12V-2x6")
    parser.add_argument("--brand", type=str, default=None, help="Filter by brand (e.g. Seasonic, Corsair, be quiet!)")
    parser.add_argument("--min-price", type=int, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in UAH")
    parser.add_argument("--sort", "--sort-by", dest="sort", choices=["value", "watts", "tier", "price"], default="value", help="Legacy sort criterion")
    parser.add_argument("--target-approved", "-n", type=int, default=8, help="Number of verified PSUs to return")
    parser.add_argument("--pages", type=int, default=25, help="Max OLX pages to fetch")
    parser.add_argument("--harvest", action="store_true", help="Harvest up to 25 pages into local cache")
    parser.add_argument("--deep", "--all-pages", action="store_true", help="Deep multi-window crawl")
    parser.add_argument("--refresh", action="store_true", help="Force fetching fresh listings from OLX")
    parser.add_argument("--mega", "--mega-table", "--show-mega-table", action="store_true", dest="show_mega_table", help="Show pre-AI Mega Table")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI inspection")
    parser.add_argument("--allow-no-delivery", action="store_true", help="Allow listings without OLX Delivery")
    parser.add_argument("--show-rejected", action="store_true", help="Display rejected and flagged listings in table")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed AI & heuristic evaluations")
    parser.add_argument("--export-csv", type=str, default=None, help="Export full matched dataset to CSV")
    parser.add_argument("--export-md", type=str, default=None, help="Save Markdown report")
    add_common_mode_and_ai_args(parser)
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    eff_min = "Platinum" if args.platinum else ("Gold" if args.gold else ("Bronze" if args.bronze else None))

    run_psu_analyzer(
        query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        min_watts=args.min_watts,
        max_watts=args.max_watts,
        tier_filter=args.tier,
        eff_min=eff_min,
        modular_only=args.modular,
        sfx_only=args.sfx,
        atx3_only=args.atx3,
        brand_filter=args.brand,
        sort_criterion=args.sort,
        mode=args.mode,
        weights=args.weights,
        max_risk=args.max_risk,
        ai_provider=args.ai_provider,
        ai_model=args.ai_model,
        ai_base_url=args.ai_base_url,
        re_audit=args.re_audit,
        only_olx_delivery=not args.allow_no_delivery,
        target_approved=args.target_approved,
        max_pages=args.pages,
        harvest=args.harvest,
        deep=args.deep,
        refresh=args.refresh,
        show_mega_table=args.show_mega_table,
        show_rejected=args.show_rejected,
        use_ai=not args.no_ai,
        human_review=args.human_review,
        verbose=args.verbose,
        output_md=args.export_md,
        output_csv=args.export_csv,
    )


if __name__ == "__main__":
    main()
