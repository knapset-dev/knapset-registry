"""
GPU AI Semantic Inspector for OLX Listings.
Supports any AI provider (Gemini, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, Ollama, CLI)
and memoizes verdicts into the persistent AuditLedger.
"""

from typing import Dict, Any
from ai_inspector import BaseHardwareAIInspector


class GPUAIInspector(BaseHardwareAIInspector):
    category = "gpu"

    def build_candidate_payload(self, idx: int, cand: Dict[str, Any], clean_desc: str) -> Dict[str, Any]:
        g = cand.get("gpu") or cand.get("spec") or {}
        fps_1440 = cand.get("fps_1440p", g.get("fps_1440p", 0))
        return {
            "candidate_id": idx,
            "listing_id": cand.get("summary", {}).get("id", cand.get("id")),
            "model": g.get("model", cand.get("model", "")),
            "price_uah": cand.get("price", 0),
            "market_range_uah": f"{g.get('market_used_min', 0)}-{g.get('market_used_max', 0)}",
            "vram_gb": cand.get("vram_gb", g.get("vram_gb", 0)),
            "risk_level": g.get("risk_level", "LOW"),
            "architecture_risk_notes": g.get("risk_notes", ""),
            "est_fps_1440p": fps_1440,
            "est_fps_1080p": cand.get("fps_1080p", g.get("fps_1080p", 0)),
            "cost_uah_per_fps": cand.get("uah_per_fps", round(float(cand.get("price", 0)) / max(1.0, float(fps_1440 or 60)), 1)),
            "title": cand.get("summary", {}).get("title", cand.get("title", "")),
            "seller_name": cand.get("summary", {}).get("seller_name", "Unknown"),
            "seller_account_created": str(cand.get("summary", {}).get("seller_created", ""))[:10],
            "olx_delivery_enabled": cand.get("summary", {}).get("has_olx_delivery", True),
            "description": clean_desc,
        }

    def build_prompt(self, payload_json: str, sort_by: str) -> str:
        return f"""You are an expert PC hardware inspector analyzing GPU classified ads on OLX.ua (Ukraine).
Detect subtle human nuance, evasive language, excuses, or covert red flags in Ukrainian/Russian/English.

CRITICAL GPU CHECKS:
1. Evasions & Untested Excuses: "немає монітора/БЖ для перевірки", "дісталась по обміну", "кулери крутяться значить має працювати", "продаю як є без повернень/претензій".
2. Prepayment & Delivery Refusal (MANDATORY REJECT):
   - Asking for card deposit / prepayment ("передплата на карту").
   - Seller refusing postal shipping in text ("без почт", "без отправок", "тільки самовивіз", "только из рук в руки", "олх доставкою не відправляю").
3. Defective / Stripped Hardware (MANDATORY REJECT):
   - Baking/reballing ("прогріта", "ребол"), artifacts ("артефакти", "смуги"), dead display ports, VRAM errors (MATS/MODS), crashes under load.
   - Stripped donor PCBs ("No GPU, VRAM", "без чіпа", "без пам'яті", "тільки охолодження").
   - Storefront multi-model bait listings where price is only for the cheapest listed card ("від ... грн", listing 4+ different GPUs).
4. Hardware Generation & Mining Risks:
   - CRITICAL RISK (Polaris RX 470/480/570/580/590): Downgrade to CAUTION if no FurMark/Superposition proof is offered or modded BIOS is mentioned.
   - HIGH RISK (Pascal GTX 10-series; GDDR6X RTX 3080/3080 Ti/3090): Flag thermal pad degradation or 100C+ hotspot signs; boost confidence if serviced with PTM7950 / Odyssey / FurMark proof.

NOTE: Read the ENTIRE description—sellers often paste generic specs at the top and write crucial condition notes at the bottom.

Input Listings:
```json
{payload_json}
```

INSTRUCTIONS:
1. Assign each candidate a verdict:
   - "APPROVED": Working GPU, honest description, realistic price, allows OLX Delivery.
   - "CAUTION": Working GPU with minor caveats (heavy mining generation without stress-test proof, noisy fan, missing box).
   - "REJECTED": Defective, untested excuse, stripped PCB, bait pricing, prepayment trap, or refuses OLX Delivery.
2. Provide `confidence_score` (0-100) and 1-2 concise `reasons`.
3. Rank non-rejected candidates for mode/criterion: {sort_by.upper()}.

Return ONLY valid JSON matching this exact schema:
{{
  "evaluations": [
    {{
      "candidate_id": 1,
      "verdict": "APPROVED",
      "confidence_score": 88,
      "reasons": ["Clean condition with FurMark proof", "OLX Delivery active"]
    }}
  ],
  "final_ranked_ids": [1],
  "disqualified_ids": []
}}"""


AIInspector = GPUAIInspector
