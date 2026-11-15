"""
PC Domain Search Module & Search Instruction.

Acts as the Search Instruction for computer hardware:
Defines how to take any marketplace provider (implementing BaseMarketProvider)
and execute domain-specific searches across PC sections (GPU, CPU, Motherboard, RAM, PSU),
extracting hardware specifications and normalizing candidates for the sorter.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from analyzer_core import fmt_deal_pct, make_terminal_link, pad_ansi
from extensions.pc.modes import compute_market_discount_pct
from currency import format_price, get_active_currency, normalize_listing_price
from extensions.pc.cpu_database import identify_cpu
from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightRegistry
from extensions.base import BaseSearchInstruction
from extensions.pc.gpu_database import identify_gpu
from extensions.pc.mobo_database import identify_motherboard
from provider_template import BaseMarketProvider, ProviderFeatureAdapter, ProviderItem, get_market_provider
from extensions.pc.psu_database import identify_psu
from extensions.pc.ram_database import identify_ram

PC_CRITERIA_DOCS: Dict[str, Dict[str, str]] = {
    "gpu": {
        "vram": "Minimum VRAM in GB (e.g. 8, 12, 16, 24)",
        "vendor": "GPU vendor / architecture (nvidia, amd, intel)",
        "max_tdp": "Maximum power draw in Watts (e.g. 200, 250, 320)",
        "min_fps": "Minimum estimated 1440p gaming FPS",
    },
    "cpu": {
        "socket": "Platform socket (AM4, AM5, LGA1700, LGA1200, LGA1151v2, LGA2011-v3)",
        "threads": "Minimum thread count (e.g. 8, 12, 16, 24, 32)",
        "x3d": "Require AMD 3D V-Cache (yes/true/1)",
        "min_index": "Minimum gaming performance index",
    },
    "mobo": {
        "socket": "Supported socket (AM4, AM5, LGA1700, LGA1200, LGA1151v2)",
        "ddr": "Supported memory generation (DDR4, DDR5)",
        "tier": "Minimum VRM quality tier (S, A, B, C)",
        "chipset": "Specific chipset (e.g. B550, B650, Z690, Z790)",
        "form_factor": "Motherboard size (ATX, Micro-ATX, Mini-ITX)",
    },
    "ram": {
        "ddr": "Memory generation (DDR4, DDR5)",
        "min_gb": "Minimum total kit capacity in GB (16, 32, 64)",
        "modules": "Module count (strictly 2 or 4 sticks)",
        "max_ns": "Maximum true latency in nanoseconds (e.g. 10.0, 11.5)",
    },
    "psu": {
        "watts": "Minimum rated wattage (e.g. 550, 650, 750, 850, 1000)",
        "tier": "Minimum Cultists tier (A, B, C)",
        "gold": "Require 80 Plus Gold/Platinum efficiency (yes/true/1)",
        "form_factor": "Size standard (ATX, SFX, SFX-L)",
    },
}

_IDENTIFIERS: Dict[str, Callable[[str], Optional[Dict[str, Any]]]] = {
    "gpu": identify_gpu,
    "cpu": identify_cpu,
    "mobo": identify_motherboard,
    "ram": identify_ram,
    "psu": identify_psu,
}


def get_pc_criteria(section_id: Optional[str] = None) -> Dict[str, str]:
    """Returns documentation of available search criteria for a PC section."""
    if section_id:
        return dict(PC_CRITERIA_DOCS.get(section_id.lower().strip(), {}))
    res: Dict[str, str] = {}
    for sec, crits in PC_CRITERIA_DOCS.items():
        for k, v in crits.items():
            res[f"{sec}.{k}"] = v
    return res


class PCSearchInstruction(BaseSearchInstruction):
    """
    PC Search Instruction.
    Guides any marketplace provider (BaseMarketProvider) to search and extract
    PC components, mapping them into normalized Candidate dictionaries.
    """

    domain_id = "pc"

    def get_supported_criteria(self, section_id: Optional[str] = None) -> Dict[str, str]:
        return get_pc_criteria(section_id)

    def instruct_search(
        self,
        provider: BaseMarketProvider,
        section_id: str,
        query: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        criteria: Optional[Dict[str, Any]] = None,
        limit: int = 15,
        scorer: Optional[DomainScorer] = None,
        weights_reg: Optional[WeightRegistry] = None,
        mode: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        sec_key = (section_id or "gpu").lower().strip()
        if sec_key not in ("gpu", "cpu", "mobo", "ram", "psu"):
            sec_key = "gpu"

        identifier = _IDENTIFIERS.get(sec_key, identify_gpu)
        crit = criteria or {}

        # 1. Instruct the provider to fetch items using domain category hint.
        # When domain criteria or broad category browsing is requested, fetch all available
        # candidates from the provider so domain specs (socket, threads, tiers) can be evaluated.
        fetch_limit = None if (criteria or not query) else max(100, limit * 4)
        raw_items = provider.search_items(
            query=query or "",
            category_hint=sec_key,
            min_price=min_price,
            max_price=max_price,
            limit=fetch_limit,
        )

        matched: List[Dict[str, Any]] = []
        prov_src = getattr(provider, "source_name", getattr(provider, "name", ""))

        for item in raw_items:
            item_d = ProviderFeatureAdapter.adapt_item(item, prov_src)
            active_curr = get_active_currency()
            normalize_listing_price(item_d, target_currency=active_curr)
            price = float(item_d.get("price", 0.0))
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue

            title = item_d.get("title", "")
            info = identifier(title)
            if not info:
                continue

            model = info.get("model", "")

            # Keyword query check (model & title)
            if query:
                q = query.lower().strip()
                haystack = f"{model} {title}".lower()
                if q not in haystack:
                    continue

            # Criteria matching instructions
            crit_ok = True
            for ck, cv in crit.items():
                ck_norm = ck.lower().strip()
                cv_str = str(cv).strip().lower()

                if ck_norm in ("socket",):
                    cand_sock = str(info.get("socket", "")).lower()
                    if cv_str != cand_sock:
                        crit_ok = False
                        break
                elif ck_norm in ("ddr", "ddr_type"):
                    cand_ddr = str(info.get("ddr_type", "")).lower()
                    if cv_str != cand_ddr:
                        crit_ok = False
                        break
                elif ck_norm in ("threads", "min_threads"):
                    try:
                        cand_th = int(info.get("threads", 0))
                        if cand_th < int(cv):
                            crit_ok = False
                            break
                    except ValueError:
                        pass
                elif ck_norm in ("vram", "min_vram"):
                    try:
                        cand_vram = int(info.get("vram_gb", 0))
                        if cand_vram < int(cv):
                            crit_ok = False
                            break
                    except ValueError:
                        pass
                elif ck_norm in ("watts", "min_watts", "wattage"):
                    try:
                        cand_w = int(info.get("wattage", 0))
                        if cand_w < int(cv):
                            crit_ok = False
                            break
                    except ValueError:
                        pass
                elif ck_norm in ("tier", "vrm_tier", "psu_tier"):
                    cand_t = str(info.get("tier") or info.get("vrm_tier", "")).upper()
                    target_t = cv_str.upper().replace("TIER", "").strip()
                    if target_t and target_t not in cand_t:
                        crit_ok = False
                        break
                elif ck_norm in ("x3d",):
                    cand_x3d = bool(info.get("is_x3d") or "x3d" in model.lower())
                    want_x3d = cv_str in ("yes", "true", "1")
                    if cand_x3d != want_x3d:
                        crit_ok = False
                        break
                elif ck_norm in ("gold",):
                    cand_gold = bool(info.get("is_gold") or "gold" in model.lower() or "gold" in title.lower())
                    want_gold = cv_str in ("yes", "true", "1")
                    if cand_gold != want_gold:
                        crit_ok = False
                        break

            if not crit_ok:
                continue

            # Enrich candidate dictionary
            median_p = float(info.get("median_price", price) or price)
            discount_pct = compute_market_discount_pct(price, info)

            candidate = dict(item_d)
            candidate.update(
                {
                    "section_id": sec_key,
                    "model": model,
                    "spec": info,
                    "specs": info,
                    "median_price": median_p,
                    "discount_pct": discount_pct,
                }
            )

            # Score using domain weights if available
            if scorer and weights_reg:
                prof = weights_reg.resolve_profile(mode or "best")
                cand_score = scorer.score_component(sec_key, candidate, prof)
                candidate["mode_score"] = cand_score
                candidate["search_score"] = cand_score
            else:
                base_score = max(0.0, 100.0 - (price / max(1.0, median_p)) * 30.0)
                candidate["mode_score"] = base_score
                candidate["search_score"] = base_score

            matched.append(candidate)

        # Rank by score descending, then price ascending
        matched.sort(key=lambda x: (-x.get("mode_score", 0.0), x.get("price", 0.0)))
        return matched[:limit]

    def instruct_load_all(
        self,
        provider: Optional[Any] = None,
        budget: Optional[float] = None,
        refresh: bool = False,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if isinstance(provider, BaseMarketProvider):
            prov = provider
        elif isinstance(provider, str):
            prov = get_market_provider(provider, live=refresh)
        else:
            prov = get_market_provider(live=refresh)
        prov_src = getattr(prov, "source_name", getattr(prov, "name", ""))
        pools: Dict[str, List[Dict[str, Any]]] = {}
        skip_cats = set(kwargs.get("skip_categories") or ())

        for cat in ("gpu", "cpu", "mobo", "ram", "psu", "prebuilt"):
            if cat in skip_cats:
                pools[cat] = []
                continue
            if cat == "prebuilt" and not refresh:
                try:
                    results = prov.search_items(category_hint="prebuilt", limit=None)
                    pools["prebuilt"] = [
                        r if (isinstance(r, dict) and "is_secure_deal" in r and "condition" in r)
                        else ProviderFeatureAdapter.adapt_item(r, prov_src)
                        for r in results
                    ]
                except Exception:
                    pools["prebuilt"] = []
                continue
            results = prov.search_items(category_hint=cat, limit=None)
            pools[cat] = [
                r if (isinstance(r, dict) and "is_secure_deal" in r and "condition" in r)
                else ProviderFeatureAdapter.adapt_item(r, prov_src)
                for r in results
            ]

        return pools


pc_search_instruction = PCSearchInstruction()


def search_pc(
    section_id: str,
    query: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    criteria: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
    limit: int = 15,
    scorer: Optional[DomainScorer] = None,
    weights_reg: Optional[WeightRegistry] = None,
    provider: Optional[BaseMarketProvider] = None,
) -> List[Dict[str, Any]]:
    """
    Searches candidates within a PC category matching query and domain criteria,
    ranked by active mode score.
    """
    if isinstance(provider, BaseMarketProvider):
        prov = provider
    elif isinstance(provider, str):
        prov = get_market_provider(provider)
    else:
        prov = get_market_provider()
    return pc_search_instruction.instruct_search(
        provider=prov,
        section_id=section_id,
        query=query,
        min_price=min_price,
        max_price=max_price,
        criteria=criteria,
        limit=limit,
        scorer=scorer,
        weights_reg=weights_reg,
        mode=mode,
    )


def print_pc_search_results(
    results: List[Dict[str, Any]],
    section_id: str,
    layout: DomainLayout,
    mode: Optional[str] = None,
) -> None:
    """Renders PC candidates in a clean aligned table."""
    sec_key = (section_id or "gpu").lower().strip()
    sec = layout.get_section(sec_key)
    sec_label = sec.label if sec else sec_key.upper()
    mode_name = (mode or "best").upper()

    print(f"\nFound {len(results)} {sec_label} candidates (Mode: {mode_name}):\n")
    if not results:
        print(f"  No {sec_label} listings matched your criteria.")
        return

    headers = ["Model", "Price", "Discount", "Key Specs", "Condition", "Secure Deal", "Link"]
    widths = [20, 11, 10, 26, 12, 12, 16]

    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    head = "│ " + " │ ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " │"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    print(top)
    print(head)
    print(mid)

    for cand in results:
        m = cand.get("model", "")[: widths[0]]
        p = format_price(float(cand.get("price", 0.0)), cand.get("currency"))
        disc = fmt_deal_pct(cand.get("discount_pct", 0.0))

        # Format key specs based on section
        info = cand.get("specs") or {}
        if sec_key == "gpu":
            specs_str = f"{info.get('vram_gb', 0)}GB │ ~{info.get('fps_1440p', 0)}fps │ {info.get('tdp', 0)}W"
        elif sec_key == "cpu":
            specs_str = f"{info.get('socket', '')} │ {info.get('threads', 0)}T │ {info.get('l3_cache_mb', 0)}M"
        elif sec_key == "mobo":
            specs_str = f"{info.get('socket', '')} │ {info.get('ddr_type', '')} │ {info.get('vrm_tier', '')}-Tier"
        elif sec_key == "ram":
            specs_str = f"{info.get('capacity_gb', 0)}GB │ {info.get('gen', '')} │ {info.get('latency_ns', 0.0):.1f}ns"
        elif sec_key == "psu":
            specs_str = f"{info.get('wattage', 0)}W │ {info.get('tier', '')}-Tier"
        else:
            specs_str = str(info)[: widths[3]]

        cond_str = str(cand.get("condition_label") or ("New" if cand.get("is_new") else "Used"))[: widths[4]]
        is_sec = bool(cand.get("is_secure_deal", cand.get("has_buyer_protection", False)))
        deliv = "YES" if is_sec else "NO"
        url = cand.get("url", "")
        raw_link = f"id:{cand.get('id', '')}"
        link_str = make_terminal_link(url, raw_link) if url else raw_link

        p_str = pad_ansi(m, widths[0])
        pr_str = pad_ansi(p, widths[1])
        d_str = pad_ansi(disc, widths[2])
        sp_str = pad_ansi(specs_str, widths[3])
        cd_str = pad_ansi(cond_str, widths[4])
        dl_str = pad_ansi(deliv, widths[5])
        lk_str = pad_ansi(link_str, widths[6])

        print(f"│ {p_str} │ {pr_str} │ {d_str} │ {sp_str} │ {cd_str} │ {dl_str} │ {lk_str} │")

    print(bot)
    print()
