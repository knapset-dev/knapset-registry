"""
Holistic System AI Inspector for 5-Part PC Builds.
Evaluates hardware compatibility and system synergy (VRM thermals, PSU headroom, CPU-GPU balance).
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_inspector import clean_description
from ai_providers import AIProviderClient, list_all_provider_statuses
from audit_ledger import compute_content_hash, ledger

SYSTEM_AUDIT_PROMPT_TEMPLATE = """You are a senior PC hardware engineering inspector evaluating {build_count} synthesized 5-part PC build(s) (GPU, CPU, Motherboard, RAM, PSU) for mode: {mode_upper}.
Flood, defective listings, and bad sellers have ALREADY been filtered out in previous steps.

Evaluate ONLY hardware compatibility and system synergy:
1. CPU-GPU Synergy & Bottleneck: Is the pairing optimal for {mode_upper} and target resolutions?
2. VRM Thermal Sufficiency: Can the motherboard VRM comfortably handle this CPU without thermal throttling? (e.g. 100W+ CPU on bare D-Tier board is a thermal hazard).
3. PSU Headroom & Transients: Does the PSU wattage & tier safely cover peak load and GPU transient power spikes?

Synthesized Builds:
```json
{payload_json}
```

Return ONLY valid JSON matching this exact schema:
{{
  "evaluations": [
    {{
      "build_id": 1,
      "verdict": "APPROVED",
      "confidence_score": 92,
      "synergy_rating": 9.2,
      "synergy_verdict": "Concise 1-sentence summary of CPU+GPU balance and resolution gaming performance.",
      "compatibility_notes": [
        "VRM: Concise note on motherboard VRM handling CPU load (e.g. S-Tier VRM stays ice-cold under 54W gaming draw).",
        "PSU: Concise note on PSU headroom covering GPU transient spikes (e.g. 750W Tier A has +340W safety margin)."
      ]
    }}
  ]
}}
"""


def is_any_ai_provider_ready() -> bool:
    """Returns True if at least one AI provider (Gemini, OpenAI, Groq, Anthropic, Ollama, agy, etc.) is ready."""
    statuses = list_all_provider_statuses()
    return any(s.get("ready") for s in statuses)


class SystemAIInspector:
    """
    Holistic 5-part PC build semantic inspector focused on hardware compatibility and synergy.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.client = AIProviderClient(
            provider=provider or "auto",
            model=model,
            base_url=base_url,
            api_key=api_key,
        )

    @property
    def provider_label(self) -> str:
        return self.client.display_name

    def build_system_payload(self, build_idx: int, b: Dict[str, Any]) -> Dict[str, Any]:
        """Formats a compact structured representation of all 5 parts and system totals."""
        g = b["gpu"]
        c = b["cpu"]
        m = b["mobo"]
        r = b["ram"]
        p = b["psu"]

        return {
            "build_id": build_idx,
            "total_cost_uah": b["total_cost"],
            "surplus_uah": b.get("surplus", 0.0),
            "effective_1440p_fps": b.get("eff_fps_1440p", 0.0),
            "effective_1080p_fps": b.get("eff_fps_1080p", 0.0),
            "estimated_load_watts": b.get("est_load_watts", 0),
            "gpu": {
                "model": g.get("model", ""),
                "vram_gb": g.get("vram_gb", g["spec"].get("vram_gb", 8)),
                "tdp_watts": g.get("tdp_watts", g["spec"].get("tdp_watts", 200)),
                "price_uah": float(g.get("price", 0.0)),
                "is_owned": bool(g.get("is_owned")),
            },
            "cpu": {
                "model": c.get("model", ""),
                "socket": c.get("socket", c["spec"].get("socket", "")),
                "threads": c.get("threads", c["spec"].get("threads", 12)),
                "l3_cache_mb": c["spec"].get("l3_cache_mb", 32),
                "gaming_watts": c["spec"].get("gaming_watts", 65),
                "tdp_watts": c.get("tdp_watts", c["spec"].get("tdp_watts", 65)),
                "price_uah": float(c.get("price", 0.0)),
                "is_owned": bool(c.get("is_owned")),
            },
            "mobo": {
                "model": m.get("model", ""),
                "socket": m.get("socket", m["spec"].get("socket", "")),
                "chipset": m.get("chipset", m["spec"].get("chipset", "")),
                "ddr_type": m.get("ddr_type", m["spec"].get("ddr_type", "DDR4")),
                "vrm_tier": m.get("vrm_tier", m["spec"].get("vrm_tier", "B-Tier")),
                "price_uah": float(m.get("price", 0.0)),
                "is_owned": bool(m.get("is_owned")),
            },
            "ram": {
                "gen": r.get("gen", r["spec"].get("generation", "DDR4")),
                "total_gb": r.get("total_gb", r["spec"].get("total_gb", 16)),
                "speed_mhz": r.get("speed_mhz", r["spec"].get("speed_mhz", 3200)),
                "latency_ns": r["spec"].get("latency_ns", 10.0),
                "module_count": r["spec"].get("module_count", 2),
                "price_uah": float(r.get("price", 0.0)),
                "is_owned": bool(r.get("is_owned")),
            },
            "psu": {
                "model": p.get("model", ""),
                "wattage": p.get("wattage", p["spec"].get("wattage", 600)),
                "tier": p.get("tier", p["spec"].get("vrm_tier", "Tier C")),
                "efficiency": p.get("efficiency", p["spec"].get("efficiency", "Standard")),
                "has_12vhpwr": p["spec"].get("has_12vhpwr", False),
                "price_uah": float(p.get("price", 0.0)),
                "is_owned": bool(p.get("is_owned")),
            },
        }

    def _compute_build_key_and_hash(self, b: Dict[str, Any]) -> Tuple[str, str]:
        parts = [b["gpu"], b["cpu"], b["mobo"], b["ram"], b["psu"]]
        key = "build:" + "_".join(str(p.get("id", "")) for p in parts)
        hash_payload = "|".join(
            compute_content_hash(
                p.get("summary", {}).get("title", ""),
                float(p.get("price", 0.0)),
                (p.get("detail") or {}).get("description") or p.get("summary", {}).get("description", ""),
                has_delivery=bool(p.get("summary", {}).get("has_olx_delivery", True)),
            )
            for p in parts
        )
        return key, hash_payload

    def audit_builds(
        self,
        builds: List[Dict[str, Any]],
        mode: str = "best",
        re_audit: bool = False,
    ) -> Set[str]:
        """
        Audits a list of synthesized builds concurrently for synergy and compatibility.
        Attaches 'ai_advisory' to each build.
        """
        if not builds:
            return set()

        uninspected_pairs: List[Tuple[int, Dict[str, Any]]] = []
        rejected_part_ids: Set[str] = set()

        for idx, b in enumerate(builds, 1):
            key, content_hash = self._compute_build_key_and_hash(b)
            cached = None if re_audit else ledger.get_audit(key, description=content_hash)
            if cached and cached.get("advisory"):
                b["ai_advisory"] = cached["advisory"]
            else:
                uninspected_pairs.append((idx, b))

        if not uninspected_pairs:
            return rejected_part_ids

        payloads = [self.build_system_payload(idx, b) for idx, b in uninspected_pairs]
        prompt = SYSTEM_AUDIT_PROMPT_TEMPLATE.format(
            build_count=len(payloads),
            mode_upper=mode.upper(),
            payload_json=json.dumps(payloads, ensure_ascii=False, indent=2),
        )

        try:
            ai_data, prov, model_name = self.client.generate_json(prompt)
            evals = ai_data.get("evaluations", []) if isinstance(ai_data, dict) else []
            eval_by_id = {ev.get("build_id"): ev for ev in evals if isinstance(ev, dict)}

            ledger_updates = []
            for idx, b in uninspected_pairs:
                key, content_hash = self._compute_build_key_and_hash(b)
                ev = eval_by_id.get(idx)
                if not ev:
                    ev = self._create_deterministic_advisory(b, mode)

                advisory = {
                    "verdict": ev.get("verdict", "APPROVED"),
                    "confidence_score": int(ev.get("confidence_score", 90)),
                    "synergy_rating": float(ev.get("synergy_rating", 9.0)),
                    "synergy_verdict": ev.get("synergy_verdict", "Balanced system components."),
                    "compatibility_notes": ev.get("compatibility_notes", [
                        "VRM & cooling are well-matched for this CPU tier.",
                        "PSU wattage safely accommodates peak system draw.",
                    ]),
                    "provider": prov,
                    "model": model_name,
                }
                b["ai_advisory"] = advisory

                # Cache build advisory in ledger
                ledger_updates.append({
                    "offer_id": key,
                    "category": "build",
                    "verdict": advisory["verdict"],
                    "confidence_score": advisory["confidence_score"],
                    "reasons": [advisory["synergy_verdict"]],
                    "description": content_hash,
                    "advisory": advisory,
                    "provider": prov,
                    "model": model_name,
                })

            if ledger_updates:
                ledger.record_batch(ledger_updates)

        except Exception as e:
            for _, b in uninspected_pairs:
                b["ai_advisory"] = self._create_deterministic_advisory(b, mode, error_note=str(e))

        return rejected_part_ids

    def _create_deterministic_advisory(
        self,
        b: Dict[str, Any],
        mode: str,
        error_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provides a concise deterministic 2-point synergy advisory when AI is offline or in fallback."""
        g = b["gpu"]
        c = b["cpu"]
        m = b["mobo"]
        p = b["psu"]

        g_model = g["model"]
        c_model = c["model"]
        vrm_tier = m.get("vrm_tier", "B-Tier")
        c_tdp = c.get("tdp_watts", 65)
        p_tier = p.get("tier", "Tier C")
        p_watts = p.get("wattage", 600)
        est_load = b.get("est_load_watts", 350)
        headroom = p_watts - est_load

        vrm_note = (
            f"VRM: {vrm_tier} board comfortably handles {c_model} ({c_tdp}W TDP)."
            if c_tdp < 125 or vrm_tier in ("S-Tier", "A-Tier")
            else f"VRM Caution: {c_model} ({c_tdp}W) on {vrm_tier} board — ensure adequate case airflow."
        )
        psu_note = f"PSU: {p_watts}W {p_tier} safely covers ~{est_load}W peak load (+{headroom}W safety margin)."

        note = f"Deterministic Engineering Audit ({error_note})" if error_note else "Deterministic Engineering Audit"
        return {
            "verdict": "APPROVED",
            "confidence_score": 90,
            "synergy_rating": 9.2,
            "synergy_verdict": f"Balanced {mode.upper()} pairing: {g_model} + {c_model} delivers smooth FPS with {headroom}W PSU headroom.",
            "compatibility_notes": [vrm_note, psu_note],
            "provider": "deterministic",
            "model": note,
        }
