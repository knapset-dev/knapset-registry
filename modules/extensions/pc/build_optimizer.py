#!/usr/bin/env python3
"""
Combinatorial PC System Build Synthesizer ("The Best You Can Get" Multi-Mode Engine).

Formulates platform-compatible, electrically balanced 5-part PC builds (GPU, CPU,
Motherboard, RAM, PSU) from live/cached OLX market listings using:
  - Per-Model & Per-Tier Pareto Frontier pruning (<50ms combinatorial synthesis)
  - All 15+ Unified Optimization Modes ('best', 'sweet-spot', 'value', 'safe',
    'max-perf', 'deal-hunter', 'esports', 'efficiency', 'future-proof',
    'ai-workstation', 'budget-king', custom configs/modes.json, and CLI --weights)
  - CPU-GPU bottleneck modeling, VRM-to-TDP safety rules, and PSU transient headroom
  - Optional live Multi-Provider AI Audit (--ai-audit) with automatic fallback re-synthesis
"""

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ai_providers import list_provider_names
from analyzer_core import fmt_deal_pct, get_status_badge, make_terminal_link, pad_ansi
from audit_ledger import ledger
from extensions.pc.bundle_detector import extract_bundle_propositions
from extensions.pc.cpu_ai_inspector import CPUAIInspector
from extensions.pc.cpu_database import CPU_DATABASE, identify_cpu
from extensions.pc.cpu_scam_detector import CPUScamDetector
from extensions.pc.gpu_ai_inspector import GPUAIInspector
from extensions.pc.gpu_database import GPU_DATABASE, identify_gpu
from extensions.pc.gpu_scam_detector import GPUScamDetector
from extensions.pc.human_review import DEFAULT_CATEGORY_TARGETS, HumanReviewResult, run_human_validation_review
from market_client import MarketClient, check_delivery_refusal, load_market_cache
from extensions.pc.mobo_ai_inspector import MotherboardAIInspector
from extensions.pc.mobo_database import CHIPSET_SPECS, identify_motherboard
from extensions.pc.mobo_scam_detector import MotherboardScamDetector
from extensions.pc.modes import (
    LEGACY_SOCKETS,
    PSU_TIER_RANK,
    ModeProfile,
    compute_effective_build_fps,
    compute_market_discount_pct,
    get_mode_names,
    is_listing_disqualified,
    resolve_mode,
    score_build,
    score_component,
)
from extensions.pc.psu_ai_inspector import PSUAIInspector
from extensions.pc.psu_database import identify_psu
from extensions.pc.psu_scam_detector import PSUScamDetector
from extensions.pc.ram_ai_inspector import RAMAIInspector
from extensions.pc.ram_database import identify_ram
from extensions.pc.ram_scam_detector import RAMScamDetector
from extensions.pc.system_ai_inspector import SystemAIInspector, is_any_ai_provider_ready

ALL_CATEGORIES = ("gpu", "cpu", "mobo", "ram", "psu")
TWO_DIMM_CHIPSETS = {"A320", "A520", "A620", "H610", "H810", "H510", "H410", "H310", "H110"}


def parse_target_query(raw_val: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Parses unified flag input into (is_owned, clean_query)."""
    if not raw_val:
        return False, None
    s = raw_val.strip()
    if s.lower().startswith("owned:"):
        return True, s[6:].strip()
    return False, s


def matches_lock_query(comp: Dict[str, Any], query: str) -> bool:
    """Matches listing against user lock query using case-insensitive token overlap."""
    if not query:
        return True
    q_norm = query.strip().lower()
    model = str(comp.get("model", "")).lower()
    title = str((comp.get("summary") or {}).get("title", "")).lower()
    if q_norm in model or q_norm in title:
        return True
    tokens = [t for t in re.split(r"[\s\-_]+", q_norm) if t]
    if tokens and all(t in model or t in title for t in tokens):
        return True
    return False


def resolve_owned_gpu(query: str) -> Dict[str, Any]:
    """Resolves exact specs for owned GPU, costing 0 ₴."""
    g_info = identify_gpu(query)
    if not g_info:
        for prefix in ("RTX ", "GTX ", "RX ", "Radeon RX ", "Arc "):
            g_info = identify_gpu(prefix + query)
            if g_info:
                break
    if not g_info:
        q_tokens = [t.upper() for t in re.split(r"[\s\-_]+", query) if t]
        for model_name, specs in GPU_DATABASE.items():
            if all(t in model_name for t in q_tokens):
                g_info = {"model": model_name, **specs}
                break
    if not g_info:
        raise ValueError(
            f"Could not resolve owned GPU model from '{query}'. "
            f"Tip: Specify model name, e.g. --gpu \"owned:RTX 3080\" or --gpu \"owned:RX 6800 XT\"."
        )

    clean_ev = {
        "risk_score": 0,
        "red_flags": [],
        "warnings": [],
        "audit": None,
        "is_ai_approved": True,
        "is_ai_rejected": False,
    }
    return {
        "id": "owned_gpu",
        "summary": {"id": "owned_gpu", "title": f"Owned {g_info['model']}", "price": 0.0, "url": ""},
        "spec": g_info,
        "gpu": g_info,
        "model": g_info["model"],
        "price": 0.0,
        "fps_1440p": g_info["fps_1440p"],
        "fps_1080p": g_info["fps_1080p"],
        "vram_gb": g_info["vram_gb"],
        "tdp_watts": g_info.get("tdp_watts", 200),
        "discount_pct": 0.0,
        "url": "",
        "is_owned": True,
        "eval": clean_ev,
        "heuristic": clean_ev,
        "ai_eval": None,
    }


def resolve_owned_cpu(query: str) -> Dict[str, Any]:
    """Resolves exact specs for owned CPU, costing 0 ₴."""
    c_info = identify_cpu(query)
    if not c_info:
        for prefix in ("Ryzen ", "Intel Core ", "AMD Ryzen ", "Core "):
            c_info = identify_cpu(prefix + query)
            if c_info:
                break
    if not c_info:
        q_tokens = [t.upper() for t in re.split(r"[\s\-_]+", query) if t]
        for model_name, specs in CPU_DATABASE.items():
            if all(t in model_name for t in q_tokens):
                c_info = {"model": model_name, **specs}
                break
    if not c_info:
        raise ValueError(
            f"Could not resolve owned CPU model from '{query}'. "
            f"Tip: Specify model name, e.g. --cpu \"owned:Ryzen 5 5600\" or --cpu \"owned:Core i7-13700K\"."
        )

    clean_ev = {
        "risk_score": 0,
        "red_flags": [],
        "warnings": [],
        "audit": None,
        "is_ai_approved": True,
        "is_ai_rejected": False,
    }
    return {
        "id": "owned_cpu",
        "summary": {"id": "owned_cpu", "title": f"Owned {c_info['model']}", "price": 0.0, "url": ""},
        "spec": c_info,
        "cpu": c_info,
        "model": c_info["model"],
        "socket": c_info["socket"],
        "price": 0.0,
        "fps_gaming": c_info["fps_gaming"],
        "fps_1pct_low": c_info.get("fps_1pct_low", round(c_info["fps_gaming"] * 0.73, 1)),
        "l3_cache_mb": c_info.get("l3_cache_mb", 32),
        "cb_r23_multi": c_info.get("cb_r23_multi", c_info["threads"] * 950),
        "cores": c_info["cores"],
        "threads": c_info["threads"],
        "tdp_watts": c_info.get("tdp_watts", 65),
        "gaming_watts": c_info.get("gaming_watts", 50),
        "discount_pct": 0.0,
        "url": "",
        "is_owned": True,
        "eval": clean_ev,
        "heuristic": clean_ev,
        "ai_eval": None,
    }


def resolve_owned_mobo(query: str) -> Dict[str, Any]:
    """Resolves exact specs for owned Motherboard, costing 0 ₴."""
    m_info = identify_motherboard(query)
    if not m_info:
        q_clean = query.strip().upper().replace(" ", "").replace("-", "")
        socket_defaults = {
            "AM5": {"model": "B650 Motherboard", "socket": "AM5", "chipset": "B650", "ddr_type": "DDR5", "vrm_tier": "B-Tier"},
            "AM4": {"model": "B550 Motherboard", "socket": "AM4", "chipset": "B550", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
            "LGA1700": {
                "model": "B760 Motherboard", "socket": "LGA1700", "chipset": "B760",
                "ddr_type": "DDR4" if "ddr4" in query.lower() else "DDR5", "vrm_tier": "B-Tier",
            },
            "LGA1851": {"model": "B860 Motherboard", "socket": "LGA1851", "chipset": "B860", "ddr_type": "DDR5", "vrm_tier": "B-Tier"},
            "LGA1200": {"model": "B560 Motherboard", "socket": "LGA1200", "chipset": "B560", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
            "LGA1151V2": {"model": "Z390 Motherboard", "socket": "LGA1151v2", "chipset": "Z390", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
            "LGA1151": {"model": "B250 Motherboard", "socket": "LGA1151", "chipset": "B250", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
            "LGA2011V3": {"model": "X99 Motherboard", "socket": "LGA2011-v3", "chipset": "X99", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
        }
        if q_clean in socket_defaults:
            m_info = dict(socket_defaults[q_clean])
        else:
            q_low = query.lower()
            for pat, chip, sock, ddr, vrm, _, _ in CHIPSET_SPECS:
                if re.search(pat, q_low):
                    m_info = {
                        "model": f"{chip} Motherboard",
                        "brand": "Generic",
                        "chipset": chip,
                        "socket": sock,
                        "ddr_type": ddr,
                        "vrm_tier": vrm,
                    }
                    break
    if not m_info:
        raise ValueError(
            f"Could not resolve owned Motherboard chipset or socket from '{query}'. "
            f"Tip: Specify chipset or socket, e.g. --mobo \"owned:B550\" or --mobo \"owned:AM5\"."
        )

    clean_ev = {
        "risk_score": 0,
        "red_flags": [],
        "warnings": [],
        "audit": None,
        "is_ai_approved": True,
        "is_ai_rejected": False,
    }
    return {
        "id": "owned_mobo",
        "summary": {"id": "owned_mobo", "title": f"Owned {m_info['model']}", "price": 0.0, "url": ""},
        "spec": m_info,
        "mobo": m_info,
        "model": m_info["model"],
        "socket": m_info["socket"],
        "chipset": m_info.get("chipset", "Generic"),
        "ddr_type": m_info["ddr_type"],
        "vrm_tier": m_info.get("vrm_tier", "B-Tier"),
        "price": 0.0,
        "discount_pct": 0.0,
        "url": "",
        "is_owned": True,
        "eval": clean_ev,
        "heuristic": clean_ev,
        "ai_eval": None,
    }


def resolve_owned_ram(query: str) -> Dict[str, Any]:
    """Resolves exact specs for owned Desktop RAM kit, costing 0 ₴."""
    r_info = identify_ram(query)
    q_low = query.lower()
    gen = "DDR5" if "ddr5" in q_low else "DDR4"
    if r_info:
        mod_cnt = r_info.get("module_count", 1)
        if mod_cnt < 2 and not ("1x" in q_low or "single" in q_low):
            mod_cnt = 2
        total_gb = r_info["total_gb"]
        gen = r_info["generation"]
        speed = r_info["speed_mhz"]
        lat = r_info.get("latency_ns", 10.0)
    else:
        total_gb = 32 if ("32" in q_low or gen == "DDR5") else (64 if "64" in q_low else 16)
        speed = 6000 if gen == "DDR5" else 3200
        cl = 36 if gen == "DDR5" else 16
        lat = round((cl * 2000.0) / speed, 1)
        mod_cnt = 2

    clean_ev = {
        "risk_score": 0,
        "red_flags": [],
        "warnings": [],
        "audit": None,
        "is_ai_approved": True,
        "is_ai_rejected": False,
    }
    spec_dict = {
        "model": f"{total_gb}GB {gen}-{speed}",
        "generation": gen,
        "total_gb": total_gb,
        "speed_mhz": speed,
        "latency_ns": lat,
        "module_count": mod_cnt,
        "form_factor": "UDIMM",
        "risk_level": "LOW",
    }
    return {
        "id": "owned_ram",
        "summary": {"id": "owned_ram", "title": f"Owned {spec_dict['model']}", "price": 0.0, "url": ""},
        "spec": spec_dict,
        "ram": spec_dict,
        "model": spec_dict["model"],
        "gen": gen,
        "total_gb": total_gb,
        "speed_mhz": speed,
        "price": 0.0,
        "discount_pct": 0.0,
        "url": "",
        "is_owned": True,
        "eval": clean_ev,
        "heuristic": clean_ev,
        "ai_eval": None,
    }


def resolve_owned_psu(query: str) -> Dict[str, Any]:
    """Resolves exact specs for owned Power Supply Unit, costing 0 ₴."""
    p_info = identify_psu(query)
    q_low = query.lower()
    if p_info:
        wattage = p_info["wattage"]
        eff = p_info.get("efficiency", "Standard")
        tier = p_info.get("vrm_tier", "Tier B")
        model = p_info["model"]
    else:
        m_w = re.search(r"(\d{3,4})\s*w?", q_low)
        wattage = int(m_w.group(1)) if m_w else 750
        eff = "Gold" if "gold" in q_low else ("Platinum" if "plat" in q_low else "Bronze")
        tier = "Tier A" if ("tier a" in q_low or "seasonic" in q_low or "corsair rm" in q_low) else "Tier B"
        model = f"Owned {wattage}W {eff}"

    if tier == "Tier C" and ("gold" in q_low or "seasonic" in q_low or "corsair" in q_low or "be quiet" in q_low):
        tier = "Tier B"
    elif tier == "Tier C" and not any(haz in q_low for haz in ("kcas", "vx", "p750gm")):
        tier = "Tier B"

    clean_ev = {
        "risk_score": 0,
        "red_flags": [],
        "warnings": [],
        "audit": None,
        "is_ai_approved": True,
        "is_ai_rejected": False,
    }
    spec_dict = {
        "model": model,
        "wattage": wattage,
        "efficiency": eff,
        "vrm_tier": tier,
        "tier": tier,
        "form_factor": "ATX",
        "has_12vhpwr": bool("12vhpwr" in q_low or "atx3" in q_low or "atx 3" in q_low),
        "risk_level": "LOW",
    }
    return {
        "id": "owned_psu",
        "summary": {"id": "owned_psu", "title": f"Owned {model}", "price": 0.0, "url": ""},
        "spec": spec_dict,
        "psu": spec_dict,
        "model": model,
        "wattage": wattage,
        "tier": tier,
        "efficiency": eff,
        "price": 0.0,
        "discount_pct": 0.0,
        "url": "",
        "is_owned": True,
        "eval": clean_ev,
        "heuristic": clean_ev,
        "ai_eval": None,
    }


def _evaluate_listing(
    item: Dict[str, Any],
    spec: Dict[str, Any],
    detector: Any,
    re_audit: bool = False,
) -> Dict[str, Any]:
    """Runs heuristic analysis and checks persistent AuditLedger in O(1)."""
    offer_id = str(item.get("id", ""))
    desc = item.get("description") or (item.get("raw") or {}).get("description", "")
    price = float(item.get("price", 0.0))
    title = item.get("title", "")
    detail = item.get("detail") or item.get("raw") or {"description": desc}

    has_deliv = item.get("has_olx_delivery", True)
    audit_rec = None
    if not re_audit:
        audit_rec = ledger.get_audit(
            offer_id,
            title=title,
            price=price,
            description=desc,
            has_delivery=has_deliv,
        )

    heur = detector.analyze_listing(item, detail, spec)
    is_approved = bool(audit_rec and audit_rec.get("verdict") == "APPROVED")
    return {
        "risk_score": (
            0 if is_approved
            else int(heur.get("risk_score", 0))
        ),
        "red_flags": [] if is_approved else heur.get("red_flags", []),
        "warnings": heur.get("warnings", []),
        "audit": audit_rec,
        "is_ai_approved": is_approved,
        "is_ai_rejected": bool(audit_rec and audit_rec.get("verdict") == "REJECTED"),
    }


def _extract_item_condition(item: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Extracts (is_new, condition, condition_label) safely without returning 'None' strings."""
    is_new = bool(item.get("is_new") or item.get("condition") == "new")
    cond = str(item.get("condition") or ("new" if is_new else "used")).lower()
    raw_lbl = item.get("condition_label")
    if raw_lbl:
        cond_lbl = str(raw_lbl)
    elif is_new or cond == "new":
        cond_lbl = "new"
    elif cond == "refurbished":
        cond_lbl = "refurbished / outlet"
    elif cond in ("for_parts", "not_working"):
        cond_lbl = "for parts"
    else:
        cond_lbl = "used"
    return is_new, cond, cond_lbl


def _passes_mode_gate(
    category: str,
    cand: Dict[str, Any],
    profile: ModeProfile,
) -> bool:
    """Applies universal defect blocks and mode-specific hardware safety gates."""
    if cand.get("condition") in ("for_parts", "not_working"):
        return False

    ev = cand.get("eval") or cand.get("heuristic") or {}
    if ev.get("is_ai_rejected"):
        return False

    is_approved = ev.get("is_ai_approved")
    if not is_approved:
        flags = ev.get("red_flags") or []
        if flags:
            # Never allow unverified broken, donor, mining-rig bulk, missing-cables, or prepayment-trap parts into builds
            return False

        risk = ev.get("risk_score", 0)
        if risk > profile.max_risk:
            return False
    else:
        # Human/AI/script approved items bypass heuristic red flags and risk restrictions
        risk = 0 if is_approved else ev.get("risk_score", 0)
        if risk > profile.max_risk:
            return False

    spec = cand.get("spec") or {}
    arch_risk = spec.get("risk_level", "LOW")
    if profile.name == "safe" and arch_risk in ("CRITICAL", "HIGH"):
        return False
    if profile.block_critical_arch and arch_risk == "CRITICAL":
        return False

    if profile.form_factors and category in ("mobo", "psu"):
        ff = spec.get("form_factor", "")
        if ff and ff not in profile.form_factors:
            return False

    if category == "psu":
        p_tier = spec.get("vrm_tier", "Tier C")
        t_rank = PSU_TIER_RANK.get(p_tier, 2)
        min_rank = PSU_TIER_RANK.get(profile.min_psu_tier, 2)
        if p_tier == "Tier D":
            return False
        if profile.name in ("safe", "best") and t_rank < min_rank:
            return False

    return True


def _select_pareto_gpus(
    gpus: List[Dict[str, Any]],
    profile: ModeProfile,
    max_total: int = 48,
) -> List[Dict[str, Any]]:
    """
    Selects up to `max_total` Pareto-optimal GPU candidates:
    - Top 2 listings per distinct GPU model (avoids flooding with 25 identical RX 580s)
    - Balanced across price tiers so both mid-range and flagship GPUs remain reachable
    """
    for g in gpus:
        g["mode_score"] = score_component("gpu", g, profile)

    by_model: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for g in gpus:
        by_model[g["model"]].append(g)

    champions: List[Dict[str, Any]] = []
    for _, items in by_model.items():
        items.sort(key=lambda x: (-x.get("mode_score", 0.0), x.get("price", 0.0), (x.get("eval") or {}).get("risk_score", 0)))
        champions.extend(items[:2])

    champions.sort(key=lambda x: (-x["mode_score"], -x["fps_1440p"], x["price"]))
    if len(champions) <= max_total:
        return champions

    # Preserve top mode-scored cards AND top FPS ceiling cards within budget
    selected_ids = set()
    selected: List[Dict[str, Any]] = []
    for g in champions[: max_total - 10]:
        selected_ids.add(g["id"])
        selected.append(g)

    by_raw_fps = sorted(champions, key=lambda x: (-x["fps_1440p"], x["price"]))
    for g in by_raw_fps:
        if len(selected) >= max_total:
            break
        if g["id"] not in selected_ids:
            selected_ids.add(g["id"])
            selected.append(g)

    return selected


def _select_pareto_cpus(
    cpus: List[Dict[str, Any]],
    profile: ModeProfile,
    max_total: int = 52,
) -> List[Dict[str, Any]]:
    """Selects top 2 listings per CPU model while preserving socket, 1%-low (X3D), value sweet-spots, and workstation champions."""
    for c in cpus:
        c["mode_score"] = score_component("cpu", c, profile)

    by_model: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cpus:
        by_model[c["model"]].append(c)

    champions: List[Dict[str, Any]] = []
    for _, items in by_model.items():
        items.sort(key=lambda x: (-x.get("mode_score", 0.0), x.get("price", 0.0), (x.get("eval") or {}).get("risk_score", 0)))
        champions.extend(items[:2])

    champions.sort(key=lambda x: (-x["mode_score"], -x["fps_gaming"], x["price"]))
    if len(champions) <= max_total:
        return champions

    selected_ids = set()
    selected: List[Dict[str, Any]] = []

    # 1. Guarantee top champions per socket: both peak performance and price-to-performance sweet spots
    by_sock: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in champions:
        by_sock[c["socket"]].append(c)
    for sock, s_items in by_sock.items():
        quota = 7 if sock in ("AM5", "LGA1700", "AM4", "LGA1851") else 4
        # Peak performance / mode_score
        s_items.sort(key=lambda x: (-x["mode_score"], x["price"]))
        for c in s_items[:quota]:
            if len(selected) < max_total and c["id"] not in selected_ids:
                selected_ids.add(c["id"])
                selected.append(c)
        # Price-to-performance sweet spot (gaming FPS per ₴)
        s_items_by_val = sorted(s_items, key=lambda x: (-(x["fps_gaming"] / max(1.0, x["price"])), x["price"]))
        for c in s_items_by_val[:quota]:
            if len(selected) < max_total and c["id"] not in selected_ids:
                selected_ids.add(c["id"])
                selected.append(c)

    # 2. Preserve highest 1%-low / gaming-FPS CPUs (X3D & flagship) so high-tier GPUs always have top partners
    for c in sorted(
        champions,
        key=lambda x: (-x["spec"].get("fps_1pct_low", x["fps_gaming"] * 0.73), -x["fps_gaming"], x["price"]),
    )[:10]:
        if len(selected) < max_total and c["id"] not in selected_ids:
            selected_ids.add(c["id"])
            selected.append(c)

    # 3. Preserve top multi-core Cinebench R23 champions for workstation/creator profiles
    for c in sorted(
        champions,
        key=lambda x: (-x["spec"].get("cb_r23_multi", x["threads"] * 950), x["price"]),
    )[:6]:
        if len(selected) < max_total and c["id"] not in selected_ids:
            selected_ids.add(c["id"])
            selected.append(c)

    # 4. Fill remaining slots by overall mode_score
    for c in champions:
        if len(selected) >= max_total:
            break
        if c["id"] not in selected_ids:
            selected_ids.add(c["id"])
            selected.append(c)

    return selected


def _select_pareto_mobos(
    mobos: List[Dict[str, Any]],
    profile: ModeProfile,
    per_socket_ddr: int = 7,
) -> Dict[str, List[Dict[str, Any]]]:
    """Groups motherboards by socket and keeps Pareto-optimal boards per (ddr_type, vrm_tier)."""
    for m in mobos:
        m["mode_score"] = score_component("mobo", m, profile)

    by_sock_ddr: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for m in mobos:
        by_sock_ddr[(m["socket"], m["ddr_type"])].append(m)

    by_socket: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for (sock, _), items in by_sock_ddr.items():
        # Best per VRM tier + cheapest per VRM tier + lowest price fallback + highest mode_score
        items.sort(key=lambda x: (-x["mode_score"], x["price"]))
        picked: List[Dict[str, Any]] = []
        seen_ids = set()
        seen_tiers = set()
        for item in items:
            v_tier = item["spec"].get("vrm_tier", "B-Tier")
            if v_tier not in seen_tiers:
                seen_tiers.add(v_tier)
                seen_ids.add(item["id"])
                picked.append(item)
        # Ensure cheapest clean board per VRM tier (B-Tier, A-Tier, S-Tier) is included so builds don't overspend
        for target_tier in ("B-Tier", "A-Tier", "S-Tier"):
            tier_items = [x for x in items if x["spec"].get("vrm_tier", "B-Tier") == target_tier]
            if tier_items:
                cheapest_tier = min(tier_items, key=lambda x: x["price"])
                if cheapest_tier["id"] not in seen_ids and len(picked) < per_socket_ddr:
                    seen_ids.add(cheapest_tier["id"])
                    picked.append(cheapest_tier)
        # Ensure cheapest clean board overall is always included for tight budget combos
        cheapest = min(items, key=lambda x: x["price"])
        if cheapest["id"] not in seen_ids:
            seen_ids.add(cheapest["id"])
            picked.append(cheapest)
        for item in items:
            if len(picked) >= per_socket_ddr:
                break
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                picked.append(item)
        by_socket[sock].extend(picked)

    return by_socket


def _select_pareto_rams(
    rams: List[Dict[str, Any]],
    profile: ModeProfile,
    per_ddr: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    """Groups desktop UDIMM RAM by DDR generation and guarantees 16GB & 32GB kits are always represented."""
    for r in rams:
        r["mode_score"] = score_component("ram", r, profile)

    by_ddr: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rams:
        gen = r.get("gen") or r.get("ddr_type") or (r.get("spec") or {}).get("generation") or (r.get("ram") or {}).get("generation", "DDR4")
        r["gen"] = gen
        by_ddr[gen].append(r)

    out: Dict[str, List[Dict[str, Any]]] = {}
    for ddr, items in by_ddr.items():
        picked: List[Dict[str, Any]] = []
        seen_ids = set()
        by_cap: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for item in items:
            cap = item.get("total_gb") or (item.get("spec") or {}).get("total_gb") or (item.get("spec") or {}).get("capacity_gb") or (item.get("ram") or {}).get("total_gb", 16)
            item["total_gb"] = cap
            by_cap[cap].append(item)

        # Priority 1: Always preserve cheapest & top-scored 16GB, 24GB (2x12GB), and 32GB dual-channel kits
        for priority_cap in (16, 24, 32):
            cap_items = by_cap.get(priority_cap, [])
            if not cap_items:
                continue
            cap_items.sort(key=lambda x: (-x["mode_score"], x["price"]))
            for ci in cap_items[:2]:
                if ci["id"] not in seen_ids:
                    seen_ids.add(ci["id"])
                    picked.append(ci)
            cheapest_cap = min(cap_items, key=lambda x: x["price"])
            if cheapest_cap["id"] not in seen_ids:
                seen_ids.add(cheapest_cap["id"])
                picked.append(cheapest_cap)
            dual_items = [x for x in cap_items if x["spec"].get("module_count", 1) == 2]
            if dual_items:
                cheapest_dual = min(dual_items, key=lambda x: x["price"])
                if cheapest_dual["id"] not in seen_ids:
                    seen_ids.add(cheapest_dual["id"])
                    picked.append(cheapest_dual)

        # Priority 2: Fill remaining slots with 48GB/64GB/8GB or highest mode_score kits
        for cap, cap_items in sorted(by_cap.items()):
            if cap in (16, 24, 32):
                continue
            cap_items.sort(key=lambda x: (-x["mode_score"], x["price"]))
            for ci in cap_items[:2]:
                if len(picked) < per_ddr and ci["id"] not in seen_ids:
                    seen_ids.add(ci["id"])
                    picked.append(ci)

        out[ddr] = picked[:per_ddr]
    return out


def _select_pareto_psus(
    psus: List[Dict[str, Any]],
    profile: ModeProfile,
    max_total: int = 18,
) -> List[Dict[str, Any]]:
    """Keeps best PSU per (wattage_bucket, vrm_tier) plus cheapest clean units."""
    for p in psus:
        p["mode_score"] = score_component("psu", p, profile)

    buckets: Dict[Tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
    for p in psus:
        wattage = int(p.get("wattage") or p.get("watts") or (p.get("spec") or {}).get("wattage", 500))
        tier = p.get("tier") or (p.get("spec") or {}).get("tier", "Tier C")
        p["wattage"] = wattage
        p["tier"] = tier
        w_bucket = (wattage // 100) * 100
        buckets[(w_bucket, tier)].append(p)

    picked: List[Dict[str, Any]] = []
    seen_ids = set()
    for _, items in sorted(buckets.items()):
        items.sort(key=lambda x: (-x["mode_score"], x["price"]))
        best_p = items[0]
        seen_ids.add(best_p["id"])
        picked.append(best_p)
        cheapest_p = min(items, key=lambda x: x["price"])
        if cheapest_p["id"] not in seen_ids:
            seen_ids.add(cheapest_p["id"])
            picked.append(cheapest_p)

    picked.sort(key=lambda x: (-x["mode_score"], x["price"]))
    return picked[:max_total]


def synthesize_builds(
    gpus: List[Dict[str, Any]],
    cpus: List[Dict[str, Any]],
    mobos: List[Dict[str, Any]],
    rams: List[Dict[str, Any]],
    psus: List[Dict[str, Any]],
    budget: float,
    profile: ModeProfile,
    top_n: int = 3,
    excluded_ids: Optional[set] = None,
    bundles: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Runs Pareto-pruned combinatorial synthesis across all 5 categories (plus optional
    multi-component bundles and prebuilt PCs) and returns up to `top_n` distinct,
    highest-scoring PC builds under `profile`.
    """
    excluded = excluded_ids or set()

    g_pool = _select_pareto_gpus([x for x in gpus if x["id"] not in excluded], profile, max_total=36) if gpus else []
    c_pool = _select_pareto_cpus([x for x in cpus if x["id"] not in excluded], profile, max_total=52) if cpus else []
    m_by_sock = _select_pareto_mobos([x for x in mobos if x["id"] not in excluded], profile, per_socket_ddr=7) if mobos else {}
    r_by_ddr = _select_pareto_rams([x for x in rams if x["id"] not in excluded], profile, per_ddr=10) if rams else {}
    p_pool = _select_pareto_psus([x for x in psus if x["id"] not in excluded], profile, max_total=16) if psus else []
    active_bundles = [b for b in (bundles or []) if b.get("id") not in excluded]

    has_standalone_pools = bool(g_pool and c_pool and m_by_sock and r_by_ddr and p_pool)
    if not has_standalone_pools and not active_bundles:
        return []

    # Pre-compute UAH prices on all Pareto candidates once to avoid repeated currency lookups in inner loop
    sample_curr = (
        (g_pool[0].get("currency") if g_pool else None)
        or ((g_pool[0].get("summary") or {}).get("currency") if g_pool else None)
        or (c_pool[0].get("currency") if c_pool else None)
        or (next(iter(active_bundles[0]["components"].values())).get("currency") if active_bundles else None)
        or "UAH"
    )
    from extensions.pc.modes import _infer_uah_price
    curr_mult = 1.0 if (not sample_curr or sample_curr in ("UAH", "uah", "₴", "грн")) else _infer_uah_price(1.0, sample_curr)
    budget_uah = max(1.0, float(budget) * curr_mult)
    for pool_list in (g_pool, c_pool, p_pool, *[ v for v in m_by_sock.values() ], *[ v for v in r_by_ddr.values() ]):
        for item in pool_list:
            item["_price_uah"] = float(item.get("_allocated_price", item.get("price", 0.0))) * curr_mult

    p_by_price = sorted(p_pool, key=lambda x: x["price"]) if p_pool else []
    min_psu_price = p_by_price[0]["price"] if p_by_price else 0.0

    # Pre-compute minimum possible (mobo + ram + psu) floor per socket for fast branch-and-bound pruning
    socket_min_floor: Dict[str, float] = {}
    for sock, sock_mobos in m_by_sock.items():
        best_floor = float("inf")
        for m in sock_mobos:
            ddr_rams = r_by_ddr.get(m["ddr_type"])
            if ddr_rams:
                min_r = min(r["price"] for r in ddr_rams)
                best_floor = min(best_floor, m["price"] + min_r + min_psu_price)
        if best_floor < float("inf"):
            socket_min_floor[sock] = best_floor

    best_by_archetype: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

    if has_standalone_pools:
        for g in g_pool:
            g_price = g["price"]
            g_tdp = g.get("tdp_watts", (g.get("spec") or {}).get("tdp_w", 200))
            headroom = 160 if g_tdp >= 250 else 130
            min_gpu_psu = (
                850 if g_tdp >= 400
                else 750 if g_tdp >= 320
                else 700 if g_tdp >= 275
                else 650 if g_tdp >= 220
                else 500
            )

            for c in c_pool:
                c_spec = c["spec"]
                c_cores = int(c.get("cores", c_spec.get("cores", 6)))
                if c_cores < 6 and g["fps_1440p"] >= 65 and profile.name != "budget-king":
                    continue
                is_x3d = bool(c_spec.get("is_x3d") or "X3D" in c["model"].upper())
                c_low = float(c_spec.get("fps_1pct_low", c["fps_gaming"] * (0.775 if is_x3d else 0.73)))
                c_l3 = float(c_spec.get("l3_cache_mb", 96.0 if is_x3d else 32.0))

                # L3 cache and strong 1% Low floor lift effective CPU gaming throughput
                effective_cpu_floor = c["fps_gaming"] * 0.60 + (c_low * 1.35) * 0.40

                min_floor_mult = (
                    0.95 if profile.name in ("future-proof", "ai-workstation")
                    else 1.02 if profile.name == "deal-hunter"
                    else 1.05
                )
                if effective_cpu_floor < (g["fps_1440p"] * min_floor_mult):
                    continue

                sock = c["socket"]
                floor = socket_min_floor.get(sock)
                if floor is None:
                    continue
                if g_price + c["price"] + floor > budget:
                    continue

                c_tdp = c.get("tdp_watts", (c_spec or {}).get("tdp_w", 65))
                req_watts = max(min_gpu_psu, int(g_tdp + c_tdp + headroom))
                valid_psus = [p for p in p_pool if p["wattage"] >= req_watts]
                if not valid_psus:
                    continue

                # Evaluate up to 2 PSU choices: highest mode-scored valid PSU and cheapest valid PSU
                psu_choices = [valid_psus[0]]
                cheapest_valid_psu = min(valid_psus, key=lambda x: x["price"])
                if cheapest_valid_psu["id"] != valid_psus[0]["id"]:
                    psu_choices.append(cheapest_valid_psu)

                max_sock_dimms = 8 if sock == "LGA2011-v3" else 4
                c_lanes = c_spec.get("pcie_lanes_gpu", 16)
                c_game_w = c_spec.get("gaming_watts", int(c_tdp * 0.72))
                est_load = int(g_tdp + c_game_w + 55)

                for m in m_by_sock[sock]:
                    # Block putting 125W+ CPUs onto bare D-Tier VRM boards, and 200W+ unlocked i7/i9s onto sub-A-Tier boards
                    vrm_tier = m["spec"].get("vrm_tier", "B-Tier")
                    if c_tdp >= 125 and vrm_tier == "D-Tier":
                        continue
                    if c_tdp >= 200 and vrm_tier not in ("S-Tier", "A-Tier"):
                        continue
                    ddr_rams = r_by_ddr.get(m["ddr_type"])
                    if not ddr_rams:
                        continue

                    partial_cost = g_price + c["price"] + m["price"]
                    if partial_cost + min_psu_price > budget:
                        continue

                    is_two_dimm_board = (
                        m["spec"].get("form_factor") == "ITX"
                        or m.get("chipset") in TWO_DIMM_CHIPSETS
                    )
                    max_board_dimms = 2 if is_two_dimm_board else max_sock_dimms

                    for r in ddr_rams:
                        mod_cnt = r["spec"].get("module_count", 2)
                        if mod_cnt < 2 or mod_cnt > max_board_dimms:
                            continue
                        rcost = partial_cost + r["price"]
                        if rcost > budget:
                            continue

                        is_ddr5 = (r.get("gen") == "DDR5" or r["spec"].get("generation") == "DDR5")
                        eff_1440, eff_1080, cpu_ratio = compute_effective_build_fps(
                            g["fps_1440p"], g["fps_1080p"], c["fps_gaming"],
                            cpu_1pct_low=c_low,
                            l3_cache_mb=c_l3,
                            ram_latency_ns=r["spec"].get("latency_ns", 10.0),
                            pcie_lanes_gpu=c_lanes,
                            is_ddr5=is_ddr5,
                        )

                        for p in psu_choices:
                            total_cost = rcost + p["price"]
                            if total_cost > budget:
                                continue

                            cand_build = {
                                "gpu": g,
                                "cpu": c,
                                "mobo": m,
                                "ram": r,
                                "psu": p,
                                "total_cost": total_cost,
                                "_total_cost_uah": max(1.0, total_cost * curr_mult),
                                "_budget_uah": budget_uah,
                                "surplus": budget - total_cost,
                                "req_watts": req_watts,
                                "est_load_watts": est_load,
                                "eff_fps_1440p": eff_1440,
                                "eff_fps_1080p": eff_1080,
                                "cpu_ratio": cpu_ratio,
                            }
                            b_score = score_build(cand_build, budget, profile)
                            cand_build["build_score"] = b_score

                            archetype = (g["model"], c["model"], sock, r["gen"])
                            prev = best_by_archetype.get(archetype)
                            if prev is None or b_score > prev["build_score"]:
                                best_by_archetype[archetype] = cand_build

    # Synthesize builds incorporating multi-component bundles and complete Prebuilt PCs
    for b in active_bundles:
        b_comps = b["components"]
        is_prebuilt = bool(b.get("is_prebuilt"))
        for b_comp in b_comps.values():
            if "_price_uah" not in b_comp or not b_comp["_price_uah"]:
                b_comp["_price_uah"] = float(b_comp.get("_allocated_price", b_comp.get("price", 0.0))) * curr_mult

        b_gpus = [b_comps["gpu"]] if "gpu" in b_comps else g_pool
        b_cpus = [b_comps["cpu"]] if "cpu" in b_comps else c_pool
        if not (b_gpus and b_cpus):
            continue

        for g in b_gpus:
            g_price = g["price"]
            g_tdp = g.get("tdp_watts", (g.get("spec") or {}).get("tdp_w", 200))
            headroom = 160 if g_tdp >= 250 else 130
            min_gpu_psu = (
                850 if g_tdp >= 400
                else 750 if g_tdp >= 320
                else 700 if g_tdp >= 275
                else 650 if g_tdp >= 220
                else 500
            )

            for c in b_cpus:
                c_spec = c["spec"]
                c_cores = int(c.get("cores", c_spec.get("cores", 6)))
                if not is_prebuilt and c_cores < 6 and g["fps_1440p"] >= 65 and profile.name != "budget-king":
                    continue
                is_x3d = bool(c_spec.get("is_x3d") or "X3D" in c["model"].upper())
                c_low = float(c_spec.get("fps_1pct_low", c["fps_gaming"] * (0.775 if is_x3d else 0.73)))
                c_l3 = float(c_spec.get("l3_cache_mb", 96.0 if is_x3d else 32.0))
                effective_cpu_floor = c["fps_gaming"] * 0.60 + (c_low * 1.35) * 0.40

                min_floor_mult = (
                    0.82 if is_prebuilt
                    else 0.95 if profile.name in ("future-proof", "ai-workstation")
                    else 1.02 if profile.name == "deal-hunter"
                    else 1.05
                )
                if effective_cpu_floor < (g["fps_1440p"] * min_floor_mult):
                    continue

                sock = c["socket"]
                if "mobo" in b_comps:
                    if b_comps["mobo"]["socket"] != sock:
                        continue
                    b_mobos = [b_comps["mobo"]]
                else:
                    b_mobos = m_by_sock.get(sock, [])
                if not b_mobos:
                    continue

                c_tdp = c.get("tdp_watts", (c_spec or {}).get("tdp_w", 65))
                req_watts = max(min_gpu_psu, int(g_tdp + c_tdp + headroom))
                if "psu" in b_comps:
                    bp = b_comps["psu"]
                    # If user owns a higher-wattage PSU on a Prebuilt PC, allow upgrading PSU slot at 0 cost
                    if is_prebuilt and p_pool and len(p_pool) == 1 and p_pool[0].get("is_owned") and p_pool[0]["wattage"] > bp["wattage"]:
                        psu_choices = [p_pool[0]]
                    elif bp["wattage"] >= req_watts or (is_prebuilt and bp["wattage"] >= int(g_tdp + c_tdp + 80)):
                        psu_choices = [bp]
                    else:
                        continue
                else:
                    valid_psus = [p for p in p_pool if p["wattage"] >= req_watts]
                    if not valid_psus:
                        continue
                    psu_choices = [valid_psus[0]]
                    cheapest_valid_psu = min(valid_psus, key=lambda x: x["price"])
                    if cheapest_valid_psu["id"] != valid_psus[0]["id"]:
                        psu_choices.append(cheapest_valid_psu)

                max_sock_dimms = 8 if sock == "LGA2011-v3" else 4
                c_lanes = c_spec.get("pcie_lanes_gpu", 16)
                c_game_w = c_spec.get("gaming_watts", int(c_tdp * 0.72))
                est_load = int(g_tdp + c_game_w + 55)

                for m in b_mobos:
                    vrm_tier = m["spec"].get("vrm_tier", "B-Tier")
                    if not is_prebuilt:
                        if c_tdp >= 125 and vrm_tier == "D-Tier":
                            continue
                        if c_tdp >= 200 and vrm_tier not in ("S-Tier", "A-Tier"):
                            continue

                    if "ram" in b_comps:
                        if b_comps["ram"]["gen"] != m["ddr_type"]:
                            continue
                        ddr_rams = [b_comps["ram"]]
                    else:
                        ddr_rams = r_by_ddr.get(m["ddr_type"], [])
                    if not ddr_rams:
                        continue

                    partial_cost = g_price + c["price"] + m["price"]
                    if partial_cost > budget:
                        continue

                    is_two_dimm_board = (
                        m["spec"].get("form_factor") == "ITX"
                        or m.get("chipset") in TWO_DIMM_CHIPSETS
                    )
                    max_board_dimms = 2 if is_two_dimm_board else max_sock_dimms

                    for r in ddr_rams:
                        mod_cnt = r["spec"].get("module_count", 2)
                        if not is_prebuilt and (mod_cnt < 2 or mod_cnt > max_board_dimms):
                            continue
                        rcost = partial_cost + r["price"]
                        if rcost > budget:
                            continue

                        is_ddr5 = (r.get("gen") == "DDR5" or r["spec"].get("generation") == "DDR5")
                        eff_1440, eff_1080, cpu_ratio = compute_effective_build_fps(
                            g["fps_1440p"], g["fps_1080p"], c["fps_gaming"],
                            cpu_1pct_low=c_low,
                            l3_cache_mb=c_l3,
                            ram_latency_ns=r["spec"].get("latency_ns", 10.0),
                            pcie_lanes_gpu=c_lanes,
                            is_ddr5=is_ddr5,
                        )

                        for p in psu_choices:
                            total_cost = rcost + p["price"]
                            if total_cost > budget:
                                continue

                            cand_build = {
                                "gpu": g,
                                "cpu": c,
                                "mobo": m,
                                "ram": r,
                                "psu": p,
                                "total_cost": total_cost,
                                "_total_cost_uah": max(1.0, total_cost * curr_mult),
                                "_budget_uah": budget_uah,
                                "surplus": budget - total_cost,
                                "req_watts": req_watts,
                                "est_load_watts": est_load,
                                "eff_fps_1440p": eff_1440,
                                "eff_fps_1080p": eff_1080,
                                "cpu_ratio": cpu_ratio,
                                "is_bundle_build": True,
                                "is_prebuilt": is_prebuilt,
                                "bundle_label": b.get("bundle_label"),
                                "bundle_id": b.get("id"),
                                "bundle_categories": b.get("categories"),
                            }
                            b_score = score_build(cand_build, budget, profile)
                            cand_build["build_score"] = b_score

                            archetype = (g["model"], c["model"], sock, r["gen"])
                            prev = best_by_archetype.get(archetype)
                            if prev is None or b_score > prev["build_score"]:
                                best_by_archetype[archetype] = cand_build

    if not best_by_archetype:
        return []

    all_builds = list(best_by_archetype.values())
    has_owned_parts = any(
        b.get(cat, {}).get("is_owned")
        for b in all_builds
        for cat in ALL_CATEGORIES
    )
    # In modern/flagship/workstation modes, prefer builds utilizing >=70% of budget when available (skip if parts are owned)
    if not has_owned_parts and profile.name not in ("value", "deal-hunter", "budget-king"):
        min_util = (
            0.70
            if profile.name in ("best", "max-perf", "sweet-spot", "esports", "future-proof", "ai-workstation", "4k-ultra", "creator-pro")
            else 0.62
        )
        # Protect exceptional high-performing bargain builds from being discarded by hard cutoff (Option 2A)
        max_pool_fps = max((b.get("eff_fps_1440p", 0.0) for b in all_builds), default=0.0)
        well_utilized = [
            b for b in all_builds
            if b["total_cost"] >= budget * min_util or b.get("eff_fps_1440p", 0.0) >= max_pool_fps * 0.92
        ]
        if well_utilized:
            all_builds = well_utilized

    all_builds.sort(key=lambda b: (-b["build_score"], -b["eff_fps_1440p"], b["total_cost"]))

    # Select diverse top_n builds:
    # 1. Enforce distinct CPU models so we never duplicate a CPU with a strictly worse GPU.
    # 2. Allow top GPU to be featured across distinct platforms (max 2 per GPU model when alternatives exist).
    # 3. Always maintain distinct (GPU model, CPU model) pairs.
    final_builds: List[Dict[str, Any]] = []
    seen_pairs: set = set()
    seen_cpus: set = set()
    gpu_model_counts: Dict[str, int] = {}
    distinct_gpus = len({b["gpu"]["model"] for b in all_builds})
    max_per_gpu = max(1, min(2, top_n - 1)) if distinct_gpus > 1 and top_n > 1 else top_n

    for b in all_builds:
        g_mod = b["gpu"]["model"]
        c_mod = b["cpu"]["model"]
        pair = (g_mod, c_mod)

        if pair in seen_pairs:
            continue
        if c_mod in seen_cpus:
            continue
        if gpu_model_counts.get(g_mod, 0) >= max_per_gpu:
            continue

        seen_pairs.add(pair)
        seen_cpus.add(c_mod)
        gpu_model_counts[g_mod] = gpu_model_counts.get(g_mod, 0) + 1
        final_builds.append(b)
        if len(final_builds) >= top_n:
            break

    # Second pass: distinct (GPU model, CPU model) pairs if fewer than top_n distinct CPUs fit
    if len(final_builds) < top_n:
        for b in all_builds:
            pair_key = (b["gpu"]["model"], b["cpu"]["model"])
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            final_builds.append(b)
            if len(final_builds) >= top_n:
                break

    # Third pass: fill from remaining distinct component archetypes if still under top_n
    if len(final_builds) < top_n:
        used_keys = {(x["gpu"]["id"], x["cpu"]["id"], x["mobo"]["id"]) for x in final_builds}
        for b in all_builds:
            k = (b["gpu"]["id"], b["cpu"]["id"], b["mobo"]["id"])
            if k not in used_keys:
                used_keys.add(k)
                final_builds.append(b)
                if len(final_builds) >= top_n:
                    break

    return final_builds


def _audit_winning_builds_live(
    builds: List[Dict[str, Any]],
    client: MarketClient,
    profile: ModeProfile,
    inspector: SystemAIInspector,
    re_audit: bool = False,
) -> set:
    """
    Audits synthesized builds holistically using SystemAIInspector,
    fetching live full listing descriptions and cross-checking the 4-pillar physics.
    Returns any listing IDs that were disqualified/rejected so clean replacements can be built.
    """
    all_ids = []
    for b in builds:
        for cat in ALL_CATEGORIES:
            part = b[cat]
            if not part.get("is_owned"):
                all_ids.append(str(part["id"]))

    unique_ids = list(dict.fromkeys(all_ids))
    if unique_ids:
        try:
            details_map = client.get_batch_details(unique_ids)
            for b in builds:
                for cat in ALL_CATEGORIES:
                    part = b[cat]
                    if not part.get("is_owned"):
                        pid = str(part["id"])
                        if pid in details_map:
                            part["detail"] = details_map[pid]
        except Exception as e:
            print(f"   Notice: Live details fetch ({e}) — continuing with cached descriptions.")

    return inspector.audit_builds(builds, mode=profile.name, re_audit=re_audit)


def run_build_optimizer(
    budget: Optional[float] = None,
    mode: str = "best",
    domain: str = "pc",
    weights: Optional[str] = None,
    socket: Optional[str] = None,
    min_threads: Optional[int] = None,
    max_risk: Optional[int] = None,
    gpu: Optional[str] = None,
    cpu: Optional[str] = None,
    mobo: Optional[str] = None,
    ram: Optional[str] = None,
    psu: Optional[str] = None,
    top_builds: int = 5,
    refresh: bool = False,
    ai_audit: bool = False,
    no_ai: bool = False,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    re_audit: bool = False,
    human_review: bool = False,
    ai_prescreen: bool = False,
    force_review: bool = False,
    human_only: Optional[bool] = None,
    review_candidates: Optional[Union[int, Dict[str, int]]] = None,
    input_func: Optional[Callable[[str], str]] = None,
    export_json: Optional[str] = None,
    candidate_pool: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    provider: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    t_start = time.perf_counter()

    from currency import get_active_currency, convert_currency, canonical_currency, normalize_candidate_pool, format_price
    active_curr = get_active_currency()
    if budget is not None:
        core_budget = float(budget)
    else:
        core_budget = 800.0 if canonical_currency(active_curr) in ("USDT", "USD") else convert_currency(800.0, "USDT", active_curr)

    effective_human_only = human_only if human_only is not None else bool(human_review)

    if domain and domain.lower() != "pc":
        from extension_registry import get_extension
        from set_synthesizer import print_domain_sets

        ext = get_extension(domain)
        layout = ext.get_layout()
        weights_reg = ext.get_weights_registry()
        scorer = ext.get_scorer()
        search_inst = ext.get_search_instruction()
        sorter = ext.get_sorter()
        profile = weights_reg.resolve_profile(mode, weights_override=weights)

        print(f"\n   Synthesizing {layout.title}")
        raw_cands = candidate_pool or search_inst.instruct_load_all(provider=provider, budget=core_budget, refresh=refresh)
        candidates = normalize_candidate_pool(raw_cands, target_currency=active_curr)

        counts = [f"{sec.label}s={len(candidates.get(sec.id, []))}" for sec in layout.sections]
        print(f"   Candidate pool: {' | '.join(counts)}")

        sets = sorter.sort_and_synthesize(
            layout=layout,
            scorer=scorer,
            profile=profile,
            candidate_pool=candidates,
            budget=core_budget,
            top_n=top_builds,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        if not sets:
            print(f"\nNo compatible sets could be synthesized within budget {format_price(core_budget, active_curr)}.")
            return []

        print_domain_sets(layout, profile, sets, elapsed_ms=elapsed_ms)

        if export_json:
            out_p = Path(export_json)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(sets, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Exported {len(sets)} set(s) to {out_p}")

        return sets

    # Heuristic detection when a caller/test passes a UAH budget (>= 5000) and a raw UAH candidate_pool
    effective_curr = active_curr
    if candidate_pool and core_budget >= 5000.0 and canonical_currency(active_curr) in ("USDT", "USD"):
        sample_prices = [
            float(it.get("price", 0))
            for items in candidate_pool.values()
            for it in items
            if not it.get("currency") and float(it.get("price", 0)) > 0
        ]
        if sample_prices and (sum(sample_prices) / len(sample_prices)) >= 400.0:
            effective_curr = "UAH"

    profile = resolve_mode(mode, default="best", weights_override=weights, max_risk_override=max_risk)
    budget_in_uah = convert_currency(core_budget, from_currency=effective_curr, to_currency="UAH")

    print("\n   Synthesizing PC Builds")

    # Parse locked & owned components
    gpu_owned, gpu_query = parse_target_query(gpu)
    cpu_owned, cpu_query = parse_target_query(cpu)
    mobo_owned, mobo_query = parse_target_query(mobo)
    ram_owned, ram_query = parse_target_query(ram)
    psu_owned, psu_query = parse_target_query(psu)

    cpu_cand = None
    if cpu_owned:
        cpu_cand = resolve_owned_cpu(cpu_query)
        if socket and socket.upper() != cpu_cand["socket"].upper():
            print(f"\nSocket conflict: Owned CPU '{cpu_cand['model']}' uses {cpu_cand['socket']}, but --socket was set to {socket}.")
            return []

    mobo_cand = None
    if mobo_owned:
        mobo_cand = resolve_owned_mobo(mobo_query)
        if socket and socket.upper() != mobo_cand["socket"].upper():
            print(f"\nSocket conflict: Owned Motherboard '{mobo_cand['model']}' uses {mobo_cand['socket']}, but --socket was set to {socket}.")
            return []
        if cpu_owned and mobo_cand["socket"].upper() != cpu_cand["socket"].upper():
            print(f"\nPlatform incompatibility: Owned CPU '{cpu_cand['model']}' ({cpu_cand['socket']}) cannot fit on owned Motherboard '{mobo_cand['model']}' ({mobo_cand['socket']}).")
            return []

    ram_cand = None
    if ram_owned:
        ram_cand = resolve_owned_ram(ram_query)
        if mobo_owned and ram_cand["gen"] != mobo_cand["ddr_type"]:
            print(f"\nMemory generation incompatibility: Owned RAM is {ram_cand['gen']}, but owned Motherboard requires {mobo_cand['ddr_type']}.")
            return []

    raw_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    if candidate_pool:
        raw_by_cat = normalize_candidate_pool(candidate_pool, target_currency=effective_curr)
    else:
        from extensions.pc.search import pc_search_instruction
        owned_skip = [
            cat for cat, is_o in (
                ("gpu", gpu_owned),
                ("cpu", cpu_owned),
                ("mobo", mobo_owned),
                ("ram", ram_owned),
                ("psu", psu_owned),
            )
            if is_o
        ]
        loaded_raw = pc_search_instruction.instruct_load_all(
            provider=provider,
            budget=core_budget,
            refresh=refresh,
            skip_categories=owned_skip,
        )
        raw_by_cat = normalize_candidate_pool(loaded_raw, target_currency=effective_curr)

    for cat in ALL_CATEGORIES:
        is_this_owned = (
            (cat == "gpu" and gpu_owned)
            or (cat == "cpu" and cpu_owned)
            or (cat == "mobo" and mobo_owned)
            or (cat == "ram" and ram_owned)
            or (cat == "psu" and psu_owned)
        )
        if is_this_owned:
            raw_by_cat[cat] = []

    gpu_det = GPUScamDetector()
    cpu_det = CPUScamDetector()
    mobo_det = MotherboardScamDetector()
    ram_det = RAMScamDetector()
    psu_det = PSUScamDetector()

    # Dynamic feasibility ceilings so high-tier GPUs & X3D CPUs are never artificially blocked,
    # while low-end legacy cards (e.g. 36 FPS GTX 1080 Ti) are pruned from high budgets (e.g. 46k ₴).
    if budget_in_uah < 10000:
        min_gpu_fps = 12
        min_gpu_price_uah = 1400
    elif budget_in_uah < 16000:
        min_gpu_fps = 14 if profile.name in ("budget-king", "value") else 18
        min_gpu_price_uah = 1800
    elif budget_in_uah < 25000:
        min_gpu_fps = 35
        min_gpu_price_uah = 3500
    elif budget_in_uah < 38000:
        min_gpu_fps = 45 if profile.name in ("budget-king", "value") else 52
        min_gpu_price_uah = 4500
    else:
        min_gpu_fps = 50 if profile.name in ("budget-king", "value") else 60
        min_gpu_price_uah = 6000

    min_gpu_price = convert_currency(min_gpu_price_uah, "UAH", effective_curr)

    min_other_cost_gpu_uah = 0.0
    if not cpu_owned:
        min_other_cost_gpu_uah += 500 if budget_in_uah < 10000 else (800 if budget_in_uah < 18000 else 1500)
    if not mobo_owned:
        min_other_cost_gpu_uah += 600 if budget_in_uah < 10000 else (900 if budget_in_uah < 18000 else 1300)
    if not ram_owned:
        min_other_cost_gpu_uah += 400 if budget_in_uah < 10000 else (600 if budget_in_uah < 16000 else 900)
    if not psu_owned:
        min_other_cost_gpu_uah += 500 if budget_in_uah < 10000 else (800 if budget_in_uah < 16000 else 1100)
    min_other_cost_gpu = convert_currency(min_other_cost_gpu_uah, "UAH", effective_curr)
    max_gpu_price = max(min_gpu_price + convert_currency(1000.0, "UAH", effective_curr), core_budget - min_other_cost_gpu)

    # 1. Classify GPUs
    gpu_list: List[Dict[str, Any]] = []
    if gpu_owned:
        gpu_cand = resolve_owned_gpu(gpu_query)
        gpu_cand["currency"] = effective_curr
        gpu_list = [gpu_cand]
        print(f"   Locked GPU (Owned): {gpu_cand['model']} (" + format_price(0, effective_curr) + ")")
    else:
        for item in raw_by_cat["gpu"]:
            # Sorter is site-agnostic: evaluates universal buyer protection (is_secure_deal)
            is_secure = bool(item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False))))
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue
            price = float(item.get("price", 0))
            if not (min_gpu_price <= price <= max_gpu_price):
                continue
            g_info = identify_gpu(item.get("title", ""))
            if g_info and g_info.get("fps_1440p", 0) >= min_gpu_fps:
                ev = _evaluate_listing(item, g_info, gpu_det, re_audit=re_audit)
                is_n, cond, cond_lbl = _extract_item_condition(item)
                cand = {
                    "id": item["id"],
                    "summary": item,
                    "spec": g_info,
                    "gpu": g_info,
                    "model": g_info["model"],
                    "price": price,
                    "currency": effective_curr,
                    "fps_1440p": g_info["fps_1440p"],
                    "fps_1080p": g_info["fps_1080p"],
                    "vram_gb": g_info["vram_gb"],
                    "tdp_watts": g_info.get("tdp_watts", 200),
                    "discount_pct": compute_market_discount_pct(price, g_info, price_currency=effective_curr, spec_currency="UAH"),
                    "url": item.get("url", ""),
                    "source": item.get("source", "olx.ua"),
                    "is_secure_deal": is_secure,
                    "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
                    "is_new": is_n,
                    "condition": cond,
                    "condition_label": cond_lbl,
                    "eval": ev,
                    "heuristic": ev,
                    "ai_eval": ev["audit"],
                }
                if _passes_mode_gate("gpu", cand, profile):
                    gpu_list.append(cand)
        if gpu_query:
            filtered_gpus = [g for g in gpu_list if matches_lock_query(g, gpu_query)]
            if not filtered_gpus:
                print(f"\nNo marketplace listings found matching locked GPU: '{gpu_query}'.")
                print("   Tip: Check spelling (e.g. 'RTX 3080') or run 'python main.py sync -c gpu'.")
                return []
            gpu_list = filtered_gpus
            print(f"   Locked GPU (Marketplace): '{gpu_query}' ({len(gpu_list)} listings)")

    # Filter out dead PCIe 3.0 legacy architectures (Pascal, Polaris) at >=25k ₴ unless explicitly locked
    if not gpu_owned and not gpu_query and budget_in_uah >= 25000 and profile.name not in ("budget-king", "value"):
        modern_gpus = [
            g for g in gpu_list
            if g.get("spec", {}).get("risk_level") != "CRITICAL"
            and not (
                "mesh shaders" in g.get("spec", {}).get("risk_notes", "").lower()
                or "legacy" in g.get("spec", {}).get("risk_notes", "").lower()
            )
        ]
        if modern_gpus:
            gpu_list = modern_gpus

    # 2. Classify CPUs
    min_cpu_price_uah = 500 if budget_in_uah < 10000 else (800 if budget_in_uah < 18000 else 1500)
    min_cpu_price = convert_currency(min_cpu_price_uah, "UAH", effective_curr)
    min_other_cost_cpu_uah = 0.0
    if not gpu_owned:
        min_other_cost_cpu_uah += 1400 if budget_in_uah < 10000 else (2200 if budget_in_uah < 18000 else 4500)
    if not mobo_owned:
        min_other_cost_cpu_uah += 600 if budget_in_uah < 10000 else (900 if budget_in_uah < 18000 else 1300)
    if not ram_owned:
        min_other_cost_cpu_uah += 400 if budget_in_uah < 10000 else (600 if budget_in_uah < 16000 else 900)
    if not psu_owned:
        min_other_cost_cpu_uah += 500 if budget_in_uah < 10000 else (800 if budget_in_uah < 16000 else 1100)
    min_other_cost_cpu = convert_currency(min_other_cost_cpu_uah, "UAH", effective_curr)
    max_cpu_price = max(min_cpu_price + convert_currency(1000.0, "UAH", effective_curr), core_budget - min_other_cost_cpu)

    cpu_list: List[Dict[str, Any]] = []
    if cpu_owned:
        cpu_cand["currency"] = effective_curr
        cpu_list = [cpu_cand]
        print(f"   Locked CPU (Owned): {cpu_cand['model']} ({cpu_cand['socket']} | " + format_price(0, effective_curr) + ")")
    else:
        for item in raw_by_cat["cpu"]:
            # Sorter is site-agnostic: evaluates universal buyer protection (is_secure_deal)
            is_secure = bool(item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False))))
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue
            price = float(item.get("price", 0))
            if not (min_cpu_price <= price <= max_cpu_price):
                continue
            c_info = identify_cpu(item.get("title", ""), item.get("description", ""))
            if c_info:
                if socket and c_info["socket"].upper() != socket.upper():
                    continue
                if min_threads and c_info.get("threads", 0) < min_threads:
                    continue
                ev = _evaluate_listing(item, c_info, cpu_det, re_audit=re_audit)
                is_n, cond, cond_lbl = _extract_item_condition(item)
                cand = {
                    "id": item["id"],
                    "summary": item,
                    "spec": c_info,
                    "cpu": c_info,
                    "model": c_info["model"],
                    "socket": c_info["socket"],
                    "price": price,
                    "currency": effective_curr,
                    "fps_gaming": c_info["fps_gaming"],
                    "fps_1pct_low": c_info.get("fps_1pct_low", round(c_info["fps_gaming"] * 0.73, 1)),
                    "l3_cache_mb": c_info.get("l3_cache_mb", 32),
                    "cb_r23_multi": c_info.get("cb_r23_multi", c_info["threads"] * 950),
                    "cores": c_info["cores"],
                    "threads": c_info["threads"],
                    "tdp_watts": c_info.get("tdp_watts", 65),
                    "gaming_watts": c_info.get("gaming_watts", 50),
                    "discount_pct": compute_market_discount_pct(price, c_info, price_currency=effective_curr, spec_currency="UAH"),
                    "url": item.get("url", ""),
                    "source": item.get("source", "olx.ua"),
                    "is_secure_deal": is_secure,
                    "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
                    "is_new": is_n,
                    "condition": cond,
                    "condition_label": cond_lbl,
                    "eval": ev,
                    "heuristic": ev,
                    "ai_eval": ev["audit"],
                }
                if _passes_mode_gate("cpu", cand, profile):
                    cpu_list.append(cand)
        if cpu_query:
            filtered_cpus = [c for c in cpu_list if matches_lock_query(c, cpu_query)]
            if not filtered_cpus:
                print(f"\nNo marketplace listings found matching locked CPU: '{cpu_query}'.")
                print("   Tip: Check spelling (e.g. 'Ryzen 5 7500F') or run 'python main.py sync -c cpu'.")
                return []
            cpu_list = filtered_cpus
            print(f"   Locked CPU (Marketplace): '{cpu_query}' ({len(cpu_list)} listings)")

    # 3. Classify Motherboards
    min_mobo_price_uah = 600 if budget_in_uah < 10000 else (900 if budget_in_uah < 18000 else 1300)
    min_mobo_price = convert_currency(min_mobo_price_uah, "UAH", effective_curr)
    max_mobo_price = core_budget * 0.45
    mobo_list: List[Dict[str, Any]] = []
    if mobo_owned:
        mobo_cand["currency"] = effective_curr
        mobo_list = [mobo_cand]
        print(f"   Locked Motherboard (Owned): {mobo_cand['model']} ({mobo_cand['socket']} {mobo_cand['ddr_type']} | " + format_price(0, effective_curr) + ")")
    else:
        for item in raw_by_cat["mobo"]:
            # Sorter is site-agnostic: evaluates universal buyer protection (is_secure_deal)
            is_secure = bool(item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False))))
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue
            price = float(item.get("price", 0))
            if not (min_mobo_price <= price <= max_mobo_price):
                continue
            m_info = identify_motherboard(item.get("title", ""), item.get("description", ""))
            if m_info and not m_info.get("is_bundle"):
                if socket and m_info["socket"].upper() != socket.upper():
                    continue
                if cpu_owned and m_info["socket"].upper() != cpu_cand["socket"].upper():
                    continue
                ev = _evaluate_listing(item, m_info, mobo_det, re_audit=re_audit)
                is_n, cond, cond_lbl = _extract_item_condition(item)
                cand = {
                    "id": item["id"],
                    "summary": item,
                    "spec": m_info,
                    "mobo": m_info,
                    "model": m_info["model"],
                    "socket": m_info["socket"],
                    "chipset": m_info["chipset"],
                    "ddr_type": m_info["ddr_type"],
                    "vrm_tier": m_info.get("vrm_tier", "B-Tier"),
                    "price": price,
                    "currency": effective_curr,
                    "discount_pct": compute_market_discount_pct(price, m_info, price_currency=effective_curr, spec_currency="UAH"),
                    "url": item.get("url", ""),
                    "source": item.get("source", "olx.ua"),
                    "is_secure_deal": is_secure,
                    "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
                    "is_new": is_n,
                    "condition": cond,
                    "condition_label": cond_lbl,
                    "eval": ev,
                    "heuristic": ev,
                    "ai_eval": ev["audit"],
                }
                if _passes_mode_gate("mobo", cand, profile):
                    mobo_list.append(cand)
        if mobo_query:
            filtered_mobos = [m for m in mobo_list if matches_lock_query(m, mobo_query)]
            if not filtered_mobos:
                print(f"\nNo marketplace listings found matching locked Motherboard: '{mobo_query}'.")
                print("   Tip: Check spelling (e.g. 'B650' or 'B550') or run 'python main.py sync -c mobo'.")
                return []
            mobo_list = filtered_mobos
            print(f"   Locked Motherboard (Marketplace): '{mobo_query}' ({len(mobo_list)} listings)")

    # Filter out dead PCIe 3.0 legacy platforms at >=25k ₴ unless explicitly requested via --socket or locked
    if not socket and not cpu_owned and not mobo_owned and budget_in_uah >= 25000 and profile.name != "budget-king":
        modern_cpus = [c for c in cpu_list if c["socket"] not in LEGACY_SOCKETS]
        modern_mobos = [m for m in mobo_list if m["socket"] not in LEGACY_SOCKETS]
        if modern_cpus and modern_mobos:
            cpu_list = modern_cpus
            mobo_list = modern_mobos
        if budget_in_uah >= 32000 and profile.name in ("best", "sweet-spot", "future-proof", "max-perf", "esports", "4k-ultra", "deal-hunter"):
            zen3_plus_cpus = [c for c in cpu_list if c["fps_gaming"] >= 138.0]
            if zen3_plus_cpus:
                cpu_list = zen3_plus_cpus

    # 4. Classify Dual-Channel Desktop UDIMM RAM (16GB, 24GB, 32GB, 48GB, 64GB — strictly 2x/4x sticks)
    valid_ram_caps = {8, 16, 24, 32, 48, 64} if budget_in_uah < 14000 else {16, 24, 32, 48, 64}
    min_ram_price_uah = 400 if budget_in_uah < 10000 else (600 if budget_in_uah < 16000 else 900)
    min_ram_price = convert_currency(min_ram_price_uah, "UAH", effective_curr)
    max_ram_price = core_budget * 0.35
    ram_list: List[Dict[str, Any]] = []
    if ram_owned:
        ram_cand["currency"] = effective_curr
        ram_list = [ram_cand]
        print(f"   Locked RAM (Owned): {ram_cand['model']} (" + format_price(0, effective_curr) + ")")
    else:
        for item in raw_by_cat["ram"]:
            # Sorter is site-agnostic: evaluates universal buyer protection (is_secure_deal)
            is_secure = bool(item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False))))
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue
            price = float(item.get("price", 0))
            if not (min_ram_price <= price <= max_ram_price):
                continue
            r_info = identify_ram(item.get("title", ""), item.get("description", ""))
            if (
                r_info
                and r_info.get("form_factor") in ("UDIMM", "UNKNOWN", "ECC_UDIMM")
                and r_info.get("total_gb") in valid_ram_caps
                and r_info.get("module_count", 1) >= 2
            ):
                ev = _evaluate_listing(item, r_info, ram_det, re_audit=re_audit)
                is_n, cond, cond_lbl = _extract_item_condition(item)
                cand = {
                    "id": item["id"],
                    "summary": item,
                    "spec": r_info,
                    "ram": r_info,
                    "model": r_info["model"],
                    "gen": r_info["generation"],
                    "total_gb": r_info["total_gb"],
                    "speed_mhz": r_info["speed_mhz"],
                    "price": price,
                    "currency": effective_curr,
                    "discount_pct": compute_market_discount_pct(price, r_info, price_currency=effective_curr, spec_currency="UAH"),
                    "url": item.get("url", ""),
                    "source": item.get("source", "olx.ua"),
                    "is_secure_deal": is_secure,
                    "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
                    "is_new": is_n,
                    "condition": cond,
                    "condition_label": cond_lbl,
                    "eval": ev,
                    "heuristic": ev,
                    "ai_eval": ev["audit"],
                }
                if _passes_mode_gate("ram", cand, profile):
                    ram_list.append(cand)
        if ram_query:
            filtered_rams = [r for r in ram_list if matches_lock_query(r, ram_query)]
            if not filtered_rams:
                print(f"\nNo marketplace listings found matching locked RAM: '{ram_query}'.")
                print("   Tip: Check spelling (e.g. '32GB DDR4' or 'DDR5') or run 'python main.py sync -c ram'.")
                return []
            ram_list = filtered_rams
            print(f"   Locked RAM (Marketplace): '{ram_query}' ({len(ram_list)} listings)")

    # 5. Classify PSUs
    min_psu_price_uah = 500 if budget_in_uah < 10000 else (800 if budget_in_uah < 16000 else 1100)
    min_psu_price = convert_currency(min_psu_price_uah, "UAH", effective_curr)
    max_psu_price = core_budget * 0.30
    psu_list: List[Dict[str, Any]] = []
    if psu_owned:
        psu_cand = resolve_owned_psu(psu_query)
        psu_cand["currency"] = effective_curr
        psu_list = [psu_cand]
        print(f"   Locked PSU (Owned): {psu_cand['model']} ({psu_cand['wattage']}W | " + format_price(0, effective_curr) + ")")
    else:
        for item in raw_by_cat["psu"]:
            # Sorter is site-agnostic: evaluates universal buyer protection (is_secure_deal)
            is_secure = bool(item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False))))
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue
            price = float(item.get("price", 0))
            if not (min_psu_price <= price <= max_psu_price):
                continue
            p_info = identify_psu(item.get("title", ""), item.get("description", ""))
            if p_info and p_info.get("wattage", 0) >= 500:
                ev = _evaluate_listing(item, p_info, psu_det, re_audit=re_audit)
                is_n, cond, cond_lbl = _extract_item_condition(item)
                cand = {
                    "id": item["id"],
                    "summary": item,
                    "spec": p_info,
                    "psu": p_info,
                    "model": p_info["model"],
                    "wattage": p_info["wattage"],
                    "tier": p_info["vrm_tier"],
                    "efficiency": p_info["efficiency"],
                    "price": price,
                    "currency": effective_curr,
                    "discount_pct": compute_market_discount_pct(price, p_info, price_currency=effective_curr, spec_currency="UAH"),
                    "url": item.get("url", ""),
                    "source": item.get("source", "olx.ua"),
                    "is_secure_deal": is_secure,
                    "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
                    "is_new": is_n,
                    "condition": cond,
                    "condition_label": cond_lbl,
                    "eval": ev,
                    "heuristic": ev,
                    "ai_eval": ev["audit"],
                }
                if _passes_mode_gate("psu", cand, profile):
                    psu_list.append(cand)
        if psu_query:
            filtered_psus = [p for p in psu_list if matches_lock_query(p, psu_query)]
            if not filtered_psus:
                print(f"\nNo marketplace listings found matching locked PSU: '{psu_query}'.")
                print("   Tip: Check spelling (e.g. '750W' or 'Seasonic') or run 'python main.py sync -c psu'.")
                return []
            psu_list = filtered_psus
            print(f"   Locked PSU (Marketplace): '{psu_query}' ({len(psu_list)} listings)")

    def _cat_summary(name: str, pool: List[Dict[str, Any]], owned: bool, locked: Optional[str]) -> str:
        if owned:
            return f"{name.upper()}s=1 (OWNED)"
        if locked:
            return f"{name.upper()}s={len(pool)} (LOCKED)"
        return f"{name.upper()}s={len(pool)}"

    # Detect multi-component bundle & prebuilt PC propositions
    bundle_list: List[Dict[str, Any]] = []
    excluded_from_bundles: Set[str] = set()
    if gpu_owned:
        excluded_from_bundles.add("gpu")
    if cpu_owned:
        excluded_from_bundles.add("cpu")
    if mobo_owned:
        excluded_from_bundles.add("mobo")
    if ram_owned:
        excluded_from_bundles.add("ram")
    if psu_owned:
        excluded_from_bundles.add("psu")

    bundle_locks: Dict[str, str] = {}
    if gpu_query and not gpu_owned:
        bundle_locks["gpu"] = gpu_query
    if cpu_query and not cpu_owned:
        bundle_locks["cpu"] = cpu_query
    if mobo_query and not mobo_owned:
        bundle_locks["mobo"] = mobo_query
    if ram_query and not ram_owned:
        bundle_locks["ram"] = ram_query
    if psu_query and not psu_owned:
        bundle_locks["psu"] = psu_query

    bundle_list = extract_bundle_propositions(
        raw_by_cat=raw_by_cat,
        effective_curr=effective_curr,
        profile=profile,
        budget_in_uah=budget_in_uah,
        core_budget=core_budget,
        socket_filter=socket,
        min_threads=min_threads,
        min_gpu_fps=min_gpu_fps,
        re_audit=re_audit,
        excluded_categories=excluded_from_bundles,
        locked_queries=bundle_locks,
        max_bundles=45,
    )

    bundle_summary = ""
    if bundle_list:
        prebuilt_count = sum(1 for b in bundle_list if b.get("is_prebuilt"))
        if prebuilt_count > 0:
            bundle_summary = f" | BUNDLES={len(bundle_list)} (incl. {prebuilt_count} Prebuilt)"
        else:
            bundle_summary = f" | BUNDLES={len(bundle_list)}"

    print(
        f"   Candidate pool: "
        f"{_cat_summary('gpu', gpu_list, gpu_owned, gpu_query)} | "
        f"{_cat_summary('cpu', cpu_list, cpu_owned, cpu_query)} | "
        f"{_cat_summary('mobo', mobo_list, mobo_owned, mobo_query)} | "
        f"{_cat_summary('ram', ram_list, ram_owned, ram_query)} | "
        f"{_cat_summary('psu', psu_list, psu_owned, psu_query)}"
        f"{bundle_summary}"
    )

    has_standalone_components = bool(gpu_list and cpu_list and mobo_list and ram_list and psu_list)
    has_prebuilt_or_complete_bundles = any(b.get("is_prebuilt") for b in bundle_list)

    if not has_standalone_components and not has_prebuilt_or_complete_bundles:
        print("\nInsufficient verified components in local cache for these constraints.")
        print("   Tip: Run 'python main.py sync' or adjust --budget / --mode / --socket.")
        return []

    if human_review:
        target_approved_param = (
            review_candidates
            if review_candidates is not None
            else DEFAULT_CATEGORY_TARGETS
        )
        max_cands_param = (
            review_candidates
            if isinstance(review_candidates, int)
            else None
        )
        review_res = run_human_validation_review(
            gpu_list=gpu_list,
            cpu_list=cpu_list,
            mobo_list=mobo_list,
            ram_list=ram_list,
            psu_list=psu_list,
            budget=core_budget,
            profile=profile,
            ledger=ledger,
            input_func=input_func,
            max_candidates=max_cands_param,
            target_approved=target_approved_param,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_base_url=ai_base_url,
            no_ai=no_ai,
            re_audit=re_audit,
            ai_prescreen=ai_prescreen,
            force_review=force_review,
            human_only=effective_human_only,
        )

        if isinstance(review_res, HumanReviewResult):
            locked_g = review_res.locked_gpu
            locked_c = review_res.locked_cpu
            locked_m = review_res.locked_mobo
            locked_r = review_res.locked_ram
            locked_p = review_res.locked_psu

            gpu_list = [locked_g] if locked_g else review_res.final_gpus
            cpu_list = [locked_c] if locked_c else review_res.final_cpus
            mobo_list = [locked_m] if locked_m else review_res.final_mobos
            ram_list = [locked_r] if locked_r else review_res.final_rams
            psu_list = [locked_p] if locked_p else review_res.final_psus
        else:
            locked_g, locked_c, gpu_list, cpu_list = review_res
            if locked_g:
                gpu_list = [locked_g]
            if locked_c:
                cpu_list = [locked_c]

        if not (gpu_list and cpu_list and mobo_list and ram_list and psu_list):
            print("\nNo remaining compatible components in candidate pool after human review.")
            return []

    if ai_prescreen and not human_review:
        from extensions.pc.human_review import _get_category_inspector, pre_screen_proposals_with_ai
        # Pre-screen top candidate proposals with category AI inspectors to detect defects & scams
        for cat_name, cat_label, c_pool in [
            ("gpu", "GPU", gpu_list),
            ("cpu", "CPU", cpu_list),
            ("mobo", "Motherboard", mobo_list),
            ("ram", "RAM", ram_list),
            ("psu", "PSU", psu_list),
        ]:
            insp = _get_category_inspector(cat_name, ai_provider, ai_model, ai_base_url, no_ai, ai_prescreen)
            if insp:
                cat_target = DEFAULT_CATEGORY_TARGETS.get(cat_name, 5)
                pre_app = [c for c in c_pool if (c.get("eval") or {}).get("is_ai_approved")]
                if len(pre_app) >= cat_target and not re_audit and not force_review:
                    continue
                unreviewed = [c for c in c_pool if not (c.get("eval") or {}).get("is_ai_approved") and not (c.get("eval") or {}).get("is_ai_rejected")]
                if unreviewed:
                    needed = max(1, cat_target - len(pre_app)) if not re_audit and not force_review else 10
                    clean_top, rejected_top = pre_screen_proposals_with_ai(
                        cat_name=cat_name,
                        cat_label=cat_label,
                        candidates=unreviewed,
                        needed_count=min(len(unreviewed), needed),
                        inspector=insp,
                        mode_name=getattr(profile, "name", "best"),
                        re_audit=re_audit,
                        led=ledger,
                    )
                    rej_ids = {r["id"] for r in rejected_top}
                    if rej_ids:
                        if cat_name == "gpu":
                            gpu_list = [g for g in gpu_list if g["id"] not in rej_ids]
                        elif cat_name == "cpu":
                            cpu_list = [c for c in cpu_list if c["id"] not in rej_ids]
                        elif cat_name == "mobo":
                            mobo_list = [m for m in mobo_list if m["id"] not in rej_ids]
                        elif cat_name == "ram":
                            ram_list = [r for r in ram_list if r["id"] not in rej_ids]
                        elif cat_name == "psu":
                            psu_list = [p for p in psu_list if p["id"] not in rej_ids]

    excluded_ids: set = set()
    final_builds = synthesize_builds(
        gpu_list,
        cpu_list,
        mobo_list,
        ram_list,
        psu_list,
        budget=core_budget,
        profile=profile,
        top_n=top_builds,
        excluded_ids=excluded_ids,
        bundles=bundle_list if not human_review else None,
    )

    if human_review and not final_builds:
        print("\nCould not synthesize a compatible 5-part PC build strictly from human-approved proposals.")
        c_socks = {c.get("socket", "").upper() for c in cpu_list if c.get("socket")}
        m_socks = {m.get("socket", "").upper() for m in mobo_list if m.get("socket")}
        m_ddrs = {m.get("ddr_type", "").upper() for m in mobo_list if m.get("ddr_type")}
        r_ddrs = {str(r.get("gen", r.get("ddr_type", ""))).upper() for r in ram_list if r.get("gen") or r.get("ddr_type")}
        min_gpu_p = min((float(g.get("price", 0)) for g in gpu_list), default=0)
        min_cpu_p = min((float(c.get("price", 0)) for c in cpu_list), default=0)
        min_mobo_p = min((float(m.get("price", 0)) for m in mobo_list), default=0)
        min_ram_p = min((float(r.get("price", 0)) for r in ram_list), default=0)
        min_psu_p = min((float(p.get("price", 0)) for p in psu_list), default=0)
        min_total = min_gpu_p + min_cpu_p + min_mobo_p + min_ram_p + min_psu_p

        print(f"   • Budget ceiling: {format_price(core_budget, effective_curr)} │ Lowest possible approved combination: {format_price(min_total, effective_curr)}")
        if c_socks and m_socks and not (c_socks & m_socks):
            print(f"   • Socket mismatch: Approved CPUs require {sorted(c_socks)}, but approved Motherboards have {sorted(m_socks)}.")
        if m_ddrs and r_ddrs and not (m_ddrs & r_ddrs):
            print(f"   • RAM generation mismatch: Approved Motherboards require {sorted(m_ddrs)}, but approved RAM is {sorted(r_ddrs)}.")
        if min_total > core_budget:
            print(f"   • Budget exceeded by {format_price(min_total - core_budget, effective_curr)} (cheapest approved parts total {format_price(min_total, effective_curr)}).")
        print("   Tip: Re-run with --human-review to approve matching platform components or increase --budget.")
        return []

    if not final_builds:
        print("\nNo compatible 5-part builds fit within this budget/mode. Try widening --budget or using --mode budget-king.")
        return []

    # Holistic System AI Audit & Buyer Advisory loop (opt-in via --ai-audit, disabled by default)
    effective_use_ai = bool(ai_audit) and (not no_ai)
    if effective_use_ai:
        inspector = SystemAIInspector(
            provider=ai_provider,
            model=ai_model,
            base_url=ai_base_url,
        )
        print(f"   AI System Audit: Inspecting top synthesized builds via {inspector.provider_label}...")
        for round_idx in range(2):
            newly_rejected = _audit_winning_builds_live(
                final_builds,
                client=client,
                profile=profile,
                inspector=inspector,
                re_audit=(re_audit and round_idx == 0),
            )
            if not newly_rejected:
                break
            excluded_ids.update(newly_rejected)
            print(f"   {len(newly_rejected)} listing(s) failed system AI audit — re-synthesizing clean replacements...")
            final_builds = synthesize_builds(
                gpu_list,
                cpu_list,
                mobo_list,
                ram_list,
                psu_list,
                budget=core_budget,
                profile=profile,
                top_n=top_builds,
                excluded_ids=excluded_ids,
                bundles=bundle_list,
            )
            if not final_builds:
                break

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    print(f"   Top builds (solved in {elapsed_ms:.0f}ms):\n")

    for idx, b in enumerate(final_builds, 1):
        g, c, m, r, p = b["gpu"], b["cpu"], b["mobo"], b["ram"], b["psu"]
        parts = (g, c, m, r, p)
        avg_risk = sum((x.get("eval") or x.get("heuristic") or {}).get("risk_score", 0) for x in parts) / 5.0
        avg_disc = sum(x.get("discount_pct", 0.0) for x in parts) / 5.0

        surplus = b.get("surplus", 0)
        surplus_col = f"+{format_price(surplus, effective_curr)}" if surplus > 0 else (format_price(0, effective_curr) if surplus == 0 else format_price(surplus, effective_curr))
        if b.get("is_prebuilt"):
            title_col = f"Build #{idx} [PREBUILT]: {g['model']} + {c['model']}"
        elif b.get("is_bundle_build") and b.get("bundle_label"):
            title_col = f"Build #{idx} [{b['bundle_label']}]: {g['model']} + {c['model']}"
        else:
            title_col = f"Build #{idx}: {g['model']} + {c['model']}"
        score_col = f"{format_price(b['total_cost'], effective_curr)} (Score: {b['build_score']:.1f})"

        fps_col = f"Gaming: ~{b['eff_fps_1440p']:.0f} fps (1440p) / ~{b['eff_fps_1080p']:.0f} (1080p)"
        load_col = f"Load: ~{b['est_load_watts']}W on {p['wattage']}W"
        new_cnt = sum(1 for x in parts if (x.get("is_new") or x.get("condition") == "new"))
        outlet_cnt = sum(1 for x in parts if (str(x.get("condition", "")).lower() in ("refurbished", "outlet")))
        mkt_col = f"Mkt: {fmt_deal_pct(avg_disc)}"
        if new_cnt > 0 and outlet_cnt > 0:
            mkt_col += f" │ {new_cnt} New, {outlet_cnt} Outlet"
        elif new_cnt > 0:
            mkt_col += f" │ {new_cnt} New"
        elif outlet_cnt > 0:
            mkt_col += f" │ {outlet_cnt} Outlet"

        from currency import CURRENCY_SYMBOLS, canonical_currency
        t_cost = float(b["total_cost"])
        fps_1440 = float(b["eff_fps_1440p"])
        cost_per_fps = t_cost / max(1.0, fps_1440)
        fps_per_1k = (fps_1440 / max(1.0, t_cost)) * 1000.0
        c_canon = canonical_currency(effective_curr)
        c_sym, is_suffix = CURRENCY_SYMBOLS.get(c_canon, (c_canon, True))
        val_left = (
            f"Perf/Value: ~{cost_per_fps:.0f} {c_sym}/fps (1440p)"
            if is_suffix
            else f"Perf/Value: ~{c_sym}{cost_per_fps:.0f}/fps (1440p)"
        )
        val_mid = (
            f"~{fps_per_1k:.1f} fps / 1k {c_sym}"
            if is_suffix
            else f"~{fps_per_1k:.1f} fps / {c_sym}1k"
        )
        cpu_ratio = float(b.get("cpu_ratio", 1.0))
        val_right = f"Risk: {avg_risk:.0f}/100 │ Balance: {cpu_ratio:.2f}x"

        def _vis_len(txt: str) -> int:
            return len(re.sub(r"\x1b\[[0-9;]*m|\x1b\]8;;.*?\x1b\\", "", txt))

        left_w = max(42, _vis_len(title_col) + 2, _vis_len(fps_col) + 2, _vis_len(val_left) + 2)
        mid_w = max(27, _vis_len(score_col) + 2, _vis_len(load_col) + 2, _vis_len(val_mid) + 2)
        right_w = max(29, _vis_len(surplus_col), _vis_len(mkt_col), _vis_len(val_right))
        rule_w = max(104, left_w + 3 + mid_w + 3 + right_w)

        print("━" * rule_w)
        print(f"{pad_ansi(title_col, left_w)}│  {pad_ansi(score_col, mid_w)}│  {surplus_col}")
        print(f"{pad_ansi(fps_col, left_w)}│  {pad_ansi(load_col, mid_w)}│  {mkt_col}")
        print(f"{pad_ansi(val_left, left_w)}│  {pad_ansi(val_mid, mid_w)}│  {val_right}")
        print("─" * rule_w)

        c_l3 = c["spec"].get("l3_cache_mb", 32)
        c_low = c["spec"].get("fps_1pct_low", c["fps_gaming"] * 0.73)

        p_tier_raw = p.get("tier") or p.get("spec", {}).get("vrm_tier") or "Tier C"
        m_tier = re.search(r"Tier\s*([A-Fa-f])", str(p_tier_raw))
        if m_tier:
            p_tier_clean = f"{m_tier.group(1).upper()}-Tier"
        else:
            p_tier_clean = str(p_tier_raw).strip()

        r_tot_gb = int(r.get("total_gb") or r["spec"].get("total_gb") or r["spec"].get("capacity_gb") or 16)
        rows = [
            ("GPU", g["model"], g["price"], g, f"{g['vram_gb']}GB", f"1440p:{g['fps_1440p']:.0f}fps"),
            ("CPU", c["model"], c["price"], c, f"{c['threads']}T {c_l3}M", f"{c['fps_gaming']:.0f}/{c_low:.0f}idx"),
            ("MOBO", m["model"], m["price"], m, f"{m['socket']} {m['ddr_type']}", f"{m['vrm_tier']}"),
            ("RAM", r["model"], r["price"], r, f"{r_tot_gb}GB ({r['spec']['module_count']}x stick)", f"{r['spec']['latency_ns']:.1f}ns"),
            ("PSU", p["model"], p["price"], p, f"{p['wattage']}W", f"{p_tier_clean}"),
        ]

        formatted_rows = []
        for label, name, pr, comp, spec1, spec2 in rows:
            if comp.get("is_owned"):
                price_str = f"(OWNED │ {format_price(0, effective_curr)})"
            elif comp.get("is_bundle"):
                if comp.get("is_bundle_primary"):
                    deal_s = fmt_deal_pct(comp.get("discount_pct", 0.0))
                    price_str = f"{format_price(pr, effective_curr)} ({deal_s})"
                else:
                    target_carrier = comp.get("is_bundled_with", "BUNDLE")
                    price_str = f"({target_carrier} │ {format_price(0, effective_curr)})"
            else:
                deal_s = fmt_deal_pct(comp.get("discount_pct", 0.0))
                price_str = f"{format_price(pr, effective_curr)} ({deal_s})"

            is_new_part = bool(comp.get("is_new") or comp.get("condition") == "new")
            cond_val = str(comp.get("condition") or "").lower()
            if comp.get("is_prebuilt"):
                tag = " [PREBUILT]"
            elif comp.get("is_bundle"):
                tag = " [BUNDLE]"
            elif is_new_part:
                tag = " [NEW]"
            elif cond_val in ("refurbished", "outlet"):
                tag = " [OUTLET]"
            else:
                tag = ""
            spec2_str = f"{spec2}{tag}"
            formatted_rows.append((label, name, comp, price_str, spec1, spec2_str))

        price_w = max([22] + [_vis_len(r_p) + 3 for _, _, _, r_p, _, _ in formatted_rows])
        spec1_w = max([19] + [_vis_len(r_s1) + 3 for _, _, _, _, r_s1, _ in formatted_rows])

        for label, name, comp, price_str, spec1, spec2_str in formatted_rows:
            linked_name = pad_ansi(make_terminal_link(comp.get("url", ""), name[:19]), 22)
            price_padded = pad_ansi(price_str, price_w)
            spec1_padded = pad_ansi(spec1, spec1_w)

            print(f"  • {label:<7}{linked_name}{price_padded}{spec1_padded}{spec2_str}")

        if b.get("ai_advisory"):
            adv = b["ai_advisory"]
            rating = adv.get("synergy_rating", 9.0)
            verdict = adv.get("verdict", "APPROVED")
            print()
            print(f"  AI Synergy [{verdict} {rating:.1f}/10]: {adv.get('synergy_verdict', '')}")
            for note in adv.get("compatibility_notes", [])[:2]:
                print(f"  • {note}")
        print()

    if export_json:
        out_path = Path(export_json)
        serializable = []
        for b in final_builds:
            serializable.append({
                "mode": profile.name,
                "build_score": b["build_score"],
                "total_cost": b["total_cost"],
                "surplus": b["surplus"],
                "eff_fps_1440p": b["eff_fps_1440p"],
                "eff_fps_1080p": b["eff_fps_1080p"],
                "ai_advisory": b.get("ai_advisory"),
                "components": {
                    cat: {
                        "id": b[cat]["id"],
                        "model": b[cat]["model"],
                        "price": b[cat]["price"],
                        "is_owned": bool(b[cat].get("is_owned")),
                        "is_new": bool(b[cat].get("is_new") or b[cat].get("condition") == "new"),
                        "condition": str(b[cat].get("condition", "used")),
                        "condition_label": str(b[cat].get("condition_label", "б/в")),
                        "url": b[cat]["url"],
                        "risk_score": (b[cat].get("eval") or b[cat].get("heuristic") or {}).get("risk_score", 0),
                    }
                    for cat in ALL_CATEGORIES
                },
            })
        out_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Exported {len(serializable)} build(s) to {out_path}")

    return final_builds


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combinatorial PC Build & Set Synthesizer ('The Best You Can Get' Multi-Mode Engine)"
    )
    parser.add_argument(
        "--domain", "-D",
        type=str,
        default="pc",
        help="Target set domain extension (e.g. 'pc' [default], 'fishing' [сет на рибалку], or custom extensions)",
    )
    parser.add_argument("--budget", "-b", type=float, default=None, help="Total set budget in target currency (default: 800 USDT or 35,000 UAH)")
    parser.add_argument("--currency", "-c", type=str, default=None, help="Target currency code (default: USDT)")
    parser.add_argument("--rate", type=str, default=None, help="Exchange rate override (e.g. 'UAH:41.5')")
    parser.add_argument(
        "--mode", "-M",
        type=str,
        default="best",
        help=(
            f"Build optimization mode (default: 'best' — The Best You Can Get). "
            f"Available: {', '.join(get_mode_names())}"
        ),
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Custom weight overrides, e.g. 'perf=0.5,value=0.3,safety=0.2'",
    )
    parser.add_argument(
        "--socket",
        choices=["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200", "LGA1151v2", "LGA1151", "LGA2011-v3"],
        default=None,
        help="Lock build to a specific CPU socket",
    )
    parser.add_argument("--min-threads", "--threads", "-t", dest="min_threads", type=int, default=None, help="Minimum CPU threads (e.g. 12, 16, 24)")
    parser.add_argument("--max-risk", type=int, default=None, help="Override maximum acceptable component risk score (0-100)")
    parser.add_argument("--gpu", type=str, default=None, help="Lock GPU or specify owned GPU, e.g. --gpu \"RTX 3080\" or --gpu \"owned:RTX 3080\"")
    parser.add_argument("--cpu", type=str, default=None, help="Lock CPU or specify owned CPU, e.g. --cpu \"Ryzen 5 7500F\" or --cpu \"owned:Ryzen 5 5600\"")
    parser.add_argument("--mobo", type=str, default=None, help="Lock Mobo or specify owned Mobo, e.g. --mobo \"B650\" or --mobo \"owned:B550\"")
    parser.add_argument("--ram", type=str, default=None, help="Lock RAM or specify owned RAM, e.g. --ram \"32GB DDR5\" or --ram \"owned:32GB DDR4\"")
    parser.add_argument("--psu", type=str, default=None, help="Lock PSU or specify owned PSU, e.g. --psu \"750W Gold\" or --psu \"owned:750W\"")

    # Explicit alias flags for convenience
    parser.add_argument("--owned-gpu", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lock-gpu", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--owned-cpu", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lock-cpu", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--owned-mobo", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lock-mobo", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--owned-ram", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lock-ram", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--owned-psu", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--lock-psu", type=str, default=None, help=argparse.SUPPRESS)

    parser.add_argument("--no-case-cooler", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--provider", "-p", type=str, default="all", help="Marketplace information provider (all, olx, telemart; default: all)")
    parser.add_argument("--top-builds", "-n", type=int, default=5, help="Number of distinct PC builds to output (default: 5)")
    parser.add_argument("--refresh", action="store_true", help="Refresh all 5 market caches from OLX before optimizing")
    parser.add_argument("--ai-audit", action="store_true", help="Run holistic Laser AI System Audit on winning synthesized builds (disabled by default)")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI build audit and run purely in deterministic heuristic mode (0 tokens)")
    parser.add_argument("--ai-provider", choices=list_provider_names(), default=None, help="AI provider backend for --ai-audit")
    parser.add_argument("--ai-model", type=str, default=None, help="Override AI model name for --ai-audit")
    parser.add_argument("--ai-base-url", type=str, default=None, help="Custom base URL for local/OpenAI-compatible AI provider")
    parser.add_argument("--re-audit", action="store_true", help="Ignore cached AuditLedger verdicts during --ai-audit")
    parser.add_argument(
        "--human-review", "--interactive", "--validate", "--human",
        dest="human_review",
        action="store_true",
        help="Interactive human validation: surface top GPU deals and CPU+Platform proposals for user verification before synthesis",
    )
    parser.add_argument(
        "--ai-prescreen", "--prescreen", "--ai-filter",
        dest="ai_prescreen",
        action="store_true",
        help="Pre-screen listing descriptions with AI before human review (filters out defects/scams via LLM; disabled by default)",
    )
    parser.add_argument(
        "--candidates", "--review-candidates",
        type=int,
        default=None,
        help="Number of proposals per category to surface in --human-review (default: GPU/CPU/MOBO=7, RAM/PSU=5)",
    )
    parser.add_argument(
        "--force-review", "--re-review", "--fresh-review",
        dest="force_review",
        action="store_true",
        help="Force interactive validation review for each category, ignoring previously cached human approvals",
    )
    parser.add_argument("--export-json", type=str, default=None, help="Save synthesized builds to JSON file")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if getattr(args, "currency", None):
        from currency import set_active_currency
        set_active_currency(args.currency)
    if getattr(args, "rate", None):
        from currency import parse_rate_string
        parse_rate_string(args.rate)
    gpu_val = args.gpu or (f"owned:{args.owned_gpu}" if args.owned_gpu else args.lock_gpu)
    cpu_val = args.cpu or (f"owned:{args.owned_cpu}" if args.owned_cpu else args.lock_cpu)
    mobo_val = args.mobo or (f"owned:{args.owned_mobo}" if args.owned_mobo else args.lock_mobo)
    ram_val = args.ram or (f"owned:{args.owned_ram}" if args.owned_ram else args.lock_ram)
    psu_val = args.psu or (f"owned:{args.owned_psu}" if args.owned_psu else args.lock_psu)

    is_explicit_human_review = bool(args.human_review)
    do_human_review = is_explicit_human_review

    from provider_template import get_market_provider
    prov_inst = get_market_provider(getattr(args, "provider", "olx"), live=args.refresh)

    run_build_optimizer(
        budget=args.budget,
        mode=args.mode,
        domain=getattr(args, "domain", "pc"),
        weights=args.weights,
        socket=args.socket,
        min_threads=args.min_threads,
        max_risk=args.max_risk,
        gpu=gpu_val,
        cpu=cpu_val,
        mobo=mobo_val,
        ram=ram_val,
        psu=psu_val,
        top_builds=args.top_builds,
        refresh=args.refresh,
        ai_audit=args.ai_audit,
        no_ai=args.no_ai,
        ai_provider=args.ai_provider,
        ai_model=args.ai_model,
        ai_base_url=args.ai_base_url,
        re_audit=args.re_audit,
        human_review=do_human_review,
        ai_prescreen=args.ai_prescreen,
        force_review=args.force_review,
        human_only=is_explicit_human_review,
        review_candidates=getattr(args, "candidates", 5),
        export_json=args.export_json,
        provider=prov_inst,
    )


if __name__ == "__main__":
    main()
