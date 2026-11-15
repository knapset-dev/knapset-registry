#!/usr/bin/env python3
"""
Motherboard Market Intelligence, Multi-Mode Valuation & Multi-Provider AI Audit Engine.
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
from extensions.pc.mobo_ai_inspector import MotherboardAIInspector
from extensions.pc.mobo_database import VRM_TIER_SCORES, identify_motherboard
from extensions.pc.mobo_scam_detector import MotherboardScamDetector
from extensions.pc.modes import resolve_mode


def render_mobo_table(items: List[Dict[str, Any]], max_rows: Optional[int] = None) -> None:
    cols = [
        ("#", 3, lambda i, c: f"#{i}"),
        ("Model", 20, lambda i, c: make_terminal_link(c["summary"]["url"], f"{c['mobo']['model'][:20]:<20}")),
        ("Socket", 9, lambda i, c: c["mobo"]["socket"][:9]),
        ("RAM", 4, lambda i, c: c["mobo"]["ddr_type"]),
        ("Form", 5, lambda i, c: c["mobo"]["form_factor"][:5]),
        ("VRM", 6, lambda i, c: c["mobo"]["vrm_tier"]),
        ("Price", 9, lambda i, c: format_price(c['price'], c.get('currency'))),
        ("Deal", 5, lambda i, c: fmt_deal_pct(c.get("discount_pct", 0.0))),
        ("Status", 20, lambda i, c: get_status_badge(c)),
    ]
    render_box_table(items, cols, max_rows=max_rows)


def export_to_csv(file_path: str, items: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Model", "Socket", "Chipset", "DDR", "FormFactor", "VRM_Tier", "Price", "Vs_Market_Pct", "IsBundle", "Risk", "URL"])
        for idx, c in enumerate(items, 1):
            m = c["mobo"]
            writer.writerow([
                idx, m["model"], m["socket"], m["chipset"], m["ddr_type"], m["form_factor"],
                m["vrm_tier"], c["price"], c.get("discount_pct", 0.0), m["is_bundle"],
                (c.get("heuristic") or {}).get("risk_score", 0), c["summary"]["url"],
            ])


def write_markdown_report(file_path: str, approved: List[Dict[str, Any]], sort_label: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# OLX Motherboards (Ranked by {sort_label})\n\n")
        f.write("| # | Model | Socket | Form | RAM | Tier | Price | vs Mkt | Type | AI |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for idx, c in enumerate(approved, 1):
            ai_eval = c.get("ai_eval") or {}
            conf_pct = f"{ai_eval.get('confidence_score', 85)}%"
            disc = int(round(c.get("discount_pct", 0.0)))
            disc_str = f"-{disc}%" if disc > 0 else f"+{abs(disc)}%"
            m = c["mobo"]
            b_type = "+CPU" if m["bundle_cpu"] else ("Bundle" if m["is_bundle"] else "Board")
            p_str = format_price(c["price"], c.get("currency"))
            f.write(
                f"| #{idx} | [{m['model']}]({c['summary']['url']}) | {m['socket']} | {m['form_factor']} | "
                f"{m['ddr_type']} | {m['vrm_tier']} | {p_str} | {disc_str} | {b_type} | {conf_pct} |\n"
            )


def _normalize_socket(sock: Optional[str]) -> Optional[str]:
    if not sock:
        return None
    s = sock.strip().upper()
    if s in ("X99", "2011-3", "LGA2011-3"):
        return "LGA2011-V3"
    return s


def run_mobo_analyzer(
    query: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    socket_filter: Optional[str] = None,
    chipset_filter: Optional[str] = None,
    ddr_filter: Optional[str] = None,
    form_filter: Optional[str] = None,
    wifi_only: bool = False,
    bundle_mode: str = "all",
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
    detector = MotherboardScamDetector()
    ai = MotherboardAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url) if use_ai else None

    min_p_uah = int(convert_currency(float(min_price), active_curr, "UAH")) if (min_price and canonical_currency(active_curr) != "UAH") else min_price
    max_p_uah = int(convert_currency(float(max_price), active_curr, "UAH")) if (max_price and canonical_currency(active_curr) != "UAH") else max_price

    raw_offers = fetch_category_offers(
        client, "mobo", client.search_motherboards,
        query=query, min_price=min_p_uah, max_price=max_p_uah,
        max_pages=max_pages, harvest=harvest, deep=deep, refresh=refresh,
    )

    matched_items: List[Dict[str, Any]] = []
    seen_ids = set()
    q_low = query.lower()
    sock_norm = _normalize_socket(socket_filter)

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

        mobo_info = identify_motherboard(title, desc)
        if not mobo_info:
            continue

        if sock_norm and mobo_info["socket"].upper() != sock_norm:
            continue
        if chipset_filter and mobo_info["chipset"].upper() != chipset_filter.upper():
            continue
        if ddr_filter and mobo_info["ddr_type"] != ddr_filter:
            continue
        if form_filter and mobo_info["form_factor"] != form_filter:
            continue
        if wifi_only and not mobo_info["has_wifi"]:
            continue
        if bundle_mode == "standalone" and mobo_info["is_bundle"]:
            continue
        if bundle_mode == "bundle_only" and not mobo_info["is_bundle"]:
            continue

        min_mkt = mobo_info["market_used_min"]
        entry: Dict[str, Any] = {
            "summary": item,
            "mobo": mobo_info,
            "price": price,
            "currency": active_curr,
            "value_ratio": round(raw_uah_price / max(1.0, float(min_mkt)), 2),
            "tier_rank": VRM_TIER_SCORES.get(mobo_info["vrm_tier"], 3),
        }
        prepare_entry_metadata("mobo", entry, mobo_info, detector, re_audit=re_audit)
        matched_items.append(entry)

    if not matched_items:
        print("No Motherboards matched all requirements. Try widening thresholds.")
        return []

    def legacy_key(x: Dict[str, Any]) -> Any:
        if sort_criterion == "value":
            return (x["value_ratio"], -x["tier_rank"], x["price"])
        if sort_criterion == "tier":
            return (-x["tier_rank"], x["price"])
        return (x["price"], -x["tier_rank"])

    mode_label = sort_entries("mobo", matched_items, mode_profile, legacy_key)
    active_label = mode_label or sort_criterion.upper()
    print(f"[2/3] Built Mega Table: {len(matched_items)} matching Motherboards ranked by {active_label}.")

    if human_review:
        from extensions.pc.human_review import run_human_validation_review
        run_human_validation_review(
            mobo_list=matched_items,
            budget=float(max_price or 40000.0),
            profile=mode_profile,
        )

    if output_csv:
        export_to_csv(output_csv, matched_items)
        print(f"Exported {len(matched_items)} listings to CSV: {output_csv}")

    if show_mega_table or not use_ai:
        print(f"\nMarket Overview (Top {min(len(matched_items), 30)} candidates — 0 AI tokens):\n")
        render_mobo_table(matched_items, max_rows=30)
        if not use_ai:
            return matched_items

    all_approved, all_rejected = run_laser_audit_loop(
        matched_items, "mobo", client, detector, ai,
        target_approved=target_approved,
        sort_label=(mode_profile.name if mode_profile else sort_criterion),
        max_risk=effective_max_risk,
        re_audit=re_audit,
    )

    sort_entries("mobo", all_approved, mode_profile, legacy_key)
    all_approved = all_approved[:target_approved]
    print(f"Verified {len(all_approved)} top Motherboard recommendations!\n")

    table_items = (all_approved + all_rejected[:12]) if show_rejected else all_approved
    render_mobo_table(table_items)

    if verbose:
        print_verbose_evaluations("mobo", all_approved, all_rejected)
    if output_md:
        write_markdown_report(output_md, all_approved, active_label)
        print(f"Saved report to: {output_md}")
    return all_approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX Motherboard Multi-Mode Valuation & Multi-Provider AI Analyzer")
    parser.add_argument("--query", "-q", type=str, default="", help="Search keyword (e.g. 'b650', 'z790', 'b550')")
    parser.add_argument("--socket", "-s", type=str, default=None, help="Filter by socket (AM5, AM4, LGA1851, LGA1700, LGA1200, LGA1151v2, X99)")
    parser.add_argument("--chipset", type=str, default=None, help="Filter by chipset (e.g. B650, B850, B550, Z790)")
    parser.add_argument("--ddr5", action="store_true", help="Filter strictly to DDR5 boards")
    parser.add_argument("--ddr4", action="store_true", help="Filter strictly to DDR4 boards")
    parser.add_argument("--itx", action="store_true", help="Filter strictly to Mini-ITX")
    parser.add_argument("--matx", action="store_true", help="Filter strictly to Micro-ATX")
    parser.add_argument("--atx", action="store_true", help="Filter strictly to full ATX")
    parser.add_argument("--wifi", action="store_true", help="Filter strictly to Wi-Fi boards")
    parser.add_argument("--standalone", action="store_true", help="Exclude CPU/RAM bundles")
    parser.add_argument("--bundle-only", action="store_true", help="Show only CPU/RAM bundles")
    parser.add_argument("--min-price", type=int, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in UAH")
    parser.add_argument("--sort", "--sort-by", dest="sort", choices=["value", "tier", "price"], default="value", help="Legacy sort criterion")
    parser.add_argument("--target-approved", "-n", type=int, default=8, help="Number of verified boards to return")
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
    ddr_filter = "DDR5" if (args.ddr5 and not args.ddr4) else ("DDR4" if (args.ddr4 and not args.ddr5) else None)
    form_filter = "ITX" if args.itx else ("mATX" if args.matx else ("ATX" if args.atx else None))
    bundle_mode = "standalone" if args.standalone else ("bundle_only" if args.bundle_only else "all")

    run_mobo_analyzer(
        query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        socket_filter=args.socket,
        chipset_filter=args.chipset,
        ddr_filter=ddr_filter,
        form_filter=form_filter,
        wifi_only=args.wifi,
        bundle_mode=bundle_mode,
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
