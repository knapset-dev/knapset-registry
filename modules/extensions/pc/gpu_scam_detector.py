"""
Scam and Fake Hardware Detector for OLX GPU listings.
Analyzes price anomalies, seller trust metrics, delivery options, and pre-compiled defect signals.
"""

import re
from typing import Dict, Any, List
from scam_utils import (
    BaseScamDetector,
    compile_trigger_group,
    match_triggers,
)

_GPU_DEFECT_GROUP = compile_trigger_group([
    (r"\b(?:не\s*ма\w*\s+(?:з?о+бражен\w*|з?о+браен\w*|из?о+бражен\w*|картинк\w*|сигнал\w*|відеосигнал\w*|видеосигнал\w*)|(?:з?о+бражен\w*|з?о+браен\w*|из?о+бражен\w*|картинк\w*|сигнал\w*|відеосигнал\w*|видеосигнал\w*)\s+не\s*ма\w*|нет\s+(?:из?о+бражен\w*|з?о+бражен\w*|картинк\w*|сигнал\w*|видеосигнал\w*)|(?:из?о+бражен\w*|з?о+бражен\w*|картинк\w*|сигнал\w*|видеосигнал\w*)\s+нет\b|без\s+(?:з?о+бражен\w*|из?о+бражен\w*|картинк\w*|сигнал\w*)|(?:не|перестал\w*)\s+(?:вивод\w*|вывод\w*|вида\w*|выда\w*|дава\w*|даёт|дает|дає|показу\w*|показыва\w*)\s+(?:картинк\w*|з?о+бражен\w*|из?о+бражен\w*|сигнал\w*|відео\w*|видео\w*)|(?:картинк\w*|з?о+бражен\w*|из?о+бражен\w*|сигнал\w*)\s+не\s+(?:вивод\w*|вывод\w*|вида\w*|выда\w*|дає|дает|йде|идет)|черный\s+экран|чорний\s+екран|екран\s+чорний|экран\s+черный)\b", "Black screen / no video output disclosed"),
    (r"\b(?:зникає\s+з?о+бражен\w*|пропада\w*\s+(?:з?о+бражен\w*|из?о+бражен\w*|картинк\w*|сигнал\w*)|картинка\s+то\s+есть\s+то\s+нет\w*|зображення\s+то\s+є\s+то\s+нема\w*)\b", "Intermittent video output / signal dropouts disclosed"),
    (r"\b(?:(?:відвал|отвал)\s+(?:чіп\w*|чип\w*|гпу|gpu|ядр\w*|пам'ят\w*|памят\w*|відеочіп\w*|видеочип\w*)|після\s+(?:відвалу|отвала)|после\s+отвала)\b", "GPU core or VRAM BGA chip detachment (отвал чипа) disclosed"),
    (r"\b(?:(?:пк|комп\w*|система|материнк\w*|плата)\s+(?:її\s+|ее\s+|карту\s+|відеокарту\s+|видеокарту\s+)?(?:просто\s+)?не\s+(?:бачить|видит|визначає|определяет|розпізнає)|не\s+(?:визначається|определяется)\s+(?:в\s+)?(?:пк|систем\w*|диспетчер\w*))\b", "Card is not detected by PC / motherboard"),
    (r"\b(?:код\s*43|code\s*43|код43)\b", "Code 43 driver failure (GPU core/VRAM hardware death)"),
    (r"\b(?:не\s*(?:встановлю|устанавл|став|ставит)\w*\s*драйвер\w*|драйвер\w*\s+не\s*(?:встановлю|устанавл|став|ставит)\w*|зліта\w*\s+(?:драйвер\w*|дрова)|слета\w*\s+(?:драйвер\w*|дрова))\b", "Driver installation failure / crashes"),
    (r"\b(?:потухл\w*|потух\b|погас\w*|згас\w*|вирубил\w*|потухла\s+і\s+все)\b", "GPU cut out / died / went dark"),
    (r"\b(?:не\s+змогли\s+(?:відремонтувати|полагодити)|не\s+смогли\s+отремонтировать|в\s+сервісі\s+не\s+розібрались|в\s+сервисе\s+не\s+разобрались|поколупа\w*|колупал\w*)\b", "Failed repair / tampered or serviced hardware disclosed"),
    (r"\b(?:пошкоджен\w*|поврежден\w*|погнут\w*|зломан\w*|сломан\w*)\b", "Physical damage disclosed"),
    (r"\b(?:артефакт\w*|артифакт\w*|полосы\s+на\s+экране|смуги\s+на\s+екрані)\b", "Artifacts or defective VRAM/core"),
    (r"\b(?:прогріт\w+|грелась|прогревалась|після\s+прогріву)\b", "Card was heat-treated / baked (dying GPU chip)"),
    (r"\b(?:не\s+знаю\s+чи\s+робоч\w*|чи\s+робоч\w*\s+не\s+знаю|не\s+знаю\s+рабоч\w*|рабочая\s+или\s+нет\s+не\s+знаю)\b", "Seller claims not to know if card works (classic dead GPU disclaimer)"),
    (r"\b(?:візуально\s+на\s+місці|визуально\s+на\s+месте|(?:всі|все)\s+детал\w*\s+на\s+м[іе]с[тц]\w*|детал\w*\s+на\s+м[іе]с[тц]\w*|no\s+gpu|no\s+vram|без\s+гпу|без\s+чипа|без\s+чіпа)\b", "Stripped donor PCB / missing GPU core or VRAM"),
    (r"\b(?:vga\s+порт|vga\s+выход|роз'єм\s+vga)\b", "VGA port on modern GPU - classic fake GPU giveaway"),
    (r"\b(?:(?:потрібн\w*|треба|нужн\w*|надо|необхідн\w*|необходим\w*|доводить?ся|приходить?ся)\s+(?:\w+\s+){0,3}(?:андервольт\w*|undervolt\w*|знижувати|знизити|понижать|понизить|занижувати|занизити|фіксувати|зафіксувати|фиксировать|зафиксировать)|(?:працює|работает|стабільн\w*|стабильн\w*)\s+(?:тільки|лише|только)\s+(?:в|при|з|с|на)\s*(?:андервольт\w*|undervolt\w*|знижен\w*|занижен\w*|понижен\w*)|(?:на\s+)?(?:стоков\w*|вищ\w*|высок\w*|заводськ\w*)\s+частот\w*\s+(?:показує\s+себе\s+)?(?:не\s*стабільн\w*|виліта\w*|вылета\w*|перегріва\w*|перегрева\w*|краш\w*)|працює\s+на\s+нижч\w*\s+частот\w*|работает\s+на\s+понижен\w*\s+частот\w*|(?:зафіксувати|фіксувати|зафиксировать|фиксировать)\s+(?:андервольт\w*|undervolt\w*|вольтаж\w*|частот\w*|напруг\w*|напряжен\w*)|(?:знизити|понизить|занизити|занизить|среза\w*|скинути|сбросить)\s+(?:частот\w*|напруг\w*|напряжен\w*|power\s*limit|павер\s*ліміт))\b", "Degraded silicon / forced undervolt or underclock required for stability"),
])

_SUSPICIOUS_GROUP = compile_trigger_group([
    (r"\b(?:немає\s+змоги\s+перевірити|нет\s+возможности\s+проверить|не\s+перевіря\w*)\b", "Seller claims cannot test the card"),
    (r"\b(?:дісталась|досталась\s+от|знайшов|нашел|лежала\s+в\s+шкафу|лежала\s+в\s+шафі)\b", "Vague backstory on card origin"),
    (r"\b(?:прошит\w+|прошита\s+під|флеш\w+)\b", "Modified or flashed BIOS mentioned"),
])

_TRUST_GROUP = compile_trigger_group([
    (r"\b(?:будь-які\s+тести|любые\s+тесты|(?:надам|зроблю|скину|предоставлю|проходить|проходит)\s+(?:всі\s+|все\s+|будь-які\s+|любые\s+)?тест\w*|тест\w*\s+(?:за\s+проханням|за\s+запитом|по\s+запиту|по\s+запросу|надам|зроблю|скину)|фумарк|furmark|3dmark|superposition)\b", "Benchmark tests offered / shown"),
    (r"\b(?:відео\s+роботи|видео\s+работы|тести\s+онлайн|тесты\s+онлайн)\b", "Video proofs or online verification offered"),
    (r"\b(?:пломб\w+|на\s+пломбах|пломбы\s+на\s+месте)\b", "Original warranty seals intact"),
    (r"\b(?:гарантія\s+від\s+магазину|гарантия\s+от\s+магазина|чек|гарантійний\s+талон)\b", "Store warranty or receipt included"),
])

_MINING_MENTION_RE = re.compile(r"\b(?:майнинг|майнінг|майнила|майнил|ферм\w*|mining|риг\w*)\b")
_MINING_NEGATED_RE = re.compile(r"\b(?:не|без)\s+(?:була\s+|была\s+)?(?:в\s+)?(?:майнінг\w*|майнинг\w*|ферм\w*|риг\w*)")


class ScamDetector(BaseScamDetector):
    category = "gpu"
    suspicious_label = "PROBABLE ISSUE"
    scam_label = "LIKELY SCAM"
    min_market_crit_ratio = 0.45
    min_market_warn_ratio = 0.70
    max_market_overprice_ratio = 1.35

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

        # Multi-model SEO bait check
        if min_market > 0 and spec_info.get("multi_model_spam") and price < min_market * 0.85:
            score_delta += 30
            red_flags.append("Multi-model SEO bait pricing: Title lists 3+ GPU models with below-market price.")

        # Architectural & Aging Risk
        risk_level = spec_info.get("risk_level", "LOW")
        risk_notes = spec_info.get("risk_notes", "")
        if risk_level == "CRITICAL":
            score_delta += 20
            warnings.append(f"CRITICAL GENERATION RISK ({spec_info.get('model')}): {risk_notes}")
        elif risk_level == "HIGH":
            score_delta += 10
            warnings.append(f"HIGH ARCHITECTURAL/AGING RISK ({spec_info.get('model')}): {risk_notes}")

        # GPU Specific defects
        for exp in match_triggers(_GPU_DEFECT_GROUP, desc_lower):
            score_delta += 45
            red_flags.append(f"CRITICAL DEFECT: {exp}")

        for exp in match_triggers(_SUSPICIOUS_GROUP, desc_lower):
            score_delta += 20
            warnings.append(f"Hardware concern: {exp}")

        # Mining history detection
        if _MINING_MENTION_RE.search(desc_lower):
            if _MINING_NEGATED_RE.search(desc_lower):
                trust_signals.append("Seller explicitly claims card was NOT used for crypto mining.")
            else:
                score_delta += 20
                warnings.append("Explicit crypto mining history or rig usage mentioned in description.")

        # Trust signals
        for exp in match_triggers(_TRUST_GROUP, desc_lower):
            score_delta -= 10
            trust_signals.append(f"Verified signal: {exp}")

        return score_delta


GPUScamDetector = ScamDetector
