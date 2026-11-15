"""
High-speed Heuristic Power Supply Unit (PSU) Scam & Hardware Defect Detector for OLX.
"""

from typing import Dict, Any, List
from scam_utils import (
    BaseScamDetector,
    compile_trigger_group,
    match_triggers,
)

_PSU_DEFECT_GROUP = compile_trigger_group([
    (r"\b(?:гуде\s+вентилятор|шумить\s+кулер|тріщить\s+вентилятор|шумит\s+кулер|трещит\s+вентилятор|гудит\s+кулер|дребезжит\s+вентилятор|шум\s+подшипник\w*|вентилятор\s+під\s+заміну|кулер\s+под\s+замену)\b", "Fan bearing noise / rattle (needs replacement)"),
    (r"\b(?:пищить|свистить|пищит\s+под\s+нагрузкой|свист\s+дроселів|свистят\s+дроссели|вищить|писк\s+дроселей|писк\s+дросселей)\b", "Severe coil whine under load"),
    (r"\b(?:йде\s+в\s+захист|уходит\s+в\s+защиту|вимикається\s+під\s+навантаженням|выключается\s+в\s+играх|перезавантажується\s+пк|не\s+тримає\s+навантаження|не\s+держит\s+нагрузку)\b", "Trips OCP/OPP protection or shuts down under load"),
    (r"\b(?:після\s+ремонту|после\s+ремонта|перепаян\w*|паяні\s+конденсатори|вздутые\s+конденсаторы|здуті\s+конденсатори|паялся|після\s+кз|коротке\s+замикання|прогар|згорів\w*|сгорел\w*)\b", "Repaired, re-soldered, blown capacitors or burned components"),
])

_MISSING_CABLES_GROUP = compile_trigger_group([
    (r"\b(?:без\s+кабелів|без\s+проводів|немає\s+кабелів|немає\s+проводів|без\s+шнурів|нет\s+кабелей|нет\s+проводов|кабелі\s+відсутні|провода\s+отсутствуют)\b", "Missing all modular cables"),
    (r"\b(?:неповний\s+комплект\s+кабелів|не\s+всі\s+кабелі|не\s+все\s+провода|некомплект\s+кабелей|тільки\s+(?:24|двадцять)\s*pin|только\s+(?:24|двадцать)\s*pin)\b", "Incomplete modular cable kit"),
    (r"\b(?:без\s+кабеля\s+живлення\s+відеокарти|немає\s+pci-?e|нет\s+кабеля\s+на\s+видеокарту)\b", "Missing critical PCIe / GPU power cables"),
])

_TRUST_GROUP = compile_trigger_group([
    (r"\b(?:повний\s+комплект\s+кабелів|всі\s+кабелі\s+в\s+наявності|все\s+провода\s+в\s+наличии|рідні\s+кабелі|родные\s+кабели|родные\s+провода)\b", "Full original modular cable set confirmed"),
    (r"\b(?:пломба\s+на\s+місці|пломби\s+цілі|пломба\s+целая|пломба\s+не\s+тронута|не\s+розбирався|не\s+вскрывался|без\s+ремонтів|без\s+ремонтов)\b", "Factory warranty seals intact / unopened / unrepaired"),
    (r"\b(?:тихий|безшумний|працює\s+безшумно|кулер\s+тихий|без\s+сторонніх\s+звуків|без\s+писку|без\s+свисту)\b", "Quiet fan and no coil whine verified"),
    (r"\b(?:будь-які\s+тести|любые\s+тесты|(?:надам|зроблю|скину|предоставлю|проходить|проходит)\s+(?:всі\s+|все\s+|будь-які\s+|любые\s+)?тест\w*|тест\w*\s+(?:за\s+проханням|за\s+запитом|по\s+запиту|по\s+запросу|надам|зроблю|скину)|перевірений\s+навантаженням|тест\s+пройдено|пройшов\s+тест|відео\s+роботи)\b", "Load testing verified / benchmark proofs offered"),
    (r"\b(?:гарантія\s+від\s+магазину|гарантия\s+от\s+магазина|чек|гарантійний\s+талон|на\s+гарантії)\b", "Official store warranty or receipt included"),
])


class PSUScamDetector(BaseScamDetector):
    category = "psu"
    suspicious_label = "PROBABLE DEFECT"
    scam_label = "HAZARDOUS"
    min_market_crit_ratio = 0.35
    min_market_warn_ratio = 0.60
    max_market_overprice_ratio = 1.5

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
        modularity = spec_info.get("modularity", "Non-Mod")

        risk_level = spec_info.get("risk_level", "LOW")
        risk_notes = spec_info.get("risk_notes", "")
        if risk_level == "CRITICAL":
            score_delta += 50
            red_flags.append(f"CRITICAL SAFETY HAZARD: {risk_notes}")
        elif risk_level == "HIGH":
            score_delta += 25
            warnings.append(f"HIGH RISK UNIT: {risk_notes}")
        elif risk_level == "MEDIUM":
            score_delta += 10
            warnings.append(f"PSU NOTICE: {risk_notes}")

        for exp in match_triggers(_MISSING_CABLES_GROUP, desc_lower, first_only=True):
            if modularity in ("Full", "Semi"):
                score_delta += 35
                red_flags.append(
                    f"MODULAR CABLE HAZARD: {exp}! Finding compatible pinouts for {spec_info.get('brand')} is difficult and using mismatched cables can fry components."
                )
            else:
                warnings.append(f"Cable notice: {exp}")

        for exp in match_triggers(_PSU_DEFECT_GROUP, desc_lower):
            score_delta += 35
            red_flags.append(f"Defect detected: {exp}")

        for exp in match_triggers(_TRUST_GROUP, desc_lower):
            score_delta -= 10
            trust_signals.append(f"Verified signal: {exp}")

        return score_delta
