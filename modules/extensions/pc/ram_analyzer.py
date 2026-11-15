#!/usr/bin/env python3
"""
RAM Market Intelligence, Multi-Mode Valuation & Multi-Provider AI Audit Engine.
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
from extensions.pc.modes import resolve_mode
from extensions.pc.ram_ai_inspector import RAMAIInspector
from extensions.pc.ram_database import identify_ram
from extensions.pc.ram_scam_detector import RAMScamDetector


def fmt_val(v: float) -> str:
    return f"{int(v)}" if v == int(v) else f"{v:.1f}"


def render_ram_table(items: List[Dict[str, Any]], max_rows: Optional[int] = None) -> None:
    cols = [
        ("#", 3, lambda i, c: f"#{i}"),
        ("Model", 18, lambda i, c: make_terminal_link(c["summary"]["url"], f"{c['ram']['model'][:18]:<18}")),
        ("Type", 4, lambda i, c: c["ram"]["generation"]),
        ("Config", 7, lambda i, c: c["ram"]["config"][:7]),
        ("Speed", 8, lambda i, c: f"{c['speed_mhz']}MHz"),
        ("Lat", 6, lambda i, c: f"CL{c['ram']['cas_latency']}"),
        ("Price", 8, lambda i, c: format_price(c['price'], c.get('currency'))),
        ("Cost/GB", 5, lambda i, c: fmt_val(c["uah_per_gb"])),
        ("Deal", 5, lambda i, c: fmt_deal_pct(c.get("discount_pct", 0.0))),
        ("Status", 20, lambda i, c: get_status_badge(c)),
    ]
    render_box_table(items, cols, max_rows=max_rows)


def export_to_csv(file_path: str, items: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Model", "DDR", "FormFactor", "Config", "Total_GB", "Speed_MHz", "CAS", "Latency_ns", "Price", "Cost_Per_GB", "Vs_Market_Pct", "Risk", "URL"])
        for idx, c in enumerate(items, 1):
            r = c["ram"]
            writer.writerow([
                idx, r["model"], r["generation"], r["form_factor"], r["config"], r["total_gb"],
                r["speed_mhz"], r["cas_latency"], r["latency_ns"], c["price"], c["uah_per_gb"],
                c.get("discount_pct", 0.0), (c.get("heuristic") or {}).get("risk_score", 0), c["summary"]["url"],
            ])


def write_markdown_report(file_path: str, approved: List[Dict[str, Any]], sort_label: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# OLX RAM Modules & Kits (Ranked by {sort_label})\n\n")
        f.write("| # | Model | Type | Config | Speed | CL | Price | Cost/GB | vs Mkt | AI |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for idx, c in enumerate(approved, 1):
            ai_eval = c.get("ai_eval") or {}
            conf_pct = f"{ai_eval.get('confidence_score', 85)}%"
            disc = int(round(c.get("discount_pct", 0.0)))
            disc_str = f"-{disc}%" if disc > 0 else f"+{abs(disc)}%"
            r = c["ram"]
            p_str = format_price(c["price"], c.get("currency"))
            f.write(
                f"| #{idx} | [{r['model']}]({c['summary']['url']}) | {r['generation']} | {r['config']} | "
                f"{r['speed_mhz']}MHz | CL{r['cas_latency']} | {p_str} | {fmt_val(c['uah_per_gb'])} | {disc_str} | {conf_pct} |\n"
            )


def run_ram_analyzer(
    query: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_gb: Optional[int] = None,
    max_gb: Optional[int] = None,
    min_speed: Optional[int] = None,
    ddr_filter: Optional[str] = None,
    form_factor_filter: str = "UDIMM",
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
    detector = RAMScamDetector()
    ai = RAMAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url) if use_ai else None

    min_p_uah = int(convert_currency(float(min_price), active_curr, "UAH")) if (min_price and canonical_currency(active_curr) != "UAH") else min_price
    max_p_uah = int(convert_currency(float(max_price), active_curr, "UAH")) if (max_price and canonical_currency(active_curr) != "UAH") else max_price

    raw_offers = fetch_category_offers(
        client, "ram", client.search_rams,
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
        if raw_uah_price <= 100:
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

        ram_info = identify_ram(title, desc)
        if not ram_info:
            continue

        if ddr_filter and ram_info["generation"] != ddr_filter:
            continue
        if form_factor_filter != "ALL" and ram_info["form_factor"] != form_factor_filter:
            continue

        total_gb = ram_info["total_gb"]
        if min_gb and total_gb < min_gb:
            continue
        if max_gb and total_gb > max_gb:
            continue
        if min_speed and ram_info["speed_mhz"] < min_speed:
            continue

        entry: Dict[str, Any] = {
            "summary": item,
            "ram": ram_info,
            "price": price,
            "currency": active_curr,
            "uah_per_gb": round(price / total_gb, 1),
            "speed_mhz": ram_info["speed_mhz"],
            "total_gb": total_gb,
            "latency_ns": ram_info["latency_ns"],
        }
        prepare_entry_metadata("ram", entry, ram_info, detector, re_audit=re_audit)
        matched_items.append(entry)

    if not matched_items:
        print("No RAM kits matched all requirements. Try widening thresholds or passing --all-forms.")
        return []

    def legacy_key(x: Dict[str, Any]) -> Any:
        if sort_criterion == "value":
            return (x["uah_per_gb"], -x["speed_mhz"])
        if sort_criterion == "speed":
            return (-x["speed_mhz"], x["uah_per_gb"])
        if sort_criterion == "latency":
            return (x["latency_ns"], x["uah_per_gb"])
        if sort_criterion == "capacity":
            return (-x["total_gb"], x["uah_per_gb"])
        return (x["price"], -x["total_gb"])

    mode_label = sort_entries("ram", matched_items, mode_profile, legacy_key)
    active_label = mode_label or sort_criterion.upper()
    print(f"[2/3] Built Mega Table: {len(matched_items)} matching RAM kits ranked by {active_label}.")

    if human_review:
        from extensions.pc.human_review import run_human_validation_review
        run_human_validation_review(
            ram_list=matched_items,
            budget=float(max_price or 40000.0),
            profile=mode_profile,
        )

    if output_csv:
        export_to_csv(output_csv, matched_items)
        print(f"Exported {len(matched_items)} listings to CSV: {output_csv}")

    if show_mega_table or not use_ai:
        print(f"\nMarket Overview (Top {min(len(matched_items), 30)} candidates — 0 AI tokens):\n")
        render_ram_table(matched_items, max_rows=30)
        if not use_ai:
            return matched_items

    all_approved, all_rejected = run_laser_audit_loop(
        matched_items, "ram", client, detector, ai,
        target_approved=target_approved,
        sort_label=(mode_profile.name if mode_profile else sort_criterion),
        max_risk=effective_max_risk,
        re_audit=re_audit,
    )

    sort_entries("ram", all_approved, mode_profile, legacy_key)
    all_approved = all_approved[:target_approved]
    print(f"Verified {len(all_approved)} top RAM recommendations!\n")

    table_items = (all_approved + all_rejected[:12]) if show_rejected else all_approved
    render_ram_table(table_items)

    if verbose:
        print_verbose_evaluations("ram", all_approved, all_rejected)
    if output_md:
        write_markdown_report(output_md, all_approved, active_label)
        print(f"Saved report to: {output_md}")
    return all_approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX RAM Multi-Mode Valuation & Multi-Provider AI Analyzer")
    parser.add_argument("--query", "-q", type=str, default="", help="Search keyword (e.g. 'fury', '32gb', '6000')")
    parser.add_argument("--ddr4", action="store_true", help="Filter strictly to DDR4 memory")
    parser.add_argument("--ddr5", action="store_true", help="Filter strictly to DDR5 memory")
    parser.add_argument("--min-gb", type=int, default=None, help="Minimum total capacity in GB (e.g. 16, 32)")
    parser.add_argument("--max-gb", type=int, default=None, help="Maximum total capacity in GB")
    parser.add_argument("--min-speed", type=int, default=None, help="Minimum frequency in MHz (e.g. 3200, 6000)")
    parser.add_argument("--min-price", type=int, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in UAH")
    parser.add_argument("--all-forms", action="store_true", help="Include all form factors (UDIMM, SODIMM, ECC)")
    parser.add_argument("--laptop", "--sodimm", action="store_true", help="Filter strictly to Laptop SODIMM")
    parser.add_argument("--server", "--ecc", action="store_true", help="Filter strictly to Server ECC REG")
    parser.add_argument("--sort", "--sort-by", "-s", dest="sort", choices=["value", "speed", "latency", "price", "capacity"], default="value", help="Legacy sort criterion")
    parser.add_argument("--target-approved", "-n", type=int, default=8, help="Number of verified kits to return")
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
    ddr_filter = "DDR4" if (args.ddr4 and not args.ddr5) else ("DDR5" if (args.ddr5 and not args.ddr4) else None)
    form_filter = "ALL" if args.all_forms else ("SODIMM" if args.laptop else ("ECC_REG" if args.server else "UDIMM"))

    run_ram_analyzer(
        query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        min_gb=args.min_gb,
        max_gb=args.max_gb,
        min_speed=args.min_speed,
        ddr_filter=ddr_filter,
        form_factor_filter=form_filter,
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
