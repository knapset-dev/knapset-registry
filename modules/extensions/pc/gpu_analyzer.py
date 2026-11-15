#!/usr/bin/env python3
"""
GPU Market Intelligence, Multi-Mode Valuation & Multi-Provider AI Audit Engine.
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
from extensions.pc.gpu_ai_inspector import GPUAIInspector as AIInspector
from extensions.pc.gpu_database import identify_gpu
from extensions.pc.gpu_scam_detector import GPUScamDetector as ScamDetector
from market_client import MarketClient as OLXClient, check_delivery_refusal
from extensions.pc.modes import resolve_mode


def fmt_fps(val: float) -> str:
    return f"{int(round(val))}fps"


def fmt_val(v: float) -> str:
    return f"{int(v)}" if v == int(v) else f"{v:.1f}"


def render_gpu_table(items: List[Dict[str, Any]], max_rows: Optional[int] = None) -> None:
    cols = [
        ("#", 3, lambda i, c: f"#{i}"),
        ("Model", 16, lambda i, c: make_terminal_link(c["summary"]["url"], f"{c['gpu']['model'][:16]:<16}")),
        ("VRAM", 4, lambda i, c: f"{c['vram_gb']}G"),
        ("Price", 9, lambda i, c: format_price(c['price'], c.get('currency'))),
        ("Deal", 5, lambda i, c: fmt_deal_pct(c.get("discount_pct", 0.0))),
        ("1440p", 6, lambda i, c: fmt_fps(c["fps_1440p"])),
        ("1080p", 6, lambda i, c: fmt_fps(c["fps_1080p"])),
        ("Cost/FPS", 6, lambda i, c: fmt_val(c["uah_per_fps"])),
        ("Status", 20, lambda i, c: get_status_badge(c)),
    ]
    render_box_table(items, cols, max_rows=max_rows)


def export_to_csv(file_path: str, items: List[Dict[str, Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Model", "VRAM_GB", "Price", "Vs_Market_Pct", "FPS_1440p", "FPS_1080p", "Cost_Per_FPS", "Risk", "URL"])
        for idx, item in enumerate(items, 1):
            writer.writerow([
                idx,
                item["gpu"]["model"],
                item["vram_gb"],
                item["price"],
                item.get("discount_pct", 0.0),
                item["fps_1440p"],
                item["fps_1080p"],
                item["uah_per_fps"],
                (item.get("heuristic") or {}).get("risk_score", 0),
                item["summary"]["url"],
            ])


def write_markdown_report(file_path: str, approved: List[Dict[str, Any]], sort_label: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# OLX GPUs (Ranked by {sort_label})\n\n")
        f.write("| # | Model | VRAM | Price | vs Mkt | 1440p | 1080p | Cost/FPS | AI |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for idx, c in enumerate(approved, 1):
            ai_eval = c.get("ai_eval") or {}
            conf_pct = f"{ai_eval.get('confidence_score', 85)}%"
            disc = int(round(c.get("discount_pct", 0.0)))
            disc_str = f"-{disc}%" if disc > 0 else f"+{abs(disc)}%"
            model_md = f"[{c['gpu']['model']}]({c['summary']['url']})"
            p_str = format_price(c["price"], c.get("currency"))
            f.write(
                f"| #{idx} | **{model_md}** | {c['vram_gb']}GB | {p_str} | {disc_str} | "
                f"{fmt_fps(c['fps_1440p'])} | {fmt_fps(c['fps_1080p'])} | {fmt_val(c['uah_per_fps'])} | {conf_pct} |\n"
            )


def run_analysis(
    query: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_vram: Optional[int] = None,
    min_fps_1440p: Optional[float] = None,
    min_fps_1080p: Optional[float] = None,
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
    detector = ScamDetector()
    ai = AIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url) if use_ai else None

    min_p_uah = int(convert_currency(float(min_price), active_curr, "UAH")) if (min_price and canonical_currency(active_curr) != "UAH") else min_price
    max_p_uah = int(convert_currency(float(max_price), active_curr, "UAH")) if (max_price and canonical_currency(active_curr) != "UAH") else max_price

    raw_offers = fetch_category_offers(
        client, "gpu", client.search_gpus,
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
        if raw_uah_price <= 250:
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

        gpu_info = identify_gpu(title, desc)
        if not gpu_info:
            continue

        if min_vram and gpu_info.get("vram_gb", 0) < min_vram:
            continue
        if min_fps_1440p and gpu_info.get("fps_1440p", 0) < min_fps_1440p:
            continue
        if min_fps_1080p and gpu_info.get("fps_1080p", 0) < min_fps_1080p:
            continue
        if brand and gpu_info.get("brand", "").lower() != brand.lower():
            continue

        fps_1440p = gpu_info["fps_1440p"]
        fps_1080p = gpu_info["fps_1080p"]
        vram_gb = gpu_info["vram_gb"]
        uah_per_fps = round(price / fps_1440p, 1) if fps_1440p > 0 else 0.0

        entry: Dict[str, Any] = {
            "summary": item,
            "gpu": gpu_info,
            "price": price,
            "currency": active_curr,
            "vram_gb": vram_gb,
            "fps_1440p": fps_1440p,
            "fps_1080p": fps_1080p,
            "uah_per_fps": uah_per_fps,
            "fps_per_1k": round((fps_1440p / price) * 1000, 2) if price > 0 else 0.0,
        }
        prepare_entry_metadata("gpu", entry, gpu_info, detector, re_audit=re_audit)
        matched_items.append(entry)

    if not matched_items:
        print("No GPUs matched all requirements. Try widening thresholds.")
        return []

    def legacy_key(x: Dict[str, Any]) -> Any:
        if sort_criterion == "fps":
            return (-x["fps_1440p"], x["price"])
        if sort_criterion == "value":
            return (x["uah_per_fps"], -x["fps_1440p"])
        return (x["price"], -x["fps_1440p"])

    mode_label = sort_entries("gpu", matched_items, mode_profile, legacy_key)
    active_label = mode_label or sort_criterion.upper()
    print(f"[2/3] Built Mega Table: {len(matched_items)} matching GPUs ranked by {active_label}.")

    if human_review:
        from extensions.pc.human_review import run_human_validation_review
        run_human_validation_review(
            gpu_list=matched_items,
            cpu_list=[],
            budget=float(max_price or 40000.0),
            profile=mode_profile,
        )

    if output_csv:
        export_to_csv(output_csv, matched_items)
        print(f"Exported {len(matched_items)} listings to CSV: {output_csv}")

    if show_mega_table or not use_ai:
        print(f"\nMarket Overview (Top {min(len(matched_items), 30)} candidates — 0 AI tokens):\n")
        render_gpu_table(matched_items, max_rows=30)
        if not use_ai:
            return matched_items

    all_approved, all_rejected = run_laser_audit_loop(
        matched_items, "gpu", client, detector, ai,
        target_approved=target_approved,
        sort_label=(mode_profile.name if mode_profile else sort_criterion),
        max_risk=effective_max_risk,
        re_audit=re_audit,
    )

    sort_entries("gpu", all_approved, mode_profile, legacy_key)
    all_approved = all_approved[:target_approved]
    print(f"Verified {len(all_approved)} top GPU recommendations!\n")

    table_items = (all_approved + all_rejected[:12]) if show_rejected else all_approved
    render_gpu_table(table_items)

    if verbose:
        print_verbose_evaluations("gpu", all_approved, all_rejected)
    if output_md:
        write_markdown_report(output_md, all_approved, active_label)
        print(f"Saved report to: {output_md}")
    return all_approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX GPU Multi-Mode Valuation & Multi-Provider AI Analyzer")
    parser.add_argument("--harvest", action="store_true", help="Harvest up to 25 pages (~1,000 listings) into local cache")
    parser.add_argument("--deep", "--all-pages", action="store_true", help="Deep multi-window crawl across all price buckets")
    parser.add_argument("--refresh", action="store_true", help="Force fetching fresh listings from OLX")
    parser.add_argument("--query", "-q", type=str, default="", help="Search query (e.g. 'rtx', '4070', '9070', 'b580')")
    parser.add_argument("--min-price", type=int, default=None, help="Minimum price in UAH")
    parser.add_argument("--max-price", type=int, default=None, help="Maximum price in UAH")
    parser.add_argument("--min-vram", type=int, default=None, help="Minimum VRAM in GB (e.g. 8, 12, 16)")
    parser.add_argument("--min-fps", type=float, default=None, help="Minimum average 1440p gaming FPS")
    parser.add_argument("--min-fps-1080p", type=float, default=None, help="Minimum average 1080p gaming FPS")
    parser.add_argument("--brand", choices=["nvidia", "amd", "intel"], default=None, help="Filter by GPU brand")
    parser.add_argument("--allow-no-delivery", action="store_true", help="Include listings without OLX Delivery")
    parser.add_argument("--sort-by", "--sort", dest="sort_by", choices=["fps", "value", "price"], default="fps", help="Legacy sort criterion (when --mode is omitted)")
    parser.add_argument("--pages", type=int, default=25, help="Max OLX pages to fetch")
    parser.add_argument("--target-approved", "-n", type=int, default=8, help="Number of verified GPUs to return")
    parser.add_argument("--mega-table", "--mega", action="store_true", help="Show pre-AI Mega Table")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI inspection (instant deterministic table)")
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
        min_vram=args.min_vram,
        min_fps_1440p=args.min_fps,
        min_fps_1080p=args.min_fps_1080p,
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
