"""
Unified Optimization Modes ("Mods") Engine for Component Analyzers & PC Build Synthesizer.

Supports 11 built-in engineering profiles plus user-defined custom mods loaded from
`configs/modes.json` and ad-hoc CLI `--weights` overrides.
"""

import json
import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODES_CONFIG_PATH = _ROOT_DIR / "configs" / "modes.json"

PSU_TIER_RANK = {"Tier A": 4, "Tier B": 3, "Tier C": 2, "Tier D": 1}
MOBO_TIER_RANK = {"S-Tier": 5, "A-Tier": 4, "B-Tier": 3, "C-Tier": 2, "D-Tier": 1}
LEGACY_SOCKETS = frozenset({
    "LGA1151", "LGA1151v2", "LGA1150", "LGA1155", "LGA1156",
    "LGA2011", "LGA2011-v3", "LGA1200", "AM3+", "FM2+",
})
EFF_RANK = {
    "Titanium": 6,
    "Platinum": 5,
    "Gold": 4,
    "Silver": 3,
    "Bronze": 2,
    "White": 1,
    "Standard": 0,
}


@dataclass(frozen=True)
class ModeProfile:
    name: str
    title: str
    description: str
    max_risk: int = 35
    require_delivery: bool = True
    require_secure_deal: bool = True
    block_critical_arch: bool = False
    prefer_nvidia: bool = False
    min_vram_gb: int = 0
    min_ram_gb: int = 0
    min_psu_tier: str = "Tier C"
    preferred_sockets: Tuple[str, ...] = ()
    preferred_ddr: Optional[str] = None
    form_factors: Tuple[str, ...] = ()
    weights: Dict[str, float] = field(default_factory=dict)
    is_custom: bool = False


BUILTIN_MODES: Dict[str, ModeProfile] = {
    "best": ModeProfile(
        name="best",
        title="The Best You Can Get",
        description="Maximizes real-world gaming/compute ceiling, VRM/PSU tier quality, modern silicon, and safety within budget.",
        max_risk=30,
        require_delivery=True,
        block_critical_arch=True,
        min_psu_tier="Tier B",
        weights={"perf": 0.52, "tier": 0.14, "future": 0.11, "safety": 0.10, "value": 0.07, "deal": 0.06},
    ),
    "sweet-spot": ModeProfile(
        name="sweet-spot",
        title="Modern Price/Perf Sweet Spot",
        description="Balanced modern gaming sweet spot: bottleneck-free CPU+GPU pairing, modern platforms, and high Perf^1.5/Price without legacy e-waste.",
        max_risk=30,
        require_delivery=True,
        block_critical_arch=True,
        min_psu_tier="Tier B",
        weights={"perf": 0.44, "value": 0.20, "future": 0.14, "tier": 0.08, "deal": 0.08, "safety": 0.06},
    ),
    "value": ModeProfile(
        name="value",
        title="Pure Cost Efficiency (₴/FPS)",
        description="Ranks verified working hardware strictly by lowest ₴/FPS, ₴/GB, and ₴/Watt cost efficiency.",
        max_risk=40,
        require_delivery=True,
        weights={"value": 0.65, "perf": 0.20, "deal": 0.10, "safety": 0.05},
    ),
    "safe": ModeProfile(
        name="safe",
        title="Fortress Zero-Risk",
        description="Strictest buyer protection: Risk <= 15, mandatory OLX Delivery, blocks ex-mining CRITICAL eras, prioritizes brand-new hardware and Tier A/B PSUs.",
        max_risk=15,
        require_delivery=True,
        block_critical_arch=True,
        min_psu_tier="Tier B",
        weights={"safety": 0.35, "condition": 0.12, "tier": 0.20, "perf": 0.23, "deal": 0.10},
    ),
    "max-perf": ModeProfile(
        name="max-perf",
        title="Unleashed Raw Frame Rate",
        description="Pushes 100% toward maximum raw 1440p/1080p FPS ceiling within budget across all hardware tiers.",
        max_risk=40,
        require_delivery=True,
        weights={"perf": 0.74, "vram": 0.09, "tier": 0.06, "value": 0.06, "safety": 0.05},
    ),
    "deal-hunter": ModeProfile(
        name="deal-hunter",
        title="Market Arbitrage / Steals",
        description="Hunts genuine undervalued listings priced furthest below used market median while filtering out scam bait.",
        max_risk=30,
        require_delivery=True,
        weights={"deal": 0.55, "value": 0.20, "perf": 0.13, "safety": 0.12},
    ),
    "esports": ModeProfile(
        name="esports",
        title="1080p 240Hz-360Hz Competitive",
        description="Weights high-IPC / 3D V-Cache CPUs, 1080p FPS throughput, and tight low-nanosecond RAM timings.",
        max_risk=32,
        require_delivery=True,
        weights={"perf": 0.52, "value": 0.18, "tier": 0.10, "safety": 0.10, "deal": 0.10},
    ),
    "efficiency": ModeProfile(
        name="efficiency",
        title="Cool, Quiet & FPS/Watt",
        description="Prioritizes maximum FPS-per-Watt, low-TDP modern architectures (RTX 40/50, Zen 4/5 65W), and Gold/Platinum PSUs.",
        max_risk=30,
        require_delivery=True,
        block_critical_arch=True,
        min_psu_tier="Tier B",
        weights={"efficiency": 0.48, "perf": 0.24, "tier": 0.14, "safety": 0.14},
    ),
    "future-proof": ModeProfile(
        name="future-proof",
        title="2026+ Upgradeable Longevity",
        description="Targets AM5/LGA1851 DDR5 platforms, 12-32GB VRAM GPUs, 32GB+ DDR5, and 750W+ ATX 3.0 / 12VHPWR PSUs.",
        max_risk=30,
        require_delivery=True,
        block_critical_arch=True,
        min_vram_gb=12,
        min_ram_gb=32,
        min_psu_tier="Tier B",
        preferred_sockets=("AM5", "LGA1851"),
        preferred_ddr="DDR5",
        weights={"future": 0.42, "perf": 0.28, "vram": 0.14, "tier": 0.10, "safety": 0.06},
    ),
    "ai-workstation": ModeProfile(
        name="ai-workstation",
        title="Local LLM / CUDA / Creator",
        description="Heavily weights NVIDIA CUDA + 12-32GB VRAM capacity, high-thread CPUs (16-32t), and 32-64GB+ system memory.",
        max_risk=32,
        require_delivery=True,
        prefer_nvidia=True,
        min_vram_gb=12,
        min_ram_gb=32,
        min_psu_tier="Tier B",
        weights={"vram": 0.38, "threads": 0.22, "perf": 0.20, "tier": 0.10, "safety": 0.10},
    ),
    "budget-king": ModeProfile(
        name="budget-king",
        title="Sub-Budget Bang-for-Buck",
        description="Optimized for tight budgets (AM4 / LGA1700 DDR4 / RX 6600 / RTX 3060): maximum playable 1080p per hryvnia without broken traps.",
        max_risk=32,
        require_delivery=True,
        weights={"value": 0.46, "perf": 0.26, "deal": 0.16, "safety": 0.12},
    ),
}

# Convenient CLI aliases
MODE_ALIASES: Dict[str, str] = {
    "the-best": "best",
    "best-you-can-get": "best",
    "sweetspot": "sweet-spot",
    "sweet": "sweet-spot",
    "balanced": "sweet-spot",
    "perf": "max-perf",
    "fps": "max-perf",
    "deals": "deal-hunter",
    "steal": "deal-hunter",
    "arbitrage": "deal-hunter",
    "eco": "efficiency",
    "quiet": "efficiency",
    "future": "future-proof",
    "longevity": "future-proof",
    "ai": "ai-workstation",
    "llm": "ai-workstation",
    "cuda": "ai-workstation",
    "workstation": "ai-workstation",
    "budget": "budget-king",
}


def load_custom_modes(config_path: Path = MODES_CONFIG_PATH) -> Dict[str, ModeProfile]:
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        raw_modes = data.get("modes", data) if isinstance(data, dict) else {}
        out: Dict[str, ModeProfile] = {}
        for key, cfg in raw_modes.items():
            if key.startswith("_") or not isinstance(cfg, dict):
                continue
            k = key.strip().lower()
            out[k] = ModeProfile(
                name=k,
                title=str(cfg.get("title", k.replace("-", " ").title())),
                description=str(cfg.get("description", "Custom user-defined optimization profile.")),
                max_risk=int(cfg.get("max_risk", 32)),
                require_delivery=bool(cfg.get("require_delivery", True)),
                block_critical_arch=bool(cfg.get("block_critical_arch", False)),
                prefer_nvidia=bool(cfg.get("prefer_nvidia", False)),
                min_vram_gb=int(cfg.get("min_vram_gb", 0)),
                min_ram_gb=int(cfg.get("min_ram_gb", 0)),
                min_psu_tier=str(cfg.get("min_psu_tier", "Tier C")),
                preferred_sockets=tuple(cfg.get("preferred_sockets", [])),
                preferred_ddr=cfg.get("preferred_ddr"),
                form_factors=tuple(cfg.get("form_factors", [])),
                weights={str(wk): float(wv) for wk, wv in (cfg.get("weights") or {}).items()},
                is_custom=True,
            )
        return out
    except Exception:
        return {}


def parse_weights_string(weights_str: str) -> Dict[str, float]:
    """Parses 'perf=0.5,value=0.3,safety=0.2,condition=0.1' into normalized weights."""
    weights: Dict[str, float] = {}
    for part in (weights_str or "").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                k_clean = k.strip().lower()
                if k_clean in ("new", "brand-new", "state"):
                    k_clean = "condition"
                weights[k_clean] = max(0.0, float(v.strip()))
            except ValueError:
                continue
    total = sum(weights.values())
    if total > 0:
        return {k: round(v / total, 4) for k, v in weights.items()}
    return {"perf": 0.45, "value": 0.25, "safety": 0.15, "deal": 0.15}


def list_all_modes() -> Dict[str, ModeProfile]:
    merged = dict(BUILTIN_MODES)
    merged.update(load_custom_modes())
    return merged


def get_mode_names() -> List[str]:
    return list(list_all_modes().keys()) + ["custom"]


def resolve_mode(
    mode_name: Optional[str],
    default: str = "best",
    weights_override: Optional[str] = None,
    max_risk_override: Optional[int] = None,
) -> ModeProfile:
    raw = (mode_name or default).strip().lower()
    raw = MODE_ALIASES.get(raw, raw)
    all_modes = list_all_modes()

    if raw == "custom":
        w = parse_weights_string(weights_override or "")
        profile = ModeProfile(
            name="custom",
            title="Custom CLI Profile",
            description=f"Ad-hoc CLI weighted profile ({weights_override or 'default balanced weights'}).",
            max_risk=max_risk_override if max_risk_override is not None else 35,
            require_delivery=True,
            weights=w,
            is_custom=True,
        )
        return profile

    if raw not in all_modes:
        valid = ", ".join(list(all_modes.keys()) + ["custom"])
        raise ValueError(f"Unknown mode '{mode_name}'. Available modes: {valid}")

    profile = all_modes[raw]
    if weights_override:
        profile = replace(profile, weights=parse_weights_string(weights_override), is_custom=True)
    if max_risk_override is not None:
        profile = replace(profile, max_risk=max_risk_override)
    return profile


def _infer_uah_price(price: float, currency_hint: Optional[str] = None) -> float:
    """
    Normalizes a component price, total build cost, or budget into UAH so that
    all calibrated mathematical curves and thresholds remain invariant across currencies.
    """
    if price <= 0:
        return 0.0
    if not currency_hint or currency_hint in ("UAH", "uah", "₴", "грн"):
        return float(price)
    from currency import canonical_currency, convert_currency
    c_code = canonical_currency(currency_hint)
    if c_code == "UAH":
        return float(price)
    return convert_currency(price, from_currency=c_code, to_currency="UAH")


def compute_market_discount_pct(
    price: float,
    spec: Dict[str, Any],
    price_currency: Optional[str] = None,
    spec_currency: Optional[str] = None,
) -> float:
    """
    Returns percentage below used market median.
    Positive (+22.5) = 22.5% cheaper than typical market median (great deal).
    Negative (-15.0) = 15.0% above typical market median.
    """
    median = spec.get("market_used_median")
    if not median:
        mn = spec.get("market_used_min", 0)
        mx = spec.get("market_used_max", 0)
        median = (mn + mx) / 2.0 if (mn and mx) else 0.0
    if not median or price <= 0:
        return 0.0
    median_f = float(median)
    if price_currency or spec_currency or spec.get("currency"):
        from currency import canonical_currency, convert_currency, get_active_currency
        p_curr = price_currency or get_active_currency()
        s_curr = spec_currency or spec.get("currency") or "UAH"
        if canonical_currency(p_curr) != canonical_currency(s_curr):
            median_f = convert_currency(median_f, from_currency=s_curr, to_currency=p_curr)
    if median_f <= 0:
        return 0.0
    return round(((median_f - price) / median_f) * 100.0, 1)


def is_listing_disqualified(
    heur: Optional[Dict[str, Any]],
    ai_eval: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when listing has hard heuristic red flags or a cached AI REJECTED verdict."""
    if ai_eval:
        if ai_eval.get("verdict") == "REJECTED":
            return True
        if ai_eval.get("verdict") == "APPROVED":
            return False
    if heur and heur.get("red_flags"):
        return True
    return False


def format_listing_status_badge(
    heur: Optional[Dict[str, Any]],
    ai_eval: Optional[Dict[str, Any]] = None,
) -> str:
    """Consistent compact status badge across all 5 component analyzers."""
    if ai_eval:
        if ai_eval.get("verdict") == "APPROVED":
            if ai_eval.get("provider") == "human":
                return "[HUMAN]"
            return f"[OK ({ai_eval.get('confidence', ai_eval.get('confidence_score', 0))}%)]"
        return "[REJECTED]"
    if heur:
        if heur.get("red_flags"):
            return "[DEFECT]"
        if heur.get("risk_score", 0) >= 35 or len(heur.get("warnings", [])) >= 2:
            return "[WARNING]"
    return "[CLEAN]"


def score_component(
    category: str,
    entry: Dict[str, Any],
    profile: ModeProfile,
) -> float:
    """
    Computes a unified higher-is-better composite score (0..100+ scale) for a component
    entry under `profile`. Disqualified items receive a -1,000,000 offset so they always
    sort below clean listings while remaining visible in --mega-table / --show-rejected.
    """
    heur = entry.get("heuristic") or entry.get("eval") or {}
    ai_eval = entry.get("ai_eval")
    disqualified = is_listing_disqualified(heur, ai_eval)

    # Condition & novelty detection
    is_new = bool(entry.get("is_new") or entry.get("condition") == "new")
    condition = str(entry.get("condition") or ("new" if is_new else "used")).lower()

    if condition in ("for_parts", "not_working"):
        disqualified = True

    risk_score = float(heur.get("risk_score", 20))
    if ai_eval and ai_eval.get("verdict") == "APPROVED":
        # AI-verified or human-verified clean items earn a confidence boost
        if ai_eval.get("provider") == "human":
            risk_score = 0.0
        else:
            risk_score = max(0.0, risk_score - 8.0)

    # Brand-new sealed hardware has zero prior operational wear-and-tear
    if is_new or condition == "new":
        risk_score = max(0.0, risk_score - 10.0)

    raw_price = max(1.0, float(entry.get("_allocated_price") or entry.get("price", 1)))
    entry_curr = entry.get("currency") or (entry.get("summary") or {}).get("currency")
    price = max(1.0, _infer_uah_price(raw_price, entry_curr))
    safety_norm = max(0.0, (100.0 - risk_score) / 100.0)
    risk_over_cap_penalty = max(0.0, risk_score - profile.max_risk) * 1.4

    spec = (
        entry.get("gpu")
        or entry.get("cpu")
        or entry.get("mobo")
        or entry.get("ram")
        or entry.get("psu")
        or entry.get("spec")
        or {}
    )

    if "discount_pct" in entry and entry["discount_pct"] is not None:
        discount_pct = float(entry["discount_pct"])
    else:
        discount_pct = compute_market_discount_pct(raw_price, spec, price_currency=entry_curr or "UAH")
    # Clamp extreme suspicious discounts (>55% below median) unless low risk
    clamped_discount = min(45.0, max(-40.0, discount_pct))
    deal_norm = (clamped_discount + 40.0) / 85.0  # 0.0 .. 1.0

    # Time-series price drop signal from SQLite MarketStore (when seller lowers price over time)
    summary_dict = entry.get("summary") or {}
    price_drop_pct = float(
        entry.get("price_drop_pct")
        or summary_dict.get("price_drop_pct")
        or max(0.0, -float(entry.get("price_delta_pct") or summary_dict.get("price_delta_pct") or 0.0))
    )
    if price_drop_pct > 0.0:
        # Boost deal_norm proportionally to verified seller price reductions (capped at +0.25)
        deal_norm = min(1.15, deal_norm + min(0.25, price_drop_pct / 60.0))

    arch_risk = spec.get("risk_level", "LOW")
    arch_penalty = 0.0
    if profile.block_critical_arch and arch_risk == "CRITICAL":
        arch_penalty += 35.0
    elif profile.name == "safe" and arch_risk in ("CRITICAL", "HIGH"):
        arch_penalty += 25.0

    w = profile.weights or {"perf": 0.35, "value": 0.25, "safety": 0.15, "deal": 0.15, "tier": 0.10}
    w_perf = w.get("perf", 0.0)
    w_val = w.get("value", 0.0)
    w_safe = w.get("safety", 0.0)
    w_deal = w.get("deal", 0.0)
    w_vram = w.get("vram", 0.0)
    w_threads = w.get("threads", w.get("cores", 0.0))
    w_eff = w.get("efficiency", 0.0)
    w_fut = w.get("future", 0.0)
    w_tier = w.get("tier", 0.0)
    w_cond = w.get("condition", w.get("new", 0.0))

    perf_norm = 0.5
    val_norm = 0.5
    vram_norm = 0.5
    threads_norm = 0.5
    eff_norm = 0.5
    fut_norm = 0.5
    tier_norm = 0.5
    cond_norm = 1.0 if (is_new or condition == "new") else (0.70 if condition == "refurbished" else 0.40)
    mode_bonus = 0.0

    # Novelty / condition bonus for brand new components (scaled down on overpriced secondary parts)
    if is_new or condition == "new":
        base_new_bonus = (
            3.5 if profile.name in ("safe", "future-proof", "sweet-spot")
            else 2.5 if profile.name in ("best", "max-perf", "esports")
            else 1.8
        )
        if category in ("mobo", "ram", "psu") and discount_pct < -5.0 and profile.name != "safe":
            base_new_bonus *= 0.35
        mode_bonus += base_new_bonus
    elif condition == "refurbished":
        mode_bonus += 0.8
    elif condition in ("for_parts", "not_working"):
        mode_bonus -= 500.0

    # Verified historical price-drop bonus (especially strong in deal-hunter / value / budget-king)
    if price_drop_pct >= 2.0:
        drop_mult = 0.45 if profile.name == "deal-hunter" else (0.25 if profile.name in ("value", "budget-king", "sweet-spot") else 0.12)
        mode_bonus += min(12.0, price_drop_pct * drop_mult)

    if category == "gpu":
        fps1440 = float(spec.get("fps_1440p", entry.get("fps_1440p", 1.0)))
        fps1080 = float(spec.get("fps_1080p", entry.get("fps_1080p", 1.0)))
        vram = float(spec.get("vram_gb", entry.get("vram_gb", 4)))
        tdp = max(50.0, float(spec.get("tdp_watts", 180)))
        brand = spec.get("brand", "")

        active_fps = fps1080 if profile.name == "esports" else (fps1440 * 0.7 + fps1080 * 0.3)
        perf_norm = min(1.15, active_fps / 165.0)
        # Pure value vs sweet-spot non-linear value
        if profile.name == "value":
            val_norm = min(1.2, (fps1440 / price) * 140.0)
        else:
            # Sweet-spot curve: Perf^1.42 / Price rewards modern mid/high cards over 13 FPS RX 470s
            val_norm = min(1.2, ((fps1440 ** 1.42) / price) * 26.0)
            if fps1440 < 35:
                mode_bonus -= 22.0
            elif fps1440 < 50 and profile.name in ("best", "sweet-spot", "future-proof"):
                mode_bonus -= 10.0

        vram_norm = min(1.15, (vram / 16.0) ** 1.15)
        eff_norm = min(1.15, (fps1440 / tdp) / 0.52)
        fut_norm = min(1.1, (vram / 16.0) * 0.65 + (1.0 if arch_risk == "LOW" else 0.25) * 0.35)
        tier_norm = 0.9 if arch_risk == "LOW" else (0.55 if arch_risk == "MEDIUM" else 0.2)

        if profile.prefer_nvidia:
            mode_bonus += 18.0 if brand.lower() == "nvidia" else -15.0
        if profile.min_vram_gb and vram < profile.min_vram_gb:
            mode_bonus -= (profile.min_vram_gb - vram) * 4.5

    elif category == "cpu":
        fps = float(spec.get("fps_gaming", entry.get("fps_gaming", 60.0)))
        threads = float(spec.get("threads", entry.get("threads", 8)))
        tdp = max(35.0, float(spec.get("tdp_watts", 65)))
        sock = spec.get("socket", "")
        is_x3d = bool(spec.get("is_x3d") or "X3D" in spec.get("model", ""))
        fps_low = float(spec.get("fps_1pct_low", fps * (0.775 if is_x3d else 0.73)))
        l3_mb = float(spec.get("l3_cache_mb", 96.0 if is_x3d else 32.0))
        cb_multi = float(spec.get("cb_r23_multi", threads * 950.0))
        g_watts = float(spec.get("gaming_watts", tdp * 0.72))
        pcie_lanes = int(spec.get("pcie_lanes_gpu", 16))

        # Blend average gaming FPS with 1% low frame-time consistency (captures real 3D V-Cache uplift)
        low_weight = 0.52 if profile.name == "esports" else 0.40
        eff_cpu_fps = fps * (1.0 - low_weight) + (fps_low * 1.35) * low_weight
        perf_norm = min(1.18, eff_cpu_fps / 240.0)

        # Multi-core workstation throughput: blends real Cinebench R23 Multi score (80%) + thread count (20%)
        threads_norm = min(1.25, (cb_multi / 35000.0) * 0.80 + (threads / 24.0) * 0.20)

        is_workstation = profile.name in ("ai-workstation", "creator-pro") or w_threads >= 0.15
        if profile.name == "value":
            val_norm = min(1.22, (eff_cpu_fps / price) * 32.0)
        elif is_workstation:
            val_norm = min(
                1.22,
                ((cb_multi / price) / 2.4) * 0.72 + (((eff_cpu_fps ** 1.75) / price) * 0.55) * 0.28,
            )
        else:
            val_norm = min(1.22, ((eff_cpu_fps ** 1.80) / price) * 0.45)
            if profile.name in ("best", "sweet-spot", "future-proof", "esports", "4k-ultra"):
                if sock in LEGACY_SOCKETS:
                    mode_bonus -= 22.0
                if eff_cpu_fps < 135:
                    mode_bonus -= (135.0 - eff_cpu_fps) * 0.45

        # Real-world gaming watts (7800X3D draws ~54W in games despite 120W package TDP)
        eff_watts = max(30.0, g_watts * 0.78 + tdp * 0.22)
        eff_norm = min(1.20, (eff_cpu_fps / eff_watts) / 3.30)

        fut_norm = (
            1.0 if sock in ("AM5", "LGA1851")
            else 0.62 if sock == "LGA1700"
            else 0.52 if (sock == "AM4" and is_x3d)
            else 0.44 if sock == "AM4"
            else 0.05
        )
        if pcie_lanes < 16:
            fut_norm = max(0.05, fut_norm - (0.22 if pcie_lanes <= 4 else 0.12))

        cache_bonus = 0.14 if l3_mb >= 96 else (0.05 if l3_mb >= 32 else -0.05)
        tier_norm = min(1.12, max(0.10, perf_norm * 0.58 + threads_norm * 0.28 + cache_bonus))

        # Map `vram` weight meaningfully for CPUs (workstation multi-core value vs gaming L3 cache capacity)
        if is_workstation:
            vram_norm = min(1.20, threads_norm * 0.65 + val_norm * 0.35)
        else:
            vram_norm = min(1.15, min(1.15, l3_mb / 96.0) * 0.55 + perf_norm * 0.45)

        if profile.name == "esports":
            # Smoothly reward 1% low frame-time ceiling (replaces flat boolean X3D cliff)
            mode_bonus += max(0.0, (fps_low - 125.0) * 0.18)
        if pcie_lanes < 16 and profile.name in ("best", "sweet-spot", "future-proof", "max-perf", "4k-ultra", "esports"):
            mode_bonus -= 9.0 if pcie_lanes <= 4 else 4.5
        if profile.preferred_sockets and sock not in profile.preferred_sockets:
            mode_bonus -= 18.0

    elif category == "mobo":
        vrm_tier = spec.get("vrm_tier", "B-Tier")
        t_rank = MOBO_TIER_RANK.get(vrm_tier, 3)
        sock = spec.get("socket", "")
        ddr = spec.get("ddr_type", "DDR4")
        ff = spec.get("form_factor", "ATX")
        has_wifi = bool(spec.get("has_wifi"))

        tier_norm = t_rank / 5.0
        fut_norm = (0.65 if ddr == "DDR5" else 0.25) + (0.35 if sock in ("AM5", "LGA1851") else 0.1)
        perf_norm = tier_norm * 0.75 + (0.15 if has_wifi else 0.0) + (0.10 if ddr == "DDR5" else 0.0)
        min_mkt = max(500.0, float(spec.get("market_used_min", 2500)))
        val_norm = min(1.15, (min_mkt / price) * (0.65 + 0.12 * t_rank))
        eff_norm = tier_norm

        if profile.preferred_sockets and sock not in profile.preferred_sockets:
            mode_bonus -= 18.0
        if profile.preferred_ddr and ddr != profile.preferred_ddr:
            mode_bonus -= 15.0
        if profile.form_factors and ff not in profile.form_factors:
            mode_bonus -= 20.0

    elif category == "ram":
        gb = float(spec.get("total_gb", entry.get("total_gb", 16)))
        mhz = float(spec.get("speed_mhz", entry.get("speed_mhz", 3200)))
        lat_ns = max(7.0, float(spec.get("latency_ns", entry.get("latency_ns", 10.0))))
        ddr = spec.get("generation", "DDR4")
        mods = int(spec.get("module_count", 2))

        is_mem_heavy = profile.min_ram_gb >= 32 or profile.name in ("ai-workstation", "creator-pro", "future-proof")
        if is_mem_heavy:
            cap_score = min(1.1, gb / 32.0)
        else:
            # 16GB is plenty for gaming; 32GB+ is a modest nice-to-have bonus, not twice as good
            cap_score = 0.55 if gb < 16 else (0.92 if gb < 32 else 1.0)
        spd_score = min(1.1, (mhz / 6400.0) if ddr == "DDR5" else (mhz / 3600.0))
        lat_score = min(1.1, 10.0 / lat_ns)

        perf_norm = cap_score * 0.30 + spd_score * 0.40 + lat_score * 0.30
        if is_mem_heavy:
            val_norm = min(1.2, (gb / price) * (135.0 if ddr == "DDR5" else 80.0))
        else:
            eff_gb = min(24.0, gb)  # Don't over-reward giant 64GB kits in gaming value math
            val_norm = min(1.2, (eff_gb / price) * (160.0 if ddr == "DDR5" else 90.0))
        vram_norm = min(1.15, gb / 64.0)  # memory-heavy modes (ai-workstation / creator)
        threads_norm = vram_norm
        fut_norm = (0.72 if ddr == "DDR5" else 0.28) + (0.28 if gb >= 32 else 0.16)
        tier_norm = lat_score * 0.6 + (0.4 if mods >= 2 else 0.15)
        eff_norm = 0.9 if ddr == "DDR5" else 0.75

        if profile.name == "esports":
            mode_bonus += (lat_score - 0.85) * 30.0
        if mods < 2 and profile.name in ("best", "sweet-spot", "esports", "max-perf", "4k-ultra"):
            mode_bonus -= 14.0  # Strongly prefer dual-channel kits over single-channel sticks
        if profile.min_ram_gb and gb < profile.min_ram_gb:
            mode_bonus -= 16.0
        if profile.preferred_ddr and ddr != profile.preferred_ddr:
            mode_bonus -= 15.0

    elif category == "psu":
        watts = float(spec.get("wattage", 600))
        p_tier = spec.get("vrm_tier", "Tier C")
        t_rank = PSU_TIER_RANK.get(p_tier, 2)
        eff = spec.get("efficiency", "Standard")
        e_rank = EFF_RANK.get(eff, 0)
        mod = spec.get("modularity", "Non-Mod")
        atx3 = bool(spec.get("has_12vhpwr"))
        ff = spec.get("form_factor", "ATX")

        eff_watts = min(1050.0, watts)
        tier_norm = t_rank / 4.0
        eff_norm = e_rank / 6.0
        perf_norm = min(1.1, (eff_watts / 850.0) * 0.55 + tier_norm * 0.45)
        val_norm = min(1.2, ((eff_watts / price) / 0.38) * (0.55 + 0.15 * t_rank))
        fut_norm = (0.45 if atx3 else 0.1) + min(0.55, eff_watts / 1000.0)
        if watts >= 1300 and price < 3500 and spec.get("brand", "Generic") == "Generic":
            mode_bonus -= 22.0  # Unbranded cheap 1300W-2000W units are almost always loud ASIC/mining PSUs

        req_rank = PSU_TIER_RANK.get(profile.min_psu_tier, 2)
        if t_rank < req_rank:
            mode_bonus -= (req_rank - t_rank) * 14.0
        if mod == "Full":
            mode_bonus += 3.5
        if profile.form_factors and ff not in profile.form_factors:
            mode_bonus -= 18.0

    # Guard against scalper/overpriced listings (>20% above used market median) across all modes
    if discount_pct < -20.0:
        mode_bonus -= min(30.0, (-discount_pct - 20.0) * 0.45)

    raw_score = 100.0 * (
        w_perf * perf_norm
        + w_val * val_norm
        + w_safe * safety_norm
        + w_deal * deal_norm
        + w_vram * vram_norm
        + w_threads * threads_norm
        + w_eff * eff_norm
        + w_fut * fut_norm
        + w_tier * tier_norm
        + w_cond * cond_norm
    )
    final_score = raw_score + mode_bonus - risk_over_cap_penalty - arch_penalty
    if disqualified:
        final_score -= 1_000_000.0
    return round(final_score, 2)


@lru_cache(maxsize=16384)
def compute_effective_build_fps(
    gpu_fps_1440: float,
    gpu_fps_1080: float,
    cpu_fps_idx: float,
    cpu_1pct_low: Optional[float] = None,
    l3_cache_mb: int = 32,
    ram_latency_ns: float = 10.0,
    pcie_lanes_gpu: int = 16,
    is_ddr5: bool = False,
) -> Tuple[float, float, float]:
    """
    Computes bottleneck-adjusted `(eff_1440p, eff_1080p, cpu_balance_ratio)`.
    Models real hardware physics:
      - Blends CPU average FPS (60%) with 1% low frame-time floor (40%) so 3D V-Cache (`96-192MB` L3)
        and high-IPC CPUs earn genuine gaming uplift instead of hitting a flat +6% ceiling.
      - Models 3D V-Cache memory-latency immunity (loose DDR5 hurts 32MB CPUs ~4-6% vs ~1% on 96MB+ X3D).
      - Models DDR5 high-bandwidth advantage (offsets higher baseline nanosecond timings: 13.5ns baseline).
      - Models cut-down PCIe lane drag (`x8` / `x4` monolithic APUs like 8700F/8400F/8500G).
    """
    cpu_low = (
        float(cpu_1pct_low)
        if cpu_1pct_low is not None
        else cpu_fps_idx * (0.775 if l3_cache_mb >= 96 else 0.73)
    )
    base_cpu_idx = cpu_fps_idx * 0.60 + (cpu_low * 1.35) * 0.40

    # Differentiate baseline latency threshold between DDR4 (10.5ns) and DDR5 (13.5ns)
    ram_base_ns = 13.5 if is_ddr5 else 10.5
    excess_ns = max(0.0, float(ram_latency_ns) - ram_base_ns)
    ram_drag = min(0.02, excess_ns * 0.003) if l3_cache_mb >= 96 else min(0.095, excess_ns * 0.030)

    # DDR5 ~2x memory bandwidth boost for modern high-bandwidth engines
    ddr_bw_mult = 1.03 if is_ddr5 else 1.0

    # Cut-down PCIe lanes to discrete GPU slot (e.g. x4 on 8500G, x8 on 8700F/8400F/5700)
    pcie_mult = 0.90 if pcie_lanes_gpu <= 4 else (0.968 if pcie_lanes_gpu <= 8 else 1.0)
    eff_cpu_idx = base_cpu_idx * (1.0 - ram_drag) * pcie_mult * ddr_bw_mult

    # Calculate effective 1440p FPS (saturation curve with physical threshold)
    req_cpu_1440 = max(60.0, gpu_fps_1440 * 1.55)
    ratio_1440 = eff_cpu_idx / req_cpu_1440
    eff_1440 = round(gpu_fps_1440 * (1.0 - math.exp(-max(0.01, (ratio_1440 ** 1.35) * 2.4))), 1)

    # Calculate effective 1080p FPS
    req_cpu_1080 = max(70.0, gpu_fps_1080 * 1.40)
    ratio_1080 = eff_cpu_idx / req_cpu_1080
    eff_1080 = round(gpu_fps_1080 * (1.0 - math.exp(-max(0.01, (ratio_1080 ** 1.35) * 2.4))), 1)

    cpu_ratio = ratio_1440

    return eff_1440, eff_1080, cpu_ratio


def score_build(
    build: Dict[str, Any],
    budget: float,
    profile: ModeProfile,
) -> float:
    """
    Scores a complete 5-part PC build (`gpu`, `cpu`, `mobo`, `ram`, `psu`) under `profile`.
    Incorporates CPU-GPU bottleneck & 1%-low physics, Cinebench R23 workstation throughput,
    real gaming wattage, VRM-vs-TDP safety, PSU headroom/tier, and mode weights.
    """
    g = build["gpu"]
    c = build["cpu"]
    m = build["mobo"]
    r = build["ram"]
    p = build["psu"]

    g_spec = g.get("spec", g)
    c_spec = c.get("spec", c)
    m_spec = m.get("spec", m)
    r_spec = r.get("spec", r)
    p_spec = p.get("spec", p)

    build_curr = (
        build.get("currency")
        or g.get("currency")
        or (g.get("summary") or {}).get("currency")
        or c.get("currency")
        or (c.get("summary") or {}).get("currency")
    )
    curr_mult = 1.0 if (not build_curr or build_curr in ("UAH", "uah", "₴", "грн")) else _infer_uah_price(1.0, build_curr)
    total_cost = max(1.0, float(build.get("_total_cost_uah") or (float(build["total_cost"]) * curr_mult)))
    budget = max(1.0, float(build.get("_budget_uah") or (float(budget) * curr_mult)))
    fps1440 = float(g.get("fps_1440p", 1.0))
    fps1080 = float(g.get("fps_1080p", fps1440 * 1.25))
    cpu_fps = float(c.get("fps_gaming", c_spec.get("fps_gaming", 100.0)))
    is_x3d = bool(c_spec.get("is_x3d") or "X3D" in c_spec.get("model", ""))
    cpu_low = float(c_spec.get("fps_1pct_low", cpu_fps * (0.775 if is_x3d else 0.73)))
    l3_mb = int(c_spec.get("l3_cache_mb", 96 if is_x3d else 32))
    pcie_lanes = int(c_spec.get("pcie_lanes_gpu", 16))
    vram = float(g.get("vram_gb", g_spec.get("vram_gb", 8)))
    threads = float(c.get("threads", c_spec.get("threads", 12)))
    cb_multi = float(c_spec.get("cb_r23_multi", threads * 950.0))
    ram_gb = float(r.get("total_gb", 16))
    ram_ns = float(r_spec.get("latency_ns", 10.0))
    sock = c.get("socket", c_spec.get("socket", ""))

    # Effective bottleneck, 1%-low, RAM-latency & PCIe-lane adjusted gaming FPS
    is_ddr5 = (r.get("gen") == "DDR5" or r_spec.get("generation") == "DDR5")
    if "eff_fps_1440p" in build and "cpu_ratio" in build:
        eff_1440 = float(build["eff_fps_1440p"])
        eff_1080 = float(build.get("eff_fps_1080p", eff_1440 * 1.25))
        cpu_ratio = float(build["cpu_ratio"])
    else:
        eff_1440, eff_1080, cpu_ratio = compute_effective_build_fps(
            fps1440, fps1080, cpu_fps,
            cpu_1pct_low=cpu_low,
            l3_cache_mb=l3_mb,
            ram_latency_ns=ram_ns,
            pcie_lanes_gpu=pcie_lanes,
            is_ddr5=is_ddr5,
        )

    active_fps = eff_1080 if profile.name == "esports" else (eff_1440 * 0.68 + eff_1080 * 0.32)
    # Blend effective FPS (85%) with 1% low frame-time floor (15%) for stutter-free smoothness
    perf_norm = (active_fps / 145.0) * 0.85 + min(1.20, cpu_low / 190.0) * 0.15

    # Cost efficiency: normalized 0..1.25 so it never drowns out other weighted dimensions
    if profile.name == "value":
        val_norm = min(1.25, (eff_1440 / total_cost) * 320.0)
    else:
        val_norm = min(1.25, ((active_fps ** 1.55) / total_cost) * 22.5)

    # Aggregate safety across all 5 parts
    parts = (g, c, m, r, p)
    part_risks = [float((x.get("eval") or x.get("heuristic") or {}).get("risk_score", 0)) for x in parts]
    avg_risk = sum(part_risks) / 5.0
    max_part_risk = max(part_risks)
    safety_norm = max(0.0, (100.0 - (avg_risk * 0.65 + max_part_risk * 0.35)) / 100.0)

    # Aggregate market deal discount across all 5 parts
    avg_discount = sum(
        float(x["discount_pct"])
        if "discount_pct" in x and x["discount_pct"] is not None
        else compute_market_discount_pct(float(x["price"]), x.get("spec", x), price_currency=x.get("currency") or build_curr or "UAH")
        for x in parts
    ) / 5.0
    deal_norm = (min(40.0, max(-30.0, avg_discount)) + 30.0) / 70.0

    # Aggregate verified historical price drops across build components
    total_drop_pct = sum(
        float(
            x.get("price_drop_pct")
            or (x.get("summary") or {}).get("price_drop_pct")
            or max(0.0, -float(x.get("price_delta_pct") or (x.get("summary") or {}).get("price_delta_pct") or 0.0))
        )
        for x in parts
    )
    if total_drop_pct > 0.0:
        deal_norm = min(1.15, deal_norm + min(0.20, (total_drop_pct / 5.0) / 50.0))

    # Condition & novelty analysis across build parts
    new_parts_count = sum(1 for x in parts if (x.get("is_new") or x.get("condition") == "new"))
    refurbished_count = sum(1 for x in parts if x.get("condition") == "refurbished")
    for_parts_count = sum(1 for x in parts if x.get("condition") in ("for_parts", "not_working"))

    cond_norm = (
        new_parts_count * 1.0
        + refurbished_count * 0.70
        + (5 - new_parts_count - refurbished_count - for_parts_count) * 0.40
    ) / 5.0

    # Real-world gaming power efficiency (uses actual CPU gaming watts instead of Cinebench package TDP)
    cpu_tdp = float(c.get("tdp_watts", c_spec.get("tdp_watts", 65)))
    cpu_game_w = float(c_spec.get("gaming_watts", cpu_tdp * 0.72))

    # Component quality tier (Mobo VRM + PSU Tier + Dual-channel RAM + Modern GPU/CPU silicon)
    raw_mobo_rank = MOBO_TIER_RANK.get(m_spec.get("vrm_tier", "B-Tier"), 3)
    # 65-105W CPU or 7800X3D/5800X3D (54-68W in gaming) achieves full electrical/thermal adequacy on a B-Tier VRM board
    is_low_power_cpu = (cpu_tdp <= 105 or cpu_game_w <= 75 or is_x3d or "7800X3D" in c_spec.get("model", "").upper())
    if is_low_power_cpu and profile.name not in ("ai-workstation", "creator-pro"):
        mobo_tier_norm = {1: 0.20, 2: 0.55, 3: 0.82, 4: 0.86, 5: 0.88}.get(raw_mobo_rank, 0.75)
    else:
        mobo_tier_norm = raw_mobo_rank / 5.0

    psu_rank = PSU_TIER_RANK.get(p.get("tier", p_spec.get("vrm_tier", "Tier C")), 2)
    ram_mods = int(r_spec.get("module_count", 2))
    dual_ch_bonus = 0.08 if ram_mods in (2, 4) else 0.03
    if ram_gb >= 32:
        dual_ch_bonus += 0.02  # Modest 'nice-to-have' tiebreaker for 32GB+
    gpu_arch_risk = g_spec.get("risk_level", "MEDIUM")
    gpu_arch_bonus = 0.07 if gpu_arch_risk == "LOW" else (0.03 if gpu_arch_risk == "MEDIUM" else 0.0)
    cpu_cache_bonus = 0.05 if l3_mb >= 96 else (0.01 if l3_mb >= 32 else -0.02)
    tier_norm = mobo_tier_norm * 0.40 + (psu_rank / 4.0) * 0.38 + dual_ch_bonus + gpu_arch_bonus + cpu_cache_bonus

    sys_watts = max(120.0, float(g.get("tdp_watts", 180)) + cpu_game_w + 50.0)
    eff_rank = EFF_RANK.get(p.get("efficiency", "Standard"), 0)
    eff_norm = min(1.22, (eff_1440 / sys_watts) / 0.36) * 0.72 + (eff_rank / 6.0) * 0.28

    # Future-proofing (distinguishes upgradeable AM5/LGA1851, viable LGA1700/AM4 X3D, and dead PCIe 3.0 sockets)
    sock_fut = (
        0.34 if sock in ("AM5", "LGA1851")
        else 0.18 if (sock == "AM4" and is_x3d)
        else 0.16 if (sock == "LGA1700" or (sock == "AM4" and cpu_fps >= 140.0))
        else 0.07 if sock == "AM4"
        else 0.0
    )
    is_ddr5 = r.get("gen") == "DDR5"
    has_atx3 = bool(p_spec.get("has_12vhpwr"))
    pcie_fut_pen = 0.12 if pcie_lanes <= 4 else (0.06 if pcie_lanes <= 8 else 0.0)
    fut_norm = max(
        0.0,
        sock_fut
        + (0.21 if is_ddr5 else 0.04)
        + min(0.20, (vram / 16.0) * 0.20)
        + (0.11 if gpu_arch_risk == "LOW" else 0.03)
        + (0.10 if (has_atx3 or p.get("wattage", 600) >= 750) else 0.03)
        + (0.05 if l3_mb >= 96 else 0.0)
        - pcie_fut_pen,
    )

    vram_norm = (vram / 16.0) * 0.75 + (ram_gb / 64.0) * 0.25
    cpu_compute_norm = min(1.25, (cb_multi / 35000.0) * 0.80 + (threads / 24.0) * 0.20)
    threads_norm = cpu_compute_norm * 0.78 + (ram_gb / 64.0) * 0.22

    w = profile.weights or {"perf": 0.40, "value": 0.20, "safety": 0.15, "deal": 0.15, "tier": 0.10}
    w_cond = w.get("condition", w.get("new", 0.0))
    score = 100.0 * (
        w.get("perf", 0.0) * perf_norm
        + w.get("value", 0.0) * val_norm
        + w.get("safety", 0.0) * safety_norm
        + w.get("deal", 0.0) * deal_norm
        + w.get("tier", 0.0) * tier_norm
        + w.get("vram", 0.0) * vram_norm
        + w.get("threads", w.get("cores", 0.0)) * threads_norm
        + w.get("efficiency", 0.0) * eff_norm
        + w.get("future", 0.0) * fut_norm
        + w_cond * cond_norm
    )

    # Condition bonus for builds featuring brand new components (discounts overpriced secondary new parts)
    if new_parts_count > 0:
        per_part_bonus = 2.2 if profile.name == "safe" else (1.6 if profile.name in ("best", "sweet-spot", "future-proof") else 1.0)
        eff_new_units = 0.0
        for idx_p, part_x in enumerate(parts):
            if part_x.get("is_new") or part_x.get("condition") == "new":
                if idx_p >= 2 and float(part_x.get("discount_pct", 0.0)) < -5.0 and profile.name != "safe":
                    eff_new_units += 0.35
                else:
                    eff_new_units += 1.0
        score += eff_new_units * per_part_bonus
        if new_parts_count == 5:
            score += 2.5  # Full factory-fresh rig synergy bonus

    if for_parts_count > 0:
        score -= 500.0 * for_parts_count

    # Engineering compatibility & balance adjustments
    cpu_cores = float(c.get("cores", c_spec.get("cores", 6)))
    if cpu_tdp >= 120 and raw_mobo_rank <= 1:
        score -= 35.0  # Never put a 120W+ CPU on a bare D-Tier VRM board!
    elif (cpu_tdp >= 100 or cpu_cores >= 8) and raw_mobo_rank <= 1:
        score -= 25.0  # Heavy thermal penalty for 100W+ or 8-core CPUs (e.g. 5800X3D) on uncooled D-tier boards (A320/H81)
    elif cpu_tdp >= 150 and raw_mobo_rank <= 2:
        score -= 18.0
    if cpu_tdp >= 220 and profile.name in ("sweet-spot", "safe", "efficiency", "itx-compact"):
        score -= 7.0  # 253W CPUs require 360mm AIOs beyond standard tower cooler allocation
    c_risk = float((c.get("eval") or c.get("heuristic") or {}).get("risk_score", 0))
    if c_spec.get("risk_level") == "MEDIUM" and c_risk >= 20:
        score -= 8.0  # Guard against suspiciously cheap Raptor Lake unlocked K-CPUs (Vmin degradation risk)

    # Calibrated CPU-GPU bottleneck penalty (e.g. RTX 3080 Ti choked by Core i7-8700K -> -68.9 pts!)
    min_balance_ratio = (
        0.82 if profile.name in ("future-proof", "ai-workstation")
        else 0.86 if profile.name == "deal-hunter"
        else 0.94
    )
    if cpu_ratio < min_balance_ratio:
        deficit = min_balance_ratio - cpu_ratio
        if profile.name == "future-proof" and sock in ("AM5", "LGA1851"):
            # Upgradeable modern socket allows a slightly softer CPU-to-GPU ratio penalty
            score -= (deficit * 55.0) ** 1.15
        elif profile.name == "deal-hunter":
            score -= (deficit * 75.0) ** 1.20
        else:
            score -= (deficit * 115.0) ** 1.25

    # Reverse imbalance check: prevent overspending on CPU at the expense of GPU FPS in gaming modes
    if not g.get("is_owned") and not c.get("is_owned"):
        g_price = max(1.0, float(g.get("_price_uah") or (float(g.get("price", 1.0)) * curr_mult)))
        c_price = float(c.get("_price_uah") or (float(c.get("price", 0.0)) * curr_mult))
        # Protect bargain/deal flagship GPUs from reverse imbalance penalty:
        # compare against effective market value so a heavy discount on a powerful GPU isn't penalized
        g_ref_price = max(g_price, float(g_spec.get("market_used_min", g_price)))

        # Maximum allowed CPU-to-GPU cost ratio:
        max_cpu_ratio = (
            1.25 if profile.name == "esports"
            else 1.10 if profile.name in ("ai-workstation", "creator-pro")
            else 0.68  # For best, sweet-spot, max-perf
        )

        if c_price > g_ref_price * max_cpu_ratio:
            penalty_factor = 32.0 if profile.name in ("best", "max-perf") else 20.0
            score -= ((c_price / g_ref_price) - max_cpu_ratio) * penalty_factor

    # Prevent S-Tier motherboard overspending (> 5,000 UAH eq.) on low-power 65-105W CPUs
    # from inflating overall build score:
    m_price = float(m.get("_price_uah") or (float(m.get("price", 0.0)) * curr_mult))
    if is_low_power_cpu and m_price > 5000 and profile.name not in ("ai-workstation", "creator-pro"):
        excess_mobo = (m_price - 5000) / max(1.0, budget)
        score -= excess_mobo * 40.0

    # Dead PCIe 3.0 legacy socket penalty at mid/high budgets
    if sock in LEGACY_SOCKETS and budget >= 24000 and profile.name != "budget-king":
        score -= 22.0

    if profile.prefer_nvidia and g_spec.get("brand", "").lower() != "nvidia":
        score -= 22.0
    if profile.min_vram_gb and vram < profile.min_vram_gb:
        score -= (profile.min_vram_gb - vram) * 4.0
    if profile.min_ram_gb and ram_gb < profile.min_ram_gb:
        score -= 12.0
    if ram_mods < 2:
        score -= 35.0  # Single-channel RAM crippled bandwidth & 1% lows; dual-channel (2x/4x) is mandatory

    # Prevent RAM from eating GPU/CPU budget in gaming modes
    if not r.get("is_owned") and profile.name not in ("ai-workstation", "creator-pro", "future-proof") and not profile.min_ram_gb:
        r_price = float(r.get("_price_uah") or (float(r.get("price", 0.0)) * curr_mult))
        ram_share = r_price / max(1.0, budget)
        # В бюджеті 46k віддавати 7 000 ₴ (15+%) за пам'ять в ігровій системі — груба переплата
        if ram_share > 0.11:
            score -= (ram_share - 0.11) * 65.0

    if profile.name == "esports":
        # Smoothly reward 1% low frame-time ceiling & tight RAM latency (replaces flat boolean X3D cliff)
        score += max(0.0, (cpu_low - 125.0) * 0.16)

    # Low-latency RAM bonus / DDR5 bandwidth bonus (Option 3A)
    if not r.get("is_owned"):
        if (is_ddr5 and ram_ns <= 12.5) or (not is_ddr5 and ram_ns <= 10.0):
            score += 3.5
        elif is_ddr5:
            score += 1.5  # DDR5 modern bandwidth advantage

    if profile.name in ("future-proof", "deal-hunter", "sweet-spot"):
        # Якщо загальна знижка збірки перевищує 15% від медіани
        if avg_discount > 15.0:
            score += min(15.0, (avg_discount - 15.0) * 0.5)
        if total_drop_pct >= 3.0:
            drop_weight = 0.35 if profile.name == "deal-hunter" else 0.18
            score += min(10.0, total_drop_pct * drop_weight)

    # Multi-part bundle & Prebuilt PC synergy bonus: pre-tested BIOS/IMC compatibility + single-shipment escrow savings
    bundled_parts = [x for x in parts if x.get("is_bundle")]
    if len(bundled_parts) >= 2:
        b_disc = float(bundled_parts[0].get("discount_pct", 0.0))
        if b_disc >= -5.0:
            score += 2.5 if len(bundled_parts) >= 3 else 1.5

    # Budget utilization floors so mid/high-budget modes build rigs worthy of the user's budget class (skip when hardware is owned)
    has_owned = any(build.get(k, {}).get("is_owned") for k in ("gpu", "cpu", "mobo", "ram", "psu"))
    if not has_owned:
        util = total_cost / max(1.0, budget)
        expected_fps = min(125.0, max(25.0, budget / 440.0))
        # Protect exceptional high-performing bargain builds that already hit the FPS target for the budget
        is_high_perf_deal = (eff_1440 >= max(75.0, expected_fps * 0.92) and cpu_ratio >= min_balance_ratio)
        penalty_scale = 0.0 if (is_high_perf_deal and util >= 0.62) else (8.0 if is_high_perf_deal else 30.0)
        surplus_ratio = max(0.0, (budget - total_cost) / max(1.0, budget))

        if profile.name in ("best", "max-perf", "4k-ultra"):
            score += min(1.20, cpu_ratio) * 4.0
            if is_high_perf_deal:
                score += min(4.5, surplus_ratio * 9.0)
            elif util >= 0.75 and cpu_ratio >= min_balance_ratio:
                score += surplus_ratio * 2.5
            if util < 0.80:
                score -= (0.80 - util) * penalty_scale
        elif profile.name in ("sweet-spot", "esports", "efficiency", "safe"):
            score += min(1.18, cpu_ratio) * 4.5
            if is_high_perf_deal:
                score += min(5.5, surplus_ratio * 11.0)
            elif util >= 0.72 and cpu_ratio >= min_balance_ratio:
                score += surplus_ratio * 3.0
            if util < 0.76:
                p_scale = 0.0 if (is_high_perf_deal and util >= 0.60) else (8.0 if is_high_perf_deal else 32.0)
                score -= (0.76 - util) * p_scale
        elif profile.name in ("future-proof", "ai-workstation", "creator-pro") and util < 0.72:
            p_scale = 8.0 if is_high_perf_deal else 26.0
            score -= (0.72 - util) * p_scale
        elif profile.name == "value" and budget >= 24000 and util < 0.75:
            p_scale = 8.0 if is_high_perf_deal else 24.0
            score -= (0.75 - util) * p_scale
    else:
        score += min(1.20, cpu_ratio) * 4.0

    return round(score, 2)


def print_modes_table() -> None:
    all_modes = list_all_modes()
    print("\nOPTIMIZATION MODES ('MODS') SUITE")
    print("=" * 108)
    print(f"{'Mode':<16} | {'Origin':<9} | {'MaxRisk':<7} | {'Title':<30} | {'Strategy Summary'}")
    print("-" * 108)
    for key, prof in all_modes.items():
        origin = "Custom" if prof.is_custom else "Built-in"
        print(f"{key:<16} | {origin:<9} | {prof.max_risk:>5}/100 | {prof.title:<30} | {prof.description}")
    print("-" * 108)
    print(f"{'custom':<16} | {'CLI':<9} | {'35/100':>7} | {'Custom CLI Weights':<30} | Pass --weights 'perf=0.5,value=0.3,safety=0.2'")
    print("=" * 108)
    print(f"Add or edit persistent custom mods anytime in: {MODES_CONFIG_PATH}\n")
