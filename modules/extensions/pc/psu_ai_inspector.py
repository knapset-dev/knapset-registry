"""
PSU AI Semantic Inspector for OLX Listings.
Supports all configured AI providers and persists verdicts in AuditLedger.
"""

from typing import Dict, Any
from ai_inspector import BaseHardwareAIInspector


class PSUAIInspector(BaseHardwareAIInspector):
    category = "psu"

    def build_candidate_payload(self, idx: int, cand: Dict[str, Any], clean_desc: str) -> Dict[str, Any]:
        p = cand.get("psu") or cand.get("spec") or {}
        wattage = int(p.get("wattage", cand.get("wattage", 750)))
        tier = p.get("vrm_tier", cand.get("tier", "Tier B"))
        return {
            "candidate_id": idx,
            "listing_id": cand.get("summary", {}).get("id", cand.get("id")),
            "model": p.get("model", cand.get("model", "")),
            "brand": p.get("brand", cand.get("brand", "")),
            "wattage": wattage,
            "efficiency": p.get("efficiency", cand.get("efficiency", "Gold")),
            "modularity": p.get("modularity", "Semi-Modular"),
            "form_factor": p.get("form_factor", "ATX"),
            "tier": tier,
            "has_12vhpwr": p.get("has_12vhpwr", False),
            "price_uah": cand.get("price", 0),
            "uah_per_watt": round(float(cand.get("price", 0)) / max(1, wattage), 2),
            "risk_level": p.get("risk_level", "LOW"),
            "safety_notes": p.get("risk_notes", ""),
            "title": cand.get("summary", {}).get("title", cand.get("title", "")),
            "seller_name": cand.get("summary", {}).get("seller_name", "Unknown"),
            "seller_account_created": str(cand.get("summary", {}).get("seller_created", ""))[:10],
            "olx_delivery_enabled": cand.get("summary", {}).get("has_olx_delivery", True),
            "description": clean_desc,
        }

    def build_prompt(self, payload_json: str, sort_by: str) -> str:
        return f"""You are an expert electrical & PC PSU safety inspector analyzing classified ads on OLX.ua (Ukraine).
Detect subtle human nuance, missing modular cable hazards, or covert red flags in Ukrainian/Russian/English.

CRITICAL PSU CHECKS:
1. Missing Modular Cables (MANDATORY REJECT on modular PSUs if PCIe/CPU cables missing):
   - "без кабелів", "неповний комплект проводів", "тільки 24-pin", "немає кабеля на відеокарту". Non-standard OEM pinouts destroy hardware if mixed!
2. Electrical & Mechanical Failures (MANDATORY REJECT):
   - Trips protection / shuts down under load ("йде в захист", "вимикається в іграх"), repaired/soldered/swollen caps ("після ремонту", "паявся"), loud dying fan bearing ("гуде/тріщить кулер").
3. Known Fire / Explosion Hazards (MANDATORY REJECT):
   - Aerocool KCAS, Aerocool VX, Gigabyte GP-P750GM / P850GM early explosive revisions, or noisy server/mining PSUs.
4. Delivery Refusal & Prepayment Traps (MANDATORY REJECT):
   - Refusing OLX Delivery / postal shipping ("тільки самовивіз", "без пошти", "передплата").

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
      "reasons": ["Reputable PSU tier with full original cable set", "Unbroken seal & OLX Delivery"]
    }}
  ],
  "final_ranked_ids": [1],
  "disqualified_ids": []
}}"""
