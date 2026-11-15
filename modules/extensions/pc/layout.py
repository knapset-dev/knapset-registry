"""
PC Domain Layout.

Defines the 5 core PC sections:
1. GPU (Graphics Card)
2. CPU (Processor)
3. MOBO (Motherboard)
4. RAM (Memory)
5. PSU (Power Supply)

And electrical / architectural compatibility rules:
- CPU Socket == Motherboard Socket
- Motherboard DDR Generation == RAM Generation
- PSU Wattage >= Estimated System Load + Headroom
- Dynamic multi-currency formatting & USDT by default
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Tuple

from currency import canonical_currency, convert_currency, format_price, get_active_currency
from domain_layout import CompatibilityRule, DomainLayout, SectionDefinition


def _fmt_gpu_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    model = cand.get("model", "GPU")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)
    vram = cand.get("vram_gb", (cand.get("spec") or {}).get("vram_gb", 8))
    fps = cand.get("fps_1440p", (cand.get("spec") or {}).get("fps_1440p", 60))
    return ("GPU", model, price_str, f"{vram}GB", f"1440p:{fps:.0f}fps")


def _fmt_cpu_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    model = cand.get("model", "CPU")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)
    spec = cand.get("spec") or {}
    threads = cand.get("threads", spec.get("threads", 6))
    l3 = spec.get("l3_cache_mb", 32)
    fps_gaming = cand.get("fps_gaming", spec.get("fps_gaming", 100))
    c_low = spec.get("fps_1pct_low", fps_gaming * 0.73)
    return ("CPU", model, price_str, f"{threads}T {l3}M", f"{fps_gaming:.0f}/{c_low:.0f}idx")


def _fmt_mobo_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    model = cand.get("model", "MOBO")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)
    spec = cand.get("spec") or {}
    socket = cand.get("socket", spec.get("socket", "AM4"))
    ddr = cand.get("ddr_type", spec.get("ddr_type", "DDR4"))
    vrm = cand.get("vrm_tier", spec.get("vrm_tier", "B-Tier"))
    return ("MOBO", model, price_str, f"{socket} {ddr}", f"{vrm}")


def _fmt_ram_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    model = cand.get("model", "RAM")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)
    spec = cand.get("spec") or {}
    mods = spec.get("module_count", 2)
    tot_gb = int(cand.get("total_gb") or spec.get("total_gb") or spec.get("capacity_gb") or 16)
    lat = spec.get("latency_ns", 10.0)
    ff = str(spec.get("form_factor", cand.get("form_factor", "UDIMM"))).upper()
    col3 = f"{tot_gb}GB ({mods}x stick)"
    if ff == "UNKNOWN":
        col3 += " [? Confirm DIMM]"
    elif ff == "ECC_UDIMM":
        col3 += " [! ECC UDIMM]"
    return ("RAM", model, price_str, col3, f"{lat:.1f}ns")


def _fmt_psu_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    model = cand.get("model", "PSU")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)
    spec = cand.get("spec") or {}
    watts = cand.get("wattage", spec.get("wattage", 750))
    raw_tier = cand.get("tier", spec.get("vrm_tier", "Tier C"))
    m_tier = re.search(r"Tier\s*([A-Fa-f])", str(raw_tier))
    tier = f"{m_tier.group(1).upper()}-Tier" if m_tier else str(raw_tier).strip()
    return ("PSU", model, price_str, f"{watts}W", f"{tier}")


def _rule_cpu_mobo_socket(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    cpu = set_dict.get("cpu")
    mobo = set_dict.get("mobo")
    if not (cpu and mobo):
        return True, None
    c_sock = str(cpu.get("socket", (cpu.get("spec") or {}).get("socket", ""))).upper()
    m_sock = str(mobo.get("socket", (mobo.get("spec") or {}).get("socket", ""))).upper()
    if c_sock and m_sock and c_sock != m_sock:
        return False, f"Socket conflict: CPU requires {c_sock}, but Motherboard has {m_sock}"
    return True, None


def _rule_mobo_ram_ddr(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    mobo = set_dict.get("mobo")
    ram = set_dict.get("ram")
    if not (mobo and ram):
        return True, None
    m_ddr = str(mobo.get("ddr_type", (mobo.get("spec") or {}).get("ddr_type", ""))).upper()
    r_ddr = str(ram.get("gen", (ram.get("spec") or {}).get("gen", ""))).upper()
    if m_ddr and r_ddr and m_ddr != r_ddr:
        return False, f"Memory conflict: Motherboard requires {m_ddr}, but RAM is {r_ddr}"
    return True, None


def _rule_ram_desktop_form_factor(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    ram = set_dict.get("ram")
    if not ram:
        return True, None
    ff = str(ram.get("form_factor", (ram.get("spec") or {}).get("form_factor", "UDIMM"))).upper()
    if ff in ("SODIMM", "ECC_REG"):
        return False, f"Form factor conflict: Desktop motherboard requires UDIMM, but RAM is {ff}"

    if ff == "ECC_UDIMM":
        mobo = set_dict.get("mobo")
        if mobo:
            m_spec = mobo.get("spec") or {}
            m_chipset = str(mobo.get("chipset") or m_spec.get("chipset") or "").upper()
            m_ecc = str(mobo.get("ecc_support") or m_spec.get("ecc_support") or "unknown").lower()
            # Explicit non-ECC Intel consumer chipsets
            if m_ecc == "no" or any(m_chipset.startswith(pfx) for pfx in ("H610", "B660", "B760", "Z690", "Z790", "H410", "B460", "H510", "B560", "H310", "B360", "H110", "B150", "B250")):
                return False, f"ECC unbuffered RAM (ECC_UDIMM) is unsupported on consumer Intel chipset {m_chipset}"
    return True, None


def _rule_psu_wattage(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    psu = set_dict.get("psu")
    gpu = set_dict.get("gpu")
    cpu = set_dict.get("cpu")
    if not (psu and gpu and cpu):
        return True, None
    p_w = float(psu.get("wattage", (psu.get("spec") or {}).get("wattage", 500)))
    g_tdp = float(gpu.get("tdp_watts", (gpu.get("spec") or {}).get("tdp_w", 180)))
    c_tdp = float(cpu.get("tdp_watts", (cpu.get("spec") or {}).get("tdp_w", 65)))
    min_needed = g_tdp + c_tdp + 130
    if p_w < min_needed:
        return False, f"Insufficient PSU wattage: estimated load is {min_needed:.0f}W, but PSU is {p_w:.0f}W"
    return True, None


def _pc_headline_formatter(
    set_entry: Dict[str, Any],
    idx: int,
    total_cost: float,
    score: float,
    profile: Any,
) -> Tuple[str, str, str, str, str, str]:
    comps = set_entry["components"]
    g = comps.get("gpu", {})
    c = comps.get("cpu", {})
    p = comps.get("psu", {})

    g_mod = g.get("model", "GPU")
    c_mod = c.get("model", "CPU")
    curr = set_entry.get("currency") or (comps.get("gpu") or {}).get("currency") or get_active_currency()
    title_col = f"Build #{idx}: {g_mod} + {c_mod}"
    score_col = f"{format_price(total_cost, curr)} (Score: {score:.1f})"
    surplus = set_entry.get("surplus", 0.0)
    if surplus > 0:
        surplus_str = f"+{format_price(surplus, curr)}"
    elif surplus == 0:
        surplus_str = format_price(0, curr)
    else:
        surplus_str = format_price(surplus, curr)

    fps_1440 = g.get("fps_1440p", 60)
    fps_1080 = g.get("fps_1080p", 85)
    line2_left = f"Gaming: ~{fps_1440:.0f} fps (1440p) / ~{fps_1080:.0f} (1080p)"

    g_tdp = float(g.get("tdp_watts", (g.get("spec") or {}).get("tdp_w", 180)))
    c_tdp = float(c.get("tdp_watts", (c.get("spec") or {}).get("tdp_w", 65)))
    p_w = float(p.get("wattage", (p.get("spec") or {}).get("wattage", 750)))
    load = int(g_tdp + c_tdp + 40)
    line2_mid = f"Load: ~{load}W on {p_w:.0f}W"

    avg_disc = sum(float(x.get("discount_pct", 0.0)) for x in comps.values()) / max(1, len(comps))
    from analyzer_core import fmt_deal_pct
    line2_right = f"Mkt: {fmt_deal_pct(avg_disc)}"

    cost_per_fps = total_cost / max(1.0, fps_1440)
    fps_per_1k = (fps_1440 / max(1.0, total_cost)) * 1000.0
    val_left = f"Perf/Value: ~{cost_per_fps:.0f} {curr}/fps (1440p)"
    val_mid = f"~{fps_per_1k:.1f} fps / 1k {curr}"
    gpu_p = float(g.get("price", 0.0))
    val_right = f"GPU: ~{gpu_p / max(1.0, fps_1440):.0f} {curr}/fps"

    return title_col, score_col, surplus_str, line2_left, line2_mid, line2_right, val_left, val_mid, val_right


def create_pc_layout() -> DomainLayout:
    """Instantiates the complete PC Domain Layout."""
    active_curr = get_active_currency()
    def_budget = 800.0 if canonical_currency(active_curr) == "USDT" else convert_currency(800.0, "USDT", active_curr)
    return DomainLayout(
        domain_id="pc",
        title="PC Build",
        description="Combinatorial PC build synthesizer matching GPU, CPU, Motherboard, RAM, and Power Supply.",
        default_budget=def_budget,
        currency=active_curr,
        sections=[
            SectionDefinition(id="gpu", name="GPU", label="GPU", budget_share_min=0.30, budget_share_max=0.60, pareto_limit=36, row_formatter=_fmt_gpu_row),
            SectionDefinition(id="cpu", name="CPU", label="CPU", budget_share_min=0.15, budget_share_max=0.35, pareto_limit=52, row_formatter=_fmt_cpu_row),
            SectionDefinition(id="mobo", name="Motherboard", label="MOBO", budget_share_min=0.08, budget_share_max=0.20, pareto_limit=24, row_formatter=_fmt_mobo_row),
            SectionDefinition(id="ram", name="RAM", label="RAM", budget_share_min=0.05, budget_share_max=0.15, pareto_limit=18, row_formatter=_fmt_ram_row),
            SectionDefinition(id="psu", name="Power Supply", label="PSU", budget_share_min=0.05, budget_share_max=0.15, pareto_limit=16, row_formatter=_fmt_psu_row),
        ],
        compatibility_rules=[
            CompatibilityRule(name="cpu_mobo_socket", description="CPU socket must match motherboard socket", validator=_rule_cpu_mobo_socket, sections_involved=("cpu", "mobo")),
            CompatibilityRule(name="mobo_ram_ddr", description="Motherboard DDR generation must match RAM generation", validator=_rule_mobo_ram_ddr, sections_involved=("mobo", "ram")),
            CompatibilityRule(name="ram_desktop_form_factor", description="RAM must not be laptop SODIMM or server ECC REG", validator=_rule_ram_desktop_form_factor, sections_involved=("ram",)),
            CompatibilityRule(name="psu_wattage", description="PSU wattage must exceed system load + headroom", validator=_rule_psu_wattage, sections_involved=("gpu", "cpu", "psu")),
        ],
        headline_formatter=_pc_headline_formatter,
    )
