"""Multi-Component Bundle & Prebuilt PC Proposition Detector.

Extracts validated multi-part hardware bundles (e.g. CPU + Motherboard,
CPU + Motherboard + RAM, CPU + RAM, GPU + CPU) and complete Prebuilt PCs
from raw marketplace caches so the combinatorial build synthesizer can
evaluate them alongside standalone components without double-counting prices.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from audit_ledger import ledger
from currency import convert_currency
from extensions.pc.cpu_database import identify_cpu
from extensions.pc.cpu_scam_detector import CPUScamDetector
from extensions.pc.gpu_database import identify_gpu
from extensions.pc.gpu_scam_detector import GPUScamDetector
from extensions.pc.mobo_database import identify_motherboard
from extensions.pc.mobo_scam_detector import MotherboardScamDetector
from extensions.pc.modes import ModeProfile, PSU_TIER_RANK
from extensions.pc.psu_database import identify_psu
from extensions.pc.psu_scam_detector import PSUScamDetector
from extensions.pc.ram_database import identify_ram
from extensions.pc.ram_scam_detector import RAMScamDetector

# ---------------------------------------------------------------------------
# Intent & Exclusion Patterns
# ---------------------------------------------------------------------------

# Strip parenthetical optional add-ons like "+ 32Гб DDR5 (опціонально)"
_OPTIONAL_ITEM_RE = re.compile(
    r"(?:\+|,|\bта\b|\bі\b|\bи\b|\d+\.\s*)?\s*[^+\n,;]{1,55}?"
    r"\(\s*(?:опціонально|опционально|за\s+доплату|окремо|не\s+входить)[^)]*\)",
    re.IGNORECASE,
)

# Strip seller upsell / cross-sell / compatibility / past-rig anecdote clauses
# from descriptions so optional add-ons or "worked with my Ryzen 5800X3D"
# are never mistaken for parts included in the listing's base price.
_DESC_CUTOFF_RE = re.compile(
    r"(?:також\s+(?:можу|є|в\s+наявності|продаю|продам)|"
    r"так\s*же\s+(?:есть|могу|в\s+наличии|продаю|продам)|"
    r"можу\s+(?:додати|продати|доукомплектувати)|могу\s+(?:добавить|продать|доукомплектовать)|"
    r"ще\s+є\s+в\s+наявності|за\s+доплату|опціонально|опционально|за\s+окрему\s+плату|"
    r"можливий\s+продаж\s+з|можна\s+доукомплектувати|"
    r"яка\s+також\s+продається|який\s+також\s+продається|продається\s+окремо|продается\s+отдельно|"
    r"рекомендований\s+блок\s+живлення|рекомендуемый\s+блок\s+питания|"
    r"споживана\s+потужність|потребляемая\s+мощность|"
    r"підтримує\s+процесори|поддерживает\s+процессоры|підтримка\s+процесорів|"
    r"сумісн[аіий]\s+з\s+процесор|підійде\s+для\s+відеокарт|подойд[её]т\s+для\s+видеокарт|"
    r"працюва(?:в|ла|ли)\s+(?:у\s+парі\s+|в\s+парі\s+)?(?:з|із|зі)\b|"
    r"работа(?:л|ла|ли)\s+(?:в\s+паре\s+)?с\b|"
    r"стоя(?:в|ла|ли)\s+(?:у|в)\s+(?:моєму|моем|домашньому|домашнем|пк|комп))",
    re.IGNORECASE,
)

# Strip standard box/accessory phrases ("повний комплект", "комплект оперативної пам'яті")
# before checking whether the listing is a multi-component bundle.
_BOX_BUNDLE_CLEAN_RE = re.compile(
    r"(?:повний|полный|найповніший|рідний|родной|заводський|заводской|оригінальний|оригинальный|"
    r"стандартний|базовий|магазинный|магазинний)\s+комплект\b|"
    r"\bкомплект\s*(?:поставки|на\s+фото|як\s+з\s+магазину|коробка)|"
    r"\bкомплект(?:ом)?\s+(?:оперативн\w+\s+пам['’ʼ]?ят\w*|пам['’ʼ]?ят\w*|озу|озп|із\s+двох\s+модул\w*|з\s+2\s+планок)|"
    r"\bв\s+комплект[іи]\s*(?:є\s*)?(?:коробка|заглушка|кабел|диск|інструкція|документ|кріплення|бекплейт|кулер|вентилятор)",
    re.IGNORECASE,
)

# Strip "процесор для ігрового ПК" / "плата в комп'ютер" so standalone parts
# describing their target use case aren't flagged as prebuilt PCs.
_FOR_PC_CLEAN_RE = re.compile(
    r"(?:для|в|під|на|под)\s+(?:побудови\s+)?(?:потужного\s+|ігрового\s+|игрового\s+|домашнього\s+|офісного\s+|робочого\s+)?"
    r"(?:пк|комп['’ʼ]?ютер\w*|комп\b|системн\w+\s+блок\w*)",
    re.IGNORECASE,
)

# Explicit multi-part bundle intent in title.
_BUNDLE_INTENT_RE = re.compile(
    r"\+|"
    r"\b(?:комплект(?:ом)?|сет|кит|кіт|kit|bundle|зв['’ʼ]?язк[ау]|связк[ау]|набір|набор|"
    r"разом\s+з|разом\s+із|в\s+зборі|в\s+сборе|тушка|тушку|база\s+пк|основа\s+пк|"
    r"збірк[ау]|сборк[ау])\b|"
    r"\b(?:системн\w+\s+блок|ігровий\s+пк|игровой\s+пк|комп['’ʼ]?ютер\w*|компютер\w*|"
    r"ігровий\s+комп\w*|игровой\s+комп\w*|готовий\s+пк|готовый\s+пк|gaming\s+pc)\b",
    re.IGNORECASE,
)

# Explicit complete Prebuilt PC intent (system unit / full PC build).
_PREBUILT_PC_RE = re.compile(
    r"\b(?:системн\w+\s+блок\w*|ігровий\s+пк|игровой\s+пк|ігровий\s+комп['’ʼ]?ютер\w*|"
    r"игровой\s+компьютер\w*|ігровий\s+компютер\w*|комп['’ʼ]?ютер\s+в\s+зборі|пк\s+в\s+зборі|"
    r"пк\s+в\s+сборе|готовий\s+(?:ігровий\s+)?пк|готовый\s+(?:игровой\s+)?пк|"
    r"збірка\s+(?:для\s+)?пк|сборка\s+(?:для\s+)?пк|ігровий\s+набір|игровой\s+набор|"
    r"gaming\s+pc|prebuilt\s+pc)\b",
    re.IGNORECASE,
)

# Non-PC / broken / laptop / part-out exclusions.
_EXCLUDE_BUNDLE_RE = re.compile(
    r"\b(?:ноутбук\w*|лептоп\w*|laptop|macbook|моноблок\w*|all-in-one|"
    r"для\s+телевізор\w*|тв\s+бокс|tv\s+box|smart\s+tv|приставк\w+|playstation|ps[45]|xbox|"
    r"на\s+запчасти\w*|на\s+запчастин\w*|під\s+відновлення|под\s+восстановление|"
    r"неробоч\w+|нерабоч\w+|не\s+вмикається|не\s+включается|не\s+стартує|не\s+стартует|"
    r"куплю|обмін\s+на|обмен\s+на|оренда|аренда|ремонт\b|послуг[аи])\b",
    re.IGNORECASE,
)

# Explicit GPU family/prefix required in bundles so DDR5 6800MHz or Ryzen 5600X never match RX 6800 / RX 5600 XT.
_EXPLICIT_GPU_CONTEXT_RE = re.compile(
    r"\b(?:rtx|gtx|rx|radeon|geforce|arc\s+[ab]\d{3}|vega\s*\d+|quadro|"
    r"відеокарт\w*|видеокарт\w*|відюх\w*|видюх\w*|gpu)\b",
    re.IGNORECASE,
)

# Mask GPU VRAM, storage capacities, and motherboard max-RAM slot specs before running RAM detection.
_GPU_VRAM_MASK_RE = re.compile(
    r"\b(?:rtx|gtx|rx|radeon|geforce|arc|vega)\s*[\w\s\-]{1,22}?\b(?:3|4|6|8|10|11|12|16|20|24)\s*(?:gb|гб)(?:\s*gddr\d\w*)?",
    re.IGNORECASE,
)
_STORAGE_MASK_RE = re.compile(
    r"\b(?:ssd|hdd|nvme|m\.?2|sata|ссд|хдд|диск|вінчестер|накопичувач)\s*[\w\s\-/]{0,18}?\b\d+\s*(?:gb|гб|tb|тб)\b|"
    r"\b\d+\s*(?:gb|гб|tb|тб)\s*(?:ssd|hdd|nvme|m\.?2|sata|ссд|хдд)\b|"
    r"\b(?:120|128|240|250|256|480|500|512|960|1000|1024|2000)\s*(?:gb|гб)\b|"
    r"\b[1248]\s*(?:tb|тб)\b",
    re.IGNORECASE,
)
_MOBO_RAM_SLOT_MASK_RE = re.compile(
    r"\b[24]\s*(?:x\s*)?слот\w*\s*(?:під\s+|для\s+)?(?:озу\s+|озп\s+|пам['’ʼ]?ят\w*\s+)?(?:ddr[345])?[^.\n,;]{0,28}?(?:gb|гб)?\b|"
    r"\b(?:\(\s*)?до\s*(?:16|32|64|128|192|256)\s*(?:gb|гб)(?:\s*\))?|"
    r"\bмакс(?:имальний|имальный)?\s+об['’ʼ]?[єе]м[^.\n,;]{0,25}?(?:gb|гб)\b",
    re.IGNORECASE,
)

# Explicit RAM context required so bare numbers don't trigger RAM matches.
_EXPLICIT_RAM_RE = re.compile(
    r"\b(?:ddr[345]|ддр[345]|озу|озп|ram\b|оператив\w+|пам['’ʼ]?ят\w*|"
    r"[24]\s*[xх×]\s*(?:4|8|16|32)\s*(?:gb|гб)?|"
    r"(?:8|16|32|64)\s*(?:gb|гб)\s*(?:ddr[345]|ддр[345]|озу|озп|ram|3000|3200|3600|5200|5600|6000|6400)|"
    r"(?:3000|3200|3600|5200|5600|6000|6400)\s*(?:mhz|мгц)|"
    r"kingston|fury|hyperx|corsair|vengeance|g\.?\s*skill|ripjaws|trident|"
    r"crucial|ballistix|patriot|viper|goodram|irdm|xpg|team\s*group|t-force|lexar)\b",
    re.IGNORECASE,
)

# Optional / excluded RAM mentions ("без ОЗУ", "без оперативки", "ОЗУ опціонально").
_NO_RAM_RE = re.compile(
    r"(?:без\s+(?:озу|озп|оператив\w+|пам['’ʼ]?ят\w+|ram)|"
    r"(?:озу|озп|оператив\w+|ram)\s*(?:не\s+входить|немає|нет|опціонально|опционально|за\s+доплату|окремо))",
    re.IGNORECASE,
)

# Explicit PSU context required when extracting PSU from non-PSU categories.
_EXPLICIT_PSU_RE = re.compile(
    r"\b(?:бп|бж|блок\s+живлення|блок\s+питания|psu|power\s+supply|"
    r"seasonic|super\s*flower|corsair\s+(?:rm|cx|cv|tx|hx|ax|sf)|"
    r"be\s*quiet|chieftec|deepcool\s+(?:pk|pf|pq|dq|px|pn)|"
    r"aerocool\s+(?:vx|kcas|lux|cylon)|gamemax|vinga|1stplayer|fsp|"
    r"thermaltake\s+(?:smart|toughpower)|zalman\s+(?:zm|megamax|gigamax|wattbit)|"
    r"evga\s+\d+\s*[wb]|xilence|cougar\s+(?:vte|ste|stx|bxm|gex))\b",
    re.IGNORECASE,
)
_NO_PSU_RE = re.compile(
    r"(?:без\s+(?:бп|бж|блок\w*\s+живлення|блок\w*\s+питания|psu))",
    re.IGNORECASE,
)

# Default conservative motherboards by CPU socket for Prebuilt PCs that omit board model.
_DEFAULT_MOBO_QUERY_BY_SOCKET: Dict[str, str] = {
    "AM4": "B450",
    "AM5": "B650",
    "LGA1700": "B760 DDR4",
    "LGA1851": "B860",
    "LGA1200": "B560",
    "LGA1151v2": "B360",
    "LGA1151": "B250",
    "LGA2011-v3": "X99",
}


def _clean_text_for_bundle(title: str, description: str) -> Tuple[str, str, str]:
    """Return (clean_title, clean_desc, combined_clean) with optional items & upsells stripped."""
    clean_title = _OPTIONAL_ITEM_RE.sub(" ", title.strip())
    desc_head = _OPTIONAL_ITEM_RE.sub(" ", (description or "")[:450])
    m_cut = _DESC_CUTOFF_RE.search(desc_head)
    if m_cut:
        desc_head = desc_head[: m_cut.start()]
    m_title_cut = _DESC_CUTOFF_RE.search(clean_title)
    if m_title_cut:
        clean_title = clean_title[: m_title_cut.start()]
    return clean_title.strip(), desc_head.strip(), f"{clean_title} {desc_head}".strip()


def _has_bundle_or_prebuilt_intent(
    clean_title: str, clean_desc: str, source_category: str = ""
) -> Tuple[bool, bool]:
    """Return (has_bundle_intent, is_prebuilt_intent).

    Requires bundle/prebuilt intent in the title itself (or explicit gift/bundle phrase in desc)
    so single-part listings that mention past rig specs in the description are never misclassified.
    """
    if source_category == "prebuilt":
        return True, True

    combined = f"{clean_title} {clean_desc}"
    if _EXCLUDE_BUNDLE_RE.search(combined):
        return False, False

    title_no_box = _BOX_BUNDLE_CLEAN_RE.sub(" ", clean_title)
    desc_no_box = _BOX_BUNDLE_CLEAN_RE.sub(" ", clean_desc[:260])
    scrubbed_title = _FOR_PC_CLEAN_RE.sub(" ", title_no_box)
    scrubbed_desc = _FOR_PC_CLEAN_RE.sub(" ", desc_no_box)

    is_prebuilt = bool(_PREBUILT_PC_RE.search(title_no_box)) or bool(
        re.search(r"^(?:продам\s+)?(?:системн\w+\s+блок|ігровий\s+пк|игровой\s+пк)", desc_no_box, re.IGNORECASE)
    )
    has_title_bundle = is_prebuilt or bool(_BUNDLE_INTENT_RE.search(scrubbed_title))
    if not has_title_bundle:
        # Also allow when description explicitly states "+ материнська плата в подарунок / продається комплектом"
        has_explicit_desc_bundle = bool(
            re.search(
                r"(?:\+\s*(?:материн\w+|процесор\w*|проц\b|оператив\w+|озу)\b|"
                r"\bпрода(?:ю|ється|ется|м)\s+(?:тільки\s+|только\s+)?комплектом\b|"
                r"\bматерин\w+\s+плат\w+\s+(?:до\s+нього\s+|к\s+нему\s+)?в\s+(?:подарунок|подарок)\b)",
                scrubbed_desc,
                re.IGNORECASE,
            )
        )
        if not has_explicit_desc_bundle:
            return False, False

    return True, is_prebuilt


def _primary_category_for_bundle(cats: Set[str], is_prebuilt: bool) -> str:
    """Choose the primary carrier category that holds the bundle price."""
    if is_prebuilt and "gpu" in cats:
        return "gpu"
    for order in ("gpu", "cpu", "mobo", "ram", "psu"):
        if order in cats:
            return order
    return sorted(cats)[0]


def _extract_item_condition(item: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Extract (is_new, condition, condition_label) consistently with build_optimizer."""
    is_new = bool(item.get("is_new") or item.get("condition") == "new")
    cond = str(item.get("condition") or ("new" if is_new else "used")).lower()
    raw_lbl = item.get("condition_label")
    if raw_lbl:
        cond_lbl = str(raw_lbl)
    elif is_new or cond == "new":
        cond_lbl = "new"
    elif cond == "refurbished":
        cond_lbl = "refurbished / outlet"
    elif cond in ("for_parts", "not_working"):
        cond_lbl = "for parts"
    else:
        cond_lbl = "used"
    return is_new, cond, cond_lbl


def _passes_bundle_part_gate(
    category: str,
    cand: Dict[str, Any],
    profile: ModeProfile,
) -> bool:
    """Apply universal defect blocks and mode-specific hardware safety gates."""
    if cand.get("condition") in ("for_parts", "not_working"):
        return False

    ev = cand.get("eval") or cand.get("heuristic") or {}
    if ev.get("is_ai_rejected"):
        return False

    is_approved = ev.get("is_ai_approved")
    if not is_approved:
        if ev.get("red_flags"):
            return False
        if ev.get("risk_score", 0) > profile.max_risk:
            return False

    spec = cand.get("spec") or {}
    arch_risk = spec.get("risk_level", "LOW")
    if profile.name == "safe" and arch_risk in ("CRITICAL", "HIGH"):
        return False
    if profile.block_critical_arch and arch_risk == "CRITICAL":
        return False

    if profile.form_factors and category in ("mobo", "psu"):
        ff = spec.get("form_factor", "")
        if ff and ff not in profile.form_factors:
            return False

    if category == "psu":
        p_tier = spec.get("vrm_tier", "Tier C")
        t_rank = PSU_TIER_RANK.get(p_tier, 2)
        min_rank = PSU_TIER_RANK.get(profile.min_psu_tier, 2)
        if p_tier == "Tier D":
            # Allow non-explosive Tier D PSUs (e.g. Gamemax/Vinga) only inside complete Prebuilt PCs
            # in non-safe modes; standalone Tier D PSUs and CRITICAL fire hazards remain blocked.
            if not (cand.get("is_prebuilt") and spec.get("risk_level") != "CRITICAL" and profile.name != "safe"):
                return False
        if profile.name in ("safe", "best") and t_rank < min_rank and not cand.get("is_prebuilt"):
            return False

    return True


def extract_bundle_from_item(
    item: Dict[str, Any],
    effective_curr: str,
    detectors: Optional[Dict[str, Any]] = None,
    re_audit: bool = False,
    source_category: str = "",
) -> Optional[Dict[str, Any]]:
    """Inspect a raw marketplace listing and extract a bundle/prebuilt proposition if valid.

    Returns a dict:
        {
            "id": str,
            "title": str,
            "url": str,
            "price": float,            # in effective_curr
            "price_uah": float,        # in UAH
            "discount_pct": float,     # combined discount vs sum of constituent medians (+ = cheaper)
            "condition": str,
            "risk_score": float,
            "is_prebuilt": bool,
            "categories": List[str],   # e.g. ["cpu", "mobo", "ram"]
            "primary_category": str,   # e.g. "cpu"
            "bundle_label": str,       # e.g. "BUNDLE: CPU+MOBO+RAM" or "PREBUILT PC"
            "components": Dict[str, Dict[str, Any]],  # cat -> build_optimizer-compatible component dict
        }
    or None if the item is a single component, invalid, or fails anti-scam/price checks.
    """
    title = item.get("title", "")
    desc = item.get("description") or (item.get("raw") or {}).get("description", "")
    if not title:
        return None

    clean_title, clean_desc, combined = _clean_text_for_bundle(title, desc)
    has_intent, is_prebuilt_intent = _has_bundle_or_prebuilt_intent(
        clean_title, clean_desc, source_category=source_category
    )
    if not has_intent:
        return None

    # 1. Identify CPU first (and mask its matched span before GPU identification
    # so CPU numbers like "5600 XT", "5700", "6700", "7600" never collide with Radeon GPUs)
    c_info = identify_cpu(clean_title, clean_desc, allow_bundles=True)
    gpu_search_title = clean_title
    gpu_search_desc = clean_desc
    if c_info:
        cpu_num_m = re.search(r"\b(\d{4,5}[a-z0-9]*)\b", c_info["model"], re.IGNORECASE)
        if cpu_num_m:
            tok = re.escape(cpu_num_m.group(1))
            mask_re = re.compile(
                rf"\b(?:ryzen\s*[3579]?|core\s*i[3579]|i[3579]|r[3579]|процесор\w*|проц\b)[\s\-]*{tok}(?:\s*xt|\s*x3d|\s*f|\s*g|\s*k|\s*kf)?\b",
                re.IGNORECASE,
            )
            gpu_search_title = mask_re.sub(" ", gpu_search_title)
            gpu_search_desc = mask_re.sub(" ", gpu_search_desc)

    # 2. Identify GPU (require explicit GPU prefix/keyword so DDR5 6800MHz or Ryzen 5600X don't match GPUs;
    # for non-prebuilt bundles outside the GPU category, require GPU mention in title so description anecdotes
    # like "worked with GTX 1060" on a CPU+Mobo bundle don't pollute the bundle).
    g_info: Optional[Dict[str, Any]] = None
    if is_prebuilt_intent or source_category in ("gpu", "prebuilt"):
        if _EXPLICIT_GPU_CONTEXT_RE.search(f"{gpu_search_title} {gpu_search_desc}"):
            g_info = identify_gpu(gpu_search_title, gpu_search_desc, allow_bundles=True)
    else:
        if _EXPLICIT_GPU_CONTEXT_RE.search(gpu_search_title):
            g_info = identify_gpu(gpu_search_title, "", allow_bundles=True)

    # 3. Identify Motherboard
    m_info = identify_motherboard(clean_title, clean_desc, allow_bundles=True)

    # Verify CPU <-> Motherboard socket coherence if both are detected
    if c_info and m_info:
        if c_info["socket"] != m_info["socket"]:
            title_cpu = identify_cpu(clean_title, "", allow_bundles=True)
            title_mobo = identify_motherboard(clean_title, "", allow_bundles=True)
            if title_cpu and title_mobo and title_cpu["socket"] == title_mobo["socket"]:
                c_info, m_info = title_cpu, title_mobo
            elif title_cpu and not title_mobo:
                m_info = None
            elif title_mobo and not title_cpu:
                c_info = None
            else:
                return None

    # Infer platform memory type (DDR4 vs DDR5) from Motherboard or CPU socket
    inferred_mem_type: Optional[str] = None
    if m_info:
        inferred_mem_type = m_info.get("ddr_type")
    elif c_info:
        c_sock = c_info["socket"]
        if c_sock in ("AM5", "LGA1851"):
            inferred_mem_type = "DDR5"
        elif c_sock in ("AM4", "LGA1200", "LGA1151", "LGA1151v2", "LGA2011-v3"):
            inferred_mem_type = "DDR4"

    # 4. Identify RAM (after masking GPU VRAM, SSD/HDD storage, and Mobo RAM-slot specs)
    r_info: Optional[Dict[str, Any]] = None
    if not _NO_RAM_RE.search(f"{title} {desc[:450]}"):
        ram_text = _GPU_VRAM_MASK_RE.sub(" ", combined)
        ram_text = _STORAGE_MASK_RE.sub(" ", ram_text)
        ram_text = _MOBO_RAM_SLOT_MASK_RE.sub(" ", ram_text)
        has_explicit_ram = bool(_EXPLICIT_RAM_RE.search(ram_text))
        if not has_explicit_ram and is_prebuilt_intent and (g_info and c_info):
            has_explicit_ram = bool(
                re.search(r"\b(?:8|16|24|32|48|64)\s*(?:gb|гб)\b", ram_text, re.IGNORECASE)
            )
        if has_explicit_ram:
            ram_query = ram_text
            if (
                inferred_mem_type
                and not re.search(r"\b(?:ddr[345]|ддр[345])\b", ram_query, re.IGNORECASE)
            ):
                ram_query = f"{ram_query} {inferred_mem_type}"
            r_info = identify_ram(ram_query, "")
            if r_info:
                if r_info.get("form_factor") in ("SODIMM", "ECC_REG"):
                    r_info = None
                elif m_info and r_info["generation"] != m_info["ddr_type"]:
                    if m_info["socket"] == "LGA1700" and r_info["generation"] in ("DDR4", "DDR5"):
                        m_info = dict(m_info)
                        m_info["ddr_type"] = r_info["generation"]
                    else:
                        r_info = None

    # 5. Identify PSU (require explicit PSU context so B550/B650/Ryzen 1600 don't match PSU wattages)
    p_info: Optional[Dict[str, Any]] = None
    if not _NO_PSU_RE.search(combined) and _EXPLICIT_PSU_RE.search(combined):
        psu_clauses = [
            m.group(0)
            for m in re.finditer(
                r"(?:[\w\-]+\s+){0,4}(?:бп|бж|блок\s+живлення|блок\s+питания|psu|power\s+supply|"
                r"seasonic|super\s*flower|corsair|be\s*quiet|chieftec|deepcool|aerocool|gamemax|"
                r"vinga|1stplayer|fsp|thermaltake|zalman|evga|xilence|cougar)(?:\s+[\w\-\+!]+){0,6}",
                combined,
                re.IGNORECASE,
            )
        ]
        psu_text = " ".join(psu_clauses) if psu_clauses else clean_title
        p_cand = identify_psu(psu_text, "")
        if p_cand and p_cand.get("wattage", 0) >= 450:
            p_info = p_cand

    # 6. Prebuilt PC completion: if this is an explicit Prebuilt PC with at least GPU + CPU
    # (and at least one other component or from the 'prebuilt' category), fill any unstated
    # internal motherboard / RAM / PSU with conservative socket-compatible defaults so the
    # complete system can be synthesized as a 5-part PC build.
    explicit_count = sum(1 for x in (g_info, c_info, m_info, r_info, p_info) if x is not None)
    inferred_cats: Set[str] = set()
    is_prebuilt = False

    if is_prebuilt_intent and g_info and c_info and (explicit_count >= 3 or source_category == "prebuilt"):
        is_prebuilt = True
        c_sock = c_info["socket"]
        if not m_info:
            default_q = _DEFAULT_MOBO_QUERY_BY_SOCKET.get(c_sock, "B450")
            if r_info and c_sock == "LGA1700":
                default_q = f"B760 {r_info['generation']}"
            m_info = identify_motherboard(default_q, "", allow_bundles=True)
            if m_info:
                inferred_cats.add("mobo")
        if not r_info:
            mem_t = m_info["ddr_type"] if m_info else (inferred_mem_type or "DDR4")
            default_ram_q = "2x8GB DDR5 5600" if mem_t == "DDR5" else "2x8GB DDR4 3200"
            r_info = identify_ram(default_ram_q, "")
            if r_info:
                inferred_cats.add("ram")
        if not p_info:
            g_tdp = int(g_info.get("tdp_watts", 180))
            c_tdp = int(c_info.get("tdp_watts", 65))
            req_w = max(550, int(((g_tdp + c_tdp + 130) // 50) * 50))
            p_info = identify_psu(f"Chieftec {req_w}W Bronze", "")
            if p_info:
                inferred_cats.add("psu")

    matched_specs: Dict[str, Dict[str, Any]] = {}
    if g_info:
        matched_specs["gpu"] = g_info
    if c_info:
        matched_specs["cpu"] = c_info
    if m_info:
        matched_specs["mobo"] = m_info
    if r_info:
        matched_specs["ram"] = r_info
    if p_info:
        matched_specs["psu"] = p_info

    if len(matched_specs) < 2:
        return None
    if len(matched_specs) == 5:
        is_prebuilt = True

    # 7. Price feasibility & anti-SEO validation
    raw_price = float(item.get("price", 0) or 0)
    if raw_price <= 0:
        return None
    item_curr = item.get("currency") or effective_curr
    price_uah = convert_currency(raw_price, from_currency=item_curr, to_currency="UAH")
    bundle_price = convert_currency(price_uah, from_currency="UAH", to_currency=effective_curr)

    part_medians_uah: Dict[str, float] = {}
    part_mins_uah: Dict[str, float] = {}
    for cat, spec in matched_specs.items():
        mn = float(spec.get("market_used_min", 1000))
        mx = float(spec.get("market_used_max", mn * 1.5))
        med = float(spec.get("market_used_median") or ((mn + mx) / 2.0))
        part_mins_uah[cat] = mn
        part_medians_uah[cat] = med

    explicit_mins = [part_mins_uah[c] for c in matched_specs if c not in inferred_cats]
    sum_explicit_min = sum(explicit_mins)
    max_explicit_min = max(explicit_mins) if explicit_mins else 0.0
    sum_all_min = sum(part_mins_uah.values())
    sum_all_median = max(1.0, sum(part_medians_uah.values()))

    # Reject SEO-stuffed single-part listings whose price cannot possibly cover the bundle:
    # - Must be at least 52% of the sum of minimum used prices of all parts
    # - Must be at least 72% of the single most expensive part's minimum used price
    # - Must not exceed 185% of the sum of market medians
    if price_uah < sum_all_min * 0.52 or price_uah < sum_explicit_min * 0.55:
        return None
    if price_uah < max_explicit_min * 0.72:
        return None
    if price_uah > sum_all_median * 1.85:
        return None

    # 8. Scam & Defect Detection across all explicitly included categories
    if detectors is None:
        detectors = {
            "gpu": GPUScamDetector(),
            "cpu": CPUScamDetector(),
            "mobo": MotherboardScamDetector(),
            "ram": RAMScamDetector(),
            "psu": PSUScamDetector(),
        }

    offer_id = str(item.get("id", ""))
    has_deliv = item.get("has_olx_delivery", True)
    audit_rec = None
    if not re_audit and offer_id:
        audit_rec = ledger.get_audit(
            offer_id,
            title=title,
            price=raw_price,
            description=desc,
            has_delivery=has_deliv,
        )
    is_approved = bool(audit_rec and audit_rec.get("verdict") == "APPROVED")
    is_rejected = bool(audit_rec and audit_rec.get("verdict") == "REJECTED")
    if is_rejected:
        return None

    detail = item.get("detail") or item.get("raw") or {"description": desc}
    max_risk = 0
    combined_warnings: List[str] = []

    for cat, spec in matched_specs.items():
        if cat in inferred_cats:
            continue
        alloc_uah = price_uah * (part_medians_uah[cat] / sum_all_median)
        synthetic_item = dict(item)
        synthetic_item["price"] = alloc_uah
        synthetic_item["currency"] = "UAH"
        heur = detectors[cat].analyze_listing(synthetic_item, detail, spec)
        if not is_approved and heur.get("red_flags"):
            return None
        r_score = 0 if is_approved else int(heur.get("risk_score", 0))
        if r_score > max_risk:
            max_risk = r_score
        for w in heur.get("warnings", []):
            if w not in combined_warnings:
                combined_warnings.append(w)

    ev = {
        "risk_score": max_risk,
        "red_flags": [],
        "warnings": combined_warnings,
        "audit": audit_rec,
        "is_ai_approved": is_approved,
        "is_ai_rejected": False,
    }

    is_n, cond, cond_lbl = _extract_item_condition(item)
    is_secure = bool(
        item.get("is_secure_deal", item.get("has_buyer_protection", item.get("has_olx_delivery", False)))
    )
    # Positive discount_pct means cheaper than sum of market medians (consistent with compute_market_discount_pct)
    bundle_discount_pct = round(((sum_all_median - price_uah) / sum_all_median) * 100.0, 1)

    included_cats = [c for c in ("gpu", "cpu", "mobo", "ram", "psu") if c in matched_specs]
    primary_cat = _primary_category_for_bundle(set(included_cats), is_prebuilt)
    bundle_label = (
        "PREBUILT PC"
        if is_prebuilt
        else "BUNDLE: " + "+".join(c.upper() for c in included_cats)
    )
    bundle_id = str(item.get("id") or item.get("url") or title)

    # 9. Build normalized component dicts matching build_optimizer's exact candidate schema
    components: Dict[str, Dict[str, Any]] = {}
    for cat in included_cats:
        spec = dict(matched_specs[cat])
        share = part_medians_uah[cat] / sum_all_median
        alloc_uah = round(price_uah * share, 2)
        alloc_curr = round(bundle_price * share, 2)
        is_primary = cat == primary_cat
        comp_price = bundle_price if is_primary else 0.0

        # When a bundle states "16GB DDR4" or "32GB DDR5" without specifying "1 планкою",
        # default 16GB+ bundle RAM kits to dual-channel (2 sticks) unless single-stick is stated.
        if cat == "ram" and spec.get("module_count", 1) < 2 and spec.get("total_gb", 0) >= 16:
            if not re.search(
                r"\b(?:1\s*[xх×]\s*(?:16|32)|одн\w+\s+планк\w+|1\s+планк\w+)\b",
                combined,
                re.IGNORECASE,
            ):
                spec["module_count"] = 2

        cand: Dict[str, Any] = {
            "id": bundle_id,
            "bundle_id": bundle_id,
            "summary": item,
            "spec": spec,
            cat: spec,
            "model": spec["model"],
            "price": comp_price,
            "_price_uah": alloc_uah,
            "_allocated_price": alloc_curr,
            "bundle_price": bundle_price,
            "bundle_price_uah": price_uah,
            "currency": effective_curr,
            "discount_pct": bundle_discount_pct,
            "url": item.get("url", ""),
            "source": item.get("source", "olx.ua"),
            "is_secure_deal": is_secure,
            "deal_type": item.get("deal_type", "Secure Deal" if is_secure else "No Buyer Protection"),
            "is_new": is_n,
            "condition": cond,
            "condition_label": cond_lbl,
            "eval": ev,
            "heuristic": ev,
            "ai_eval": audit_rec,
            "is_bundle": True,
            "is_prebuilt": is_prebuilt,
            "is_bundle_primary": is_primary,
            "is_bundled_with": "PREBUILT" if is_prebuilt else primary_cat.upper(),
            "bundle_cats": included_cats,
            "bundle_label": bundle_label,
            "inferred_in_prebuilt": cat in inferred_cats,
        }

        if cat == "gpu":
            cand.update(
                {
                    "fps_1440p": spec["fps_1440p"],
                    "fps_1080p": spec["fps_1080p"],
                    "vram_gb": spec["vram_gb"],
                    "tdp_watts": spec.get("tdp_watts", 200),
                }
            )
        elif cat == "cpu":
            cand.update(
                {
                    "socket": spec["socket"],
                    "fps_gaming": spec["fps_gaming"],
                    "fps_1pct_low": spec.get("fps_1pct_low", round(spec["fps_gaming"] * 0.73, 1)),
                    "l3_cache_mb": spec.get("l3_cache_mb", 32),
                    "cb_r23_multi": spec.get("cb_r23_multi", spec["threads"] * 950),
                    "cores": spec["cores"],
                    "threads": spec["threads"],
                    "tdp_watts": spec.get("tdp_watts", 65),
                    "gaming_watts": spec.get("gaming_watts", 50),
                }
            )
        elif cat == "mobo":
            cand.update(
                {
                    "socket": spec["socket"],
                    "chipset": spec.get("chipset", "Generic"),
                    "ddr_type": spec["ddr_type"],
                    "vrm_tier": spec.get("vrm_tier", "B-Tier"),
                }
            )
        elif cat == "ram":
            cand.update(
                {
                    "gen": spec["generation"],
                    "total_gb": spec["total_gb"],
                    "speed_mhz": spec["speed_mhz"],
                }
            )
        elif cat == "psu":
            cand.update(
                {
                    "wattage": spec["wattage"],
                    "tier": spec["vrm_tier"],
                    "efficiency": spec["efficiency"],
                }
            )

        components[cat] = cand

    return {
        "id": bundle_id,
        "title": title,
        "url": item.get("url", ""),
        "price": bundle_price,
        "price_uah": price_uah,
        "discount_pct": bundle_discount_pct,
        "condition": cond,
        "is_new": is_n,
        "risk_score": max_risk,
        "is_prebuilt": is_prebuilt,
        "categories": included_cats,
        "primary_category": primary_cat,
        "bundle_label": bundle_label,
        "components": components,
    }


def extract_bundle_propositions(
    raw_by_cat: Dict[str, List[Dict[str, Any]]],
    effective_curr: str,
    profile: ModeProfile,
    budget_in_uah: float,
    core_budget: float,
    socket_filter: Optional[str] = None,
    min_threads: Optional[int] = None,
    min_gpu_fps: float = 0.0,
    re_audit: bool = False,
    excluded_categories: Optional[Set[str]] = None,
    locked_queries: Optional[Dict[str, str]] = None,
    max_bundles: int = 45,
) -> List[Dict[str, Any]]:
    """Scan raw category pools and return top-ranked bundle & prebuilt PC propositions.

    Deduplicates across categories by listing ID/URL, enforces buyer protection & mode
    gates on all included components, and prunes dominated bundles with identical specs.
    """
    detectors = {
        "gpu": GPUScamDetector(),
        "cpu": CPUScamDetector(),
        "mobo": MotherboardScamDetector(),
        "ram": RAMScamDetector(),
        "psu": PSUScamDetector(),
    }
    excluded = excluded_categories or set()
    locks = locked_queries or {}
    seen_keys: Set[str] = set()
    candidates: List[Dict[str, Any]] = []

    scan_order = ("prebuilt", "mobo", "cpu", "gpu", "ram", "psu")
    for source_cat in scan_order:
        raw_items = raw_by_cat.get(source_cat, [])
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("listings", [])
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            dedup_key = str(item.get("id") or item.get("url") or item.get("title", "")).strip()
            if not dedup_key or dedup_key in seen_keys:
                continue

            is_secure = bool(
                item.get(
                    "is_secure_deal",
                    item.get("has_buyer_protection", item.get("has_olx_delivery", False)),
                )
            )
            if (profile.require_delivery or getattr(profile, "require_secure_deal", True)) and not is_secure:
                continue

            bundle = extract_bundle_from_item(
                item,
                effective_curr=effective_curr,
                detectors=detectors,
                re_audit=re_audit,
                source_category=source_cat,
            )
            if not bundle:
                continue

            seen_keys.add(dedup_key)

            if bundle["price"] > core_budget:
                continue

            b_cats = set(bundle["categories"])
            if b_cats & excluded:
                if not (bundle["is_prebuilt"] and (b_cats & excluded) == {"psu"}):
                    continue

            comps = bundle["components"]

            # Check locked queries if user passed --gpu / --cpu / --mobo / --ram / --psu
            lock_ok = True
            for l_cat, l_q in locks.items():
                if l_q and l_cat in comps:
                    q_norm = l_q.strip().lower()
                    mod_l = str(comps[l_cat].get("model", "")).lower()
                    ttl_l = str(bundle.get("title", "")).lower()
                    tokens = [t for t in re.split(r"[\s\-_]+", q_norm) if t]
                    if not (q_norm in mod_l or q_norm in ttl_l or (tokens and all(t in mod_l or t in ttl_l for t in tokens))):
                        lock_ok = False
                        break
            if not lock_ok:
                continue

            # Socket & threads & GPU floor filters
            if socket_filter:
                c_comp = comps.get("cpu")
                m_comp = comps.get("mobo")
                if c_comp and c_comp["socket"].upper() != socket_filter.upper():
                    continue
                if m_comp and m_comp["socket"].upper() != socket_filter.upper():
                    continue
            if min_threads and "cpu" in comps:
                if comps["cpu"].get("threads", 0) < min_threads:
                    continue
            if min_gpu_fps > 0 and "gpu" in comps:
                if comps["gpu"].get("fps_1440p", 0) < min_gpu_fps:
                    continue

            # Enforce mode gate on each included component
            gate_ok = True
            for cat, comp in comps.items():
                if comp.get("inferred_in_prebuilt"):
                    continue
                if not _passes_bundle_part_gate(cat, comp, profile):
                    gate_ok = False
                    break
            if not gate_ok:
                continue

            candidates.append(bundle)

    # Deduplicate by identical (categories, model tuple), keeping the lowest-priced listing
    best_by_signature: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for b in candidates:
        sig = tuple((cat, b["components"][cat]["model"]) for cat in b["categories"])
        existing = best_by_signature.get(sig)
        if existing is None or (b["price"], b["risk_score"]) < (existing["price"], existing["risk_score"]):
            best_by_signature[sig] = b

    deduped = list(best_by_signature.values())

    def _bundle_rank_key(b: Dict[str, Any]) -> float:
        comps = b["components"]
        perf_bonus = 0.0
        if "gpu" in comps:
            perf_bonus += comps["gpu"]["fps_1440p"] * 0.55
        if "cpu" in comps:
            perf_bonus += comps["cpu"]["fps_gaming"] * 0.35
        if "ram" in comps:
            perf_bonus += min(32, comps["ram"]["total_gb"]) * 0.25
        part_bonus = len(b["categories"]) * 4.0
        discount_bonus = max(-25.0, min(45.0, b["discount_pct"])) * 1.1
        return perf_bonus + part_bonus + discount_bonus - b["risk_score"] * 0.25

    deduped.sort(key=_bundle_rank_key, reverse=True)
    return deduped[:max_bundles]
