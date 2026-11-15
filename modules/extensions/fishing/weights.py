"""
Fishing Domain Weights & Optimization Modes.

Defines scoring criteria:
- casting: Casting distance and accuracy
- durability: Blank strength and reel mechanism longevity
- lightness: Tackle lightness (ergonomic balance, minimal fatigue)
- value: Cost efficiency (performance-to-price ratio)
- deal: Discount vs median market price
- safety: Seller reliability and buyer protection / escrow

And tailored optimization profiles:
- spinning-light: Light/Ultralight predator spinning (sensitivity + lightness)
- feeder-distance: Long-range feeder rig (power + casting distance)
- budget-angler: Maximum value and reliability on a budget
- carp-heavy: Heavy trophy carp rig (blank power + drag capacity)
"""

from __future__ import annotations

from typing import Any, Dict

from currency import canonical_currency, convert_currency, get_active_currency
from domain_weights import CriterionDefinition, DomainScorer, WeightProfile, WeightRegistry


def _score_fishing_component(section_id: str, item: Dict[str, Any], profile: WeightProfile) -> float:
    """Calculates normalized score (0..100) for a fishing tackle item under the active profile."""
    spec = item.get("spec") or {}
    raw_price = max(0.01, float(item.get("price", 1.0)))
    curr = item.get("currency")
    if curr and canonical_currency(curr) != "UAH":
        price = max(1.0, convert_currency(raw_price, curr, "UAH"))
    else:
        price = max(1.0, raw_price)
    w = profile.normalized_weights()

    # Base ratings
    rating = float(spec.get("rating", 75.0))
    disc = float(item.get("discount_pct", 0.0))
    deal_score = min(100.0, max(0.0, 50.0 + disc * 1.5))
    risk = float((item.get("eval") or item.get("heuristic") or {}).get("risk_score", 0.0))
    safety_score = max(0.0, 100.0 - risk * 1.8)

    # Casting score
    casting_score = 50.0
    if section_id == "rod":
        length = float(spec.get("length_m", 2.1))
        casting_score = min(100.0, max(30.0, length * 26.0))
    elif section_id == "reel":
        spool = float(spec.get("spool_size", 2500))
        bearings = float(spec.get("bearing_count", 4))
        casting_score = min(100.0, 40.0 + (spool / 100.0) + (bearings * 5.0))
    elif section_id == "line":
        diam = float(spec.get("diameter_mm", 0.12))
        casting_score = min(100.0, max(30.0, 100.0 - diam * 250.0))

    # Durability score
    durability_score = 70.0
    if section_id == "rod":
        durability_score = float(spec.get("durability", 75.0))
    elif section_id == "reel":
        drag = float(spec.get("drag_kg", 5.0))
        durability_score = min(100.0, drag * 9.0)
    elif section_id == "line":
        test = float(spec.get("test_kg", 5.0))
        durability_score = min(100.0, test * 8.0)
    elif section_id == "tackle":
        durability_score = float(spec.get("durability_score", 8.0)) * 10.0

    # Lightness score (lower weight = higher score)
    weight_g = float(spec.get("weight_g", 150.0))
    if section_id in ("rod", "reel"):
        lightness_score = min(100.0, max(20.0, 140.0 - (weight_g / 3.0)))
    else:
        lightness_score = 75.0

    # Value score (quality / price)
    raw_perf = (casting_score * 0.4 + durability_score * 0.4 + lightness_score * 0.2)
    val_score = min(100.0, max(10.0, (raw_perf / price) * 1500.0))

    # Condition & novelty detection
    is_new = bool(item.get("is_new") or item.get("condition") == "new")
    condition = str(item.get("condition") or ("new" if is_new else "used")).lower()
    cond_score = 100.0 if (is_new or condition == "new") else (70.0 if condition == "refurbished" else 40.0)
    w_cond = w.get("condition", w.get("new", 0.0))

    if is_new or condition == "new":
        safety_score = min(100.0, safety_score + 8.0)

    score = (
        w.get("casting", 0.20) * casting_score
        + w.get("durability", 0.20) * durability_score
        + w.get("lightness", 0.20) * lightness_score
        + w.get("value", 0.20) * val_score
        + w.get("deal", 0.10) * deal_score
        + w.get("safety", 0.10) * safety_score
        + w_cond * cond_score
    )

    if is_new or condition == "new":
        score += 2.0  # Novelty / factory condition bonus
    elif condition in ("for_parts", "not_working"):
        score -= 500.0

    return round(score, 2)


def _score_fishing_set(set_dict: Dict[str, Dict[str, Any]], profile: WeightProfile, budget: float) -> float:
    """Calculates composite fishing tackle set score including balance and synergy."""
    comp_scores = []
    total_cost = 0.0
    for sec_id, it in set_dict.items():
        total_cost += float(it.get("price", 0.0))
        s = it.get("mode_score")
        if s is None:
            s = _score_fishing_component(sec_id, it, profile)
        comp_scores.append(s)

    if not comp_scores:
        return 0.0

    base = sum(comp_scores) / len(comp_scores)

    # Condition bonus across set
    new_count = sum(1 for it in set_dict.values() if it.get("is_new") or it.get("condition") == "new")
    if new_count > 0:
        base += new_count * 1.2

    # Synergy bonus for matched brand / ecosystem (e.g. Daiwa + Daiwa or Favorite + Favorite)
    brands = [
        str(it.get("spec", {}).get("brand", it.get("model", "").split()[0])).lower()
        for it in set_dict.values()
    ]
    if len(brands) >= 2 and brands[0] == brands[1] and brands[0] != "unknown":
        base += 2.5  # Brand ergonomics synergy bonus

    # Budget discipline bonus
    if budget > 0 and total_cost <= budget:
        surplus_pct = (budget - total_cost) / budget
        base += min(4.0, surplus_pct * 8.0)

    return round(min(100.0, max(0.0, base)), 2)


def create_fishing_weights_registry() -> WeightRegistry:
    """Instantiates the complete Fishing Weight Registry with criteria and profiles."""
    reg = WeightRegistry(domain_id="fishing", default_profile_name="spinning-light")

    # Criteria
    reg.register_criterion(CriterionDefinition("casting", "Casting Distance", "Prioritizes blank length, thin braided line, and smooth spool lip", default_weight=0.25))
    reg.register_criterion(CriterionDefinition("durability", "Durability & Strength", "Prioritizes blank material resilience, drag power, and breaking strength", default_weight=0.20))
    reg.register_criterion(CriterionDefinition("lightness", "Lightness & Ergonomics", "Minimizes tackle weight for comfortable all-day angling without fatigue", default_weight=0.20))
    reg.register_criterion(CriterionDefinition("value", "Price-to-Performance", "Maximizes functional tackle specs per currency unit spent", default_weight=0.20))
    reg.register_criterion(CriterionDefinition("deal", "Market Deal", "Discount percentage below median market price", default_weight=0.10))
    reg.register_criterion(CriterionDefinition("condition", "Item Condition (New vs Used)", "Prefers factory-new tackle without hidden wear", default_weight=0.10))
    reg.register_criterion(CriterionDefinition("safety", "Deal Safety", "Verified seller, minimal risk score, and escrow buyer protection", default_weight=0.05))

    # Profiles
    reg.register_profile(
        WeightProfile(
            name="spinning-light",
            title="Light & Ultralight Spinning",
            description="Sensitive, lightweight setup for perch, zander, and pike. Maximum blank feedback and low weight.",
            domain_id="fishing",
            weights={"lightness": 0.32, "casting": 0.28, "value": 0.20, "durability": 0.10, "deal": 0.05, "safety": 0.05},
        )
    )

    reg.register_profile(
        WeightProfile(
            name="feeder-distance",
            title="Feeder Distance Master",
            description="Long-range feeder rig for bream, roach, and carp. Prioritizes casting distance and cranking power.",
            domain_id="fishing",
            weights={"casting": 0.35, "durability": 0.30, "value": 0.18, "deal": 0.09, "safety": 0.08},
        )
    )

    reg.register_profile(
        WeightProfile(
            name="budget-angler",
            title="Pure Value Fisher",
            description="Maximum budget efficiency: reliable, field-proven tackle setup without brand markup.",
            domain_id="fishing",
            weights={"value": 0.45, "deal": 0.25, "durability": 0.15, "casting": 0.10, "safety": 0.05},
        )
    )

    reg.register_profile(
        WeightProfile(
            name="carp-heavy",
            title="Heavy Carp & Trophy",
            description="High-power trophy carp setup: heavy blank backbone, high-drag reel, and abrasion-resistant braid.",
            domain_id="fishing",
            weights={"durability": 0.45, "casting": 0.25, "value": 0.15, "safety": 0.10, "deal": 0.05},
        )
    )

    return reg


def create_fishing_scorer() -> DomainScorer:
    """Instantiates the scoring engine for the fishing domain."""
    return DomainScorer(
        component_scorer=_score_fishing_component,
        set_scorer=_score_fishing_set,
    )
