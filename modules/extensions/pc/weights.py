"""
PC Domain Weights & Optimization Modes.

Integrates with modes.py to provide criteria and profiles for the PC domain.
"""

from __future__ import annotations

from typing import Any, Dict

from domain_weights import CriterionDefinition, DomainScorer, WeightProfile, WeightRegistry
from extensions.pc.modes import BUILTIN_MODES, ModeProfile, score_build, score_component


def _profile_to_mode_profile(profile: WeightProfile) -> ModeProfile:
    c = profile.constraints or {}
    base = BUILTIN_MODES.get(profile.name)
    return ModeProfile(
        name=profile.name,
        title=profile.title,
        description=profile.description,
        max_risk=profile.max_risk,
        require_delivery=profile.require_delivery,
        block_critical_arch=bool(c.get("block_critical_arch", getattr(base, "block_critical_arch", False))),
        prefer_nvidia=bool(c.get("prefer_nvidia", getattr(base, "prefer_nvidia", False))),
        min_vram_gb=int(c.get("min_vram_gb", getattr(base, "min_vram_gb", 0))),
        min_ram_gb=int(c.get("min_ram_gb", getattr(base, "min_ram_gb", 0))),
        min_psu_tier=str(c.get("min_psu_tier", getattr(base, "min_psu_tier", "Tier C"))),
        preferred_sockets=tuple(c.get("preferred_sockets", getattr(base, "preferred_sockets", ()))),
        preferred_ddr=c.get("preferred_ddr", getattr(base, "preferred_ddr", None)),
        form_factors=tuple(c.get("form_factors", getattr(base, "form_factors", ()))),
        weights=profile.weights,
        is_custom=profile.is_custom,
    )


def _score_pc_component(section_id: str, candidate: Dict[str, Any], profile: WeightProfile) -> float:
    return score_component(section_id, candidate, _profile_to_mode_profile(profile))


def _score_pc_build(set_dict: Dict[str, Dict[str, Any]], profile: WeightProfile, budget: float) -> float:
    mp = _profile_to_mode_profile(profile)
    b = dict(set_dict)
    if "total_cost" not in b:
        b["total_cost"] = sum(
            float(b.get(k, {}).get("price", 0.0))
            for k in ("gpu", "cpu", "mobo", "ram", "psu")
        )
    return score_build(b, budget, mp)


def create_pc_weights_registry() -> WeightRegistry:
    reg = WeightRegistry(domain_id="pc", default_profile_name="best")

    reg.register_criterion(CriterionDefinition("perf", "Gaming & Compute Performance", "Raw 1440p FPS, CPU multicore, single-thread index", default_weight=0.50))
    reg.register_criterion(CriterionDefinition("value", "Price / Performance Efficiency", "Cost efficiency per FPS and per gigabyte", default_weight=0.20))
    reg.register_criterion(CriterionDefinition("tier", "Hardware & Silicon Quality", "VRM phases, PSU tier ranking, Japanese capacitors", default_weight=0.15))
    reg.register_criterion(CriterionDefinition("future", "Future Upgrade Headroom", "AM5/LGA1700 platform runway, PCIe 4.0/5.0, DDR5", default_weight=0.10))
    reg.register_criterion(CriterionDefinition("condition", "Item Condition (New vs Used)", "Rewards brand new, factory sealed, and warranty covered hardware", default_weight=0.10))
    reg.register_criterion(CriterionDefinition("safety", "Buyer Protection & Low Risk", "Minimizes seller risk, ex-mining risk, and defect probability", default_weight=0.05))

    for k, p in BUILTIN_MODES.items():
        reg.register_profile(
            WeightProfile(
                name=p.name,
                title=p.title,
                description=p.description,
                domain_id="pc",
                weights=dict(p.weights),
                constraints={
                    "block_critical_arch": p.block_critical_arch,
                    "prefer_nvidia": p.prefer_nvidia,
                    "min_psu_tier": p.min_psu_tier,
                    "min_vram_gb": p.min_vram_gb,
                    "min_ram_gb": p.min_ram_gb,
                    "preferred_sockets": p.preferred_sockets,
                    "preferred_ddr": p.preferred_ddr,
                    "form_factors": p.form_factors,
                },
                max_risk=p.max_risk,
                require_delivery=p.require_delivery,
                is_custom=p.is_custom,
            )
        )

    return reg


def create_pc_scorer() -> DomainScorer:
    return DomainScorer(
        component_scorer=_score_pc_component,
        set_scorer=_score_pc_build,
    )
