"""
CPU AI Semantic Inspector for OLX Listings.
Supports all configured AI providers and persists verdicts in AuditLedger.
"""

from typing import Dict, Any
from ai_inspector import BaseHardwareAIInspector


class CPUAIInspector(BaseHardwareAIInspector):
    category = "cpu"

    def build_candidate_payload(self, idx: int, cand: Dict[str, Any], clean_desc: str) -> Dict[str, Any]:
        c = cand.get("cpu") or cand.get("spec") or {}
        fps_g = float(cand.get("fps_gaming", c.get("fps_gaming", 100.0)))
        return {
            "candidate_id": idx,
            "listing_id": cand.get("summary", {}).get("id", cand.get("id")),
            "model": c.get("model", cand.get("model", "")),
            "threads": c.get("threads", 8),
            "l3_cache_mb": c.get("l3_cache_mb", 32),
            "socket": c.get("socket", "AM5"),
            "price_uah": cand.get("price", 0),
            "market_range_uah": f"{c.get('market_used_min', 0)}-{c.get('market_used_max', 0)}",
            "gaming_fps_index": fps_g,
            "gaming_1pct_low_fps": c.get("fps_1pct_low", round(fps_g * 0.73, 1)),
            "cb_r23_multi": c.get("cb_r23_multi", c.get("threads", 8) * 950),
            "cost_uah_per_fps": cand.get("uah_per_fps", round(float(cand.get("price", 0)) / max(1.0, fps_g), 1)),
            "title": cand.get("summary", {}).get("title", cand.get("title", "")),
            "seller_name": cand.get("summary", {}).get("seller_name", "Unknown"),
            "seller_account_created": str(cand.get("summary", {}).get("seller_created", ""))[:10],
            "olx_delivery_enabled": cand.get("summary", {}).get("has_olx_delivery", True),
            "description": clean_desc,
        }

    def build_prompt(self, payload_json: str, sort_by: str) -> str:
        return f"""You are an expert PC hardware inspector analyzing CPU classified ads on OLX.ua (Ukraine).
Detect subtle human nuance, evasive language, excuses, or covert red flags in Ukrainian/Russian/English.

CRITICAL CPU CHECKS:
1. Pin & Pad Integrity (AM4 PGA / LGA Pads):
   - Bent, broken, missing, or re-soldered pins ("погнуті/відламані/вирівняні ніжки"), dead memory channel ("працює тільки 1 канал ОЗП"), dead PCIe lanes -> REJECT.
2. Silicon Degradation & Delidding:
   - Intel 13th/14th Gen (13600K/13700K/13900K/14700K/14900K) instability, BSODs, crashes in UE5/shader compilation -> REJECT.
   - Engineering/Qualification samples (ES/QS/QTB0/QNCT) sold as retail, or botched delid ("скальпований") -> REJECT or heavy CAUTION.
3. Evasions, Bait Pricing & Delivery Refusal (MANDATORY REJECT):
   - "немає материнки перевірити", "не знаю чи робочий", "без претензій і повернень".
   - Storefront multi-CPU list where price is for the cheapest Celeron/Athlon.
   - Seller refusing shipping / OLX Delivery ("тільки самовивіз", "без пошти", "передплата").

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
      "reasons": ["Straight pins / verified working CPU", "Fair market price"]
    }}
  ],
  "final_ranked_ids": [1],
  "disqualified_ids": []
}}"""
