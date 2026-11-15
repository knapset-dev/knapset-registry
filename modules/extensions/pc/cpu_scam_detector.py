"""
High-speed Heuristic CPU Scam & Hardware Defect Detector for OLX.
"""

import re
from typing import Dict, Any, List
from scam_utils import (
    BaseScamDetector,
    compile_trigger_group,
    match_triggers,
)

_CPU_DEFECT_GROUP = compile_trigger_group([
    (r"\b(?:погнут\w+\s+ніжк\w*|вигнут\w+\s+ніжк\w*|зламан\w+\s+ніжк\w*|погнут\w+\s+ножк\w*)\b", "Bent or broken pins detected"),
    (r"\b(?:відпал\w+\s+ніжк\w*|відламан\w+\s+ніжк\w*|відсутн\w+\s+ніжк\w*)\b", "Missing pin on CPU detected"),
    (r"\b(?:немає\s+материнк\w+|немає\s+плати|нет\s+материнки|не\s+перевіря\w*|тестов\w+\s+стенд\w*\s+не\s*ма\w*|перевірити\s+не\s+можу|проверить\s+не\s+могу|згоріла\s+материн\w*\s+плат\w*)\b", "Seller claims lack of motherboard / test bench to verify CPU"),
    (r"\b(?:не\s+знаю\s+чи\s+робоч\w*|не\s+знаю\s+рабоч\w*)\b", "Seller does not know if CPU works"),
    (r"\b(?:інженерн\w+\s+зразок|інженерник|engineering\s+sample|q-code|qtb0|qnct|qqlt)\b", "Engineering sample (ES/QS) instead of retail"),
    (r"\b(?:крашить|вилітає|out\s+of\s+video\s+memory|синій\s+екран|bsod)\b", "Mentions crashes or instability (Intel degradation risk)"),
    (r"\b(?:скальп\w+|рідкий\s+метал|delid\w*)\b", "Delidded CPU / liquid metal applied"),
])

_TRUST_GROUP = compile_trigger_group([
    (r"\b(?:будь-які\s+тести|любые\s+тесты|(?:надам|зроблю|скину|предоставлю|проходить|проходит)\s+(?:всі\s+|все\s+|будь-які\s+|любые\s+)?тест\w*|тест\w*\s+(?:за\s+проханням|за\s+запитом|по\s+запиту|по\s+запросу|надам|зроблю|скину)|аида|aida64|cinebench|prime95|occt)\b", "Benchmark tests offered / shown"),
    (r"\b(?:ідеальний\s+стан|ідеальні\s+ніжки|ножки\s+ровные|ніжки\s+рівні)\b", "Pins confirmed straight / perfect"),
    (r"\b(?:бокс\w+|повний\s+комплект|з\s+кулером|box)\b", "Complete retail box or cooler included"),
    (r"\b(?:гарантія|гарантийный\s+талон|чек)\b", "Warranty or receipt included"),
])


class CPUScamDetector(BaseScamDetector):
    category = "cpu"
    suspicious_label = "PROBABLE DEFECT"
    scam_label = "LIKELY SCAM"
    max_market_overprice_ratio = 1.4

    def _evaluate_component_specific(
        self,
        desc_lower: str,
        title: str,
        description: str,
        price: float,
        min_market: float,
        max_market: float,
        spec_info: Dict[str, Any],
        red_flags: List[str],
        warnings: List[str],
        trust_signals: List[str],
        offer_summary: Dict[str, Any],
        offer_detail: Dict[str, Any],
    ) -> int:
        score_delta = 0

        # Multi-model SEO bait pricing
        if min_market > 0:
            is_comma_list = bool(
                re.search(r"\b\d{4}[a-z0-9]{0,3}\s*[,/]\s*\d{4}[a-z0-9]{0,3}\s*[,/]\s*\d{4}", title.lower())
            )
            if (spec_info.get("multi_model_spam") or is_comma_list) and price < min_market * 0.85:
                score_delta += 30
                red_flags.append("Multi-model SEO bait pricing: Title lists 3+ CPU models with below-market price.")

        if spec_info.get("risk_level") == "MEDIUM":
            score_delta += 8
            warnings.append(f"SILICON NOTICE ({spec_info.get('model')}): {spec_info.get('risk_notes', '')}")

        for exp in match_triggers(_CPU_DEFECT_GROUP, desc_lower):
            score_delta += 35
            red_flags.append(f"CPU hardware concern: {exp}")

        for exp in match_triggers(_TRUST_GROUP, desc_lower):
            score_delta -= 10
            trust_signals.append(f"Verified signal: {exp}")

        return score_delta
