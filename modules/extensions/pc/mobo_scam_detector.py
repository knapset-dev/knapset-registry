"""
High-speed Heuristic Motherboard Scam & Hardware Defect Detector for OLX.
"""

from typing import Dict, Any, List
from scam_utils import (
    BaseScamDetector,
    compile_trigger_group,
    match_triggers,
)

_MOBO_DEFECT_GROUP = compile_trigger_group([
    (r"\b(?:(?:погнут\w*|вигнут\w*|зігнут\w*|гнут\w*|зламан\w*|сломан\w*|відлама\w*|отлома\w*|вирва\w*|вырва\w*|відірва\w*|оторва\w*|зачепи\w*|задел\w*)\s+(?:\w+\s+){0,2}(?:ніжк\w*|ножк\w*|пін\w*|пин\w*)|(?:ніжк\w*|ножк\w*|пін\w*|пин\w*)\s+(?:на\s+сокет\w*\s+|в\s+сокет\w*\s+)?(?:погнут\w*|вигнут\w*|зламан\w*|сломан\w*|відлама\w*|вирва\w*|вырва\w*))\b", "Bent, torn, or broken socket pins detected"),
    (r"\b(?:пошкоджен\w*\s+сокет\w*|поврежден\w*\s+сокет\w*|погнут\w*\s+сокет\w*|зламан\w*\s+сокет\w*|дефект\s+сокет\w*|проблем\w+\s+з\s+сокет\w*|ніжка\s+в\s+сокеті|ножка\s+в\s+сокете|(?:один|1|два|2)\s+(?:пін\w*|пин\w*)\s+на\s+сокет\w*)\b", "Socket pin issues / physical damage"),
    (r"\b(?:не\s+працює\s+(?:один|1)\s+слот|не\s+работает\s+(?:один|1)\s+слот|не\s+працює\s+двоканал|не\s+работает\s+двухканал|немає\s+dual\s*channel|мертв\w+\s+канал\w*|канал\s+\w*\s*не\s+(?:бачить|видит)\s+оператив\w*|sata\s+не\s+работа\w*|сата\s+не\s+працю\w*)\b", "Dead memory channel / slot or SATA port failure"),
    (r"\b(?:вилама\w+\s+(?:слот|pcie|засувк\w*)|сломан\w+\s+(?:слот|pcie|защелк\w*)|відірван\w+\s+pcie)\b", "Broken PCIe slot or retention latch"),
    (r"\b(?:не\s+стартує|не\s+вмикається|не\s+включается|немає\s+ініціалізації|нет\s+инициализации)\b", "Board does not power on or post (no initialization)"),
    (r"\b(?:горить\s+(?:cpu|dram|vga)\s+led|світить\s+(?:cpu|dram|vga))\b", "Stuck on debug error LED (CPU/DRAM failure)"),
    (r"\b(?:після\s+кз|коротке\s+замикання|прогар|прогаром|згорів\w*|сгорел\w*|перегорі\w*|після\s+грози)\b", "Burned VRM MOSFETs, short circuit, or lightning strike damage"),
    (r"\b(?:невдалий\s+біос|невдала\s+прошивк\w*|окирпич\w*|цеглина|після\s+оновлення\s+біос)\b", "Corrupted or bricked BIOS flash"),
    (r"\b(?:не\s+заход\w*\s+в\s+(?:bios|біос|биос)|не\s+працю\w*\s+(?:порт\w*\s*)?(?:ethernet|lan|мереж\w*|звук|аудіо|usb|pcie|слот)|не\s+работа\w*\s+(?:порт\w*\s*)?(?:ethernet|lan|сет\w*|звук|аудио|usb|pcie|слот))\b", "Broken BIOS entry or dead onboard LAN / audio / USB / slot"),
    (r"\b(?:обмежен\w+\s+функціон\w*|постійн\w+\s+перезавантаж\w*|постоянн\w+\s+перезагруз\w*)\b", "Board instability or limited functionality disclosed"),
    (r"\b(?:після\s+ремонту|после\s+ремонта|ремонтувал\w*|ремонтировал\w*|перепаюва\w*|перепаива\w*|паялас\w*|паян\w+|був\s+здійснений\s+ремонт)\b", "Repaired or soldered PCB / IC disclosed"),
])

_MISSING_PARTS_GROUP = compile_trigger_group([
    (r"\b(?:без\s+заглушки|без\s+планки|без\s+задньої\s+планки|нет\s+заглушки|нет\s+планки)\b", "Missing rear I/O shield (заглушка в корпус)"),
    (r"\b(?:без\s+бекплейт\w*|нет\s+бэкплейт\w*|без\s+кріплення\s+кулера)\b", "Missing CPU cooler backplate / mounting brackets"),
])

_TRUST_GROUP = compile_trigger_group([
    (r"\b(?:ніжки\s+в\s+ідеалі|ножки\s+в\s+идеале|сокет\s+ідеальн\w*|сокет\s+идеальн\w*|цілий\s+сокет|состояние\s+нового)\b", "Socket pins verified completely intact & perfect"),
    (r"\b(?:повністю\s+робоча|повністю\s+справна|полностью\s+рабочая|без\s+дефектів|без\s+дефекттов)\b", "Fully functional confirmed"),
    (r"\b(?:будь-які\s+тести|любые\s+тесты|(?:надам|зроблю|скину|предоставлю|проходить|проходит)\s+(?:всі\s+|все\s+|будь-які\s+|любые\s+)?тест\w*|тест\w*\s+(?:за\s+проханням|за\s+запитом|по\s+запиту|по\s+запросу|надам|зроблю|скину)|відео\s+роботи|тест\s+пройдено)\b", "Stress test proofs / benchmark verification offered"),
    (r"\b(?:гарантія\s+від\s+магазину|гарантия\s+от\s+магазина|чек|гарантійний\s+талон)\b", "Official store receipt / warranty included"),
    (r"\b(?:повний\s+комплект|оригінальна\s+коробка|заглушка\s+є|рідна\s+коробка)\b", "Full original retail packaging and accessories included"),
])


class MotherboardScamDetector(BaseScamDetector):
    category = "mobo"
    suspicious_label = "PROBABLE DEFECT"
    scam_label = "DAMAGED"
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
        if risk_level == "CRITICAL":
            score_delta += 35
            red_flags.append(f"CRITICAL PLATFORM HAZARD: {risk_notes}")
        elif risk_level == "HIGH":
            score_delta += 20
            warnings.append(f"HIGH PLATFORM/RECYCLED RISK: {risk_notes}")
        elif risk_level == "MEDIUM":
            score_delta += 10
            warnings.append(f"VRM / PLATFORM NOTICE: {risk_notes}")

        for exp in match_triggers(_MOBO_DEFECT_GROUP, desc_lower):
            score_delta += 35
            red_flags.append(f"Defect detected: {exp}")

        for exp in match_triggers(_MISSING_PARTS_GROUP, desc_lower):
            warnings.append(f"Missing accessory: {exp}")

        for exp in match_triggers(_TRUST_GROUP, desc_lower):
            score_delta -= 10
            trust_signals.append(f"Verified signal: {exp}")

        return score_delta
