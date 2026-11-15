"""
Motherboard AI Semantic Inspector for OLX Listings.
Supports all configured AI providers and persists verdicts in AuditLedger.
"""

from typing import Dict, Any
from ai_inspector import BaseHardwareAIInspector


class MotherboardAIInspector(BaseHardwareAIInspector):
    category = "mobo"

    def build_candidate_payload(self, idx: int, cand: Dict[str, Any], clean_desc: str) -> Dict[str, Any]:
        m = cand.get("mobo") or cand.get("spec") or {}
        return {
            "candidate_id": idx,
            "listing_id": cand.get("summary", {}).get("id", cand.get("id")),
            "model": m.get("model", cand.get("model", "")),
            "socket": m.get("socket", cand.get("socket", "AM5")),
            "chipset": m.get("chipset", ""),
            "ddr_type": m.get("ddr_type", cand.get("ddr_type", "DDR5")),
            "form_factor": m.get("form_factor", "ATX"),
            "vrm_tier": m.get("vrm_tier", cand.get("vrm_tier", "B-Tier")),
            "has_wifi": m.get("has_wifi", False),
            "is_bundle": m.get("is_bundle", False),
            "price_uah": cand.get("price", 0),
            "market_range_uah": f"{m.get('market_used_min', 0)}-{m.get('market_used_max', 0)}",
            "risk_level": m.get("risk_level", "LOW"),
            "title": cand.get("summary", {}).get("title", cand.get("title", "")),
            "seller_name": cand.get("summary", {}).get("seller_name", "Unknown"),
            "seller_account_created": str(cand.get("summary", {}).get("seller_created", ""))[:10],
            "olx_delivery_enabled": cand.get("summary", {}).get("has_olx_delivery", True),
            "description": clean_desc,
        }

    def build_prompt(self, payload_json: str, sort_by: str) -> str:
        return f"""You are an expert PC hardware technician analyzing Motherboard classified ads on OLX.ua (Ukraine).
Detect subtle human nuance, evasive language, excuses, or covert red flags in Ukrainian/Russian/English.

CRITICAL MOTHERBOARD CHECKS:
1. Socket Pin Damage & Trace Failures (MANDATORY REJECT):
   - Bent, broken, or straightened socket pins ("погнуті/відламані/рівнялись ніжки сокета").
   - Hidden socket symptoms: "не працює 1-2 слоти пам'яті", "тільки одноканал", dead PCIe x16 slot, dead LAN/audio after lightning/surge.
2. Boot / POST / Repair Issues (MANDATORY REJECT):
   - "не стартує", "немає ініціалізації", "горить CPU/DRAM LED", "після ремонту/КЗ/грози", bricked BIOS ("невдала прошивка").
3. Accessories & Quirks (CAUTION):
   - Missing AM4/AM5 cooler backplate ("без бекплейту") or missing rear I/O shield ("без заглушки"), or Chinese X99/B450 boards (Machinist/Huananzhi).
4. Delivery Refusal & Prepayment Traps (MANDATORY REJECT):
   - Refusing OLX Delivery / shipping ("тільки самовивіз", "без пошти", "передплата на картку").

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
      "confidence_score": 88,
      "reasons": ["Intact socket pins and dual-channel verified", "OLX Delivery active"]
    }}
  ],
  "final_ranked_ids": [1],
  "disqualified_ids": []
}}"""
