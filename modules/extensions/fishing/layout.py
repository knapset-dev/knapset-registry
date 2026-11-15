"""
Fishing Domain Layout.

Defines the 5 core sections of a fishing set:
1. Rod (Spinning / Feeder / Carp Rod)
2. Reel (Spinning Reel)
3. Line (Braided PE / Monofilament Line)
4. Bait (Lures / Feeder Cages)
5. Tackle (Terminal Tackle / Landing Net / Accessories)

And physical / engineering compatibility rules:
- Rod test vs Lure/Bait weight (lure weight within blank casting test bounds)
- Rod power class vs Reel spool size balance (ergonomic balance by spool size)
- Line breaking strength vs Reel drag capacity (line strength matched to reel drag)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from domain_layout import CompatibilityRule, DomainLayout, SectionDefinition
from currency import canonical_currency, convert_currency, format_price, get_active_currency


def _fmt_rod_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    spec = cand.get("spec") or {}
    name = cand.get("model") or cand.get("title", "Fishing Rod")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)

    t_min = spec.get("test_min_g", 1.0)
    t_max = spec.get("test_max_g", 10.0)
    length = spec.get("length_m", 2.1)
    spec1 = f"{t_min:.0f}-{t_max:.0f}g {length:.2f}m"
    spec2 = f"{spec.get('power_class', 'Medium')[:7]}"
    return ("ROD", name, price_str, spec1, spec2)


def _fmt_reel_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    spec = cand.get("spec") or {}
    name = cand.get("model") or cand.get("title", "Spinning Reel")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)

    spool = spec.get("spool_size", 2500)
    bearings = spec.get("bearing_count", 4)
    drag = spec.get("drag_kg", 5.0)
    spec1 = f"{spool} ({bearings}BB)"
    spec2 = f"Drag:{drag:.0f}kg"
    return ("REEL", name, price_str, spec1, spec2)


def _fmt_line_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    spec = cand.get("spec") or {}
    name = cand.get("model") or cand.get("title", "Fishing Line")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)

    diam = spec.get("diameter_mm", 0.12)
    test = spec.get("test_kg", 6.0)
    l_type = spec.get("line_type", "PE 4x")
    spec1 = f"{diam:.2f}mm {test:.1f}kg"
    spec2 = f"{l_type[:7]}"
    return ("LINE", name, price_str, spec1, spec2)


def _fmt_bait_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    spec = cand.get("spec") or {}
    name = cand.get("model") or cand.get("title", "Bait & Lures")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)

    weight = spec.get("weight_g", 7.0)
    b_type = spec.get("bait_type", "Lure Set")
    spec1 = f"Wt:{weight:.1f}g"
    spec2 = f"{b_type[:7]}"
    return ("BAIT", name, price_str, spec1, spec2)


def _fmt_tackle_row(cand: Dict[str, Any], disc_fmt: Callable[[float], str]) -> Tuple[str, str, str, str, str]:
    spec = cand.get("spec") or {}
    name = cand.get("model") or cand.get("title", "Tackle Kit")
    price = float(cand.get("price", 0.0))
    disc = float(cand.get("discount_pct", 0.0))
    deal_s = disc_fmt(disc)
    curr = cand.get("currency") or get_active_currency()
    price_str = f"{format_price(price, curr)} ({deal_s})" if price > 0 else format_price(0, curr)

    t_type = spec.get("item_type", "Tackle Kit")
    dur = spec.get("durability_score", 8.0)
    spec1 = f"{t_type[:11]}"
    spec2 = f"Qual:{dur:.0f}/10"
    return ("TACKLE", name, price_str, spec1, spec2)


# ── COMPATIBILITY RULES ───────────────────────────────────────────────────────

def _rule_rod_bait_test(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validates that bait weight falls within rod lure casting test bounds."""
    rod = set_dict.get("rod")
    bait = set_dict.get("bait")
    if not (rod and bait):
        return True, None

    r_spec = rod.get("spec") or {}
    b_spec = bait.get("spec") or {}

    t_min = float(r_spec.get("test_min_g", 1.0))
    t_max = float(r_spec.get("test_max_g", 15.0))
    b_wt = float(b_spec.get("weight_g", 7.0))

    if b_wt > t_max * 1.20:
        return False, f"Blank overload: lure weight {b_wt:.1f}g exceeds rod max test ({t_max:.1f}g)"
    if b_wt < t_min * 0.50:
        return False, f"Underweight lure: {b_wt:.1f}g is too light for rod casting test ({t_min:.1f}-{t_max:.1f}g)"
    return True, None


def _rule_rod_reel_balance(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validates that reel spool size is ergonomically balanced with rod power class."""
    rod = set_dict.get("rod")
    reel = set_dict.get("reel")
    if not (rod and reel):
        return True, None

    r_spec = rod.get("spec") or {}
    re_spec = reel.get("spec") or {}

    t_max = float(r_spec.get("test_max_g", 15.0))
    spool = int(re_spec.get("spool_size", 2500))

    if t_max <= 12.0 and spool > 2500:
        return False, f"Tackle imbalance: heavy {spool} spool on delicate light blank (max test {t_max:.0f}g)"
    if t_max >= 45.0 and spool < 3000:
        return False, f"Tackle imbalance: small {spool} spool is insufficient for heavy rod (test {t_max:.0f}g)"
    return True, None


def _rule_line_drag_safety(set_dict: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validates that line breaking strength aligns with reel drag power."""
    reel = set_dict.get("reel")
    line = set_dict.get("line")
    if not (reel and line):
        return True, None

    re_spec = reel.get("spec") or {}
    l_spec = line.get("spec") or {}

    drag = float(re_spec.get("drag_kg", 5.0))
    l_test = float(l_spec.get("test_kg") or l_spec.get("breaking_strength_kg", 6.0))

    if l_test < drag * 0.50:
        return False, f"Line snap risk: {l_test:.1f}kg line is too thin for reel with {drag:.0f}kg drag"
    if l_test > drag * 3.5:
        return False, f"Reel gear strain risk: {l_test:.1f}kg line dangerously exceeds reel drag ({drag:.0f}kg)"
    return True, None


def _fishing_headline_formatter(
    set_entry: Dict[str, Any],
    idx: int,
    total_cost: float,
    score: float,
    profile: Any,
) -> Tuple[str, str, str, str, str, str]:
    comps = set_entry["components"]
    rod = comps.get("rod", {})
    reel = comps.get("reel", {})
    bait = comps.get("bait", {})

    r_name = rod.get("model") or rod.get("title", "Rod")
    re_name = reel.get("model") or reel.get("title", "Reel")
    r_words = r_name.split()
    re_words = re_name.split()
    # Strip common leading brand or length/test suffixes for compact header
    r_short = " ".join(r_words[1:3]) if len(r_words) >= 3 else r_name[:15]
    re_short = " ".join(re_words[1:3]) if len(re_words) >= 3 else re_name[:15]
    title_col = f"Set #{idx}: {r_short} + {re_short}"
    curr = set_entry.get("currency") or (rod.get("currency")) or get_active_currency()
    score_col = f"{format_price(total_cost, curr)} (Score: {score:.1f})"
    surplus = set_entry.get("surplus", 0.0)
    if surplus > 0:
        surplus_str = f"+{format_price(surplus, curr)}"
    elif surplus == 0:
        surplus_str = format_price(0, curr)
    else:
        surplus_str = format_price(surplus, curr)

    r_spec = rod.get("spec") or {}
    re_spec = reel.get("spec") or {}
    b_spec = bait.get("spec") or {}
    avg_disc = sum(float(c.get("discount_pct", 0.0)) for c in comps.values()) / max(1, len(comps))

    line2_left = f"Tackle: {r_spec.get('power_class', 'Spinning')} │ Test:{r_spec.get('test_min_g', 1):.0f}-{r_spec.get('test_max_g', 10):.0f}g"
    line2_mid = f"Reel: {re_spec.get('spool_size', 2500)} ({re_spec.get('drag_kg', 5):.0f}kg)"
    from analyzer_core import fmt_deal_pct
    line2_right = f"Mkt: {fmt_deal_pct(avg_disc)}"

    return title_col, score_col, surplus_str, line2_left, line2_mid, line2_right


def create_fishing_layout() -> DomainLayout:
    """Instantiates the complete Fishing Domain Layout."""
    active_curr = get_active_currency()
    def_budget = 150.0 if canonical_currency(active_curr) == "USDT" else convert_currency(150.0, "USDT", active_curr)
    return DomainLayout(
        domain_id="fishing",
        title="Fishing Tackle Set",
        description="Combinatorial fishing tackle synthesizer matching rods, reels, lines, baits, and tackle accessories.",
        default_budget=def_budget,
        currency=active_curr,
        sections=[
            SectionDefinition(
                id="rod",
                name="Fishing Rod",
                label="ROD",
                description="Spinning, feeder, or carp fishing rod",
                budget_share_min=0.25,
                budget_share_max=0.55,
                pareto_limit=18,
                row_formatter=_fmt_rod_row,
            ),
            SectionDefinition(
                id="reel",
                name="Spinning Reel",
                label="REEL",
                description="Spinning reel with front drag system",
                budget_share_min=0.25,
                budget_share_max=0.50,
                pareto_limit=18,
                row_formatter=_fmt_reel_row,
            ),
            SectionDefinition(
                id="line",
                name="Braided / Mono Line",
                label="LINE",
                description="PE braided line or high-strength monofilament",
                budget_share_min=0.05,
                budget_share_max=0.18,
                pareto_limit=12,
                row_formatter=_fmt_line_row,
            ),
            SectionDefinition(
                id="bait",
                name="Baits & Lures",
                label="BAIT",
                description="Set of lures, jigs, crankbaits, or feeder cages",
                budget_share_min=0.05,
                budget_share_max=0.20,
                pareto_limit=15,
                row_formatter=_fmt_bait_row,
            ),
            SectionDefinition(
                id="tackle",
                name="Tackle & Accessories",
                label="TACKLE",
                description="Landing net, rig box, terminal tackle, and tools",
                budget_share_min=0.05,
                budget_share_max=0.20,
                pareto_limit=12,
                row_formatter=_fmt_tackle_row,
            ),
        ],
        compatibility_rules=[
            CompatibilityRule(
                name="rod_bait_test",
                description="Lure/feeder weight must fall within the rod blank casting test range",
                validator=_rule_rod_bait_test,
                sections_involved=("rod", "bait"),
            ),
            CompatibilityRule(
                name="rod_reel_balance",
                description="Reel spool size must ergonomically balance with the rod power class",
                validator=_rule_rod_reel_balance,
                sections_involved=("rod", "reel"),
            ),
            CompatibilityRule(
                name="line_drag_safety",
                description="Line breaking strength must align safely with the reel drag capacity",
                validator=_rule_line_drag_safety,
                sections_involved=("reel", "line"),
            ),
        ],
        headline_formatter=_fishing_headline_formatter,
    )
