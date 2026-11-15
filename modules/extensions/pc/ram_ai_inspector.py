"""
RAM AI Semantic Inspector for OLX Listings.
Supports all configured AI providers and persists verdicts in AuditLedger.
"""

from typing import Dict, Any
from ai_inspector import BaseHardwareAIInspector


class RAMAIInspector(BaseHardwareAIInspector):
    category = "ram"

    def build_candidate_payload(self, idx: int, cand: Dict[str, Any], clean_desc: str) -> Dict[str, Any]:
        r = cand.get("ram") or cand.get("spec") or {}
        gb = float(r.get("total_gb", cand.get("total_gb", 16)))
        return {
            "candidate_id": idx,
            "listing_id": cand.get("summary", {}).get("id", cand.get("id")),
            "model": r.get("model", cand.get("model", "")),
            "generation": r.get("generation", r.get("gen", cand.get("gen", "DDR5"))),
            "form_factor": r.get("form_factor", "UDIMM"),
            "config": r.get("config", f"2x{int(gb/2)}GB"),
            "total_gb": gb,
            "speed_mhz": r.get("speed_mhz", cand.get("speed_mhz", 5600)),
            "cas_latency": f"CL{r.get('cas_latency', 38)}",
            "latency_ns": f"{r.get('latency_ns', cand.get('latency_ns', 13.6))}ns",
            "price_uah": cand.get("price", 0),
            "uah_per_gb": cand.get("uah_per_gb", round(float(cand.get("price", 0)) / max(1.0, gb), 1)),
            "title": cand.get("summary", {}).get("title", cand.get("title", "")),
            "seller_name": cand.get("summary", {}).get("seller_name", "Unknown"),
            "seller_account_created": str(cand.get("summary", {}).get("seller_created", ""))[:10],
            "olx_delivery_enabled": cand.get("summary", {}).get("has_olx_delivery", True),
            "description": clean_desc,
        }

    def build_prompt(self, payload_json: str, sort_by: str) -> str:
        return f"""You are an expert PC memory inspector analyzing DDR4/DDR5 RAM classified ads on OLX.ua (Ukraine).
Detect subtle human nuance, evasive language, bait pricing, or covert red flags in Ukrainian/Russian/English.

CRITICAL RAM CHECKS:
1. Per-Stick Bait Pricing (MANDATORY REJECT if deceptive):
   - Title advertises a kit (e.g. "32GB 2x16GB") while text says "ціна за 1 планку" / "цена за штуку", or tiered multi-item pricing ("ціна від...").
2. Form Factor Mismatch:
   - Server ECC Registered (RDIMM/LRDIMM) incompatible with desktop consumer boards -> REJECT unless clearly sought.
   - Laptop SO-DIMM -> mark CAUTION if easily confused with desktop UDIMM.
3. Stability & Physical Integrity (MANDATORY REJECT):
   - MemTest86/TM5 errors, BSODs, fails XMP/EXPO profile, knocked-off SMD capacitors, untested ("немає на чому перевірити").
4. Delivery Refusal & Prepayment Traps (MANDATORY REJECT):
   - Refusing OLX Delivery / postal shipping ("тільки самовивіз", "без відправок", "передплата").

Input Listings:
```json
{payload_json}
```

Return ONLY valid JSON matching this exact schema (ranking approved items for {sort_by.upper()}):
{{
  "evaluations": [
    {{
      "candidate_id": 1,
      "verdict": "APPROVED",
      "confidence_score": 90,
      "reasons": ["Clean desktop UDIMM kit, price is for full kit", "OLX Delivery active"]
    }}
  ],
  "final_ranked_ids": [1],
  "disqualified_ids": []
}}"""
