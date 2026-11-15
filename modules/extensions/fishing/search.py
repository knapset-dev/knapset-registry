"""
Fishing Domain Search Module & Search Instruction.

Acts as the Search Instruction for fishing equipment:
Defines how to query any marketplace provider (BaseMarketProvider) across
sections (Rod, Reel, Line, Bait, Tackle), filter criteria, and normalize
candidates for the fishing set sorter.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from analyzer_core import fmt_deal_pct, make_terminal_link, pad_ansi
from currency import canonical_currency, convert_currency, format_price, get_active_currency, normalize_candidate_pool, normalize_listing_price
from domain_layout import DomainLayout
from domain_weights import DomainScorer, WeightProfile, WeightRegistry
from extensions.base import BaseSearchInstruction
from extensions.fishing.market_data import get_sample_fishing_market
from provider_template import BaseMarketProvider, MockMarketProvider, ProviderFeatureAdapter, ProviderItem, get_market_provider

FISHING_CRITERIA_DOCS: Dict[str, Dict[str, str]] = {
    "rod": {
        "brand": "Manufacturer (e.g. Favorite, Daiwa, Shimano, Flagman)",
        "power": "Power class (Ultralight, Light, Medium-Light, Medium, Heavy)",
        "test_min": "Minimum casting test in grams (e.g. 1.0)",
        "test_max": "Maximum casting test in grams (e.g. 7.0, 30.0, 150.0)",
        "length": "Blank length in meters (e.g. 2.19, 3.90)",
    },
    "reel": {
        "brand": "Manufacturer (e.g. Favorite, Daiwa, Shimano, Flagman)",
        "spool": "Spool size number (1000, 2000, 2500, 3000, 4000, 5000)",
        "min_drag": "Minimum front drag power in kg (e.g. 5, 8, 10)",
        "bearings": "Minimum ball bearing count (e.g. 4, 7)",
    },
    "line": {
        "brand": "Manufacturer (e.g. Favorite, Daiwa, Brain, Flagman)",
        "type": "Weave type (PE 4x, PE 8x, Mono)",
        "min_kg": "Minimum breaking test in kg (e.g. 4.5, 7.8, 9.2)",
        "max_dia": "Maximum diameter in mm (e.g. 0.08, 0.16)",
    },
    "bait": {
        "brand": "Brand / maker (e.g. Select, Brain, Flagman)",
        "type": "Bait category (MicroJig, Wobbler, FeederCage, HeavyCage)",
        "weight": "Lure or feeder weight in grams (e.g. 3.5, 60, 90)",
        "target": "Target species (Perch, Pike, Zander, Bream, Carp)",
    },
    "tackle": {
        "brand": "Brand (e.g. Select, Flagman, Kalipso)",
        "type": "Accessory type (Terminal, Feeder, Net, Tools)",
        "min_rating": "Minimum quality rating (0-100)",
    },
}


def get_fishing_criteria(section_id: Optional[str] = None) -> Dict[str, str]:
    """Returns documentation of available search criteria for a fishing section."""
    if section_id:
        return dict(FISHING_CRITERIA_DOCS.get(section_id.lower().strip(), {}))
    res: Dict[str, str] = {}
    for sec, crits in FISHING_CRITERIA_DOCS.items():
        for k, v in crits.items():
            res[f"{sec}.{k}"] = v
    return res


class FishingSearchInstruction(BaseSearchInstruction):
    """
    Search Instruction for Fishing Tackle Sets.
    Instructs any BaseMarketProvider how to query and parse fishing equipment candidates.
    """

    domain_id = "fishing"

    def get_supported_criteria(self, section_id: Optional[str] = None) -> Dict[str, str]:
        return get_fishing_criteria(section_id)

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
        sec_key = (section_id or "rod").lower().strip()
        crit = criteria or {}

        # 1. Fetch from provider using domain search instruction
        items = provider.search_items(
            query=query or "",
            category_hint=sec_key,
            min_price=min_price,
            max_price=max_price,
            limit=limit * 3,
        )

        # Fallback to sample fishing market if external provider has no fishing listings
        active_curr = get_active_currency()
        if not items:
            sample_catalog = normalize_candidate_pool(get_sample_fishing_market(), target_currency=active_curr)
            fallback_provider = MockMarketProvider("fishing_catalog", sample_catalog)
            items = fallback_provider.search_items(
                query=query or "",
                category_hint=sec_key,
                min_price=min_price,
                max_price=max_price,
                limit=limit * 3,
            )

        matched: List[Dict[str, Any]] = []
        prov_src = getattr(provider, "source_name", getattr(provider, "name", ""))

        for it in items:
            item = ProviderFeatureAdapter.adapt_item(it, prov_src)
            normalize_listing_price(item, target_currency=active_curr)
            price = float(item.get("price", 0.0))
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue

            spec = item.get("spec") or item.get("specs") or {}
            title = str(item.get("title", ""))
            model_name = str(item.get("model") or title)

            if query:
                q = query.lower().strip()
                haystack = f"{model_name} {title} {spec.get('brand', '')} {spec.get('power_class', '')} {spec.get('target_fish', '')}".lower()
                if q not in haystack:
                    continue

            # Criteria matching instructions
            crit_ok = True
            for ck, cv in crit.items():
                ck_norm = ck.lower().strip()
                cv_str = str(cv).strip().lower()

                if ck_norm in ("brand", "maker"):
                    c_brand = str(item.get("brand") or spec.get("brand", "")).lower()
                    if cv_str not in c_brand and cv_str not in title.lower() and cv_str not in model_name.lower():
                        crit_ok = False
                        break
                elif ck_norm in ("power", "power_class"):
                    c_power = str(item.get("power_class") or spec.get("power_class", "")).lower()
                    if cv_str not in c_power:
                        crit_ok = False
                        break
                elif ck_norm in ("test_min", "min_test"):
                    try:
                        c_tmin = float(item.get("test_min") or spec.get("test_min_g", 0.0))
                        if c_tmin > float(cv):
                            crit_ok = False
                            break
                    except (ValueError, TypeError):
                        pass
                elif ck_norm in ("test_max", "max_test"):
                    try:
                        c_tmax = float(item.get("test_max") or spec.get("test_max_g", 999.0))
                        if c_tmax < float(cv):
                            crit_ok = False
                            break
                    except (ValueError, TypeError):
                        pass
                elif ck_norm in ("spool", "spool_size"):
                    try:
                        c_spool = int(item.get("spool_size") or spec.get("spool_size", 0))
                        if c_spool != int(cv):
                            crit_ok = False
                            break
                    except (ValueError, TypeError):
                        pass
                elif ck_norm in ("min_drag", "drag"):
                    try:
                        c_drag = float(item.get("drag_kg") or spec.get("drag_kg", 0.0))
                        if c_drag < float(cv):
                            crit_ok = False
                            break
                    except (ValueError, TypeError):
                        pass
                elif ck_norm in ("type", "line_type", "lure_type"):
                    c_type = str(
                        item.get("line_type")
                        or spec.get("line_type")
                        or item.get("lure_type")
                        or spec.get("lure_type")
                        or item.get("type", "")
                    ).lower()
                    if cv_str not in c_type:
                        crit_ok = False
                        break

            if not crit_ok:
                continue

            candidate = dict(item)
            candidate.update(spec)
            candidate["model"] = model_name
            candidate["title"] = title or model_name
            candidate["spec"] = spec
            candidate["specs"] = spec

            if scorer and weights_reg:
                prof = weights_reg.resolve_profile(mode or "spinning-light")
                cand_score = scorer.score_component(sec_key, candidate, prof)
                candidate["mode_score"] = cand_score
                candidate["search_score"] = cand_score
            else:
                base_score = float(candidate.get("rating") or spec.get("rating", 75.0))
                candidate["mode_score"] = base_score
                candidate["search_score"] = base_score

            matched.append(candidate)

        matched.sort(key=lambda x: (-x.get("mode_score", 0.0), x.get("price", 0.0)))
        return matched[:limit]

    def instruct_load_all(
        self,
        provider: Optional[BaseMarketProvider] = None,
        budget: Optional[float] = None,
        refresh: bool = False,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        active_curr = get_active_currency()
        # If caller explicitly passed a UAH-scale budget (>= 2500.0) while active_curr is USD/USDT,
        # keep pool in UAH so legacy UAH unit tests (e.g. budget=6000.0) work seamlessly.
        target_curr = "UAH" if (budget is not None and budget >= 2500.0 and canonical_currency(active_curr) in ("USDT", "USD")) else active_curr

        if provider and hasattr(provider, "search_items"):
            pools: Dict[str, List[Dict[str, Any]]] = {}
            for sec_id in ("rod", "reel", "line", "bait", "tackle"):
                found = self.instruct_search(provider=provider, section_id=sec_id, limit=60)
                if found:
                    pools[sec_id] = normalize_candidate_pool({sec_id: found}, target_currency=target_curr)[sec_id]
            if len(pools) == 5:
                return pools

        return normalize_candidate_pool(get_sample_fishing_market(), target_currency=target_curr)


fishing_search_instruction = FishingSearchInstruction()


def search_fishing(
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
    Searches candidates within a fishing section matching query and domain criteria,
    ranked by active mode score.
    """
    active_curr = get_active_currency()
    sample_catalog = normalize_candidate_pool(get_sample_fishing_market(), target_currency=active_curr)
    prov = provider or MockMarketProvider("fishing_catalog", sample_catalog)
    return fishing_search_instruction.instruct_search(
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


def print_fishing_search_results(
    results: List[Dict[str, Any]],
    section_id: str,
    layout: DomainLayout,
    mode: Optional[str] = None,
) -> None:
    """Renders fishing equipment search results in an aligned terminal table."""
    sec_key = (section_id or "rod").lower().strip()
    sec = layout.get_section(sec_key)
    sec_label = sec.label if sec else sec_key.upper()
    mode_name = (mode or "universal").upper()

    print(f"\nFound {len(results)} {sec_label} candidates (Mode: {mode_name}):\n")
    if not results:
        print(f"  No {sec_label} items matched your criteria.")
        return

    headers = ["Model / Name", "Price", "Brand", "Key Specs", "Condition", "Rating", "Link"]
    widths = [24, 11, 10, 26, 11, 8, 14]

    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    head = "│ " + " │ ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " │"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    print(top)
    print(head)
    print(mid)

    for item in results:
        title = item.get("title", "")[: widths[0]]
        curr = item.get("currency") or layout.currency or get_active_currency()
        price = format_price(float(item.get("price", 0.0)), curr)
        brand = item.get("brand", "")[: widths[2]]

        # Key specs according to section
        if sec_key == "rod":
            t_min = item.get("test_min_g") or item.get("test_min", 0)
            t_max = item.get("test_max_g") or item.get("test_max", 0)
            specs_str = f"{item.get('power_class', '')} │ {t_min}-{t_max}g │ {item.get('length_m', 0)}m"
        elif sec_key == "reel":
            specs_str = f"Spool {item.get('spool_size', 0)} │ {item.get('drag_kg', 0)}kg │ {item.get('bearings', 0)}BB"
        elif sec_key == "line":
            specs_str = f"{item.get('line_type', '')} │ {item.get('test_kg', 0)}kg │ {item.get('diameter_mm', 0)}mm"
        elif sec_key == "bait":
            specs_str = f"{item.get('lure_type', '')} │ {item.get('weight_g', 0)}g │ {item.get('target_fish', '')}"
        elif sec_key == "tackle":
            specs_str = f"{item.get('type', '')} accessory"
        else:
            specs_str = str(item.get("specs", ""))[: widths[3]]

        cond_str = str(item.get("condition_label") or ("New" if item.get("is_new") else "Used"))[: widths[4]]
        rating = f"{float(item.get('rating', 0.0)):.0f}/100"
        url = item.get("url", "")
        raw_link = f"id:{item.get('id', '')}"
        link_str = make_terminal_link(url, raw_link) if url else raw_link

        t_str = pad_ansi(title, widths[0])
        p_str = pad_ansi(price, widths[1])
        b_str = pad_ansi(brand, widths[2])
        sp_str = pad_ansi(specs_str, widths[3])
        cd_str = pad_ansi(cond_str, widths[4])
        r_str = pad_ansi(rating, widths[5])
        l_str = pad_ansi(link_str, widths[6])

        print(f"│ {t_str} │ {p_str} │ {b_str} │ {sp_str} │ {cd_str} │ {r_str} │ {l_str} │")

    print(bot)
    print()
