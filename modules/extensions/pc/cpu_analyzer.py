#!/usr/bin/env python3
"""
CPU Market Intelligence, Multi-Mode Valuation & Multi-Provider AI Audit Engine.
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
from extensions.pc.cpu_ai_inspector import CPUAIInspector
from extensions.pc.cpu_database import identify_cpu
from extensions.pc.cpu_scam_detector import CPUScamDetector
from market_client import MarketClient as OLXClient, check_delivery_refusal
from extensions.pc.modes import resolve_mode


def fmt_fps(val: float) -> str:
    return f"{int(round(val))}fps"


def fmt_val(v: float) -> str:
    return f"{int(v)}" if v == int(v) else f"{v:.1f}"


def render_cpu_table(items: List[Dict[str, Any]], max_rows: Optional[int] = None) -> None:
    cols = [
        ("#", 3, lambda i, c: f"#{i}"),
        ("Model", 18, lambda i, c: make_terminal_link(c["summary"]["url"], f"{c['cpu']['model'][:18]:<18}")),
        ("Threads", 7, lambda i, c: f"{c['threads']}t"),
        ("L3", 5, lambda i, c: f"{c.get('l3_cache_mb', 32)}M"),
        ("Socket", 9, lambda i, c: c["socket"][:9]),
        ("Price", 9, lambda i, c: format_price(c['price'], c.get('currency'))),
        ("Deal", 5, lambda i, c: fmt_deal_pct(c.get("discount_pct", 0.0))),
        ("FPS", 6, lambda i, c: fmt_fps(c["fps_gaming"])),
        ("1%Low", 6, lambda i, c: fmt_fps(c.get("fps_1pct_low", c["fps_gaming"] * 0.73))),
        ("Cost/FPS", 5, lambda i, c: fmt_val(c["uah_per_fps"])),
        ("Status", 20, lambda i, c: get_status_badge(c)),
    ]
    render_box_table(items, cols, max_rows=max_rows)


def export_to_csv(file_path: str, items: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Rank", "Model", "Threads", "L3_Cache_MB", "Socket", "Price",
            "Vs_Market_Pct", "FPS_Gaming", "FPS_1Pct_Low", "CB_R23_Multi", "Cost_Per_FPS", "Risk", "URL",
        ])
        for idx, item in enumerate(items, 1):
            writer.writerow([
                idx,
                item["cpu"]["model"],
                item["threads"],
                item.get("l3_cache_mb", 32),
                item["socket"],
                item["price"],
                item.get("discount_pct", 0.0),
                item["fps_gaming"],
                item.get("fps_1pct_low", 0.0),
                item.get("cb_r23_multi", 0),
                item["uah_per_fps"],
                (item.get("heuristic") or {}).get("risk_score", 0),
                item["summary"]["url"],
            ])


def write_markdown_report(file_path: str, approved: List[Dict[str, Any]], sort_label: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# OLX Processors (Ranked by {sort_label})\n\n")
        f.write("| # | Model | Threads | L3 | Socket | Price | vs Mkt | FPS | 1% Low | Cost/FPS | AI |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for idx, c in enumerate(approved, 1):
            ai_eval = c.get("ai_eval") or {}
            conf_pct = f"{ai_eval.get('confidence_score', 85)}%"
            disc = int(round(c.get("discount_pct", 0.0)))
            disc_str = f"-{disc}%" if disc > 0 else f"+{abs(disc)}%"
            model_md = f"[{c['cpu']['model']}]({c['summary']['url']})"
            low_fps = c.get("fps_1pct_low", c["fps_gaming"] * 0.73)
            p_str = format_price(c["price"], c.get("currency"))
            f.write(
                f"| #{idx} | **{model_md}** | {c['threads']}t | {c.get('l3_cache_mb', 32)}MB | {c['socket']} | "
                f"{p_str} | {disc_str} | {fmt_fps(c['fps_gaming'])} | {fmt_fps(low_fps)} | {fmt_val(c['uah_per_fps'])} | {conf_pct} |\n"
            )


def _normalize_socket_filter(sock: Optional[str]) -> Optional[str]:
    if not sock:
        return None
    s = sock.strip().upper()
    if s in ("X99", "2011-3", "LGA2011-3"):
        return "LGA2011-V3"
    return s


def run_analysis(
    query: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    socket: Optional[str] = None,
    min_threads: Optional[int] = None,
    min_cores: Optional[int] = None,
    min_fps: Optional[float] = None,
    brand: Optional[str] = None,
    only_olx_delivery: bool = True,
    sort_criterion: str = "fps",
    mode: Optional[str] = None,
    weights: Optional[str] = None,
    max_risk: Optional[int] = None,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    re_audit: bool = False,
    max_pages: int = 25,
    target_approved: int = 8,
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
    detector = CPUScamDetector()
    ai = CPUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url) if use_ai else None

    min_p_uah = int(convert_currency(float(min_price), active_curr, "UAH")) if (min_price and canonical_currency(active_curr) != "UAH") else min_price
    max_p_uah = int(convert_currency(float(max_price), active_curr, "UAH")) if (max_price and canonical_currency(active_curr) != "UAH") else max_price

    raw_offers = fetch_category_offers(
        client, "cpu", client.search_cpus,
        query=query, min_price=min_p_uah, max_price=max_p_uah,
        max_pages=max_pages, harvest=harvest, deep=deep, refresh=refresh,
    )

    matched_items: List[Dict[str, Any]] = []
    seen_ids = set()
    q_low = query.lower()
    sock_norm = _normalize_socket_filter(socket)

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

        cpu_info = identify_cpu(title, desc)
        if not cpu_info:
            continue

        if sock_norm and cpu_info.get("socket", "").upper() != sock_norm:
            continue
        if min_threads and cpu_info.get("threads", 0) < min_threads:
            continue
        if min_cores and cpu_info.get("cores", 0) < min_cores:
            continue
        if min_fps and cpu_info.get("fps_gaming", 0) < min_fps:
            continue
        if brand and cpu_info.get("brand", "").lower() != brand.lower():
            continue

        fps_gaming = cpu_info["fps_gaming"]
        entry: Dict[str, Any] = {
            "summary": item,
            "cpu": cpu_info,
            "price": price,
            "currency": active_curr,
            "cores": cpu_info["cores"],
            "threads": cpu_info["threads"],
            "l3_cache_mb": cpu_info.get("l3_cache_mb", 32),
            "socket": cpu_info["socket"],
            "fps_gaming": fps_gaming,
            "fps_1pct_low": cpu_info.get("fps_1pct_low", round(fps_gaming * 0.73, 1)),
            "cb_r23_multi": cpu_info.get("cb_r23_multi", cpu_info["threads"] * 950),
            "uah_per_fps": round(price / fps_gaming, 1) if fps_gaming > 0 else 0.0,
            "fps_per_1k": round((fps_gaming / price) * 1000, 2) if price > 0 else 0.0,
        }
        prepare_entry_metadata("cpu", entry, cpu_info, detector, re_audit=re_audit)
        matched_items.append(entry)

    if not matched_items:
        print("No CPUs matched all requirements. Try widening thresholds.")
        return []

    def legacy_key(x: Dict[str, Any]) -> Any:
        if sort_criterion == "fps":
            return (-x["fps_gaming"], x["price"])
        if sort_criterion == "threads":
            return (-x["threads"], -x["fps_gaming"], x["price"])
        if sort_criterion == "value":
            return (x["uah_per_fps"], -x["fps_gaming"])
        return (x["price"], -x["fps_gaming"])

    mode_label = sort_entries("cpu", matched_items, mode_profile, legacy_key)
    active_label = mode_label or sort_criterion.upper()
    print(f"[2/3] Built Mega Table: {len(matched_items)} matching CPUs ranked by {active_label}.")

    if human_review:
        from extensions.pc.human_review import run_human_validation_review
        run_human_validation_review(
            gpu_list=[],
            cpu_list=matched_items,
            budget=float(max_price or 40000.0),
            profile=mode_profile,
        )

    if output_csv:
        export_to_csv(output_csv, matched_items)
        print(f"Exported {len(matched_items)} listings to CSV: {output_csv}")

    if show_mega_table or not use_ai:
        print(f"\nMarket Overview (Top {min(len(matched_items), 30)} candidates — 0 AI tokens):\n")
        render_cpu_table(matched_items, max_rows=30)
        if not use_ai:
            return matched_items

    all_approved, all_rejected = run_laser_audit_loop(
        matched_items, "cpu", client, detector, ai,
        target_approved=target_approved,
        sort_label=(mode_profile.name if mode_profile else sort_criterion),
        max_risk=effective_max_risk,
        re_audit=re_audit,
    )

    sort_entries("cpu", all_approved, mode_profile, legacy_key)
    all_approved = all_approved[:target_approved]
    print(f"Verified {len(all_approved)} top CPU recommendations!\n")

    table_items = (all_approved + all_rejected[:12]) if show_rejected else all_approved
    render_cpu_table(table_items)

    if verbose:
        print_verbose_evaluations("cpu", all_approved, all_rejected)
    if output_md:
        write_markdown_report(output_md, all_approved, active_label)
        print(f"Saved report to: {output_md}")
    return all_approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX CPU Multi-Mode Valuation & Multi-Provider AI Analyzer")
    parser.add_argument("--harvest", action="store_true", help="Harvest up to 25 pages (~1,000 listings) into local cache")
    parser.add_argument("--deep", "--all-pages", action="store_true", help="Deep multi-window crawl across all price buckets")
    parser.add_argument("--refresh", action="store_true", help="Force fetching fresh listings from OLX")
    parser.add_argument("--query", "-q", type=str, default="", help="Search query (e.g. '7500f', '5700x3d', '9800x3d')")
    parser.add_argument("--min-price", type=int, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in UAH")
    parser.add_argument("--socket", "-s", type=str, default=None, help="Filter by socket (AM5, AM4, LGA1851, LGA1700, LGA1200)")
    parser.add_argument("--min-threads", "--threads", "-t", dest="min_threads", type=int, default=None, help="Minimum CPU threads (e.g. 12, 16, 24, 32)")
    parser.add_argument("--min-cores", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--min-fps", type=float, default=None, help="Minimum gaming FPS index (e.g. 140, 180)")
    parser.add_argument("--brand", choices=["amd", "intel"], default=None, help="Filter by CPU brand")
    parser.add_argument("--allow-no-delivery", action="store_true", help="Include listings without OLX Delivery")
    parser.add_argument("--sort-by", "--sort", dest="sort_by", choices=["fps", "value", "price", "threads"], default="fps", help="Legacy sort criterion")
    parser.add_argument("--pages", type=int, default=25, help="Max OLX pages to fetch")
    parser.add_argument("--target-approved", "-n", type=int, default=8, help="Number of verified CPUs to return")
    parser.add_argument("--mega-table", "--mega", action="store_true", help="Show pre-AI Mega Table")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI inspection")
    parser.add_argument("--show-rejected", action="store_true", help="Display rejected and flagged listings in table")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed AI & heuristic evaluations")
    parser.add_argument("--export-md", type=str, default=None, help="Save Markdown report")
    parser.add_argument("--export-csv", type=str, default=None, help="Export full matched dataset to CSV")
    add_common_mode_and_ai_args(parser)
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    run_analysis(
        query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        socket=args.socket,
        min_threads=args.min_threads,
        min_cores=args.min_cores,
        min_fps=args.min_fps,
        brand=args.brand,
        only_olx_delivery=not args.allow_no_delivery,
        sort_criterion=args.sort_by,
        mode=args.mode,
        weights=args.weights,
        max_risk=args.max_risk,
        ai_provider=args.ai_provider,
        ai_model=args.ai_model,
        ai_base_url=args.ai_base_url,
        re_audit=args.re_audit,
        max_pages=args.pages,
        target_approved=args.target_approved,
        harvest=args.harvest,
        deep=args.deep,
        refresh=args.refresh,
        show_mega_table=args.mega_table,
        show_rejected=args.show_rejected,
        use_ai=not args.no_ai,
        human_review=args.human_review,
        verbose=args.verbose,
        output_md=args.export_md,
        output_csv=args.export_csv,
    )


if __name__ == "__main__":
    main()
