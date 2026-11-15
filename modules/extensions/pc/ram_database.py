"""
RAM Benchmark & Specifications Database and Model Parser.
Parses DDR4 and DDR5 memory listings from OLX:
- Generation (DDR4 / DDR5)
- Capacity & Configuration (e.g. 2x8GB, 2x16GB, 2x32GB)
- Frequency (MHz / MT/s)
- CAS Latency (CL) and First-Word Latency (ns)
- Form Factor (Desktop UDIMM, Laptop SODIMM, Server ECC REG)
- Brand & Product Line
- Market price thresholds and Generation/Compatibility Risk Assessments
"""

import re
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple, List

# Patterns that indicate non-RAM accessories, components, or fakes
RAM_EXCLUSION_KEYWORDS = [
    r"\b(радіатор|радиатор|кулер|вентилятор)\s+(?:для\s+)?(?:пам|озу|ram)\b",
    r"\bкоробка\s+(?:від|для|без)\b",
    r"\bbox\s+only\b",
    r"\bтермопрокладк\w*\b",
    r"\b(флешк\w*|флеш-пам|sd-карт\w*|microsd|usb-накопич\w*)\b",
    r"\bперехідник\s+(?:для\s+)?(?:ram|пам)\b",
    r"\b(без\s+пам'яті|без\s+памяти|без\s+чипов|без\s+чіпів)\b",
    r"\b(муляж\w*|макет\w*|пустушк\w*|пустышк\w*|light\s+enhancement|dummy)\b",
    r"\b(обміняю|обменяю|куплю|шукаю)\b",
    r"\b(чохол|підставка|кронштейн)\b",
    r"\b(райзер|riser)\b",
    r"\bводяне\s+блок\b",
]

# Pre-compiled normalization regexes for Cyrillic visual lookalikes and spaced/dotted variants
# (e.g. Cyrillic 'о' in 'SО-DIMM', spaces in 'SO DIMM', dots in 'S.O.DIMM', Cyrillic 'СО ДИММ', 'У-ДИММ').
# Specifically requires 's' and 'o' to form an atomic token (e.g. 'so' or 's.o.') so Russian preposition 'с'
# followed by other words (e.g. 'с радиатором', 'с коробкой', 'с оптового') can never match.
_NORM_SODIMM_RE = re.compile(
    r"\b(?:[sс][oо]|[sс]\.[oо]\.?)[\s\.\-]*(?:[dд][iіиы][mм]{2}|dimm)\b",
    re.IGNORECASE,
)
_NORM_UDIMM_RE = re.compile(
    r"\b[uу][\.\s]*-?(?:[dд][iіиы][mм]{2}|dimm)\b",
    re.IGNORECASE,
)

# Form Factor detection patterns
SERVER_ECC_PATTERNS = [
    r"\b(?:ecc\s*reg|ecc\s*registered|rdimm|lrdimm)\b",
    r"\bсерверн\w*\b",
    r"\bсерверная\b",
    # Specific server RDIMM / LRDIMM manufacturer part-number signatures
    r"\bm393[ab][0-9a-z]{5,10}\b",           # Samsung Registered RDIMM (e.g. M393A2K40BB1, M393A4K40BB2)
    r"\bm386[ab][0-9a-z]{5,10}\b",           # Samsung Load-Reduced LRDIMM
    r"\bhma[0-9a-z]{3,4}[rl][0-9a-z]{5,10}\b", # SK Hynix RDIMM/LRDIMM (R = RDIMM, L = LRDIMM, e.g. HMA42GR7AFR4N)
    r"\bhmc[0-9a-z]{3,4}[rl][0-9a-z]{5,10}\b", # SK Hynix DDR5 RDIMM/LRDIMM
    r"\bkvr\d+r\d+[a-z0-9\/\-]+",             # Kingston ValueRAM RDIMM (R = Registered, e.g. KVR26R19S4/16)
    # JEDEC DDR4/DDR5 registered and load-reduced module type suffixes strictly anchored to JEDEC speed labels
    # (e.g. PC4-2666V-RE1, PC4-2400T-RC0, PC4-3200AA-RE2, PC5-4800B-RB0).
    # Speed bins (2666V, 2400T, 2933Y) are NOT server indicators on their own.
    r"\bpc[45]-\d{4,5}[a-z]+-r[a-z0-9]+\b",
    r"\bpc[45]-\d{4,5}[a-z]+-lr[a-z0-9]+\b",
]

LAPTOP_SODIMM_PATTERNS = [
    r"\bso-?dimm\b",
    r"\bноутбучн\w*\b",
    r"\b(?:для|до|к|в|на|під|под)?\s*ноутбук\w*\b",
    r"\b(?:для|до|к|в|на|під|под)\s+ноут\w*\b",
    r"\blaptop\s+ram\b",
    r"\b(?:fury|hyperx)?\s*impact\b",  # Kingston Fury Impact / HyperX Impact is strictly SO-DIMM
]

# Explicit desktop markers and part number indicators
# Uses negative lookbehind to ensure 'dimm' does NOT match 'so-dimm', 'so dimm', 'sodimm', 's.o.dimm'.
# Note: uses strict \bкомп(?:'|ʼ|ю)\w* or \bкомп\b so 'компактних' does not falsely match.
_COMP_WORD_PATTERN = r"(?:комп(?:'|ʼ|ю)\w*|комп\b)"
DESKTOP_UDIMM_PATTERNS = [
    r"(?<!\bso\s)(?<!\bso-)(?<![a-z0-9\-])(?:udimm|dimm|long-?dimm)\b",
    r"\b(?:десктоп\w*|desktop)\b",
    r"\b(?:для|до|к|в|на|під|под)?\s*(?:пк\b|" + _COMP_WORD_PATTERN + r"|стаціонарн\w*|настольн\w*|системного\s+блок\w*)\b",
    r"\b(?:радіатор\w*|радиатор\w*|rgb|argb)\b",
]

# Brand product lines that are primarily desktop, treated as weak evidence (never overriding laptop markers)
WEAK_DESKTOP_LINE_PATTERNS = [
    r"\b(?:fury\s+beast|fury\s+renegade|beast|renegade|fury)\b",
    r"\b(?:ripjaws|trident|flare)\b",
    r"\b(?:vengeance|dominator)\b",
    r"\b(?:ballistix)\b",
    r"\b(?:viper|viper\s+steel|viper\s+venom)\b",
    r"\b(?:irdm|irdm\s+pro)\b",
    r"\b(?:t-?force|t-?force\s+delta|t-?force\s+vulcan)\b",
    r"\b(?:spectrix|gammix|lancer|valueram|aegis|elite)\b",
]

# Manufacturer part-number form-factor signatures
# Strictly validated against manufacturer part number decoder guides (Samsung, SK Hynix, Crucial, Kingston, Micron)
_PART_ECC_UDIMM_RE = re.compile(
    r"\b(?:"
    r"m391[ab][0-9a-z]{5,10}"                 # Samsung unbuffered ECC UDIMM (e.g. M391A2G43BB2, M391A1G43DB0)
    r"|hma[0-9a-z]{3,4}u7[0-9a-z]{5,10}"     # SK Hynix unbuffered ECC UDIMM (U7 = ECC UDIMM, e.g. HMA41GU7AFR8N, HMA82GU7MFR8N)
    r"|hmc[0-9a-z]{3,4}u7[0-9a-z]{5,10}"     # SK Hynix unbuffered ECC UDIMM DDR5
    r"|mta(?:9|18)asf[0-9a-z]+az\b"           # Micron unbuffered ECC UDIMM (72-bit bus width, AZ = UDIMM, e.g. MTA9ASF1G72AZ)
    r"|kvr\d+e\d+[a-z0-9\/\-]+"               # Kingston ValueRAM ECC UDIMM (E = ECC Unbuffered, e.g. KVR16E11/8)
    r")\b",
    re.IGNORECASE,
)

# Explicit phrase indicating unbuffered ECC memory
_ECC_ERROR_CORRECTION_PHRASE_RE = re.compile(
    r"\b(?:"
    r"підтримк\w*\s+корекці\w*\s+помилок|"
    r"поддержк\w*\s+коррекци\w*\s+ошибок|"
    r"з\s+корекці\w*\s+помилок|"
    r"с\s+коррекци\w*\s+ошибок|"
    r"error\s+correcting|"
    r"with\s+ecc"
    r")\b",
    re.IGNORECASE,
)

# Negated ECC expressions and On-Die ECC (DDR5 feature) that must NOT trigger ECC_UDIMM or SERVER_ECC
_NEG_ECC_RE = re.compile(
    r"\b(?:без|without|no|non-?)\s*(?:підтримки\s+|поддержки\s+)?(?:ecc|есс|корекці\w*\s+помилок|коррекци\w*\s+ошибок)\b|"
    r"\bnon-ecc\b|\bnon-есс\b",
    re.IGNORECASE,
)
_ON_DIE_ECC_RE = re.compile(
    r"\b(?:on-?die|он-?дай)\s+(?:ecc|есс|код\w*|корекці\w*|коррекци\w*)\b|"
    r"\b(?:ecc|есс)\s+(?:on-?die|он-?дай)\b",
    re.IGNORECASE,
)

_PART_UDIMM_RE = re.compile(
    r"\b(?:"
    r"m378[ab][0-9a-z]{5,10}"                 # Samsung desktop UDIMM Non-ECC (e.g. M378A1K43CB2, M378B5173EB0)
    r"|hma[0-9a-z]{3,4}u6[0-9a-z]{5,10}"     # SK Hynix desktop UDIMM Non-ECC (U6 = Non-ECC UDIMM, e.g. HMA81GU6CJR8N, HMA41GU6AFR8N)
    r"|hmc[0-9a-z]{3,4}u6[0-9a-z]{5,10}"     # SK Hynix desktop UDIMM DDR5 Non-ECC (U6 = Non-ECC UDIMM)
    r"|ct\d+g[45]df[a-z0-9]+"                 # Crucial desktop DDR4/DDR5 UDIMM (DF = Desktop Form-factor, e.g. CT8G4DFRA32A)
    r"|ct\d+g[45]8c\d+u\d+"                   # Crucial desktop DDR5 UDIMM (e.g. CT16G48C40U5)
    r"|cp\d+k?\d*g[0-9a-z]+u\d+"              # Crucial Pro desktop UDIMM (e.g. CP2K48G56C46U5, CP16G56C46U5)
    r"|kvr\d+n\d+[a-z0-9\/\-]+"               # Kingston ValueRAM desktop (N = Non-ECC desktop, e.g. KVR26N19S8/8)
    r"|kf4\d+c\d+[a-z0-9\/\-]*"               # Kingston Fury DDR4 desktop (C = Clamshell / Desktop DIMM, e.g. KF432C16BB/16)
    r"|kf5\d+c\d+[a-z0-9\/\-]*"               # Kingston Fury DDR5 desktop (C = Clamshell / Desktop DIMM, e.g. KF560C36BBE/16)
    r")\b",
    re.IGNORECASE,
)

_PART_SODIMM_RE = re.compile(
    r"\b(?:"
    r"m471[ab][0-9a-z]{5,10}"                 # Samsung laptop SODIMM (e.g. M471A1K43CB1, M471A2K43CB1)
    r"|m474[ab][0-9a-z]{5,10}"                 # Samsung laptop SODIMM with ECC (e.g. M474A2K43BB1)
    r"|hma[0-9a-z]{3,4}s[0-9a-z]{5,10}"       # SK Hynix laptop SODIMM (e.g. HMA81GS6AFR8N, S = SODIMM)
    r"|hmc[0-9a-z]{3,4}s[0-9a-z]{5,10}"       # SK Hynix laptop SODIMM DDR5 (S = SODIMM)
    r"|ct\d+g[45]sf[a-z0-9]+"                 # Crucial laptop DDR4/DDR5 SODIMM (SF = Small Form-factor / SODIMM, e.g. CT8G4SFRA32A)
    r"|kvr\d+s\d+[a-z0-9\/\-]+"               # Kingston ValueRAM laptop (S = SODIMM, e.g. KVR26S19S8/8, KVR32S22S8/8)
    r"|kf4\d+s\d+[a-z0-9\/\-]*"               # Kingston Fury Impact SODIMM DDR4 (S = SODIMM, e.g. KF432S20IB/16)
    r"|kf5\d+s\d+[a-z0-9\/\-]*"               # Kingston Fury Impact SODIMM DDR5 (S = SODIMM, e.g. KF556S40IB/16)
    r")\b",
    re.IGNORECASE,
)

# Negated phrases pattern: phrases explicitly stating what the item is NOT for/compatible with.
# Handled in two patterns to cover both word orders safely without deleting part numbers or unrelated text:
# 1. Negation BEFORE device words (e.g. "не підходить для ПК", "не для ноутбука", "not for laptop").
#    Targets only device nouns so trailing part numbers (e.g. "не для ПК HMA41GU7...") are strictly preserved,
#    and unrelated English phrases like "not for sale" do not match.
# 2. Negation AFTER device words (e.g. "для ноутбука не підійде", "для ПК не підходить", "for laptop won't work").
_DEVICE_NOUNS_PATTERN = (
    r"(?:"
    r"пк\b|"
    + _COMP_WORD_PATTERN + r"|"
    r"десктоп\w*|"
    r"стаціонарн\w*|"
    r"desktop\b|"
    r"настольн\w*|"
    r"системного\s+блок\w*|"
    r"ноут\w*|"
    r"ноутбучн\w*|"
    r"laptop\b|"
    r"сервер\w*|"
    r"server\w*"
    r")"
)
_NEG_BEFORE_RE = re.compile(
    r"\b(?:не\s+підходить\s+для|не\s+підійде\s+для|не\s+підійде|не\s+для|не\s+подходит\s+для|не\s+подойдет\s+для|not\s+for|not\s+compatible\s+with)\s+"
    r"(?:будь-?яких\s+|всіх\s+|всех\s+|любых\s+)?"
    + _DEVICE_NOUNS_PATTERN + r"(?:\s*(?:та|і|и|\/|\+|,|або|или)\s*" + _DEVICE_NOUNS_PATTERN + r")*",
    re.IGNORECASE,
)
_NEG_AFTER_RE = re.compile(
    r"\b(?:для|до|под|for)\s+"
    r"(?:будь-?яких\s+|всіх\s+|всех\s+|любых\s+)?"
    + _DEVICE_NOUNS_PATTERN + r"(?:\s*(?:та|і|и|\/|\+|,|або|или)\s*" + _DEVICE_NOUNS_PATTERN + r")*\s+"
    r"(?:точно\s+|взагалі\s+|вообще\s+)?"
    r"(?:не\s+підійде|не\s+підходить|не\s+подойдет|не\s+подходит|is\s+not\s+compatible|won't\s+work)",
    re.IGNORECASE,
)

# Cutoff pattern for descriptions that list other unrelated products/listings
# (e.g. "також є комплект для ПК", "в наявності також", "також продаю", "дивіться інші оголошення").
# Note: Negative lookahead ensures 'також є гарантія', 'також є коробка', 'також є чек' are NOT cut off.
_OTHER_PRODUCTS_CUTOFF_RE = re.compile(
    r"\b(?:"
    r"також\s+є\s+(?!(?:гаранті\w*|коробк\w*|чек\w*|радіатор\w*|кулер\w*|доставк\w*|можлив\w*|торг\w*|тест\w*|перевірк\w*|самовивіз\w*)\b)|"
    r"также\s+есть\s+(?!(?:гаранти\w*|коробк\w*|чек\w*|радиатор\w*|кулер\w*|доставк\w*|возможн\w*|торг\w*|тест\w*|проверк\w*|самовывоз\w*)\b)|"
    r"також\s+в\s+наявності|"
    r"в\s+наявності\s+також|"
    r"також\s+продаю|"
    r"також\s+продається|"
    r"дивіться\s+(?:інші|мої)\s+оголошення|"
    r"смотрите\s+(?:другие|мои)\s+объявления|"
    r"также\s+в\s+наличии|"
    r"в\s+наличии\s+также|"
    r"также\s+продаю|"
    r"также\s+продается|"
    r"also\s+available|"
    r"also\s+selling|"
    r"check\s+my\s+other\s+listings"
    r")\b",
    re.IGNORECASE,
)

# Conflicting dual mention patterns (e.g. "для пк та ноутбука" / "для комп'ютера та ноута")
# Desktop word pattern specifically guards against 'компактних'
_DESKTOP_TARGET_WORDS = (
    r"(?:"
    r"пк\b|"
    + _COMP_WORD_PATTERN + r"|"
    r"десктоп\w*|"
    r"стаціонарн\w*|"
    r"desktop\b"
    r")"
)
_LAPTOP_TARGET_WORDS = r"(?:ноут\w*|laptop\b|so-?dimm\b)"

_DUAL_TARGET_RE = re.compile(
    _DESKTOP_TARGET_WORDS + r"\s*(?:та|і|и|\/|\+|,|або|или)\s*" + _LAPTOP_TARGET_WORDS + r"|"
    + _LAPTOP_TARGET_WORDS + r"\s*(?:та|і|и|\/|\+|,|або|или)\s*" + _DESKTOP_TARGET_WORDS,
    re.IGNORECASE,
)

# Brand and product line matchers
BRANDS = [
    ("Kingston Fury", r"\b(?:kingston\s+fury|fury\s+beast|fury\s+renegade)\b"),
    ("HyperX", r"\bhyperx\b"),
    ("Kingston", r"\bkingston\b"),
    ("G.Skill Trident", r"\b(?:g\.?['\s]*skills?|gskills?)\s+trident\w*\b"),
    ("G.Skill Ripjaws", r"\b(?:g\.?['\s]*skills?|gskills?)\s+ripjaws\w*\b"),
    ("G.Skill Flare", r"\b(?:g\.?['\s]*skills?|gskills?)\s+flare\w*\b"),
    ("G.Skill", r"\b(?:g\.?['\s]*skills?|gskills?)\b"),
    ("Corsair Dominator", r"\bcorsair\s+dominator\b"),
    ("Corsair Vengeance", r"\bcorsair\s+vengeance\b"),
    ("Corsair", r"\bcorsair\b"),
    ("Crucial Ballistix", r"\b(?:crucial\s+ballistix|ballistix)\b"),
    ("Crucial Pro", r"\bcrucial\s+pro\b"),
    ("Crucial", r"\b(?:crucial|micron)\b"),
    ("ADATA XPG", r"\b(?:adata\s+xpg|xpg\s+lancer|xpg\s+gammix|xpg\s+spectrix)\b"),
    ("ADATA", r"\badata\b"),
    ("TeamGroup T-Force", r"\b(?:teamgroup\s+t-?force|t-?force\s+delta|t-?force\s+vulcan)\b"),
    ("TeamGroup", r"\b(?:teamgroup|team\s+group)\b"),
    ("Patriot Viper", r"\b(?:patriot\s+viper|viper\s+steel|viper\s+venom)\b"),
    ("Patriot", r"\bpatriot\b"),
    ("Samsung", r"\bsamsung\b"),
    ("SK Hynix", r"\b(?:sk\s*hynix|hynix)\b"),
    ("Goodram IRDM", r"\b(?:goodram\s+irdm|irdm\s+pro|irdm\s+x)\b"),
    ("Goodram", r"\bgoodram\b"),
    ("Lexar", r"\blexar\b"),
    ("Netac", r"\bnetac\b"),
    ("Juhor", r"\bjuhor\b"),
    ("Kllisre", r"\bkllisre\b"),
    ("Gloway", r"\bgloway\b"),
    ("Asgard", r"\basgard\b"),
    ("Machinist", r"\bmachinist\b"),
]

# Market price guidelines for healthy used hardware in UAH (calibrated to 2026 Ukrainian market)
RAM_MARKET_BENCHMARKS = {
    # DDR4 Desktop UDIMM
    "DDR4_8GB_UDIMM": {"min": 900, "max": 2200, "typical_cl": 16, "speed": 3200},
    "DDR4_16GB_UDIMM": {"min": 1800, "max": 5800, "typical_cl": 16, "speed": 3200},
    "DDR4_32GB_UDIMM": {"min": 4200, "max": 12000, "typical_cl": 16, "speed": 3200},
    "DDR4_64GB_UDIMM": {"min": 9500, "max": 26000, "typical_cl": 18, "speed": 3200},
    # DDR5 Desktop UDIMM
    "DDR5_16GB_UDIMM": {"min": 6500, "max": 14500, "typical_cl": 36, "speed": 5600},
    "DDR5_24GB_UDIMM": {"min": 7500, "max": 16500, "typical_cl": 36, "speed": 5600},
    "DDR5_32GB_UDIMM": {"min": 13500, "max": 28000, "typical_cl": 30, "speed": 6000},
    "DDR5_48GB_UDIMM": {"min": 21000, "max": 42000, "typical_cl": 32, "speed": 6000},
    "DDR5_64GB_UDIMM": {"min": 28000, "max": 46000, "typical_cl": 32, "speed": 6000},
}

_RAM_EXCLUSION_RE = re.compile("|".join(RAM_EXCLUSION_KEYWORDS))
_SERVER_ECC_RE = re.compile("|".join(SERVER_ECC_PATTERNS))
_EXPLICIT_SODIMM_RE = re.compile(r"\b(?:sodimm|so-?dimm|(?:fury|hyperx)?\s*impact)\b", re.IGNORECASE)
_EXPLICIT_UDIMM_RE = re.compile(r"(?<!\bso\s)(?<!\bso-)(?<![a-z0-9\-])(?:udimm|long-?dimm)\b", re.IGNORECASE)
_LAPTOP_SODIMM_RE = re.compile("|".join(LAPTOP_SODIMM_PATTERNS))
_DESKTOP_UDIMM_RE = re.compile("|".join(DESKTOP_UDIMM_PATTERNS))
_WEAK_DESKTOP_LINE_RE = re.compile("|".join(WEAK_DESKTOP_LINE_PATTERNS))
_COMPILED_RAM_BRANDS: List[Tuple[str, re.Pattern]] = [(b, re.compile(p)) for b, p in BRANDS]

_DDR5_GEN_RE = re.compile(r"\b(?:ddr\s*5|ддр\s*5|pc5-?\w*)\b")
_DDR4_GEN_RE = re.compile(r"\b(?:ddr\s*4|ддр\s*4|pc4-?\w*)\b")
_DDR_LEGACY_RE = re.compile(r"\b(?:ddr\s*[123]|ддр\s*[123]|pc[23]-?\w*)\b")
_CAP_COMBO_RE = re.compile(r"\b(\d+)\s*(?:g|gb|гб)?\s*\(\s*(\d+)\s*(?:[xх*×]|по)\s*(\d+)\s*(?:g|gb|гб)?\s*\)")
_CAP_COMBO_REV_RE = re.compile(r"\b(\d+)\s*(?:[xх*×]|по)\s*(\d+)\s*(?:g|gb|гб)?\s*\(\s*(\d+)\s*(?:g|gb|гб)?\s*\)")
_CAP_PO_RE = re.compile(
    r"\b(2|4|8|дві|две|два|чотири|четыре)\s*(?:планк\w*\s+|плашк\w*\s+|модул\w*\s+|шт\w*\s+)?по\s*(\d+)\s*(?:g|gb|гб)?\b"
)
_CAP_KIT_MB_RE = re.compile(r"\b([24])\s*[xх*×]\s*(32768|16384|8192|4096)\b")
_CAP_KIT1_RE = re.compile(r"\b(\d+)\s*[xх*×]\s*(\d+)\s*(?:g|gb|гб)?\b")
_CAP_KIT2_RE = re.compile(r"\b(\d+)\s*(?:gb|гб|g)\s*[xх*×]\s*(\d+)\b")
_CAP_MB_RE = re.compile(r"\b(65536|32768|16384|8192|4096)\s*(?:mb|мб)\b")
_CAP_PLAIN_RE = re.compile(r"\b(\d+)\s*(?:gb|гб)\b")
_SPEED_RE = re.compile(
    r"\b(2133|2400|2666|2933|3000|3200|3600|4000|4133|4266|4400|4600|4800|5200|5600|6000|6200|6400|6600|6800|7000|7200|7600|8000|8200|8400)\s*(?:mhz|мгц|mt/s|мт/с)?\b"
)
_CL_DIRECT_RE = re.compile(r"\bcl\s*[:=-]?\s*(\d{2})\b")
_CL_SHORT_RE = re.compile(r"\b(?:c|cl)(\d{2})\b")
_CL_TIMINGS_RE = re.compile(r"\b(\d{2})-\d{2}-\d{2}\b")


def extract_generation(text: str) -> Optional[str]:
    """Detects DDR4 vs DDR5; returns None for DDR3/DDR2/unsupported."""
    t = text.lower()
    if _DDR5_GEN_RE.search(t):
        return "DDR5"
    if _DDR4_GEN_RE.search(t):
        return "DDR4"
    return None


def extract_form_factor(text: str) -> str:
    """Classifies RAM as Desktop UDIMM, Laptop SODIMM, Server ECC REG, Unbuffered ECC_UDIMM, or UNKNOWN.

    Hierarchical classification:
    1. Neutralize negated phrases ("не підходить для ПК або ноутбуків", "not for laptop").
    2. Check explicit SO-DIMM, RDIMM/Server ECC and Part-number signatures first so explicit markers
       take priority over dual-target mentions.
    3. Dual-target / conflicting mentions ("для ПК та ноутбуків") -> UNKNOWN.
    4. Explicit Laptop SO-DIMM keyword / Impact line -> SODIMM.
    5. Explicit Desktop UDIMM / DIMM keyword -> UDIMM.
    6. Weak desktop product line (Fury Beast, Ripjaws, Vengeance) ONLY IF no laptop keyword -> UDIMM.
    7. Otherwise -> UNKNOWN.
    """
    # 1. Normalize spaced, dotted, and Cyrillic lookalike variants of SO-DIMM and UDIMM first
    t = _NORM_SODIMM_RE.sub("sodimm", text)
    t = _NORM_UDIMM_RE.sub("udimm", t)

    # 2. Neutralize negated phrases in both word orders so device nouns do not trigger false detections
    t = _NEG_BEFORE_RE.sub(" ", t)
    t = _NEG_AFTER_RE.sub(" ", t)
    # Neutralize On-Die ECC (inherent DDR5 architectural feature) and negated ECC phrases ("без підтримки ECC", "non-ecc")
    # so they do not falsely trigger unbuffered ECC or Server ECC detections
    t = _ON_DIE_ECC_RE.sub(" ", t)
    t = _NEG_ECC_RE.sub(" ", t)
    t = t.lower()

    # 3. Check part-numbers and explicit SO-DIMM / RDIMM / Server ECC BEFORE dual-target rule:
    # Check for direct contradictions between part-number and textual form-factor mentions inside this listing:
    has_pn_sodimm = bool(_PART_SODIMM_RE.search(t))
    has_pn_udimm = bool(_PART_UDIMM_RE.search(t))
    has_pn_ecc_udimm = bool(_PART_ECC_UDIMM_RE.search(t))

    has_explicit_udimm = bool(_EXPLICIT_UDIMM_RE.search(t))
    has_explicit_sodimm = bool(_EXPLICIT_SODIMM_RE.search(t))

    # A conflict between a part number and explicit form-factor text (e.g. KVR219S6/4 described as UDIMM) resolves to UNKNOWN
    if has_pn_sodimm and has_explicit_udimm:
        return "UNKNOWN"
    if (has_pn_udimm or has_pn_ecc_udimm) and has_explicit_sodimm:
        return "UNKNOWN"

    # 3a. Laptop part-number signatures (checked before Server ECC so Samsung M474 ECC SO-DIMM stays SODIMM)
    if has_pn_sodimm:
        return "SODIMM"

    # 3b. Server ECC Registered / RDIMM / LRDIMM
    if _SERVER_ECC_RE.search(t):
        return "ECC_REG"

    # 3c. Unbuffered ECC UDIMM signatures (requires checking motherboard ECC support)
    if has_pn_ecc_udimm or (has_pn_udimm and _ECC_ERROR_CORRECTION_PHRASE_RE.search(t)):
        return "ECC_UDIMM"

    # 3d. Desktop Non-ECC part-number signatures
    if has_pn_udimm:
        return "UDIMM"

    # Check unbuffered ECC phrase with desktop indicators (e.g. desktop module with error correction)
    if _ECC_ERROR_CORRECTION_PHRASE_RE.search(t) and (has_explicit_udimm or _DESKTOP_UDIMM_RE.search(t)):
        return "ECC_UDIMM"

    # 3e. Explicit SO-DIMM marker / Impact line (checked before dual target rule)
    if _EXPLICIT_SODIMM_RE.search(t):
        if _EXPLICIT_UDIMM_RE.search(t):
            return "UNKNOWN"
        return "SODIMM"

    # 3f. Explicit UDIMM marker (checked before dual target rule)
    if _EXPLICIT_UDIMM_RE.search(t):
        return "UDIMM"

    # 4. Dual conflicting mentions ("для ПК та ноутбуків")
    if _DUAL_TARGET_RE.search(t):
        return "UNKNOWN"

    # 5. Laptop markers (e.g. "для ноутбука", "ноутбучна", "laptop ram")
    has_laptop = bool(_LAPTOP_SODIMM_RE.search(t))
    if has_laptop:
        return "SODIMM"

    # 6. Explicit Desktop markers (guarded against SO-DIMM)
    if _DESKTOP_UDIMM_RE.search(t):
        return "UDIMM"

    # 7. Weak desktop brand lines (only if no laptop signals at all)
    if _WEAK_DESKTOP_LINE_RE.search(t):
        return "UDIMM"

    # 8. Fallback
    return "UNKNOWN"


def extract_capacity_and_config(text: str) -> Tuple[Optional[int], Optional[str], int]:
    """Extracts total capacity (GB), config string (e.g. '2x16GB'), and module count."""
    t = text.lower()

    m_combo = _CAP_COMBO_RE.search(t)
    if m_combo:
        tot, first_n, second_n = int(m_combo.group(1)), int(m_combo.group(2)), int(m_combo.group(3))
        if first_n * second_n == tot:
            if first_n in (1, 2, 4) and second_n >= 4:
                return tot, f"{first_n}x{second_n}GB", first_n
            if second_n in (1, 2, 4) and first_n >= 4:
                return tot, f"{second_n}x{first_n}GB", second_n
            return tot, f"{first_n}x{second_n}GB", first_n

    m_combo_rev = _CAP_COMBO_REV_RE.search(t)
    if m_combo_rev:
        first_n, second_n, tot = int(m_combo_rev.group(1)), int(m_combo_rev.group(2)), int(m_combo_rev.group(3))
        if first_n * second_n == tot:
            if first_n in (1, 2, 4) and second_n >= 4:
                return tot, f"{first_n}x{second_n}GB", first_n
            if second_n in (1, 2, 4) and first_n >= 4:
                return tot, f"{second_n}x{first_n}GB", second_n
            return tot, f"{first_n}x{second_n}GB", first_n

    m_kit1 = _CAP_KIT1_RE.search(t)
    if m_kit1:
        a, b = int(m_kit1.group(1)), int(m_kit1.group(2))
        if a in (2, 4, 8) and b in (4, 8, 12, 16, 24, 32, 48, 64):
            tot = a * b
            return tot, f"{a}x{b}GB", a
        if b in (2, 4) and a in (4, 8, 12, 16, 24, 32, 48, 64):
            tot = a * b
            return tot, f"{b}x{a}GB", b

    m_kit2 = _CAP_KIT2_RE.search(t)
    if m_kit2:
        mod_sz, count = int(m_kit2.group(1)), int(m_kit2.group(2))
        if count in (2, 4, 8) and mod_sz in (4, 8, 12, 16, 24, 32, 48, 64):
            tot = count * mod_sz
            return tot, f"{count}x{mod_sz}GB", count

    m_po = _CAP_PO_RE.search(t)
    if m_po:
        raw_c = m_po.group(1)
        count = 2 if raw_c in ("2", "дві", "две", "два") else (4 if raw_c in ("4", "чотири", "четыре") else 8)
        mod_sz = int(m_po.group(2))
        if mod_sz in (4, 8, 12, 16, 24, 32, 48, 64):
            tot = count * mod_sz
            return tot, f"{count}x{mod_sz}GB", count

    m_kit_mb = _CAP_KIT_MB_RE.search(t)
    if m_kit_mb:
        count = int(m_kit_mb.group(1))
        mod_sz = int(m_kit_mb.group(2)) // 1024
        tot = count * mod_sz
        return tot, f"{count}x{mod_sz}GB", count

    m_mb = _CAP_MB_RE.search(t)
    if m_mb:
        tot = int(m_mb.group(1)) // 1024
        return tot, f"{tot}GB", 1

    m_plain = _CAP_PLAIN_RE.search(t)
    if m_plain:
        tot = int(m_plain.group(1))
        if tot in (4, 8, 16, 24, 32, 48, 64, 96, 128, 256):
            return tot, f"{tot}GB", 1

    return None, None, 1


def extract_speed(text: str, ddr_gen: str) -> int:
    """Extracts rated frequency in MHz / MT/s or assigns standard default."""
    m = _SPEED_RE.search(text.lower())
    if m:
        return int(m.group(1))
    return 3200 if ddr_gen == "DDR4" else 5600


def extract_cas_latency(text: str, ddr_gen: str, speed_mhz: int) -> int:
    """Extracts CAS Latency (CL) or calculates standard estimate."""
    t = text.lower()

    m1 = _CL_DIRECT_RE.search(t)
    if m1:
        val = int(m1.group(1))
        if 12 <= val <= 46:
            return val

    m2 = _CL_SHORT_RE.search(t)
    if m2:
        val = int(m2.group(1))
        if 12 <= val <= 46:
            return val

    m3 = _CL_TIMINGS_RE.search(t)
    if m3:
        val = int(m3.group(1))
        if 12 <= val <= 46:
            return val

    if ddr_gen == "DDR4":
        if speed_mhz <= 2666:
            return 17
        if speed_mhz <= 3200:
            return 16
        if speed_mhz <= 3600:
            return 18
        return 19
    if speed_mhz <= 5200:
        return 40
    if speed_mhz <= 5600:
        return 38
    if speed_mhz <= 6400:
        return 32
    return 34


def extract_brand_and_model(text: str) -> Tuple[str, str]:
    """Identifies brand and model line."""
    t = text.lower()
    matched_brand = "Generic"
    for brand_name, cre in _COMPILED_RAM_BRANDS:
        if cre.search(t):
            matched_brand = brand_name
            break

    series = ""
    if "renegade" in t:
        series = "Renegade"
    elif "beast" in t:
        series = "Beast"
    elif "predator" in t:
        series = "Predator"
    elif "trident z5" in t:
        series = "Trident Z5"
    elif "trident z" in t:
        series = "Trident Z"
    elif "ripjaws" in t:
        series = "Ripjaws V"
    elif "flare" in t:
        series = "Flare X5"
    elif "dominator" in t:
        series = "Dominator"
    elif "vengeance" in t:
        series = "Vengeance"
    elif "ballistix" in t:
        series = "Ballistix"
    elif "lancer" in t:
        series = "Lancer"
    elif "vulcan" in t:
        series = "Vulcan"
    elif "delta" in t:
        series = "Delta"
    elif "viper" in t:
        series = "Viper"

    model_display = f"{matched_brand} {series}".strip() if series and series not in matched_brand else matched_brand
    return matched_brand, model_display


@lru_cache(maxsize=8192)
def _identify_ram_cached(title: str, desc_head: str) -> Optional[Tuple[Tuple[str, Any], ...]]:
    t_lower = title.lower()
    if _RAM_EXCLUSION_RE.search(t_lower):
        return None
    if desc_head and re.search(r"\b(?:муляж\w*|пустушк\w*|пустышк\w*|light\s+enhancement|чисто\s+визуально\s+как\s+настоящ)\b", desc_head.lower()):
        return None
    # Reject multi-SKU price-list spam titles advertising both DDR4 and DDR5 simultaneously, or legacy DDR1/DDR2/DDR3 titles
    if _DDR5_GEN_RE.search(t_lower) and _DDR4_GEN_RE.search(t_lower):
        return None
    if _DDR_LEGACY_RE.search(t_lower):
        return None

    title_speed_m = _SPEED_RE.search(t_lower)
    title_speed = int(title_speed_m.group(1)) if title_speed_m else None

    ddr_gen = extract_generation(t_lower)
    if not ddr_gen:
        if title_speed is not None and title_speed <= 3600:
            ddr_gen = "DDR4"
        elif title_speed is not None and title_speed >= 4800:
            ddr_gen = "DDR5"
        else:
            ddr_gen = extract_generation(desc_head[:500]) if desc_head else None
            if not ddr_gen:
                return None

    # Enforce JEDEC physical speed boundary if title explicitly states <=3600MHz (cannot be DDR5)
    if title_speed is not None and title_speed <= 3600 and ddr_gen == "DDR5":
        ddr_gen = "DDR4"

    # Weigh title first, description second, and resolve disagreeing evidence to UNKNOWN
    # Clean description of cross-product advertising ("також є", "в наявності також") before analyzing
    desc_clean = desc_head
    if desc_clean:
        m_cut = _OTHER_PRODUCTS_CUTOFF_RE.search(desc_clean)
        if m_cut:
            desc_clean = desc_clean[:m_cut.start()].strip()

    title_form = extract_form_factor(t_lower)
    if desc_clean:
        desc_form = extract_form_factor(desc_clean[:500])
        if title_form == "UNKNOWN":
            form_factor = desc_form
        elif desc_form != "UNKNOWN" and desc_form != title_form:
            # Check if evidence directly pertains to the same module:
            # An explicit title wins unless the description's contradictory evidence is about the same module
            # (e.g. part number in title is contradicted by description, or description introduces a conflicting part number)
            title_has_pn = bool(_PART_SODIMM_RE.search(t_lower) or _PART_UDIMM_RE.search(t_lower) or _PART_ECC_UDIMM_RE.search(t_lower))
            # Part-number scan covers the whole description (desc_head), ensuring part numbers are never missed even if located after a product cutoff
            desc_has_pn = bool(
                _PART_SODIMM_RE.search(desc_head.lower()) or
                _PART_UDIMM_RE.search(desc_head.lower()) or
                _PART_ECC_UDIMM_RE.search(desc_head.lower())
            )
            if title_has_pn or desc_has_pn:
                # Part number contradiction on the same module SKU -> resolve to UNKNOWN
                form_factor = "UNKNOWN"
            else:
                title_is_explicit = bool(
                    _EXPLICIT_SODIMM_RE.search(t_lower) or
                    _EXPLICIT_UDIMM_RE.search(t_lower) or
                    _SERVER_ECC_RE.search(t_lower) or
                    _LAPTOP_SODIMM_RE.search(t_lower) or
                    _DESKTOP_UDIMM_RE.search(t_lower)
                )
                if title_is_explicit:
                    # Clear explicit title wins over loose/unrelated description mention
                    form_factor = title_form
                else:
                    # Weak title line vs contradictory description -> resolve to UNKNOWN
                    form_factor = "UNKNOWN"
        else:
            form_factor = title_form
    else:
        form_factor = title_form

    total_gb, config_str, module_count = extract_capacity_and_config(t_lower)
    if not total_gb and desc_head:
        total_gb, config_str, module_count = extract_capacity_and_config(desc_head[:500])
    elif total_gb and module_count == 1 and desc_head:
        # Refine kit configuration when title only states total GB (e.g. '16GB') and description clarifies '(2x8GB)'
        d_tot, d_cfg, d_mods = extract_capacity_and_config(desc_head[:500])
        if d_tot == total_gb and d_mods in (2, 4):
            config_str, module_count = d_cfg, d_mods
    if not total_gb:
        return None

    speed_mhz = extract_speed(t_lower, ddr_gen)
    if speed_mhz in (3200, 5600) and not _SPEED_RE.search(t_lower) and desc_head:
        speed_mhz = extract_speed(desc_head[:500], ddr_gen)

    cl = extract_cas_latency(t_lower, ddr_gen, speed_mhz)
    if not _CL_DIRECT_RE.search(t_lower) and desc_head:
        desc_cl = extract_cas_latency(desc_head, ddr_gen, speed_mhz)
        if desc_cl != cl:
            cl = desc_cl

    latency_ns = round((cl * 2000.0) / speed_mhz, 1)

    brand, model_name = extract_brand_and_model(t_lower)
    if brand == "Generic" and desc_head:
        desc_brand, desc_model = extract_brand_and_model(desc_head[:500])
        if desc_brand != "Generic":
            brand, model_name = desc_brand, desc_model

    risk_level = "LOW"
    risk_notes = "Standard desktop memory kit."

    if form_factor == "ECC_REG":
        risk_level = "CRITICAL"
        risk_notes = "INCOMPATIBLE WITH CONSUMER MOTHERBOARDS: Server ECC Registered memory. Will NOT post in standard B450/B550/B650/Z690/Z790 systems."
    elif form_factor == "SODIMM":
        risk_level = "HIGH"
        risk_notes = "LAPTOP FORM FACTOR (SO-DIMM): Incompatible with standard desktop DIMM slots without special adapters."
    elif form_factor == "ECC_UDIMM":
        risk_level = "HIGH"
        risk_notes = "UNBUFFERED ECC MEMORY (ECC UDIMM): Requires motherboard & CPU with explicit ECC support (e.g. selected AMD AM4/AM5 boards). Most consumer Intel boards will fail to POST or run in non-ECC mode; verify motherboard QVL before purchasing."
    elif form_factor == "UNKNOWN":
        risk_level = "MEDIUM"
        risk_notes = "AMBIGUOUS FORM FACTOR: Listing lacks explicit desktop/laptop markers; confirm physical DIMM pinout with seller before purchasing."
    elif brand in ("Juhor", "Kllisre", "Gloway", "Asgard", "Machinist"):
        risk_level = "MEDIUM"
        risk_notes = "Budget white-label brand. Often utilizes recycled/reballed server BGA dies or generic SPDs with loose secondary timings."
    elif speed_mhz >= 7200:
        risk_level = "MEDIUM"
        risk_notes = "High-speed DDR5 (>7000 MT/s). Requires high-end motherboard and IMC silicon lottery; may fail rated XMP/EXPO without manual voltage tuning."

    bench_key = f"{ddr_gen}_{total_gb}GB_{form_factor}"
    bench = RAM_MARKET_BENCHMARKS.get(bench_key, {})
    min_market = bench.get("min", total_gb * (65 if ddr_gen == "DDR4" else 120))
    max_market = bench.get("max", total_gb * (120 if ddr_gen == "DDR4" else 220))

    out = {
        "generation": ddr_gen,
        "form_factor": form_factor,
        "total_gb": total_gb,
        "config": config_str,
        "module_count": module_count,
        "speed_mhz": speed_mhz,
        "cas_latency": cl,
        "latency_ns": latency_ns,
        "brand": brand,
        "model": model_name,
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "market_used_min": min_market,
        "market_used_max": max_market,
        "market_used_median": (min_market + max_market) // 2,
    }
    return tuple(out.items())


def identify_ram(title: str, description: str = "") -> Optional[Dict[str, Any]]:
    """
    Analyzes title and description at C-regex speed to extract verified RAM specifications.
    Returns None if listing is not a DDR4 or DDR5 RAM module.
    """
    if not title:
        return None
    cached = _identify_ram_cached(title, (description or "")[:1000])
    return dict(cached) if cached is not None else None
