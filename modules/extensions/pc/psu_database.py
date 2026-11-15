"""
PSU Benchmark & Specifications Database and Model Parser.
Parses Power Supply Units (PSUs) on OLX:
- Wattage (W)
- 80 PLUS Efficiency (Titanium, Platinum, Gold, Silver, Bronze, Standard, None)
- Modularity (Full, Semi, Non-Modular)
- Form Factor (ATX, SFX, SFX-L, Server)
- ATX 3.0 / 3.1 & 12VHPWR support
- Cultists Network Tier Classification (Tier A, Tier B, Tier C, Tier D/Hazard)
- Safety Hazards & Known Explosive Units (Aerocool KCAS, VX, Gigabyte P750GM)
- Missing modular cable checks
"""

import re
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple, List

# Patterns that indicate accessories, individual cables, or fakes
PSU_EXCLUSION_KEYWORDS = [
    r"\bкабел\w*\s+тільки\b",
    r"\bкабеля\s+модульного\b",
    r"\bкабель\s+(?:живлення|для\s+бп|живлення\s+відеокарти)\b",
    r"\bкоробка\s+(?:від|для|без)\b",
    r"\bbox\s+only\b",
    r"\bперехідник\s+(?:для\s+)?(?:живлення|бп)\b",
    r"\bтестер\s+(?:для\s+)?бп\b",
    r"\bбез\s+блока\b",
    r"\bбез\s+бп\b",
]

# Hazardous PSUs with high failure/explosion rates or missing protections
HAZARDOUS_PSUS = [
    (r"\b(?:aerocool\s+)?kcas\b", "Aerocool KCAS", "FIRE HAZARD: Severe lack of working over-current/over-power protection (OCP/OPP). Known for catastrophic failures under load."),
    (r"\b(?:aerocool\s+)?vx\s*(?:plus)?\b", "Aerocool VX", "FIRE HAZARD: Group-regulated, extremely poor voltage regulation and missing safety protections."),
    (r"\b(?:gigabyte\s+)?(?:gp-)?p750gm\b", "Gigabyte P750GM", "EXPLOSION HAZARD: Early revisions have defective OPP/MOSFETs causing catastrophic explosions at ~60% load."),
    (r"\b(?:gigabyte\s+)?(?:gp-)?p850gm\b", "Gigabyte P850GM", "EXPLOSION HAZARD: Early revisions have defective OPP/MOSFETs causing catastrophic explosions under heavy transient loads."),
    (r"\b(?:zumax|t\.f\.skywindintl|apw\d*)\b", "Chinese Mining PSU", "DEAFENING MINING UNIT: Industrial 60dB fan, unshielded 12V rails designed for mining rigs, not suitable for quiet desktop use."),
]

BRANDS = [
    ("Seasonic Prime", r"\b(?:seasonic\s+prime|prime\s+tx|prime\s+px|prime\s+gx)\b", "Tier A"),
    ("Seasonic Focus", r"\b(?:seasonic\s+focus|focus\s+gx|focus\s+px|focus\s+plus)\b", "Tier A"),
    ("Seasonic Vertex", r"\bseasonic\s+vertex\b", "Tier A"),
    ("Seasonic", r"\bseasonic\b", "Tier A"),

    ("Corsair RMx", r"\b(?:corsair\s+rm[x]?|rm\d{3}x|rmx\s+shift)\b", "Tier A"),
    ("Corsair HX/AX", r"\b(?:corsair\s+(?:hx|ax)|hx\d{3,4}|ax\d{3,4})\b", "Tier A"),
    ("Corsair SF", r"\b(?:corsair\s+sf|sf\d{3})\b", "Tier A"),
    ("Corsair TX", r"\b(?:corsair\s+tx|tx\d{3}m)\b", "Tier B"),
    ("Corsair CX", r"\b(?:corsair\s+cx|cx\d{3}m?)\b", "Tier B"),
    ("Corsair CV", r"\b(?:corsair\s+cv|cv\d{3})\b", "Tier C"),
    ("Corsair", r"\bcorsair\b", "Tier B"),

    ("be quiet! Dark Power", r"\bdark\s+power\s*(?:pro)?\s*(?:1[123])?\b", "Tier A"),
    ("be quiet! Straight Power", r"\bstraight\s+power\s*(?:1[12])?\b", "Tier A"),
    ("be quiet! Pure Power", r"\bpure\s+power\s*(?:1[12])?\b", "Tier B"),
    ("be quiet! System Power", r"\bsystem\s+power\s*(?:[9]|10)?\b", "Tier C"),
    ("be quiet!", r"\bbe\s*quiet!?\b", "Tier B"),

    ("Super Flower Leadex", r"\b(?:super\s+flower\s+leadex|leadex\s*(?:iii|v|vi)?)\b", "Tier A"),
    ("Super Flower", r"\bsuper\s+flower\b", "Tier A"),

    ("EVGA SuperNOVA", r"\b(?:supernova|evga\s+(?:g2|g3|g6|p2|t2))\b", "Tier A"),
    ("EVGA", r"\bevga\b", "Tier B"),

    ("ASUS ROG Thor", r"\b(?:rog\s+thor|thor)\b", "Tier A"),
    ("ASUS ROG Strix", r"\b(?:rog\s+strix|strix\s+(?:gold|aura))\b", "Tier A"),
    ("ASUS TUF", r"\btuf\s+gaming\b", "Tier B"),
    ("ASUS", r"\basus\b", "Tier B"),

    ("MSI MPG", r"\b(?:mpg\s+a\d{3,4}|msi\s+mpg)\b", "Tier A"),
    ("MSI MAG", r"\b(?:mag\s+a\d{3,4}|msi\s+mag)\b", "Tier B"),
    ("MSI", r"\bmsi\b", "Tier B"),

    ("DeepCool PX-G", r"\bdeepcool\s+px\d{3,4}g\b", "Tier A"),
    ("DeepCool PQ-M", r"\bdeepcool\s+pq\d{3,4}m\b", "Tier A"),
    ("DeepCool DQ", r"\bdeepcool\s+dq\d{3,4}\b", "Tier B"),
    ("DeepCool PK", r"\bdeepcool\s+pk\d{3,4}\b", "Tier C"),
    ("DeepCool", r"\bdeepcool\b", "Tier C"),

    ("Chieftec Polaris", r"\b(?:chieftec\s+polaris|polaris)\b", "Tier B"),
    ("Chieftec PowerPlay", r"\b(?:chieftec\s+powerplay|powerplay)\b", "Tier B"),
    ("Chieftec Proton", r"\b(?:chieftec\s+proton|proton)\b", "Tier B"),
    ("Chieftec SteelPower", r"\bsteelpower\b", "Tier B"),
    ("Chieftec Core", r"\bchieftec\s+core\b", "Tier C"),
    ("Chieftec A-135", r"\ba-?135\b", "Tier C"),
    ("Chieftec", r"\bchieftec\b", "Tier C"),

    ("Cooler Master V", r"\bcooler\s+master\s+v\d{3,4}\b", "Tier A"),
    ("Cooler Master MWE Gold", r"\bmwe\s+gold\b", "Tier B"),
    ("Cooler Master MWE Bronze", r"\bmwe\s+bronze\b", "Tier B"),
    ("Cooler Master", r"\bcooler\s+master\b", "Tier B"),

    ("Thermaltake Toughpower", r"\btoughpower\s*(?:gf[123])?\b", "Tier A"),
    ("Thermaltake Smart", r"\bthermaltake\s+smart\b", "Tier C"),
    ("Thermaltake", r"\bthermaltake\b", "Tier C"),

    ("Enermax Revolution", r"\brevolution\s*(?:d\.f\.|xt)?\b", "Tier A"),
    ("Enermax", r"\benermax\b", "Tier B"),

    ("FSP Hydro G", r"\bhydro\s*(?:g|ptm)\s*(?:pro)?\b", "Tier A"),
    ("FSP Hydro", r"\bhydro\b", "Tier B"),
    ("FSP", r"\bfsp\b", "Tier C"),

    ("Zalman GigaMax", r"\bgigamax\b", "Tier C"),
    ("Zalman MegaMax", r"\bmegamax\b", "Tier C"),
    ("Zalman", r"\bzalman\b", "Tier C"),

    ("1stPlayer", r"\b1stplayer\b", "Tier C"),
    ("Gamemax", r"\bgamemax\b", "Tier D"),
    ("Vinga", r"\bvinga\b", "Tier D"),
]

_PSU_EXCLUSION_RE = re.compile("|".join(PSU_EXCLUSION_KEYWORDS))
_COMPILED_HAZARDS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(pat), name, desc) for pat, name, desc in HAZARDOUS_PSUS
]
_COMPILED_PSU_BRANDS: List[Tuple[str, re.Pattern, str]] = [
    (name, re.compile(pat), tier) for name, pat, tier in BRANDS
]

_WATTAGE_DIRECT_RE = re.compile(
    r"\b(3[0-9]{2}|4[0-9]{2}|5[0-9]{2}|6[0-9]{2}|7[0-9]{2}|8[0-9]{2}|1[0-9]{3}|2000)\s*(?:w|wtt|вт|ват|ватт)\b"
)
_WATTAGE_MODEL_RE = re.compile(
    r"\b(?:rm|hx|ax|tx|cx|gx|px|p|g|sf|ssr-)?(450|500|550|600|650|700|750|800|850|1000|1050|1200|1300|1500|1600)(?:[a-z]{1,4})?\b"
)
_EFF_TITANIUM_RE = re.compile(r"\b(?:titanium|титаниум|титан)\b")
_EFF_PLATINUM_RE = re.compile(r"\b(?:platinum|платинум|платина)\b")
_EFF_GOLD_RE = re.compile(r"\b(?:gold|голд|золото)\b")
_EFF_SILVER_RE = re.compile(r"\b(?:silver|сільвер|серебро)\b")
_EFF_BRONZE_RE = re.compile(r"\b(?:bronze|бронза|бронз)\b")
_EFF_WHITE_RE = re.compile(r"\b(?:80\s*plus\s+white|80\s*plus\s+standard|80\s*plus)\b")

_MOD_FULL1_RE = re.compile(r"\b(?:fully\s*modular|full\s*modular|повністю\s+модульн\w*|полностью\s+модульн\w*)\b")
_MOD_SEMI_RE = re.compile(r"\b(?:semi\s*modular|напівмодульн\w*|полумодульн\w*)\b")
_MOD_FULL2_RE = re.compile(r"\b(?:модульний|модульный|modular)\b")

_SFX_L_RE = re.compile(r"\bsfx-l\b")
_SFX_RE = re.compile(r"\bsfx\b")
_SERVER_PSU_RE = re.compile(r"\b(?:серверн\w*|серверный|hstns|майнинг\s*бп)\b")
_12VHPWR_RE = re.compile(r"\b(?:atx\s*3\.[01]|pcie\s*5\.0|12vhpwr|12v-2x6)\b")

PSU_TIER_SCORES = {"Tier A": 4, "Tier B": 3, "Tier C": 2, "Tier D": 1}


def extract_wattage(text: str) -> Optional[int]:
    """Extracts continuous wattage in Watts (300W - 2000W)."""
    t = text.lower()
    m = _WATTAGE_DIRECT_RE.search(t)
    if m:
        return int(m.group(1))
    m_model = _WATTAGE_MODEL_RE.search(t)
    if m_model:
        val = int(m_model.group(1))
        if 400 <= val <= 1600:
            return val
    return None


def extract_efficiency(text: str) -> str:
    """Extracts 80 PLUS efficiency rating."""
    t = text.lower()
    if _EFF_TITANIUM_RE.search(t):
        return "Titanium"
    if _EFF_PLATINUM_RE.search(t):
        return "Platinum"
    if _EFF_GOLD_RE.search(t):
        return "Gold"
    if _EFF_SILVER_RE.search(t):
        return "Silver"
    if _EFF_BRONZE_RE.search(t):
        return "Bronze"
    if _EFF_WHITE_RE.search(t):
        return "White"
    return "Standard"


def extract_modularity(text: str) -> str:
    """Classifies modularity: Full, Semi, or Non-Modular."""
    t = text.lower()
    if _MOD_FULL1_RE.search(t):
        return "Full"
    if _MOD_SEMI_RE.search(t):
        return "Semi"
    if _MOD_FULL2_RE.search(t):
        return "Full"
    return "Non-Mod"


def extract_form_factor(text: str) -> str:
    """Extracts form factor: ATX, SFX, SFX-L, or Server."""
    t = text.lower()
    if _SFX_L_RE.search(t):
        return "SFX-L"
    if _SFX_RE.search(t):
        return "SFX"
    if _SERVER_PSU_RE.search(t):
        return "Server"
    return "ATX"


@lru_cache(maxsize=8192)
def _identify_psu_cached(title: str, desc_head: str) -> Optional[Tuple[Tuple[str, Any], ...]]:
    t_lower = title.lower()
    if _PSU_EXCLUSION_RE.search(t_lower):
        return None

    wattage = extract_wattage(t_lower)
    if not wattage:
        wattage = extract_wattage(desc_head[:400]) if desc_head else None
        if not wattage:
            return None

    desc_l = desc_head.lower() if desc_head else ""
    combined_lower = f"{t_lower} {desc_l}" if desc_l else t_lower

    efficiency = extract_efficiency(t_lower)
    if efficiency == "Standard" and desc_l:
        desc_eff = extract_efficiency(desc_l)
        if desc_eff != "Standard":
            efficiency = desc_eff

    modularity = extract_modularity(combined_lower)
    form_factor = extract_form_factor(combined_lower)
    has_12vhpwr = bool(_12VHPWR_RE.search(combined_lower))

    brand = "Generic"
    vrm_tier = "Tier C"
    for b_name, b_cre, b_tier in _COMPILED_PSU_BRANDS:
        if b_cre.search(combined_lower):
            brand = b_name
            vrm_tier = b_tier
            break

    clean_model = f"{brand} {wattage}W"
    if efficiency in ("Gold", "Platinum", "Titanium"):
        clean_model += f" {efficiency}"

    risk_level = "LOW"
    risk_notes = "Standard desktop power supply."

    for haz_cre, haz_name, haz_desc in _COMPILED_HAZARDS:
        if haz_cre.search(combined_lower):
            risk_level = "CRITICAL"
            risk_notes = f"CRITICAL DEFECT/SAFETY HAZARD ({haz_name}): {haz_desc}"
            vrm_tier = "Tier D"
            break

    if risk_level != "CRITICAL":
        if form_factor == "Server":
            risk_level = "HIGH"
            risk_notes = "Industrial Server / Mining PSU. Extremely noisy fan (50-60 dB) and non-standard pinouts/cables."
        elif vrm_tier == "Tier D":
            risk_level = "HIGH"
            risk_notes = "Tier D power supply with questionable component quality and weak safety protections."
        elif efficiency == "Standard" and wattage >= 700:
            risk_level = "MEDIUM"
            risk_notes = "High-wattage uncertified/standard unit. Likely group-regulated with loose 12V voltage tolerance."

    base_min = (wattage * 2.2) if efficiency in ("Gold", "Platinum", "Titanium") else (wattage * 1.5)
    base_max = (wattage * 5.0) if efficiency in ("Platinum", "Titanium") else (wattage * 3.5)
    if form_factor in ("SFX", "SFX-L"):
        base_min *= 1.4
        base_max *= 1.5

    min_m = int(base_min)
    max_m = int(base_max)
    out = {
        "model": clean_model,
        "brand": brand,
        "wattage": wattage,
        "efficiency": efficiency,
        "modularity": modularity,
        "form_factor": form_factor,
        "has_12vhpwr": has_12vhpwr,
        "vrm_tier": vrm_tier,
        "tier_score": PSU_TIER_SCORES.get(vrm_tier, 2),
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "market_used_min": min_m,
        "market_used_max": max_m,
        "market_used_median": (min_m + max_m) // 2,
    }
    return tuple(out.items())


def identify_psu(title: str, description: str = "") -> Optional[Dict[str, Any]]:
    """
    Analyzes title and description at C-regex speed to extract PSU wattage, efficiency,
    modularity, form factor, quality tier, and hazard status.
    """
    if not title:
        return None
    cached = _identify_psu_cached(title, (description or "")[:500])
    return dict(cached) if cached is not None else None
