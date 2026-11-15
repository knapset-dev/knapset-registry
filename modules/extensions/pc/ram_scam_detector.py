"""
High-speed Heuristic RAM Scam & Defect Detector for OLX.
"""

from typing import Dict, Any, List
from scam_utils import (
    BaseScamDetector,
    compile_trigger_group,
    match_triggers,
)

_RAM_CRITICAL_DEFECT_GROUP = compile_trigger_group([
    (r"\b(?:синій\s+екран|синий\s+экран|bsod|дамп\s+пам|крашить|вилітає|зависає)\b", "Memory instability or BSODs mentioned"),
    (r"\b(?:помилк\w+\s+в\s+memtest|ошибк\w+\s+в\s+memtest|сипле\s+помилк\w*|сыпет\s+ошибк\w*)\b", "MemTest memory errors reported"),
    (r"\b(?:не\s+знаю\s+чи\s+робоч\w*|не\s+знаю\s+рабоч\w*|тестов\w+\s+стенд\w*\s+не\s*ма\w*|перевірити\s+не\s+можу|проверить\s+не\s+могу|згоріла\s+материн\w*\s+плат\w*)\b", "Seller does not know or cannot verify if RAM works"),
    (r"\b(?:збит\w+\s+(?:смд|конденсатор|елемент)|скол\w*|відірван\w*)\b", "Physical damage to PCB or SMD components"),
    (r"\b(?:муляж\w*|пустушк\w*|пустышк\w*|light\s+enhancement)\b", "Dummy RGB filler kit (zero memory capacity)"),
])

_RAM_SOFT_CONCERN_GROUP = compile_trigger_group([
    (r"\b(?:не\s+тримає\s+xmp|не\s+держит\s+xmp|не\s+стартує\s+на\s+xmp)\b", "Fails to run at rated XMP / EXPO frequency"),
    (r"\b(?:немає\s+змоги\s+перевірити|нет\s+возможности\s+проверить|не\s+перевіря\w*)\b", "Seller claims lack of PC to test memory"),
])

_BAIT_PRICING_GROUP = compile_trigger_group([
    (r"\b(?:ціна\s+за\s+(?:одну|1)\s+(?:планку|штуку)|цена\s+за\s+(?:одну|1)\s+(?:планку|штуку))\b", "Bait pricing: Price is strictly PER STICK, not for the entire kit pictured"),
    (r"\b(?:ціна\s+вказана\s+за\s+(?:одну|1)|цена\s+указана\s+за\s+(?:одну|1))\b", "Bait pricing: Listing price is for single stick only"),
    (r"\b(?:ціна\s+від|цена\s+от)\b", "Bait pricing: Listing uses tiered multi-item pricing"),
    (r"\b(?:все\s+цены|всі\s+ціни)\s+(?:и\s+наличие\s+|та\s+наявність\s+)?на\s+\w*\s*фото\b", "Bait pricing: Multi-SKU price-list ad (headline price does not match all capacities)"),
])

_TRUST_GROUP = compile_trigger_group([
    (r"\b(?:memtest\s*(?:86)?\s*(?:без\s+помилок|чисто|пройдено|пройшов|без\s+ошибок)|tm5\s+пройдено|testmem5\s+пройден)\b", "Stress-tested memory (MemTest86 / TestMem5 clean)"),
    (r"\b(?:будь-які\s+тести|любые\s+тесты|(?:надам|зроблю|скину|предоставлю|проходить|проходит)\s+(?:всі\s+|все\s+|будь-які\s+|любые\s+)?тест\w*|тест\w*\s+(?:за\s+проханням|за\s+запитом|по\s+запиту|по\s+запросу|надам|зроблю|скину)|аида|aida64|memtest)\b", "Verification tests offered / available"),
    (r"\b(?:гарантія\s+від\s+магазину|гарантия\s+от\s+магазина|чек|гарантійний\s+талон)\b", "Official store receipt / warranty included"),
    (r"\b(?:на\s+гарантії|гарантія\s+діє|офіційна\s+гарантія)\b", "Valid manufacturer / store warranty"),
    (r"\b(?:нова\s+запакована|запакована|запакований|пломби\s+цілі|нові\s+в\s+упаковці)\b", "Brand new / factory sealed packaging"),
])


class RAMScamDetector(BaseScamDetector):
    category = "ram"
    suspicious_label = "PROBABLE ISSUE"
    scam_label = "LIKELY DEFECT"
    min_market_crit_ratio = 0.40
    min_market_warn_ratio = 0.65
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

        risk_level = spec_info.get("risk_level", "LOW")
        risk_notes = spec_info.get("risk_notes", "")
        form_factor = spec_info.get("form_factor", "")
        if risk_level == "CRITICAL":
            score_delta += 35
            red_flags.append(f"INCOMPATIBLE FOR DESKTOP: {risk_notes}")
        elif risk_level == "HIGH":
            score_delta += 25
            red_flags.append(f"INCOMPATIBLE FORM FACTOR: {risk_notes}")
        elif form_factor == "UNKNOWN":
            score_delta += 25
            warnings.append(f"AMBIGUOUS FORM FACTOR: {risk_notes}")
        elif risk_level == "MEDIUM":
            score_delta += 10
            warnings.append(f"TIER / STABILITY NOTICE: {risk_notes}")

        combined_text = f"{title.lower()} {desc_lower}"

        for exp in match_triggers(_BAIT_PRICING_GROUP, combined_text):
            score_delta += 30
            if spec_info.get("module_count", 1) >= 2:
                red_flags.append(exp)
            else:
                warnings.append(f"Pricing notice: {exp}")

        for exp in match_triggers(_RAM_CRITICAL_DEFECT_GROUP, combined_text):
            score_delta += 40
            red_flags.append(f"CRITICAL DEFECT: {exp}")

        for exp in match_triggers(_RAM_SOFT_CONCERN_GROUP, combined_text):
            score_delta += 20
            warnings.append(f"Hardware concern: {exp}")

        for exp in match_triggers(_TRUST_GROUP, combined_text):
            score_delta -= 10
            trust_signals.append(f"Verified signal: {exp}")

        return score_delta
