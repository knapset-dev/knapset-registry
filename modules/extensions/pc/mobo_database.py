"""
Motherboard Benchmark & Specifications Database and Model Parser.
Parses AMD and Intel motherboards from OLX:
- Socket (AM5, AM4, LGA1851, LGA1700, LGA1200, LGA1151, LGA1150, LGA1155, LGA2011-3/X99)
- Chipset (B650, B550, Z790, B760, X670E, Z690, B450, etc.)
- Memory Type (DDR5 vs DDR4)
- Form Factor (ATX, Micro-ATX, Mini-ITX, E-ATX)
- VRM Quality Tier (S-Tier, A-Tier, B-Tier, C-Tier, D-Tier)
- Wi-Fi Capability
- Bundle vs Standalone Board Detection
- Architectural & Physical Risk Assessments
"""

import re
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple, List

# Patterns that indicate non-motherboard accessories, coolers, or full PCs/laptops
MOBO_EXCLUSION_KEYWORDS = [
    r"\b(?:водяне|водянка|сжо|сро|кулер|вентилятор|радіатор|cooler)\s+(?:для\s+)?(?:процесор|cpu)\b",
    r"\bкоробка\s+(?:від|для|без)\b",
    r"\bbox\s+only\b",
    r"\bтермопрокладк\w*\b",
    r"\bтермопаст\w*\b",
    r"\b(?:чохол|підставка|кронштейн)\b",
    r"\b(?:райзер|riser)\b",
    r"\b(?:бекплейт|backplate)\s+тільки\b",
    r"\b(?:заглушка|i/o\s+shield)\s+тільки\b",
    r"\bноутбук\w*\b",
    r"\bсистемний\s+блок\b",
]

CHIPSET_SPECS = [
    # AMD AM5 (DDR5 only)
    (r"\bx870e[a-z0-9\-]*\b", "X870E", "AM5", "DDR5", "S-Tier", 11000, 25000),
    (r"\bx870[a-z0-9\-]*\b", "X870", "AM5", "DDR5", "A-Tier", 9000, 16000),
    (r"\bb850[a-z0-9\-]*\b", "B850", "AM5", "DDR5", "A-Tier", 6200, 11500),
    (r"\bb840[a-z0-9\-]*\b", "B840", "AM5", "DDR5", "B-Tier", 4500, 8000),
    (r"\bx670e[a-z0-9\-]*\b", "X670E", "AM5", "DDR5", "S-Tier", 10000, 22000),
    (r"\bx670[a-z0-9\-]*\b", "X670", "AM5", "DDR5", "A-Tier", 8000, 14000),
    (r"\bb650e[a-z0-9\-]*\b", "B650E", "AM5", "DDR5", "A-Tier", 7500, 13000),
    (r"\bb650[a-z0-9\-]*\b", "B650", "AM5", "DDR5", "B-Tier", 4200, 8500),
    (r"\ba620[a-z0-9\-]*\b", "A620", "AM5", "DDR5", "C-Tier", 2800, 4800),

    # AMD AM4 (DDR4 only)
    (r"\bx570s?[a-z0-9\-]*\b", "X570", "AM4", "DDR4", "A-Tier", 4500, 9000),
    (r"\bb550[a-z0-9\-]*\b", "B550", "AM4", "DDR4", "B-Tier", 2800, 6000),
    (r"\ba520[a-z0-9\-]*\b", "A520", "AM4", "DDR4", "C-Tier", 1800, 3200),
    (r"\bx470[a-z0-9\-]*\b", "X470", "AM4", "DDR4", "B-Tier", 2500, 4500),
    (r"\b(?:hi)?b450[a-z0-9\-]*\b", "B450", "AM4", "DDR4", "B-Tier", 1900, 3800),
    (r"\bx370[a-z0-9\-]*\b", "X370", "AM4", "DDR4", "B-Tier", 2000, 3500),
    (r"\ba?b350[a-z0-9\-]*\b", "B350", "AM4", "DDR4", "C-Tier", 1500, 2600),
    (r"\ba320[a-z0-9\-]*\b", "A320", "AM4", "DDR4", "D-Tier", 1200, 2200),

    # Intel LGA1851
    (r"\bz890[a-z0-9\-]*\b", "Z890", "LGA1851", "DDR5", "S-Tier", 11000, 28000),
    (r"\bb860[a-z0-9\-]*\b", "B860", "LGA1851", "DDR5", "B-Tier", 5500, 9500),
    (r"\bh810[a-z0-9\-]*\b", "H810", "LGA1851", "DDR5", "C-Tier", 3600, 6200),

    # Intel LGA1700 (DDR5 or DDR4)
    (r"\bz790[a-z0-9\-]*\b", "Z790", "LGA1700", "DDR5", "A-Tier", 6500, 16000),
    (r"\bb760[a-z0-9\-]*\b", "B760", "LGA1700", "DDR5", "B-Tier", 3800, 7500),
    (r"\bh770[a-z0-9\-]*\b", "H770", "LGA1700", "DDR5", "B-Tier", 4000, 7000),
    (r"\bh610[a-z0-9\-]*\b", "H610", "LGA1700", "DDR4", "C-Tier", 2200, 3800),
    (r"\bz690[a-z0-9\-]*\b", "Z690", "LGA1700", "DDR5", "A-Tier", 5000, 11000),
    (r"\bb660[a-z0-9\-]*\b", "B660", "LGA1700", "DDR4", "B-Tier", 3000, 6000),
    (r"\bh670[a-z0-9\-]*\b", "H670", "LGA1700", "DDR4", "B-Tier", 3200, 5800),

    # Intel LGA1200 (DDR4 only)
    (r"\bz590[a-z0-9\-]*\b", "Z590", "LGA1200", "DDR4", "A-Tier", 4000, 8000),
    (r"\bb560[a-z0-9\-]*\b", "B560", "LGA1200", "DDR4", "B-Tier", 2500, 4800),
    (r"\bh510[a-z0-9\-]*\b", "H510", "LGA1200", "DDR4", "C-Tier", 1800, 3200),
    (r"\bz490[a-z0-9\-]*\b", "Z490", "LGA1200", "DDR4", "A-Tier", 3200, 6500),
    (r"\bb460[a-z0-9\-]*\b", "B460", "LGA1200", "DDR4", "B-Tier", 2200, 4000),
    (r"\bh410[a-z0-9\-]*\b", "H410", "LGA1200", "DDR4", "C-Tier", 1600, 2800),

    # Intel LGA1151v2 (8th/9th Gen Coffee Lake, DDR4)
    (r"\bz390[a-z0-9\-]*\b", "Z390", "LGA1151v2", "DDR4", "A-Tier", 3000, 6000),
    (r"\bb365[a-z0-9\-]*\b", "B365", "LGA1151v2", "DDR4", "B-Tier", 1800, 3200),
    (r"\bb360[a-z0-9\-]*\b", "B360", "LGA1151v2", "DDR4", "B-Tier", 1700, 3000),
    (r"\bh310[a-z0-9\-]*\b", "H310", "LGA1151v2", "DDR4", "C-Tier", 1300, 2300),
    (r"\bz370[a-z0-9\-]*\b", "Z370", "LGA1151v2", "DDR4", "A-Tier", 2500, 4500),

    # Intel LGA1151 (6th/7th Gen Skylake/Kaby Lake, DDR4)
    (r"\bz270[a-z0-9\-]*\b", "Z270", "LGA1151", "DDR4", "B-Tier", 2000, 3500),
    (r"\bb250[a-z0-9\-]*\b", "B250", "LGA1151", "DDR4", "C-Tier", 1400, 2500),
    (r"\bz170[a-z0-9\-]*\b", "Z170", "LGA1151", "DDR4", "B-Tier", 1800, 3000),
    (r"\bb150[a-z0-9\-]*\b", "B150", "LGA1151", "DDR4", "C-Tier", 1300, 2200),
    (r"\bh110[a-z0-9\-]*\b", "H110", "LGA1151", "DDR4", "C-Tier", 1200, 2000),

    # LGA2011-v3 / LGA2011 (Xeon & X99 / X79)
    (r"\bx-?99[a-z0-9\-]*\b", "X99", "LGA2011-v3", "DDR4", "B-Tier", 1800, 4500),
    (r"\bx-?79[a-z0-9\-]*\b", "X79", "LGA2011", "DDR3", "C-Tier", 1200, 2500),

    # Intel LGA1150 / 1155 (DDR3)
    (r"\bz97[a-z0-9\-]*\b", "Z97", "LGA1150", "DDR3", "B-Tier", 1800, 3200),
    (r"\bb85[a-z0-9\-]*\b", "B85", "LGA1150", "DDR3", "C-Tier", 1200, 2200),
    (r"\bh81[a-z0-9\-]*\b", "H81", "LGA1150", "DDR3", "D-Tier", 900, 1600),
    (r"\bz77[a-z0-9\-]*\b", "Z77", "LGA1155", "DDR3", "B-Tier", 1700, 3000),
    (r"\bb75[a-z0-9\-]*\b", "B75", "LGA1155", "DDR3", "C-Tier", 1100, 2000),
    (r"\bh61[a-z0-9\-]*\b", "H61", "LGA1155", "DDR3", "D-Tier", 800, 1500),
]

BRANDS = [
    ("ASUS ROG", r"\b(?:rog\s+maximus|rog\s+strix|rog\s+crosshair)\b"),
    ("ASUS TUF", r"\btuf\s+gaming\b"),
    ("ASUS Prime", r"\bprime\b"),
    ("ASUS ProArt", r"\bproart\b"),
    ("ASUS", r"\basus\b"),
    ("MSI MEG", r"\bmeg\b"),
    ("MSI MPG", r"\bmpg\b"),
    ("MSI MAG", r"\b(?:mag\s+tomahawk|tomahawk|mag\s+mortar|mortar|torpedo)\b"),
    ("MSI Gaming", r"\b(?:gaming\s+plus|gaming\s+pro)\b"),
    ("MSI", r"\bmsi\b"),
    ("Gigabyte AORUS", r"\b(?:aorus\s+master|aorus\s+pro|aorus\s+elite|aorus\s+ultra|aorus)\b"),
    ("Gigabyte Gaming", r"\bgaming\s+x\b"),
    ("Gigabyte DS3H", r"\bds3h\b"),
    ("Gigabyte", r"\bgigabyte\b"),
    ("ASRock Taichi", r"\btaichi\b"),
    ("ASRock Steel Legend", r"\bsteel\s+legend\b"),
    ("ASRock Phantom", r"\bphantom\s+gaming\b"),
    ("ASRock LiveMixer", r"\blivemixer\b"),
    ("ASRock Pro4", r"\bpro4\b"),
    ("ASRock", r"\b(?:asrock|as\s+rock)\b"),
    ("Machinist", r"\bmachinist\b"),
    ("Huananzhi", r"\bhuananzhi\b"),
    ("Jginyue", r"\bjginyue\b"),
    ("Biostar", r"\bbiostar\b"),
    ("NZXT", r"\bnzxt\b"),
]

_MOBO_EXCLUSION_RE = re.compile("|".join(MOBO_EXCLUSION_KEYWORDS))
_BUNDLE_SAFE_MOBO_EXCLUSION_RE = re.compile(
    "|".join(kw for kw in MOBO_EXCLUSION_KEYWORDS if kw != r"\bсистемний\s+блок\b")
)
_CYRILLIC_CHIPSET_TRANS = str.maketrans({
    "в": "b", "а": "a", "н": "h", "х": "x", "м": "m", "к": "k", "е": "e", "с": "c", "р": "p", "о": "o", "і": "i",
})
_CHIPSET_CYR_TOKEN_RE = re.compile(r"\b[a-zа-яіїє]{1,3}-?\d{2,3}[a-zа-яіїє0-9\-]*\b")


def _normalize_mobo_tokens(text_l: str) -> str:
    return _CHIPSET_CYR_TOKEN_RE.sub(lambda m: m.group(0).translate(_CYRILLIC_CHIPSET_TRANS), text_l)


_CHIPSET_FAST_RE = re.compile(r"\b(?:hi|a)?[xzbah]-?\d{2,3}")
_COMPILED_CHIPSETS: List[Tuple[re.Pattern, str, str, str, str, int, int]] = [
    (re.compile(pat), ch, sock, ddr, tier, p_min, p_max)
    for pat, ch, sock, ddr, tier, p_min, p_max in CHIPSET_SPECS
]
_COMPILED_BRANDS: List[Tuple[str, re.Pattern]] = [
    (b_name, re.compile(b_pat)) for b_name, b_pat in BRANDS
]
_ITX_RE = re.compile(r"\b(?:itx|mini-itx|mini\s*itx)\b")
_EATX_RE = re.compile(r"\b(?:eatx|e-atx|extended\s*atx)\b")
_MATX_RE = re.compile(r"\b(?:matx|micro-atx|micro\s*atx|u-atx|uatx)\b")
_BUNDLE_RE = re.compile(
    r"(?<!повний\s)(?<!полный\s)(?<!коробочний\s)(?<!заводський\s)\b(?:комплект|комлект|кіт|bundle)\b"
    r"(?!\s*[:\-]?\s*(?:коробк\w*|мат\s*плат\w*|плат\w*\s*,?\s*заглушк\w*|заглушк\w*|поставк\w*))"
    r"|\+\s*(?:cpu|проц|процесор|ryzen|райзен|i[3579]|xeon|celeron|pentium|athlon|ram|озу|пам|кулер)"
)
_DESC_BUNDLE_RE = re.compile(
    r"\b(?:продається\s+комплектом|ціна\s+за\s+комплект|цена\s+.*\s+за\s+(?:комплект|мат\.?\s*плат\w*\s*\+\s*проц\w*)|"
    r"(?:материн\w*\s+плат\w*|плата|материнка)\s*\+\s*(?:процесор\w*|проц\w*|cpu|ryzen|i[3579])|"
    r"в\s+комплекті\s+(?:процесор\w*|проц\w*|ryzen|intel\s+core))\b"
)
_BUNDLE_CPU_RE = re.compile(r"\b(?:i[3579][\s\-]?\d{4,5}[a-z]*|ryzen\s*[3579][\s\-]?\d{4}[a-z]*|e5[\s\-]?\d{4}[a-z0-9]*)\b")
_DDR4_RE = re.compile(r"\b(?:d4|ddr4|ддр4)\b")
_DDR5_RE = re.compile(r"\b(?:d5|ddr5|ддр5)\b")
_WIFI_RE = re.compile(r"\b(?:wi-?fi|wifi|wireless|ax|ac)\b")
_PRIME_K_RE = re.compile(r"\bprime\b[^\n]*?-k\b", re.IGNORECASE)

VRM_TIER_SCORES = {"S-Tier": 5, "A-Tier": 4, "B-Tier": 3, "C-Tier": 2, "D-Tier": 1}


def extract_form_factor(text: str, chipset_raw: str = "") -> str:
    """Extracts ATX, mATX, ITX, or E-ATX form factor."""
    t = text.lower()
    if _ITX_RE.search(t):
        return "ITX"
    if _EATX_RE.search(t):
        return "E-ATX"
    if _MATX_RE.search(t):
        return "mATX"

    raw = chipset_raw.lower()
    if raw.endswith("i"):
        return "ITX"
    if raw.endswith("m") or "-m" in raw or " m " in t:
        return "mATX"

    return "ATX"


def extract_bundle_info(text: str, is_description: bool = False) -> Tuple[bool, str]:
    """Detects if motherboard is sold in a bundle with CPU / RAM."""
    t = text.lower()
    if is_description:
        is_bundle = bool(_DESC_BUNDLE_RE.search(t))
        cpu_note = ""
        if is_bundle:
            m_cpu = _BUNDLE_CPU_RE.search(t)
            if m_cpu:
                cpu_note = m_cpu.group(0).upper()
        return is_bundle, cpu_note

    is_bundle = bool(_BUNDLE_RE.search(t))
    cpu_note = ""
    m_cpu = _BUNDLE_CPU_RE.search(t)
    if m_cpu:
        cpu_note = m_cpu.group(0).upper()
        is_bundle = True

    return is_bundle, cpu_note


@lru_cache(maxsize=8192)
def _identify_mobo_cached(title: str, desc_head: str, allow_bundles: bool = False) -> Optional[Tuple[Tuple[str, Any], ...]]:
    t_lower = _normalize_mobo_tokens(title.lower())
    excl_re = _BUNDLE_SAFE_MOBO_EXCLUSION_RE if allow_bundles else _MOBO_EXCLUSION_RE
    if excl_re.search(t_lower):
        return None

    desc_l = _normalize_mobo_tokens(desc_head.lower()) if desc_head else ""
    matched_chipset = None
    chipset_name = ""
    socket_name = ""
    ddr_type = ""
    vrm_tier = "B-Tier"
    market_min = 2000
    market_max = 6000
    raw_chipset_str = ""

    if _CHIPSET_FAST_RE.search(t_lower):
        for cre, ch, sock, ddr, tier, p_min, p_max in _COMPILED_CHIPSETS:
            m = cre.search(t_lower)
            if m:
                matched_chipset = ch
                raw_chipset_str = m.group(0)
                chipset_name, socket_name, ddr_type, vrm_tier = ch, sock, ddr, tier
                market_min, market_max = p_min, p_max
                break

    if not matched_chipset and desc_l and _CHIPSET_FAST_RE.search(desc_l):
        for cre, ch, sock, ddr, tier, p_min, p_max in _COMPILED_CHIPSETS:
            m = cre.search(desc_l)
            if m:
                matched_chipset = ch
                raw_chipset_str = m.group(0)
                chipset_name, socket_name, ddr_type, vrm_tier = ch, sock, ddr, tier
                market_min, market_max = p_min, p_max
                break

    if not matched_chipset:
        return None

    combined_lower = f"{t_lower} {desc_l}" if desc_l else t_lower

    if socket_name == "LGA1700":
        if _DDR4_RE.search(combined_lower):
            ddr_type = "DDR4"
        elif _DDR5_RE.search(combined_lower):
            ddr_type = "DDR5"
        else:
            ddr_type = "DDR5" if chipset_name in ("Z790", "B760", "Z690") else "DDR4"

    form_factor = extract_form_factor(combined_lower, raw_chipset_str)

    brand = "Generic"
    for b_name, b_cre in _COMPILED_BRANDS:
        if b_cre.search(combined_lower):
            brand = b_name
            break

    b_low = brand.lower()
    if any(s in b_low for s in ("rog", "aorus master", "taichi", "meg")):
        vrm_tier = "S-Tier"
    elif any(s in b_low for s in ("tuf", "tomahawk", "aorus", "steel legend", "mortar", "proart")):
        if vrm_tier not in ("S-Tier",):
            vrm_tier = "A-Tier"
    elif any(s in combined_lower for s in ("hdv", "h610m")) or _PRIME_K_RE.search(combined_lower):
        vrm_tier = "D-Tier" if chipset_name in ("A320", "H81", "H61") else "C-Tier"

    has_wifi = bool(_WIFI_RE.search(combined_lower))

    is_bundle, bundle_cpu = extract_bundle_info(t_lower, is_description=False)
    if not is_bundle and desc_l:
        is_bundle, bundle_cpu = extract_bundle_info(desc_l[:300], is_description=True)

    clean_model = f"{brand} {chipset_name}".strip()
    if form_factor == "ITX":
        clean_model += "-I"
    elif form_factor == "mATX" and not clean_model.endswith("M"):
        clean_model += "-M"

    risk_level = "LOW"
    risk_notes = "Standard desktop motherboard from established manufacturer."

    if brand in ("Machinist", "Huananzhi", "Jginyue"):
        risk_level = "HIGH"
        risk_notes = "Chinese recycled board (Huananzhi/Machinist). Often uses repurposed B85/H81 server chips with unofficial BIOS modifications."
    elif socket_name in ("LGA1150", "LGA1155"):
        risk_level = "MEDIUM"
        risk_notes = "Legacy platform (11+ years old). High risk of dried electrolytic capacitors or worn power delivery."
    elif vrm_tier == "D-Tier":
        risk_level = "MEDIUM"
        risk_notes = "Entry-level VRM without heatsinks. Unsuitable for 8+ core or high-TDP CPUs (VRM thermal throttling risk)."

    out = {
        "model": clean_model,
        "brand": brand,
        "chipset": chipset_name,
        "socket": socket_name,
        "ddr_type": ddr_type,
        "form_factor": form_factor,
        "vrm_tier": vrm_tier,
        "vrm_score": VRM_TIER_SCORES.get(vrm_tier, 3),
        "has_wifi": has_wifi,
        "is_bundle": is_bundle,
        "bundle_cpu": bundle_cpu,
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "market_used_min": market_min,
        "market_used_max": market_max,
        "market_used_median": (market_min + market_max) // 2,
    }
    return tuple(out.items())


def identify_motherboard(title: str, description: str = "", allow_bundles: bool = False) -> Optional[Dict[str, Any]]:
    """
    Analyzes title and description at C-regex speed to extract motherboard socket,
    chipset, form factor, VRM tier, brand, bundle status, and architectural risk.
    """
    if not title:
        return None
    cached = _identify_mobo_cached(title, (description or "")[:500], allow_bundles=allow_bundles)
    return dict(cached) if cached is not None else None
