"""
Human Validation Review Engine for Hardware Market Intelligence.

Surfaces the most advantageous GPU proposals and approximately processed CPU + Platform/Memory
proposals for interactive manual verification prior to final PC build synthesis.
"""

import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from audit_ledger import AuditLedger, ledger as default_ledger
from currency import canonical_currency, convert_currency, format_price, get_active_currency
from extensions.pc.mobo_database import CHIPSET_SPECS
from extensions.pc.ram_database import RAM_MARKET_BENCHMARKS
from scam_utils import extract_snippet, strip_html_fast


# Realistic default motherboard and memory cost baseline by CPU socket,
# aligned directly with CHIPSET_SPECS (mobo_database.py) and RAM_MARKET_BENCHMARKS (ram_database.py)
PLATFORM_DEFAULTS = {
    "AM5": {
        "mobo_name": "A620 / B650",
        "mobo_price": 3200.0,
        "ram_desc": "32GB (2x16GB) DDR5 6000MHz",
        "ram_price": 9800.0,
        "gen": "DDR5",
    },
    "AM4": {
        "mobo_name": "B450 / A520",
        "mobo_price": 2000.0,
        "ram_desc": "16GB (2x8GB) DDR4 3200MHz",
        "ram_price": 1400.0,
        "gen": "DDR4",
    },
    "LGA1851": {
        "mobo_name": "H810 / B860",
        "mobo_price": 5200.0,
        "ram_desc": "32GB (2x16GB) DDR5 6000MHz",
        "ram_price": 9800.0,
        "gen": "DDR5",
    },
    "LGA1700": {
        "mobo_name": "H610 / B660",
        "mobo_price": 2400.0,
        "ram_desc": "16GB (2x8GB) DDR4 3200MHz",
        "ram_price": 1400.0,
        "gen": "DDR4",
    },
    "LGA1200": {
        "mobo_name": "H410 / B460",
        "mobo_price": 1900.0,
        "ram_desc": "16GB (2x8GB) DDR4 3200MHz",
        "ram_price": 1300.0,
        "gen": "DDR4",
    },
    "LGA1151v2": {
        "mobo_name": "H310 / B365",
        "mobo_price": 1600.0,
        "ram_desc": "16GB (2x8GB) DDR4 2666MHz",
        "ram_price": 1200.0,
        "gen": "DDR4",
    },
    "LGA1151": {
        "mobo_name": "H110 / B250",
        "mobo_price": 1300.0,
        "ram_desc": "16GB (2x8GB) DDR4 2400MHz",
        "ram_price": 1200.0,
        "gen": "DDR4",
    },
    "LGA2011-v3": {
        "mobo_name": "X99",
        "mobo_price": 2000.0,
        "ram_desc": "16GB-32GB DDR4",
        "ram_price": 1400.0,
        "gen": "DDR4",
    },
}


def _record_human_verdict(
    led: AuditLedger,
    item: Dict[str, Any],
    category: str,
    verdict: str,
    reason: str,
) -> Optional[Dict[str, Any]]:
    """Persists human validation review verdict to the main AuditLedger and updates candidate."""
    item_id = str(item.get("id", ""))
    if not item_id:
        return None
    summary = item.get("summary") or {}
    raw_desc = (
        summary.get("description")
        or (summary.get("raw") or {}).get("description", "")
        or item.get("description", "")
        or (item.get("raw") or {}).get("description", "")
    )
    price = float(item.get("price", 0.0))
    has_deliv = bool(
        summary.get("is_secure_deal")
        if "is_secure_deal" in summary
        else summary.get("has_buyer_protection")
        if "has_buyer_protection" in summary
        else summary.get("has_olx_delivery")
        if "has_olx_delivery" in summary
        else item.get("is_secure_deal")
        if "is_secure_deal" in item
        else item.get("has_buyer_protection")
        if "has_buyer_protection" in item
        else item.get("has_olx_delivery", item.get("has_delivery", True))
    )
    title = summary.get("title", item.get("model", ""))
    url = item.get("url") or summary.get("url", "")
    led.record_audit(
        item_id,
        category=category,
        verdict=verdict,
        confidence_score=100,
        reasons=[reason],
        title=title,
        price=price,
        description=raw_desc,
        url=url,
        provider="human",
        model="manual-validation",
        has_delivery=has_deliv,
    )
    rec = led.get_audit(item_id) or {}
    item.setdefault("eval", {})["audit"] = rec
    item["eval"]["is_ai_approved"] = (verdict == "APPROVED")
    item["eval"]["is_ai_rejected"] = (verdict == "REJECTED")
    item["ai_eval"] = rec
    return rec


def _item_currency(item: Optional[Dict[str, Any]], pool: Optional[List[Dict[str, Any]]] = None, budget: Optional[float] = None) -> str:
    """Determines the currency of a candidate item or pool, defaulting to UAH for raw UAH inputs."""
    if item:
        c = item.get("currency") or (item.get("summary") or {}).get("currency")
        if c:
            return canonical_currency(c)
    if pool:
        for it in pool:
            c = it.get("currency") or (it.get("summary") or {}).get("currency")
            if c:
                return canonical_currency(c)
    if budget and budget >= 5000.0:
        return "UAH"
    return "UAH"


def _to_uah(amount: float, curr: str) -> float:
    if amount <= 0 or canonical_currency(curr) == "UAH":
        return float(amount)
    return convert_currency(amount, from_currency=curr, to_currency="UAH")


def _from_uah(amount_uah: float, curr: str) -> float:
    if amount_uah <= 0 or canonical_currency(curr) == "UAH":
        return float(amount_uah)
    return convert_currency(amount_uah, from_currency="UAH", to_currency=curr)


def estimate_cpu_platform_cost(
    cpu_cand: Dict[str, Any],
    mobo_pool: Optional[List[Dict[str, Any]]] = None,
    ram_pool: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Computes realistic platform and memory cost for a CPU candidate based on
    CHIPSET_SPECS and RAM_MARKET_BENCHMARKS tables.
    Uses clean candidate pool medians when available, falling back to calibrated platform defaults.
    """
    curr = _item_currency(cpu_cand, mobo_pool or ram_pool)
    socket = str(cpu_cand.get("socket", "AM4")).upper()
    c_spec = cpu_cand.get("spec", cpu_cand)
    cpu_price = float(cpu_cand.get("price", 0.0))
    fps_gaming = float(cpu_cand.get("fps_gaming", c_spec.get("fps_gaming", 100.0)))
    is_x3d = bool(c_spec.get("is_x3d") or "X3D" in cpu_cand.get("model", "").upper())
    cpu_low = float(c_spec.get("fps_1pct_low", fps_gaming * (0.775 if is_x3d else 0.73)))

    def_plat = PLATFORM_DEFAULTS.get(
        socket,
        {
            "mobo_name": f"{socket} Motherboard",
            "mobo_price": 2000.0,
            "ram_desc": "16GB DDR4",
            "ram_price": 1350.0,
            "gen": "DDR4",
        },
    )

    mobo_price = _from_uah(def_plat["mobo_price"], curr)
    mobo_name = def_plat["mobo_name"]
    min_mobo_p = _from_uah(700.0, curr)

    if mobo_pool:
        matching_mobos = [
            m for m in mobo_pool
            if m.get("socket", "").upper() == socket
            and not (m.get("eval", {}).get("is_ai_rejected") or m.get("eval", {}).get("red_flags"))
            and float(m.get("price", 0)) >= min_mobo_p
        ]
        if matching_mobos:
            matching_mobos.sort(key=lambda m: float(m.get("price", 0)))
            cap_price = _from_uah(def_plat["mobo_price"] * 1.25, curr)
            budget_mobos = [m for m in matching_mobos if float(m.get("price", 0)) <= cap_price]
            if budget_mobos:
                idx = min(len(budget_mobos) - 1, max(0, min(1, len(budget_mobos) // 3)))
                chosen_m = budget_mobos[idx]
                mobo_price = float(chosen_m.get("price", mobo_price))
                mobo_name = chosen_m.get("model", mobo_name)

    ram_gen = def_plat["gen"]
    ram_price = _from_uah(def_plat["ram_price"], curr)
    ram_desc = def_plat["ram_desc"]
    min_ram_p = _from_uah(600.0, curr)

    if ram_pool:
        target_caps = {16, 32} if ram_gen == "DDR5" else {16}
        matching_rams = [
            r for r in ram_pool
            if r.get("gen") == ram_gen
            and r.get("spec", {}).get("form_factor", "UDIMM") in ("UDIMM", "UNKNOWN", "ECC_UDIMM")
            and r.get("spec", {}).get("module_count", 2) >= 2
            and not (r.get("eval", {}).get("is_ai_rejected") or r.get("eval", {}).get("red_flags"))
            and float(r.get("price", 0)) >= min_ram_p
        ]
        cap_matched = [r for r in matching_rams if r.get("total_gb") in target_caps]
        pool_to_use = cap_matched or matching_rams
        if pool_to_use:
            pool_to_use.sort(key=lambda r: float(r.get("price", 0)))
            cap_price = _from_uah(def_plat["ram_price"] * 1.25, curr)
            budget_rams = [r for r in pool_to_use if float(r.get("price", 0)) <= cap_price]
            if budget_rams:
                idx = min(len(budget_rams) - 1, max(0, min(1, len(budget_rams) // 3)))
                chosen_r = budget_rams[idx]
                ram_price = float(chosen_r.get("price", ram_price))
                ram_desc = f"{chosen_r.get('total_gb', 16)}GB (2x) {ram_gen}"

    platform_cost = round(mobo_price + ram_price, 0 if curr == "UAH" else 2)
    total_platform_cost = round(cpu_price + platform_cost, 0 if curr == "UAH" else 2)
    total_platform_cost_uah = _to_uah(total_platform_cost, curr)

    # Effective CPU index taking into account 1% low & 3D V-Cache
    effective_cpu_floor = fps_gaming * 0.60 + (cpu_low * 1.35) * 0.40
    platform_uah_per_fps = round(total_platform_cost / max(1.0, fps_gaming), 1)
    platform_value_index = round((effective_cpu_floor / max(1.0, total_platform_cost_uah)) * 1000.0, 2)

    return {
        "socket": socket,
        "mobo_name": mobo_name,
        "mobo_price": mobo_price,
        "ram_desc": ram_desc,
        "ram_price": ram_price,
        "platform_cost": platform_cost,
        "total_platform_cost": total_platform_cost,
        "effective_cpu_floor": effective_cpu_floor,
        "platform_uah_per_fps": platform_uah_per_fps,
        "platform_value_index": platform_value_index,
        "is_x3d": is_x3d,
    }


# Default targets for component pools in human validation review
DEFAULT_CATEGORY_TARGETS: Dict[str, int] = {
    "gpu": 7,
    "cpu": 7,
    "mobo": 7,
    "ram": 5,
    "psu": 5,
}


def _resolve_category_target(
    cat_name: str,
    target_approved: Optional[Union[int, Dict[str, int]]] = None,
    max_candidates: Optional[int] = None,
) -> int:
    if isinstance(target_approved, dict):
        return target_approved.get(cat_name, DEFAULT_CATEGORY_TARGETS.get(cat_name, 5))
    if isinstance(target_approved, int):
        return target_approved
    if max_candidates is not None:
        return max_candidates
    return DEFAULT_CATEGORY_TARGETS.get(cat_name, 5)


def select_top_gpu_deals(
    gpu_list: List[Dict[str, Any]],
    budget: Optional[float] = None,
    profile: Optional[Any] = None,
    limit: int = 7,
) -> List[Dict[str, Any]]:
    """Ranks and surfaces the most advantageous GPU proposals matching the build tier."""
    curr = _item_currency(None, gpu_list, budget)
    budget_uah = _to_uah(budget, curr) if budget else None

    def _evaluate_candidates(apply_tier_filters: bool) -> List[Tuple[float, Dict[str, Any]]]:
        cands = []
        min_fps = 0.0
        if apply_tier_filters and budget_uah:
            if budget_uah >= 38000:
                min_fps = 55.0
            elif budget_uah >= 26000:
                min_fps = 40.0

        for g in gpu_list:
            ev = g.get("eval") or g.get("heuristic") or {}
            if ev.get("is_ai_rejected") or ev.get("red_flags"):
                continue
            price = float(g.get("price", 0.0))
            if price <= 0:
                continue
            price_uah = _to_uah(price, curr)

            spec = g.get("spec") or g.get("gpu") or {}
            arch_risk = spec.get("risk_level", "LOW")
            risk_notes = spec.get("risk_notes", "").lower()
            is_legacy = (arch_risk == "CRITICAL") or ("mesh shaders" in risk_notes or "legacy" in risk_notes)
            fps1440 = float(g.get("fps_1440p", spec.get("fps_1440p", 40.0)))

            if apply_tier_filters and budget_uah and budget_uah >= 28000 and is_legacy:
                continue
            if min_fps > 0.0 and fps1440 < min_fps:
                continue

            discount = float(g.get("discount_pct", 0.0))
            vram = float(g.get("vram_gb", spec.get("vram_gb", 8.0)))
            uah_per_fps = price_uah / max(1.0, fps1440)

            score = (
                (discount * 0.55)
                + ((160.0 / max(50.0, uah_per_fps)) * 35.0)
                + (min(24.0, vram) / 16.0 * 15.0)
            )

            if profile is not None:
                try:
                    from extensions.pc.modes import score_component
                    prof_score = score_component("gpu", g, profile)
                    score = (score * 0.45) + (prof_score * 0.55)
                except Exception:
                    pass

            if budget and budget > 0:
                gpu_share = price / budget
                if 0.30 <= gpu_share <= 0.65:
                    score += 10.0
                elif gpu_share < 0.20:
                    score -= (0.20 - gpu_share) * 50.0

            cands.append((score, g))
        return cands

    candidates = _evaluate_candidates(apply_tier_filters=True)
    if not candidates and gpu_list:
        candidates = _evaluate_candidates(apply_tier_filters=False)

    candidates.sort(key=lambda x: x[0], reverse=True)

    selected = []
    seen_models = set()
    for _, g in candidates:
        model = g.get("model", "")
        if model in seen_models:
            continue
        seen_models.add(model)
        selected.append(g)
        if len(selected) >= limit:
            break

    return selected


def select_top_cpu_platform_deals(
    cpu_list: List[Dict[str, Any]],
    mobo_list: Optional[List[Dict[str, Any]]] = None,
    ram_list: Optional[List[Dict[str, Any]]] = None,
    budget: Optional[float] = None,
    profile: Optional[Any] = None,
    limit: int = 7,
) -> List[Dict[str, Any]]:
    """Ranks and surfaces the most advantageous CPU proposals with platform/memory costs factored in."""
    curr = _item_currency(None, cpu_list, budget)
    budget_uah = _to_uah(budget, curr) if budget else None

    def _evaluate_candidates(apply_tier_filters: bool) -> List[Tuple[float, Dict[str, Any], Dict[str, Any]]]:
        cands = []
        for c in cpu_list:
            ev = c.get("eval") or c.get("heuristic") or {}
            if ev.get("is_ai_rejected") or ev.get("red_flags"):
                continue
            price = float(c.get("price", 0.0))
            if price <= 0:
                continue

            plat = estimate_cpu_platform_cost(c, mobo_pool=mobo_list, ram_pool=ram_list)
            discount = float(c.get("discount_pct", 0.0))
            is_x3d = plat["is_x3d"]
            sock = plat.get("socket", "")

            if apply_tier_filters and budget and budget_uah:
                if budget_uah >= 32000 and sock in ("LGA1151", "LGA1151v2", "LGA1150", "LGA1200", "LGA2011-v3"):
                    continue
                if plat["total_platform_cost"] > budget * 0.70:
                    continue

            score = (
                (plat["platform_value_index"] * 0.50)
                + (discount * 0.30)
                + (4.0 if is_x3d else 0.0)
                + ((plat["effective_cpu_floor"] / 200.0) * 15.0)
            )

            if profile is not None:
                try:
                    from extensions.pc.modes import score_component
                    prof_score = score_component("cpu", c, profile)
                    score = (score * 0.50) + (prof_score * 0.50)
                except Exception:
                    pass

            cands.append((score, c, plat))
        return cands

    candidates = _evaluate_candidates(apply_tier_filters=True)
    if not candidates and cpu_list:
        candidates = _evaluate_candidates(apply_tier_filters=False)

    candidates.sort(key=lambda x: x[0], reverse=True)

    selected = []
    seen_models = set()
    for _, c, plat in candidates:
        model = c.get("model", "")
        if model in seen_models:
            continue
        seen_models.add(model)
        c_copy = dict(c)
        c_copy["platform_eval"] = plat
        selected.append(c_copy)
        if len(selected) >= limit:
            break

    return selected


def _format_snippet(text: str, max_chars: int = 240) -> str:
    clean = strip_html_fast(text or "")
    snip = extract_snippet(clean)
    lines = [ln.strip() for ln in snip.split("\n") if ln.strip()]
    merged = " ".join(lines)
    if len(merged) > max_chars:
        return merged[: max_chars - 3] + "..."
    return merged


def select_top_mobo_deals(
    mobo_list: List[Dict[str, Any]],
    target_sockets: Optional[set] = None,
    budget: Optional[float] = None,
    profile: Optional[Any] = None,
    limit: int = 7,
) -> List[Dict[str, Any]]:
    """Ranks and surfaces top motherboard proposals matching target sockets."""
    curr = _item_currency(None, mobo_list, budget)
    budget_uah = _to_uah(budget, curr) if budget else None
    cands = []
    for m in mobo_list:
        ev = m.get("eval") or m.get("heuristic") or {}
        if ev.get("is_ai_rejected") or ev.get("red_flags"):
            continue
        price = float(m.get("price", 0.0))
        if price <= 0:
            continue
        sock = str(m.get("socket", "")).upper()
        if target_sockets and sock not in target_sockets:
            continue

        if budget and budget > 0:
            max_mobo_price = max(_from_uah(2400.0, curr), budget * 0.35)
            if price > max_mobo_price:
                continue

        discount = float(m.get("discount_pct", 0.0))
        spec = m.get("spec") or m.get("mobo") or {}
        vrm_tier = spec.get("vrm_tier", m.get("vrm_tier", "B-Tier"))
        vrm_bonus = {"S-Tier": 18.0, "A-Tier": 12.0, "B-Tier": 6.0, "C-Tier": 0.0}.get(vrm_tier, 0.0)

        is_ddr5_budget = bool(budget_uah and budget_uah >= 28000)
        ddr_bonus = 10.0 if (m.get("ddr_type") == "DDR5" and is_ddr5_budget) else (6.0 if m.get("ddr_type") == "DDR4" else 0.0)
        cost_ratio = price / max(1.0, budget or _from_uah(35000.0, curr))

        score = (discount * 0.35) + vrm_bonus + ddr_bonus - (cost_ratio * 15.0)
        if profile is not None:
            try:
                from extensions.pc.modes import score_component
                prof_score = score_component("mobo", m, profile)
                score = (score * 0.40) + (prof_score * 0.60)
            except Exception:
                pass
        cands.append((score, m))

    cands.sort(key=lambda x: x[0], reverse=True)
    selected = []
    seen_models = set()
    for _, m in cands:
        model = m.get("model", "")
        if model in seen_models:
            continue
        seen_models.add(model)
        selected.append(m)
        if len(selected) >= limit:
            break
    return selected


def select_top_ram_deals(
    ram_list: List[Dict[str, Any]],
    target_gens: Optional[set] = None,
    budget: Optional[float] = None,
    profile: Optional[Any] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Ranks and surfaces top dual-channel RAM kit proposals."""
    curr = _item_currency(None, ram_list, budget)
    cands = []
    for r in ram_list:
        ev = r.get("eval") or r.get("heuristic") or {}
        if ev.get("is_ai_rejected") or ev.get("red_flags"):
            continue
        price = float(r.get("price", 0.0))
        if price <= 0:
            continue
        gen = str(r.get("gen", "")).upper()
        if target_gens and gen not in target_gens:
            continue

        if budget and budget > 0:
            max_ram_price = max(_from_uah(2000.0, curr), budget * 0.25)
            if price > max_ram_price:
                continue

        discount = float(r.get("discount_pct", 0.0))
        gb = float(r.get("total_gb", 16))
        mhz = float(r.get("speed_mhz", 3200))
        spec = r.get("spec") or r.get("ram") or {}
        lat_ns = max(7.0, float(spec.get("latency_ns", r.get("latency_ns", 10.0))))

        score = (discount * 0.35) + min(20.0, (gb / 32.0) * 15.0) + min(15.0, (mhz / 6000.0) * 10.0) + ((10.0 / lat_ns) * 10.0)
        if profile is not None:
            try:
                from extensions.pc.modes import score_component
                prof_score = score_component("ram", r, profile)
                score = (score * 0.40) + (prof_score * 0.60)
            except Exception:
                pass
        cands.append((score, r))

    cands.sort(key=lambda x: x[0], reverse=True)
    selected = []
    seen_models = set()
    for _, r in cands:
        model = r.get("model", "")
        if model in seen_models:
            continue
        seen_models.add(model)
        selected.append(r)
        if len(selected) >= limit:
            break
    return selected


def select_top_psu_deals(
    psu_list: List[Dict[str, Any]],
    min_watts: int = 650,
    budget: Optional[float] = None,
    profile: Optional[Any] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Ranks and surfaces top power supply proposals."""
    curr = _item_currency(None, psu_list, budget)
    cands = []
    for p in psu_list:
        ev = p.get("eval") or p.get("heuristic") or {}
        if ev.get("is_ai_rejected") or ev.get("red_flags"):
            continue
        price = float(p.get("price", 0.0))
        if price <= 0:
            continue
        watts = float(p.get("wattage", 0))
        if watts < min_watts:
            continue

        if budget and budget > 0:
            max_psu_price = max(_from_uah(1800.0, curr), budget * 0.20)
            if price > max_psu_price:
                continue

        discount = float(p.get("discount_pct", 0.0))
        tier = p.get("tier", "Tier C")
        tier_score = {"Tier A": 20.0, "Tier B": 12.0, "Tier C": 5.0}.get(tier, 0.0)

        score = (discount * 0.35) + tier_score + min(15.0, (watts / 850.0) * 10.0)
        if profile is not None:
            try:
                from extensions.pc.modes import score_component
                prof_score = score_component("psu", p, profile)
                score = (score * 0.40) + (prof_score * 0.60)
            except Exception:
                pass
        cands.append((score, p))

    cands.sort(key=lambda x: x[0], reverse=True)
    selected = []
    seen_models = set()
    for _, p in cands:
        model = p.get("model", "")
        if model in seen_models:
            continue
        seen_models.add(model)
        selected.append(p)
        if len(selected) >= limit:
            break
    return selected


class HumanReviewResult:
    """Encapsulates the result of human validation review with backward-compatible 4-item tuple unpacking."""

    def __init__(
        self,
        locked_gpu: Optional[Dict[str, Any]] = None,
        locked_cpu: Optional[Dict[str, Any]] = None,
        final_gpus: Optional[List[Dict[str, Any]]] = None,
        final_cpus: Optional[List[Dict[str, Any]]] = None,
        locked_mobo: Optional[Dict[str, Any]] = None,
        locked_ram: Optional[Dict[str, Any]] = None,
        locked_psu: Optional[Dict[str, Any]] = None,
        final_mobos: Optional[List[Dict[str, Any]]] = None,
        final_rams: Optional[List[Dict[str, Any]]] = None,
        final_psus: Optional[List[Dict[str, Any]]] = None,
        approved_by_cat: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ):
        self.locked_gpu = locked_gpu
        self.locked_cpu = locked_cpu
        self.locked_mobo = locked_mobo
        self.locked_ram = locked_ram
        self.locked_psu = locked_psu
        self.final_gpus = final_gpus or []
        self.final_cpus = final_cpus or []
        self.final_mobos = final_mobos or []
        self.final_rams = final_rams or []
        self.final_psus = final_psus or []
        self.approved_by_cat = approved_by_cat or {}

    def __iter__(self):
        # 100% backward compatible: `locked_g, locked_c, fg, fc = run_human_validation_review(...)`
        return iter((self.locked_gpu, self.locked_cpu, self.final_gpus, self.final_cpus))

    def __getitem__(self, index):
        t = (
            self.locked_gpu, self.locked_cpu, self.final_gpus, self.final_cpus,
            self.final_mobos, self.final_rams, self.final_psus
        )
        return t[index]

    def __len__(self):
        return 4


def _get_ledger_record(led: AuditLedger, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetches cached audit record with content-hash verification, falling back to ID lookup."""
    item_id = str(item.get("id", ""))
    if not item_id:
        return None
    summary = item.get("summary") or {}
    title = summary.get("title", item.get("model", ""))
    price = float(item.get("price", 0.0))
    desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    has_deliv = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    rec = led.get_audit(item_id, title=title, price=price, description=desc, has_delivery=has_deliv)
    if rec is None:
        rec = led.get_audit(item_id)
    return rec


def _is_item_approved(led: AuditLedger, item: Dict[str, Any], human_only: bool = True) -> bool:
    """Checks whether this specific candidate was verified and approved in AuditLedger."""
    rec = _get_ledger_record(led, item)
    if not rec or rec.get("verdict") != "APPROVED":
        return False
    if human_only:
        return rec.get("provider") == "human"
    return True


def _is_item_rejected(led: AuditLedger, item: Dict[str, Any]) -> bool:
    """Checks whether this specific candidate was blacklisted/rejected in AuditLedger."""
    rec = _get_ledger_record(led, item)
    return bool(rec and rec.get("verdict") == "REJECTED")


def _print_gpu_proposal(idx: int, total: int, g: Dict[str, Any]) -> None:
    price = float(g.get("price", 0.0))
    disc = float(g.get("discount_pct", 0.0))
    disc_str = f"({disc:+.0f}% vs median)" if disc != 0 else ""
    summary = g.get("summary") or {}
    seller = summary.get("seller_name", "Unknown")
    is_sec = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    has_deliv = "YES" if is_sec else "NO"
    url = g.get("url") or summary.get("url", "")
    raw_desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    snip = _format_snippet(raw_desc)
    ev = g.get("eval") or {}
    risk = ev.get("risk_score", 0)
    warns = ev.get("warnings") or []
    warn_str = f" │ Warnings: {', '.join(warns[:1])}" if warns else ""

    print("─" * 78)
    print(f"[GPU {idx}/{total}] {g.get('model')}  │  {format_price(price)} {disc_str}")
    print(f"  • Title  : {summary.get('title', g.get('model'))[:64]}")
    if url:
        print(f"  • Link   : {url}")
    print(f"  • Specs  : {g.get('fps_1440p', 0):.0f} FPS (1440p) / {g.get('fps_1080p', 0):.0f} FPS (1080p) │ {g.get('vram_gb', 0)}GB VRAM")
    print(f"  • Seller : {seller} │ Secure Deal: {has_deliv} │ Risk: {risk}/100{warn_str}")
    if snip:
        print(f"  • Notes  : \"{snip}\"")


def _print_cpu_proposal(idx: int, total: int, c: Dict[str, Any], mobo_list: Optional[List[Dict[str, Any]]] = None, ram_list: Optional[List[Dict[str, Any]]] = None) -> None:
    price = float(c.get("price", 0.0))
    disc = float(c.get("discount_pct", 0.0))
    disc_str = f"({disc:+.0f}% vs median)" if disc != 0 else ""
    summary = c.get("summary") or {}
    seller = summary.get("seller_name", "Unknown")
    is_sec = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    has_deliv = "YES" if is_sec else "NO"
    url = c.get("url") or summary.get("url", "")
    raw_desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    snip = _format_snippet(raw_desc)
    plat = c.get("platform_eval") or estimate_cpu_platform_cost(c, mobo_pool=mobo_list, ram_pool=ram_list)

    c_spec = c.get("spec", c)
    l3 = c.get("l3_cache_mb", c_spec.get("l3_cache_mb", 32))
    x3d_tag = " (3D V-Cache)" if plat.get("is_x3d") else ""

    print("─" * 78)
    print(f"[CPU {idx}/{total}] {c.get('model')} ({plat['socket']})  │  {format_price(price)} {disc_str}")
    print(f"  • Title   : {summary.get('title', c.get('model'))[:64]}")
    if url:
        print(f"  • Link    : {url}")
    print(f"  • Specs   : {c.get('fps_gaming', 0):.0f} FPS index (1% Low: {c.get('fps_1pct_low', 0):.0f}) │ {l3}MB L3{x3d_tag}")
    print(f"  • Seller  : {seller} │ Secure Deal: {has_deliv}")
    print("  ┌─ Approximate Platform Investment ───────────────────────────────────────┐")
    print(f"  │  Mobo {plat['socket']:<8}: ~{format_price(plat['mobo_price'])} ({plat['mobo_name'][:36]})")
    print(f"  │  RAM        : ~{format_price(plat['ram_price'])} ({plat['ram_desc'][:36]})")
    print(f"  │  Platform Cost  : ~{format_price(plat['platform_cost'])} (Mobo + RAM)")
    print(f"  │  TOTAL PLATFORM : ~{format_price(plat['total_platform_cost'])} (CPU + Mobo + RAM) │ {plat['platform_uah_per_fps']:.1f} Cost/FPS")
    print("  └─────────────────────────────────────────────────────────────────────────┘")
    if snip:
        print(f"  • Notes   : \"{snip}\"")


def _print_mobo_proposal(idx: int, total: int, m: Dict[str, Any]) -> None:
    price = float(m.get("price", 0.0))
    disc = float(m.get("discount_pct", 0.0))
    disc_str = f"({disc:+.0f}% vs median)" if disc != 0 else ""
    summary = m.get("summary") or {}
    seller = summary.get("seller_name", "Unknown")
    is_sec = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    has_deliv = "YES" if is_sec else "NO"
    url = m.get("url") or summary.get("url", "")
    raw_desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    snip = _format_snippet(raw_desc)
    spec = m.get("spec") or m.get("mobo") or {}
    vrm = spec.get("vrm_tier", m.get("vrm_tier", "B-Tier"))
    sock = m.get("socket", spec.get("socket", "AM5"))
    ddr = m.get("ddr_type", spec.get("ddr_type", "DDR5"))
    ff = spec.get("form_factor", m.get("form_factor", "ATX"))
    ev = m.get("eval") or {}
    risk = ev.get("risk_score", 0)

    print("─" * 78)
    print(f"[MOBO {idx}/{total}] {m.get('model')}  │  {format_price(price)} {disc_str}")
    print(f"  • Title  : {summary.get('title', m.get('model'))[:64]}")
    if url:
        print(f"  • Link   : {url}")
    print(f"  • Specs  : {sock} │ {ddr} │ VRM: {vrm} │ Form Factor: {ff}")
    print(f"  • Seller : {seller} │ Secure Deal: {has_deliv} │ Risk: {risk}/100")
    if snip:
        print(f"  • Notes  : \"{snip}\"")


def _print_ram_proposal(idx: int, total: int, r: Dict[str, Any]) -> None:
    price = float(r.get("price", 0.0))
    disc = float(r.get("discount_pct", 0.0))
    disc_str = f"({disc:+.0f}% vs median)" if disc != 0 else ""
    summary = r.get("summary") or {}
    seller = summary.get("seller_name", "Unknown")
    is_sec = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    has_deliv = "YES" if is_sec else "NO"
    url = r.get("url") or summary.get("url", "")
    raw_desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    snip = _format_snippet(raw_desc)
    spec = r.get("spec") or r.get("ram") or {}
    gb = r.get("total_gb", spec.get("total_gb", 32))
    gen = r.get("gen", spec.get("gen", "DDR5"))
    mhz = r.get("speed_mhz", spec.get("speed_mhz", 6000))
    mods = r.get("module_count", spec.get("module_count", 2))
    lat_ns = r.get("latency_ns", spec.get("latency_ns", 10.0))
    cas = spec.get("cas_latency", "")
    cas_str = f"CL{cas} " if cas else ""
    ev = r.get("eval") or {}
    risk = ev.get("risk_score", 0)

    print("─" * 78)
    print(f"[RAM {idx}/{total}] {r.get('model')}  │  {format_price(price)} {disc_str}")
    print(f"  • Title  : {summary.get('title', r.get('model'))[:64]}")
    if url:
        print(f"  • Link   : {url}")
    print(f"  • Specs  : {gb}GB ({mods}x sticks) {gen}-{mhz} {cas_str}│ {lat_ns:.1f}ns True Latency")
    print(f"  • Seller : {seller} │ Secure Deal: {has_deliv} │ Risk: {risk}/100")
    if snip:
        print(f"  • Notes  : \"{snip}\"")


def _print_psu_proposal(idx: int, total: int, p: Dict[str, Any]) -> None:
    price = float(p.get("price", 0.0))
    disc = float(p.get("discount_pct", 0.0))
    disc_str = f"({disc:+.0f}% vs median)" if disc != 0 else ""
    summary = p.get("summary") or {}
    seller = summary.get("seller_name", "Unknown")
    is_sec = summary.get("is_secure_deal", summary.get("has_buyer_protection", summary.get("has_olx_delivery", True)))
    has_deliv = "YES" if is_sec else "NO"
    url = p.get("url") or summary.get("url", "")
    raw_desc = summary.get("description") or (summary.get("raw") or {}).get("description", "")
    snip = _format_snippet(raw_desc)
    spec = p.get("spec") or p.get("psu") or {}
    watts = p.get("wattage", spec.get("wattage", 750))
    tier = p.get("tier", spec.get("vrm_tier", "Tier B"))
    eff = p.get("efficiency", spec.get("efficiency", "Gold"))
    ev = p.get("eval") or {}
    risk = ev.get("risk_score", 0)

    print("─" * 78)
    print(f"[PSU {idx}/{total}] {p.get('model')}  │  {format_price(price)} {disc_str}")
    print(f"  • Title  : {summary.get('title', p.get('model'))[:64]}")
    if url:
        print(f"  • Link   : {url}")
    print(f"  • Specs  : {watts}W │ Cultists {tier} │ {eff} Efficiency")
    print(f"  • Seller : {seller} │ Secure Deal: {has_deliv} │ Risk: {risk}/100")
    if snip:
        print(f"  • Notes  : \"{snip}\"")


def _is_category_satisfied(
    pre_approved: List[Dict[str, Any]],
    ranked_cands: List[Dict[str, Any]],
    effective_target: int,
    led: AuditLedger,
    human_only: bool = True,
) -> bool:
    """
    Determines whether a category has sufficient pre-approved proposals
    in AuditLedger to bypass manual interactive review.
    """
    if not ranked_cands:
        return True
    if not pre_approved:
        return False

    # 1. Full target quota satisfied
    if len(pre_approved) >= effective_target and effective_target > 0:
        return True

    # 2. All available unrejected candidates are already validated
    unreviewed = [c for c in ranked_cands if not _is_item_approved(led, c, human_only=human_only)]
    if not unreviewed:
        return True

    # 3. User previously human-validated this category and approved alternatives
    # (at least 3 components for pool <= 5, or 4 for pool >= 7) -> avoids premature bypass
    min_approved = min(effective_target, 3 if effective_target <= 5 else 4)
    if human_only:
        human_approved = [
            c for c in pre_approved
            if (_get_ledger_record(led, c) or {}).get("provider") == "human"
        ]
        if len(human_approved) >= min_approved:
            return True
    else:
        # In non-human-only mode (e.g. AI prescreen), any high-confidence approvals (human, AI, script) suffice
        if len(pre_approved) >= min_approved:
            return True

    return False


def _get_category_inspector(
    cat_name: str,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    no_ai: bool = False,
    ai_prescreen: bool = False,
) -> Optional[Any]:
    """Instantiates the specialized hardware AI inspector for this category if AI pre-screening is active."""
    if no_ai or not ai_prescreen:
        return None
    try:
        from extensions.pc.system_ai_inspector import is_any_ai_provider_ready
        if not (ai_provider or is_any_ai_provider_ready()):
            return None
        if cat_name == "gpu":
            from extensions.pc.gpu_ai_inspector import GPUAIInspector
            return GPUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url)
        elif cat_name == "cpu":
            from extensions.pc.cpu_ai_inspector import CPUAIInspector
            return CPUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url)
        elif cat_name == "mobo":
            from extensions.pc.mobo_ai_inspector import MotherboardAIInspector
            return MotherboardAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url)
        elif cat_name == "ram":
            from extensions.pc.ram_ai_inspector import RAMAIInspector
            return RAMAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url)
        elif cat_name == "psu":
            from extensions.pc.psu_ai_inspector import PSUAIInspector
            return PSUAIInspector(provider=ai_provider, model=ai_model, base_url=ai_base_url)
    except Exception:
        return None
    return None


def pre_screen_proposals_with_ai(
    cat_name: str,
    cat_label: str,
    candidates: List[Dict[str, Any]],
    needed_count: int,
    inspector: Any,
    mode_name: str = "best",
    re_audit: bool = False,
    led: Optional[AuditLedger] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Pre-screens unreviewed candidate listings through category AI inspector in batches.
    Disqualifies broken/defective/scam listings, persisting verdicts to AuditLedger,
    and returns (clean_candidates, rejected_candidates) so the human only validates genuine offers.
    """
    if not inspector or not candidates:
        return list(candidates), []

    clean_candidates: List[Dict[str, Any]] = []
    rejected_candidates: List[Dict[str, Any]] = []
    batch_size = 5
    idx = 0

    print(f"AI Pre-screen ({inspector.provider_label}): Checking {cat_label} descriptions for defects & scams...")

    while idx < len(candidates) and len(clean_candidates) < needed_count:
        chunk = candidates[idx : idx + batch_size]
        idx += batch_size

        try:
            res = inspector.inspect_and_rank_batch(chunk, sort_by=mode_name, re_audit=re_audit)
            app = res.get("approved", [])
            rej = res.get("rejected", [])
            clean_candidates.extend(app)
            rejected_candidates.extend(rej)
        except Exception as e:
            clean_candidates.extend(chunk)
            break

    if rejected_candidates:
        summary_reasons = []
        for r in rejected_candidates:
            model = r.get("model") or (r.get("summary") or {}).get("title", "Item")[:24]
            reasons = (r.get("ai_eval") or {}).get("reasons") or ["Flagged by AI"]
            summary_reasons.append(f"{model} ({reasons[0]})")
        print(f"   AI filtered out {len(rejected_candidates)} defective/risky listing(s) before review:")
        for sr in summary_reasons[:4]:
            print(f"      • {sr}")
        if len(summary_reasons) > 4:
            print(f"      • ...and {len(summary_reasons) - 4} more")

    return clean_candidates, rejected_candidates


def _review_category(
    cat_name: str,
    cat_label: str,
    cat_icon: str,
    pool: List[Dict[str, Any]],
    ranked_cands: List[Dict[str, Any]],
    pre_approved: List[Dict[str, Any]],
    effective_target: int,
    is_interactive: bool,
    input_func: Optional[Callable[[str], str]],
    led: AuditLedger,
    printer: Callable[[int, int, Dict[str, Any]], None],
    max_candidates: int = 5,
    strict_max: bool = False,
    ai_inspector: Optional[Any] = None,
    mode_name: str = "best",
    re_audit: bool = False,
    force_review: bool = False,
    human_only: bool = True,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes validation review for a single component category.
    Returns (locked_item, approved_items, filtered_pool).
    """
    filtered_pool = list(pool)
    locked_item: Optional[Dict[str, Any]] = None

    # If already satisfied by pre-approved items in AuditLedger, bypass interactive review!
    if not force_review and not re_audit and _is_category_satisfied(pre_approved, ranked_cands, effective_target, led, human_only=human_only):
        approved_items = list(pre_approved[:effective_target])
        print(f"\n{cat_label.upper()}: {len(approved_items)} top candidate(s) already validated in AuditLedger — bypassing review.")
        final_pool = approved_items
        return locked_item, approved_items, final_pool

    approved_items = [] if (force_review or re_audit) else list(pre_approved[:effective_target])
    unreviewed = [c for c in ranked_cands if not _is_item_approved(led, c, human_only=human_only) and not _is_item_rejected(led, c)]

    if not unreviewed:
        final_pool = approved_items if approved_items else filtered_pool
        return locked_item, approved_items, final_pool

    # Determine candidates to surface
    needed = max(1, effective_target - len(approved_items))
    target_clean = max_candidates if strict_max else max(needed * 3, max_candidates * 2)

    if ai_inspector and unreviewed:
        clean_cands, rejected_cands = pre_screen_proposals_with_ai(
            cat_name=cat_name,
            cat_label=cat_label,
            candidates=unreviewed,
            needed_count=target_clean,
            inspector=ai_inspector,
            mode_name=mode_name,
            re_audit=re_audit,
            led=led,
        )
        if rejected_cands:
            rej_ids = {str(r.get("id")) for r in rejected_cands if r.get("id")}
            filtered_pool = [x for x in filtered_pool if str(x.get("id")) not in rej_ids]
        candidates_to_surface = clean_cands[:target_clean]
    else:
        candidates_to_surface = unreviewed[:target_clean]

    if not candidates_to_surface:
        final_pool = approved_items if approved_items else filtered_pool
        return locked_item, approved_items, final_pool

    surfaced_display_count = min(len(candidates_to_surface), max_candidates if strict_max else effective_target)
    if approved_items:
        print(f"\nTOP {cat_label.upper()} PROPOSALS ({len(approved_items)} already approved from previous validations, {effective_target - len(approved_items)} needed):")
    else:
        print(f"\nTOP {cat_label.upper()} PROPOSALS ({surfaced_display_count} surfaced):")

    approve_all = False
    surfaced_count = 0

    for idx, item in enumerate(candidates_to_surface, 1):
        if len(approved_items) >= effective_target and effective_target > 0:
            break
        if strict_max and surfaced_count >= max_candidates:
            break

        surfaced_count += 1
        printer(surfaced_count, surfaced_display_count, item)

        if not is_interactive:
            approved_items.append(item)
            _record_human_verdict(
                led, item, cat_name, "APPROVED", "Auto-approved via non-interactive validation review"
            )
            continue

        if approve_all:
            break

        prompt_msg = "  [y] Approve / [l] Lock for build / [n] Reject & blacklist / [s] Skip / [a] All / [d] Done: "
        while True:
            try:
                raw_in = input_func(prompt_msg) if input_func else input(prompt_msg)
                choice = (raw_in or "y").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "a"
                print("\n  [Review interrupted — auto-approving remaining active deals]")

            if choice in ("y", "yes", ""):
                approved_items.append(item)
                _record_human_verdict(
                    led, item, cat_name, "APPROVED", "Human validated & approved via interactive market review"
                )
                print(f"  Approved & saved to AuditLedger ({len(approved_items)}/{effective_target} ready)")
                break
            elif choice in ("l", "lock"):
                locked_item = item
                approved_items.append(item)
                _record_human_verdict(
                    led, item, cat_name, "APPROVED", "Human validated & locked for PC build synthesis"
                )
                print(f"  Locked {cat_label} for build synthesis: {item.get('model')} ({format_price(float(item.get('price', 0)))})")
                break
            elif choice in ("n", "no", "reject"):
                filtered_pool = [x for x in filtered_pool if x.get("id") != item.get("id")]
                _record_human_verdict(
                    led, item, cat_name, "REJECTED", "Rejected by user during human validation review"
                )
                print(f"  Disqualified & blacklisted in AuditLedger: {item.get('model')}")
                break
            elif choice in ("s", "skip"):
                print("  Skipped")
                break
            elif choice in ("a", "all"):
                approve_all = True
                approved_items.append(item)
                _record_human_verdict(
                    led, item, cat_name, "APPROVED", "Human validated & approved via interactive review (approve all)"
                )
                for rem in candidates_to_surface[idx:]:
                    if len(approved_items) < effective_target:
                        approved_items.append(rem)
                        _record_human_verdict(
                            led, rem, cat_name, "APPROVED", "Human validated & approved via interactive review (approve all)"
                        )
                print(f"  Approved this and all remaining {cat_label.upper()}s (saved to AuditLedger)")
                break
            elif choice in ("d", "done"):
                if approved_items:
                    print(f"  Finalized {cat_label.upper()} review early with {len(approved_items)} approved proposal(s).")
                    approve_all = True
                    break
                else:
                    print("  Warning: No components approved yet. Please approve at least one or skip.")
            else:
                print("  Invalid choice. Enter 'y', 'l', 'n', 's', 'a', or 'd'.")

        if approve_all:
            break

    final_pool = [locked_item] if locked_item else (approved_items if approved_items else filtered_pool)
    return locked_item, approved_items, final_pool


def run_human_validation_review(
    gpu_list: Optional[List[Dict[str, Any]]] = None,
    cpu_list: Optional[List[Dict[str, Any]]] = None,
    mobo_list: Optional[List[Dict[str, Any]]] = None,
    ram_list: Optional[List[Dict[str, Any]]] = None,
    psu_list: Optional[List[Dict[str, Any]]] = None,
    budget: float = 35000.0,
    profile: Optional[Any] = None,
    ledger: Optional[AuditLedger] = None,
    input_func: Optional[Callable[[str], str]] = None,
    max_candidates: Optional[int] = None,
    target_approved: Optional[Union[int, Dict[str, int]]] = None,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    no_ai: bool = False,
    re_audit: bool = False,
    ai_prescreen: bool = False,
    force_review: bool = False,
    human_only: bool = True,
) -> HumanReviewResult:
    """
    Interactive human validation loop: surfaces top deals across all active PC component categories
    (GPU, CPU+Platform, Motherboard, RAM, PSU) for user verification before PC build synthesis.
    Allows user to Approve [y], Lock into build [l], Reject & blacklist [n], Skip [s], Approve all [a], or Done [d].
    Bypasses validation automatically if top candidates are already verified & approved in AuditLedger.
    """
    led = ledger or default_ledger
    strict_max = (target_approved is None and max_candidates is not None)

    def _cat_target(cat: str) -> int:
        if isinstance(target_approved, dict):
            return target_approved.get(cat, DEFAULT_CATEGORY_TARGETS.get(cat, 5))
        if isinstance(target_approved, int):
            return target_approved
        if max_candidates is not None:
            return max_candidates
        return DEFAULT_CATEGORY_TARGETS.get(cat, 5)

    def _cat_max(cat: str) -> int:
        if max_candidates is not None:
            return max_candidates
        return _cat_target(cat)

    mode_name = getattr(profile, "name", "best") if profile else "best"

    # 1. Prepare clean pools (excluding blacklisted items)
    filtered_gpus = [g for g in (gpu_list or []) if not _is_item_rejected(led, g)]
    filtered_cpus = [c for c in (cpu_list or []) if not _is_item_rejected(led, c)]
    filtered_mobos = [m for m in (mobo_list or []) if not _is_item_rejected(led, m)]
    filtered_rams = [r for r in (ram_list or []) if not _is_item_rejected(led, r)]
    filtered_psus = [p for p in (psu_list or []) if not _is_item_rejected(led, p)]

    active_configs = []
    if filtered_gpus:
        active_configs.append("gpu")
    if filtered_cpus:
        active_configs.append("cpu")
    if filtered_mobos:
        active_configs.append("mobo")
    if filtered_rams:
        active_configs.append("ram")
    if filtered_psus:
        active_configs.append("psu")

    is_interactive = (input_func is not None) or (sys.stdin and sys.stdin.isatty())

    # Pre-approved items from AuditLedger
    pre_app_gpus = [g for g in filtered_gpus if _is_item_approved(led, g, human_only=human_only)]
    pre_app_cpus = [c for c in filtered_cpus if _is_item_approved(led, c, human_only=human_only)]
    pre_app_mobos = [m for m in filtered_mobos if _is_item_approved(led, m, human_only=human_only)]
    pre_app_rams = [r for r in filtered_rams if _is_item_approved(led, r, human_only=human_only)]
    pre_app_psus = [p for p in filtered_psus if _is_item_approved(led, p, human_only=human_only)]

    can_bypass_all = bool(active_configs) and not force_review and not re_audit
    if "gpu" in active_configs and not _is_category_satisfied(pre_app_gpus, filtered_gpus, _cat_target("gpu"), led, human_only=human_only):
        can_bypass_all = False
    if "cpu" in active_configs and not _is_category_satisfied(pre_app_cpus, filtered_cpus, _cat_target("cpu"), led, human_only=human_only):
        can_bypass_all = False
    if "mobo" in active_configs and not _is_category_satisfied(pre_app_mobos, filtered_mobos, _cat_target("mobo"), led, human_only=human_only):
        can_bypass_all = False
    if "ram" in active_configs and not _is_category_satisfied(pre_app_rams, filtered_rams, _cat_target("ram"), led, human_only=human_only):
        can_bypass_all = False
    if "psu" in active_configs and not _is_category_satisfied(pre_app_psus, filtered_psus, _cat_target("psu"), led, human_only=human_only):
        can_bypass_all = False

    # Platform coherence & budget feasibility verification
    viable_platforms: List[Tuple[str, str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]] = []
    if can_bypass_all and "cpu" in active_configs and "mobo" in active_configs:
        c_socks = {c.get("socket", "").upper() for c in pre_app_cpus if c.get("socket")}
        m_socks = {m.get("socket", "").upper() for m in pre_app_mobos if m.get("socket")}
        shared_socks = c_socks & m_socks

        min_g_cost = min((float(g.get("price", 0)) for g in pre_app_gpus), default=0.0) if "gpu" in active_configs else 0.0
        min_p_cost = min((float(p.get("price", 0)) for p in pre_app_psus), default=0.0) if "psu" in active_configs else 0.0

        for sock in shared_socks:
            s_cpus = [c for c in pre_app_cpus if c.get("socket", "").upper() == sock]
            s_mobos = [m for m in pre_app_mobos if m.get("socket", "").upper() == sock]
            if not s_cpus or not s_mobos:
                continue
            mobo_ddrs = {m.get("ddr_type", "").upper() for m in s_mobos if m.get("ddr_type")}
            for ddr in mobo_ddrs:
                sm_ddr = [m for m in s_mobos if m.get("ddr_type", "").upper() == ddr]
                sr_ddr = [r for r in pre_app_rams if str(r.get("gen", r.get("ddr_type", ""))).upper() == ddr] if "ram" in active_configs else [{}]
                if not sr_ddr and "ram" in active_configs and not human_only:
                    sr_ddr = [r for r in filtered_rams if str(r.get("gen", r.get("ddr_type", ""))).upper() == ddr]
                if not sm_ddr or not sr_ddr:
                    continue

                min_c = min((float(c.get("price", 0)) for c in s_cpus), default=0.0)
                min_m = min((float(m.get("price", 0)) for m in sm_ddr), default=0.0)
                min_r = min((float(r.get("price", 0)) for r in sr_ddr if r), default=0.0)
                platform_min_cost = min_g_cost + min_c + min_m + min_r + min_p_cost

                if budget and budget > 0 and platform_min_cost > budget * 1.05:
                    continue

                viable_platforms.append((sock, ddr, s_cpus, sm_ddr, sr_ddr))

        if not viable_platforms:
            can_bypass_all = False

    elif can_bypass_all and budget and budget > 0:
        min_g = min((float(g.get("price", 0)) for g in pre_app_gpus), default=0.0) if "gpu" in active_configs else 0.0
        min_c = min((float(c.get("price", 0)) for c in pre_app_cpus), default=0.0) if "cpu" in active_configs else 0.0
        min_m = min((float(m.get("price", 0)) for m in pre_app_mobos), default=0.0) if "mobo" in active_configs else 0.0
        min_r = min((float(r.get("price", 0)) for r in pre_app_rams), default=0.0) if "ram" in active_configs else 0.0
        min_p = min((float(p.get("price", 0)) for p in pre_app_psus), default=0.0) if "psu" in active_configs else 0.0
        if (min_g + min_c + min_m + min_r + min_p) > budget * 1.05:
            can_bypass_all = False

    if can_bypass_all:
        print("   User validation review:")
        if "gpu" in active_configs:
            print(f"   • {'GPU':<16} : {min(len(pre_app_gpus), _cat_target('gpu'))}")
        if "cpu" in active_configs:
            print(f"   • {'CPU + Platform':<16} : {min(len(pre_app_cpus), _cat_target('cpu'))}")
        if "mobo" in active_configs:
            print(f"   • {'Motherboard':<16} : {min(len(pre_app_mobos), _cat_target('mobo'))}")
        if "ram" in active_configs:
            print(f"   • {'RAM':<16} : {min(len(pre_app_rams), _cat_target('ram'))}")
        if "psu" in active_configs:
            print(f"   • {'Power Supply':<16} : {min(len(pre_app_psus), _cat_target('psu'))}")

        final_g = pre_app_gpus[:_cat_target("gpu")] if pre_app_gpus else filtered_gpus
        final_p = pre_app_psus[:_cat_target("psu")] if pre_app_psus else filtered_psus

        if viable_platforms:
            cpus_by_sock: Dict[str, List[Dict[str, Any]]] = {}
            mobos_by_sock: Dict[str, List[Dict[str, Any]]] = {}
            rams_by_ddr: Dict[str, List[Dict[str, Any]]] = {}

            for sock, ddr, s_c, s_m, s_r in viable_platforms:
                cpus_by_sock.setdefault(sock, [])
                for c in s_c:
                    if c not in cpus_by_sock[sock]:
                        cpus_by_sock[sock].append(c)
                mobos_by_sock.setdefault(sock, [])
                for m in s_m:
                    if m not in mobos_by_sock[sock]:
                        mobos_by_sock[sock].append(m)
                rams_by_ddr.setdefault(ddr, [])
                for r in s_r:
                    if r and r not in rams_by_ddr[ddr]:
                        rams_by_ddr[ddr].append(r)

            def _round_robin_group(grouped: Dict[str, List[Dict[str, Any]]], limit: int) -> List[Dict[str, Any]]:
                copy_dict = {k: list(v) for k, v in grouped.items()}
                out: List[Dict[str, Any]] = []
                keys = list(copy_dict.keys())
                while len(out) < limit and any(copy_dict.values()):
                    for k in keys:
                        if copy_dict[k]:
                            out.append(copy_dict[k].pop(0))
                            if len(out) >= limit:
                                break
                return out

            final_c = _round_robin_group(cpus_by_sock, _cat_target("cpu")) if cpus_by_sock else filtered_cpus[:_cat_target("cpu")]
            final_m = _round_robin_group(mobos_by_sock, _cat_target("mobo")) if mobos_by_sock else filtered_mobos[:_cat_target("mobo")]
            final_r = _round_robin_group(rams_by_ddr, _cat_target("ram")) if rams_by_ddr else filtered_rams[:_cat_target("ram")]
        else:
            final_c = pre_app_cpus[:_cat_target("cpu")] if pre_app_cpus else filtered_cpus
            final_m = pre_app_mobos[:_cat_target("mobo")] if pre_app_mobos else filtered_mobos
            final_r = pre_app_rams[:_cat_target("ram")] if pre_app_rams else filtered_rams

        return HumanReviewResult(
            locked_gpu=None,
            locked_cpu=None,
            final_gpus=final_g,
            final_cpus=final_c,
            locked_mobo=None,
            locked_ram=None,
            locked_psu=None,
            final_mobos=final_m,
            final_rams=final_r,
            final_psus=final_p,
            approved_by_cat={
                "gpu": final_g,
                "cpu": final_c,
                "mobo": final_m,
                "ram": final_r,
                "psu": final_p,
            },
        )

    print("\n" + "─" * 78)
    print("User Validation Review (--human-review)")
    print("Surfacing top candidate deals for manual inspection before build synthesis.")
    if is_interactive:
        print("Options: [y] Approve │ [l] Lock for build │ [n] Reject & blacklist │ [s] Skip │ [a] All │ [d] Done")
    else:
        print("(Non-interactive session: displaying top deal breakdown)")
    print("─" * 78)

    locked_results: Dict[str, Optional[Dict[str, Any]]] = {}
    approved_results: Dict[str, List[Dict[str, Any]]] = {}
    final_results: Dict[str, List[Dict[str, Any]]] = {}
    limit_deals = max(max(_cat_max(c) for c in ("gpu", "cpu", "mobo", "ram", "psu")) * 4, 30)

    # ── STEP 1: GPU REVIEW ─────────────────────────────────────────────────
    min_gpu_cost = 0.0
    max_gpu_tdp = 150.0
    if filtered_gpus:
        ranked_gpus = select_top_gpu_deals(filtered_gpus, budget=budget, profile=profile, limit=limit_deals)
        pre_app_g = [g for g in ranked_gpus if _is_item_approved(led, g, human_only=human_only)]
        insp_gpu = _get_category_inspector("gpu", ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
        t_gpu = _cat_target("gpu")
        m_gpu = _cat_max("gpu")
        lock_g, app_g, fin_g = _review_category(
            cat_name="gpu",
            cat_label="GPU",
            cat_icon="",
            pool=filtered_gpus,
            ranked_cands=ranked_gpus,
            pre_approved=pre_app_g,
            effective_target=t_gpu,
            is_interactive=is_interactive,
            input_func=input_func,
            led=led,
            printer=lambda idx, tot, x: _print_gpu_proposal(idx, tot, x),
            max_candidates=m_gpu,
            strict_max=strict_max,
            ai_inspector=insp_gpu,
            mode_name=mode_name,
            re_audit=re_audit,
            force_review=force_review,
            human_only=human_only,
        )
        locked_results["gpu"] = lock_g
        approved_results["gpu"] = app_g
        final_results["gpu"] = fin_g
        active_gpus = [lock_g] if lock_g else (app_g if app_g else filtered_gpus)
        min_gpu_cost = min((float(g.get("price", 0)) for g in active_gpus), default=0.0)
        max_gpu_tdp = max((float((g.get("spec") or g).get("tdp_w", 150)) for g in active_gpus), default=150.0)

    # ── STEP 2: CPU + PLATFORM REVIEW ─────────────────────────────────────
    min_cpu_cost = 0.0
    max_cpu_tdp = 65.0
    approved_sockets = set()
    if filtered_cpus:
        ranked_cpus = select_top_cpu_platform_deals(
            filtered_cpus,
            mobo_list=filtered_mobos,
            ram_list=filtered_rams,
            budget=budget,
            profile=profile,
            limit=limit_deals,
        )
        pre_app_c = [c for c in ranked_cpus if _is_item_approved(led, c, human_only=human_only)]
        insp_cpu = _get_category_inspector("cpu", ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
        t_cpu = _cat_target("cpu")
        m_cpu = _cat_max("cpu")
        lock_c, app_c, fin_c = _review_category(
            cat_name="cpu",
            cat_label="CPU + Platform",
            cat_icon="",
            pool=filtered_cpus,
            ranked_cands=ranked_cpus,
            pre_approved=pre_app_c,
            effective_target=t_cpu,
            is_interactive=is_interactive,
            input_func=input_func,
            led=led,
            printer=lambda idx, tot, x: _print_cpu_proposal(idx, tot, x, mobo_list, ram_list),
            max_candidates=m_cpu,
            strict_max=strict_max,
            ai_inspector=insp_cpu,
            mode_name=mode_name,
            re_audit=re_audit,
            force_review=force_review,
            human_only=human_only,
        )
        locked_results["cpu"] = lock_c
        approved_results["cpu"] = app_c
        final_results["cpu"] = fin_c
        active_cpus = [lock_c] if lock_c else (app_c if app_c else filtered_cpus)
        approved_sockets = {c.get("socket", "").upper() for c in active_cpus if c.get("socket")}
        min_cpu_cost = min((float(c.get("price", 0)) for c in active_cpus), default=0.0)
        max_cpu_tdp = max((float((c.get("spec") or c).get("tdp_w", 65)) for c in active_cpus), default=65.0)

    # ── STEP 3: MOTHERBOARD REVIEW ────────────────────────────────────────
    min_mobo_cost = 0.0
    approved_ddrs = set()
    if filtered_mobos:
        ranked_mobos = select_top_mobo_deals(
            filtered_mobos,
            target_sockets=approved_sockets if approved_sockets else None,
            budget=budget,
            profile=profile,
            limit=limit_deals,
        )
        if not ranked_mobos and approved_sockets:
            ranked_mobos = select_top_mobo_deals(filtered_mobos, budget=budget, profile=profile, limit=limit_deals)

        pre_app_m = [m for m in ranked_mobos if _is_item_approved(led, m, human_only=human_only)]
        insp_mobo = _get_category_inspector("mobo", ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
        t_mobo = _cat_target("mobo")
        m_mobo = _cat_max("mobo")
        lock_m, app_m, fin_m = _review_category(
            cat_name="mobo",
            cat_label="Motherboard",
            cat_icon="",
            pool=filtered_mobos,
            ranked_cands=ranked_mobos,
            pre_approved=pre_app_m,
            effective_target=t_mobo,
            is_interactive=is_interactive,
            input_func=input_func,
            led=led,
            printer=lambda idx, tot, x: _print_mobo_proposal(idx, tot, x),
            max_candidates=m_mobo,
            strict_max=strict_max,
            ai_inspector=insp_mobo,
            mode_name=mode_name,
            re_audit=re_audit,
            force_review=force_review,
            human_only=human_only,
        )
        locked_results["mobo"] = lock_m
        approved_results["mobo"] = app_m
        final_results["mobo"] = fin_m
        active_mobos = [lock_m] if lock_m else (app_m if app_m else filtered_mobos)
        approved_ddrs = {m.get("ddr_type", "").upper() for m in active_mobos if m.get("ddr_type")}
        min_mobo_cost = min((float(m.get("price", 0)) for m in active_mobos), default=0.0)

    # ── STEP 4: RAM REVIEW ────────────────────────────────────────────────
    min_ram_cost = 0.0
    if filtered_rams:
        ranked_rams = select_top_ram_deals(
            filtered_rams,
            target_gens=approved_ddrs if approved_ddrs else None,
            budget=budget,
            profile=profile,
            limit=limit_deals,
        )
        if not ranked_rams and approved_ddrs:
            ranked_rams = select_top_ram_deals(filtered_rams, budget=budget, profile=profile, limit=limit_deals)

        pre_app_r = [r for r in ranked_rams if _is_item_approved(led, r, human_only=human_only)]
        insp_ram = _get_category_inspector("ram", ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
        t_ram = _cat_target("ram")
        m_ram = _cat_max("ram")
        lock_r, app_r, fin_r = _review_category(
            cat_name="ram",
            cat_label="RAM",
            cat_icon="",
            pool=filtered_rams,
            ranked_cands=ranked_rams,
            pre_approved=pre_app_r,
            effective_target=t_ram,
            is_interactive=is_interactive,
            input_func=input_func,
            led=led,
            printer=lambda idx, tot, x: _print_ram_proposal(idx, tot, x),
            max_candidates=m_ram,
            strict_max=strict_max,
            ai_inspector=insp_ram,
            mode_name=mode_name,
            re_audit=re_audit,
            force_review=force_review,
            human_only=human_only,
        )
        locked_results["ram"] = lock_r
        approved_results["ram"] = app_r
        final_results["ram"] = fin_r
        active_rams = [lock_r] if lock_r else (app_r if app_r else filtered_rams)
        min_ram_cost = min((float(r.get("price", 0)) for r in active_rams), default=0.0)

    # ── STEP 5: POWER SUPPLY REVIEW ───────────────────────────────────────
    if filtered_psus:
        needed_watts = int(max_gpu_tdp + max_cpu_tdp + 150)
        min_w = 500 if needed_watts <= 500 else (550 if needed_watts <= 550 else (650 if needed_watts <= 650 else 750))
        ranked_psus = select_top_psu_deals(
            filtered_psus,
            min_watts=min_w,
            budget=budget,
            profile=profile,
            limit=limit_deals,
        )
        if not ranked_psus:
            ranked_psus = select_top_psu_deals(filtered_psus, min_watts=500, budget=budget, profile=profile, limit=limit_deals)

        pre_app_p = [p for p in ranked_psus if _is_item_approved(led, p, human_only=human_only)]
        insp_psu = _get_category_inspector("psu", ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
        t_psu = _cat_target("psu")
        m_psu = _cat_max("psu")
        lock_p, app_p, fin_p = _review_category(
            cat_name="psu",
            cat_label="Power Supply",
            cat_icon="",
            pool=filtered_psus,
            ranked_cands=ranked_psus,
            pre_approved=pre_app_p,
            effective_target=t_psu,
            is_interactive=is_interactive,
            input_func=input_func,
            led=led,
            printer=lambda idx, tot, x: _print_psu_proposal(idx, tot, x),
            max_candidates=m_psu,
            strict_max=strict_max,
            ai_inspector=insp_psu,
            mode_name=mode_name,
            re_audit=re_audit,
            force_review=force_review,
            human_only=human_only,
        )
        locked_results["psu"] = lock_p
        approved_results["psu"] = app_p
        final_results["psu"] = fin_p

    print("─" * 78)
    for cat_name, cat_label in [("gpu", "GPU"), ("cpu", "CPU + Platform"), ("mobo", "Motherboard"), ("ram", "RAM"), ("psu", "Power Supply")]:
        if cat_name not in active_configs:
            continue
        l_item = locked_results.get(cat_name)
        a_items = approved_results.get(cat_name) or []
        f_items = final_results.get(cat_name) or []
        if l_item:
            print(f"   Locked {cat_label}: {l_item.get('model')} ({format_price(float(l_item.get('price', 0)))})")
        elif a_items:
            print(f"   Constraining {cat_label} synthesis to {len(a_items)} approved proposals")
        else:
            print(f"   Using verified marketplace pool for {cat_label} ({len(f_items)} candidates)")
    print("   Proceeding to combinatorial build synthesis...\n")

    return HumanReviewResult(
        locked_gpu=locked_results.get("gpu"),
        locked_cpu=locked_results.get("cpu"),
        final_gpus=final_results.get("gpu", filtered_gpus),
        final_cpus=final_results.get("cpu", filtered_cpus),
        locked_mobo=locked_results.get("mobo"),
        locked_ram=locked_results.get("ram"),
        locked_psu=locked_results.get("psu"),
        final_mobos=final_results.get("mobo", filtered_mobos),
        final_rams=final_results.get("ram", filtered_rams),
        final_psus=final_results.get("psu", filtered_psus),
        approved_by_cat=approved_results,
    )

