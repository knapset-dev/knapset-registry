import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_CORE_CANDIDATES = (REPO_ROOT.parent / "omniforge", REPO_ROOT.parent / "hardware-market-intelligence")
CORE_ROOT = next((p for p in _CORE_CANDIDATES if p.exists()), _CORE_CANDIDATES[0])
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))
MODULES_DIR = REPO_ROOT / "modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
import extensions  # noqa: E402
_ext_dir = str(MODULES_DIR / "extensions")
extensions.__path__ = [_ext_dir] + [p for p in extensions.__path__ if p != _ext_dir]

from ai_providers import extract_json_object, list_provider_names, normalize_provider_name
from audit_ledger import AuditLedger
from extensions.pc.build_optimizer import (
    matches_lock_query,
    parse_target_query,
    resolve_owned_cpu,
    resolve_owned_gpu,
    resolve_owned_mobo,
    resolve_owned_psu,
    resolve_owned_ram,
    run_build_optimizer,
    synthesize_builds,
)
from extensions.pc.cpu_database import CPU_DATABASE, identify_cpu
from extensions.pc.cpu_scam_detector import CPUScamDetector
from extensions.pc.gpu_database import identify_gpu
from extensions.pc.gpu_scam_detector import GPUScamDetector
from extensions.pc.mobo_database import identify_motherboard
from extensions.pc.mobo_scam_detector import MotherboardScamDetector
from extensions.pc.modes import (
    compute_effective_build_fps,
    compute_market_discount_pct,
    get_mode_names,
    is_listing_disqualified,
    parse_weights_string,
    resolve_mode,
    score_build,
    score_component,
)
from extensions.pc.psu_database import identify_psu
from extensions.pc.psu_scam_detector import PSUScamDetector
from extensions.pc.ram_database import identify_ram
from extensions.pc.ram_scam_detector import RAMScamDetector
from extensions.pc.system_ai_inspector import SystemAIInspector


def _make_sample_item(item_id: str, title: str, price: float) -> dict:
    return {
        "id": item_id,
        "title": title,
        "price": float(price),
        "has_buyer_protection": True,
        "has_olx_delivery": True,
        "photos_count": 5,
        "description": "Працює відмінно, перевірено, будь-які тести, без дефектів.",
        "url": f"https://olx.ua/{item_id}",
        "source": "olx.ua",
    }


SAMPLE_HERMETIC_PC_POOL = {
    "gpu": [
        _make_sample_item("g1", "ASUS TUF RTX 3080 10GB", 15000),
        _make_sample_item("g2", "MSI RTX 3060 12GB", 8000),
        _make_sample_item("g3", "Sapphire RX 580 8GB", 1800),
        _make_sample_item("g4", "Palit GTX 1060 6GB", 2000),
    ],
    "cpu": [
        _make_sample_item("c1", "AMD Ryzen 7 7800X3D AM5", 12000),
        _make_sample_item("c2", "AMD Ryzen 5 7500F AM5", 5000),
        _make_sample_item("c3", "AMD Ryzen 5 5600 AM4", 3500),
        _make_sample_item("c4", "Intel Core i5-12400F LGA1700", 3800),
        _make_sample_item("c5", "Intel Core i7-8700 LGA1151v2", 3000),
        _make_sample_item("c6", "Intel Xeon E5-2680 v4 LGA2011-v3", 500),
        _make_sample_item("c7", "Intel Core i3-8100 LGA1151v2", 500),
    ],
    "mobo": [
        _make_sample_item("m1", "MSI B650 Tomahawk AM5 DDR5", 4500),
        _make_sample_item("m2", "Gigabyte B550M AM4 DDR4", 2500),
        _make_sample_item("m3", "ASUS Prime B660 LGA1700 DDR4", 3000),
        _make_sample_item("m4", "Biostar H310 LGA1151v2 DDR4", 1000),
        _make_sample_item("m5", "Generic X99-M LGA2011-v3 DDR4", 1100),
        _make_sample_item("m6", "Generic H110 LGA1151 DDR4", 600),
    ],
    "ram": [
        _make_sample_item("r1", "Kingston 32GB (2x16GB) DDR5 6000MHz", 14000),
        _make_sample_item("r2", "Kingston 16GB (2x8GB) DDR4 3200MHz", 2000),
        _make_sample_item("r3", "Generic 8GB (2x4GB) DDR4 2666MHz", 1000),
    ],
    "psu": [
        _make_sample_item("p1", "Seasonic Focus 750W Gold", 2500),
        _make_sample_item("p2", "DeepCool PK650D 650W Bronze", 1500),
        _make_sample_item("p3", "FSP 500W 80+", 600),
    ],
}


class TestHardwareDatabases(unittest.TestCase):
    def test_gpu_database_2026_models_and_seo_spam_defense(self):
        rtx50 = identify_gpu("Відеокарта ASUS TUF GeForce RTX 5070 Ti 16GB GDDR7")
        self.assertIsNotNone(rtx50)
        self.assertEqual(rtx50["model"], "RTX 5070 TI")
        self.assertEqual(rtx50["vram_gb"], 16)

        rx9070 = identify_gpu("Sapphire Pulse AMD Radeon RX 9070 XT 16GB")
        self.assertIsNotNone(rx9070)
        self.assertEqual(rx9070["model"], "RX 9070 XT")

        b580 = identify_gpu("Intel Arc B580 Limited Edition 12GB")
        self.assertIsNotNone(b580)
        self.assertEqual(b580["model"], "ARC B580")

        # Left-to-right SEO keyword stuffing defense
        seo_ad = identify_gpu("Продам Sapphire RX 580 8GB Nitro+ (не GTX 1070 1080Ti RTX 3060)")
        self.assertIsNotNone(seo_ad)
        self.assertEqual(seo_ad["model"], "RX 580")

        # Stripped donor board exclusion
        donor = identify_gpu("Донор плата RTX 3080 No GPU, VRAM на запчастини")
        self.assertIsNone(donor)

    def test_cpu_database_2026_models_and_sockets(self):
        x3d = identify_cpu("Процесор AMD Ryzen 7 9800X3D AM5 Tray")
        self.assertIsNotNone(x3d)
        self.assertEqual(x3d["model"], "RYZEN 7 9800X3D")
        self.assertEqual(x3d["socket"], "AM5")
        self.assertTrue(x3d.get("is_x3d"))

        ultra = identify_cpu("Intel Core Ultra 7 265K LGA1851 Box")
        self.assertIsNotNone(ultra)
        self.assertEqual(ultra["model"], "CORE ULTRA 7 265K")
        self.assertEqual(ultra["socket"], "LGA1851")

        # Left-to-right SEO spam defense
        seo_cpu = identify_cpu("AMD Ryzen 5 3600 AM4 (аналог 5600X 5800X3D i5-12400F)")
        self.assertIsNotNone(seo_cpu)
        self.assertEqual(seo_cpu["model"], "RYZEN 5 3600")

        # Electrical socket separation: 9th gen vs 7th gen Intel
        i7_9700k = identify_cpu("Intel Core i7-9700K")
        i7_7700k = identify_cpu("Intel Core i7-7700K")
        self.assertEqual(i7_9700k["socket"], "LGA1151v2")
        self.assertEqual(i7_7700k["socket"], "LGA1151")

    def test_mobo_database_sockets_and_2026_chipsets(self):
        b850 = identify_motherboard("Материнська плата MSI MAG B850 Tomahawk WiFi AM5")
        self.assertIsNotNone(b850)
        self.assertEqual(b850["socket"], "AM5")
        self.assertEqual(b850["ddr_type"], "DDR5")

        z390 = identify_motherboard("ASUS Prime Z390-A")
        z270 = identify_motherboard("MSI Z270 Gaming Pro")
        x99 = identify_motherboard("Huananzhi X99-TF")
        self.assertEqual(z390["socket"], "LGA1151v2")
        self.assertEqual(z270["socket"], "LGA1151")
        self.assertEqual(x99["socket"], "LGA2011-v3")

    def test_ram_database_combo_notations_and_form_factors(self):
        kit_std = identify_ram("Kingston Fury DDR5 32GB (2x16GB) 6000MHz CL30")
        kit_rev = identify_ram("G.Skill Ripjaws DDR4 32GB (16x2) 3600MHz CL16")
        self.assertIsNotNone(kit_std)
        self.assertIsNotNone(kit_rev)
        self.assertEqual((kit_std["total_gb"], kit_std["module_count"]), (32, 2))
        self.assertEqual((kit_rev["total_gb"], kit_rev["module_count"]), (32, 2))
        self.assertEqual(kit_std["form_factor"], "UDIMM")

        sodimm = identify_ram("Samsung 16GB DDR4 3200MHz SO-DIMM для ноутбука")
        ecc = identify_ram("Серверна пам'ять Samsung 32GB DDR4 ECC REG 2666V")
        self.assertEqual(sodimm["form_factor"], "SODIMM")
        self.assertEqual(ecc["form_factor"], "ECC_REG")

    def test_psu_database_tiers_and_atx3(self):
        tier_a = identify_psu("Блок живлення Seasonic Focus GX-850 850W 80+ Gold ATX 3.0 12VHPWR")
        tier_d = identify_psu("Блок питания Aerocool VX Plus 600W")
        self.assertIsNotNone(tier_a)
        self.assertIsNotNone(tier_d)
        self.assertEqual(tier_a["vrm_tier"], "Tier A")
        self.assertTrue(tier_a["has_12vhpwr"])
        self.assertEqual(tier_d["vrm_tier"], "Tier D")


class TestScamDetectorsAndLedger(unittest.TestCase):
    def test_all_five_scam_detectors_flag_critical_defects(self):
        # 1. Dead RAM must emit hard red_flags (not just soft warnings!)
        ram_spec = identify_ram("Kingston 16GB DDR4 3200MHz")
        ram_res = RAMScamDetector().analyze_listing(
            {"title": "DDR4 16GB на запчастини", "price": 400, "has_olx_delivery": True},
            {"description": "Планка не стартує, синій екран BSOD, помилки в MemTest86"},
            ram_spec,
        )
        self.assertTrue(len(ram_res["red_flags"]) > 0, "Dead/BSOD RAM must trigger hard red_flags")

        # 2. GPU artifacts / Code 43 & defective wording
        gpu_spec = identify_gpu("RTX 3070 8GB")
        gpu_res = GPUScamDetector().analyze_listing(
            {"title": "RTX 3070 під ремонт", "price": 4500, "has_olx_delivery": True},
            {"description": "Помилка код 43, артефакти на екрані."},
            gpu_spec,
        )
        self.assertTrue(len(gpu_res["red_flags"]) > 0)

        # Real-world OLX defect case: 'Несправна відеокарта... куллери крутяться, зобраення немає'
        gpu_broken_3090 = GPUScamDetector().analyze_listing(
            {"title": "Несправна відеокарта MSI GeForce RTX 3090 GAMING X TRIO 24G", "price": 16000, "has_olx_delivery": True},
            {"description": "Продаю не справну відеокарту. В один момент потухла і все. Куллери крутяться, зобраення немає. Заніс в сервіс в будинку, не розібрались. Без претензій та повернень, рподаю як є"},
            identify_gpu("RTX 3090"),
        )
        self.assertTrue(len(gpu_broken_3090["red_flags"]) >= 2)
        self.assertEqual(gpu_broken_3090["risk_score"], 100)

        # Real-world OLX defect case: Code 43 / driver failure / intermittent signal
        gpu_code43 = GPUScamDetector().analyze_listing(
            {"title": "RTX 3090 MSI TRIO GAME 384 bit 24 gb неустанавлюетса драйвера  код 43", "price": 14000, "has_olx_delivery": True},
            {"description": "RTX 3090 MSI TRIO GAME 384 bit 24 gb неустанавлюетса драйвера  код 43, картинка то есть то нету, когда картинка есть неустанавливаютса драйвера пишет код 43,все детали на месте ничего не ремонтирива"},
            identify_gpu("RTX 3090"),
        )
        self.assertTrue(len(gpu_code43["red_flags"]) >= 3)
        self.assertEqual(gpu_code43["risk_score"], 100)

        # Real-world OLX defect case: 'потребує діагностики', 'працює нестабільно буває зникає зображення', 'условно працює'
        gpu_diag_1080ti = GPUScamDetector().analyze_listing(
            {"title": "Відеокарта Zotac GTX 1080 Ti AMP! Extreme 11GB — потребує діагностики!", "price": 5499, "has_olx_delivery": True},
            {"description": "Стан: зовні гарний, усі три вентилятори обертаються. Перевірялась на стенді, запускається й визначається, але працює нестабільно буває зникає зображення. Працює лише на стенді. Условно працює."},
            identify_gpu("GTX 1080 TI"),
        )
        self.assertTrue(len(gpu_diag_1080ti["red_flags"]) >= 3)
        self.assertEqual(gpu_diag_1080ti["risk_score"], 100)

        # 3. CPU dead / bent pins
        cpu_spec = identify_cpu("Ryzen 5 5600X")
        cpu_res = CPUScamDetector().analyze_listing(
            {"title": "Ryzen 5 5600X", "price": 1200, "has_olx_delivery": True},
            {"description": "Відламані ніжки, не стартує комп'ютер."},
            cpu_spec,
        )
        self.assertTrue(len(cpu_res["red_flags"]) > 0)

        # 4. Motherboard bent socket pins
        mobo_spec = identify_motherboard("ASUS TUF B550-Plus")
        mobo_res = MotherboardScamDetector().analyze_listing(
            {"title": "ASUS B550", "price": 1000, "has_olx_delivery": True},
            {"description": "Погнуті ніжки сокета, не працює перший слот ОЗУ."},
            mobo_spec,
        )
        self.assertTrue(len(mobo_res["red_flags"]) > 0)

        # 5. PSU missing modular cables
        psu_spec = identify_psu("Corsair RM750x 750W Gold Modular")
        psu_res = PSUScamDetector().analyze_listing(
            {"title": "Corsair RM750x", "price": 900, "has_olx_delivery": True},
            {"description": "Продається тільки сам блок без модульних кабелів."},
            psu_spec,
        )
        self.assertTrue(len(psu_res["red_flags"]) > 0)

    def test_audit_ledger_sha256_invalidation_and_batch_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "audit_ledger.json"
            led = AuditLedger(ledger_path=ledger_file)
            led.record_batch([
                {
                    "offer_id": "555",
                    "category": "gpu",
                    "verdict": "APPROVED",
                    "confidence_score": 91,
                    "reasons": ["Clean seals, FurMark 64C"],
                    "title": "RTX 4070 Super",
                    "price": 22500.0,
                    "description": "Повний комплект, пломба.",
                    "provider": "gemini",
                }
            ])

            hit = led.get_audit("555", title="RTX 4070 Super", price=22500.0, description="Повний комплект, пломба.")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["verdict"], "APPROVED")

            # Seller changes description to confess defect -> hash mismatch must invalidate cache!
            invalidated = led.get_audit("555", title="RTX 4070 Super", price=22500.0, description="З'явились артефакти")
            self.assertIsNone(invalidated)

            # Seller turns off OLX delivery -> hash mismatch must invalidate cache!
            invalidated_delivery = led.get_audit("555", title="RTX 4070 Super", price=22500.0, description="Повний комплект, пломба.", has_delivery=False)
            self.assertIsNone(invalidated_delivery)

            # Legacy entry written without has_delivery field
            led._cache["777"] = {
                "id": "777",
                "verdict": "REJECTED",
                "confidence_score": 98,
                "title": "Legacy Card",
                "price": 5000.0,
                "hash": hashlib.sha256("Legacy Card|5000.00|Some legacy desc".encode("utf-8")).hexdigest()[:16],
            }
            hit_legacy = led.get_audit("777", title="Legacy Card", price=5000.0, description="Some legacy desc", has_delivery=True)
            self.assertIsNotNone(hit_legacy)
            self.assertEqual(hit_legacy["verdict"], "REJECTED")

            # But if delivery is toggled off, legacy entry is invalidated!
            invalidated_legacy = led.get_audit("777", title="Legacy Card", price=5000.0, description="Some legacy desc", has_delivery=False)
            self.assertIsNone(invalidated_legacy)


class TestAIProvidersModesAndBuildOptimizer(unittest.TestCase):
    def test_ai_provider_json_extraction_and_aliases(self):
        self.assertEqual(normalize_provider_name("claude"), "anthropic")
        self.assertEqual(normalize_provider_name("gpt"), "openai")
        self.assertEqual(normalize_provider_name("lmstudio"), "openai-compat")
        self.assertIn("gemini", list_provider_names())
        self.assertIn("ollama", list_provider_names())

        raw_with_think = """
        <think>Let me inspect the Ukrainian description carefully...</think>
        Here is the evaluation:
        ```json
        {
          "evaluations": [
            {"id": 1, "verdict": "APPROVED", "confidence": 89, "reasons": ["Clean GPU"],}
          ],
        }
        ```
        """
        parsed = extract_json_object(raw_with_think)
        self.assertEqual(parsed["evaluations"][0]["verdict"], "APPROVED")
        self.assertEqual(parsed["evaluations"][0]["confidence"], 89)

    def test_all_15_modes_and_custom_weights(self):
        mode_names = get_mode_names()
        for expected in (
            "best", "sweet-spot", "value", "safe", "max-perf", "deal-hunter",
            "esports", "efficiency", "future-proof", "ai-workstation", "budget-king",
            "custom",
        ):
            self.assertIn(expected, mode_names)
            prof = resolve_mode(expected, weights_override="perf=6,safety=4" if expected == "custom" else None)
            self.assertTrue(len(prof.weights) > 0)

        w = parse_weights_string("perf=3, value=1")
        self.assertAlmostEqual(w["perf"], 0.75)
        self.assertAlmostEqual(w["value"], 0.25)

        clean_gpu = {
            "price": 16000.0,
            "gpu": identify_gpu("RX 6900 XT"),
            "heuristic": {"risk_score": 10, "red_flags": [], "warnings": []},
        }
        defect_gpu = {
            "price": 8000.0,
            "gpu": identify_gpu("RX 6900 XT"),
            "heuristic": {"risk_score": 85, "red_flags": ["Artifacting"], "warnings": []},
        }
        prof_best = resolve_mode("best")
        self.assertGreater(score_component("gpu", clean_gpu, prof_best), 50.0)
        self.assertLess(score_component("gpu", defect_gpu, prof_best), -900_000.0)
        self.assertTrue(is_listing_disqualified(defect_gpu["heuristic"], None))

    def test_cpu_threads_not_ecores_scoring(self):
        # Ryzen 9 7900X (12c / 24t) must outscore Intel i5-14600K (14c / 20t with 8 E-cores) on pure thread weight
        r9_24t = {
            "price": 10000.0,
            "cpu": identify_cpu("Ryzen 9 7900X"),
            "heuristic": {"risk_score": 10, "red_flags": [], "warnings": []},
        }
        i5_ecore_20t = {
            "price": 10000.0,
            "cpu": identify_cpu("Core i5-14600K"),
            "heuristic": {"risk_score": 10, "red_flags": [], "warnings": []},
        }
        prof_threads = resolve_mode("custom", weights_override="threads=1.0")
        self.assertGreater(
            score_component("cpu", r9_24t, prof_threads),
            score_component("cpu", i5_ecore_20t, prof_threads),
        )

    def test_build_optimizer_dimm_and_psu_transient_physics(self):
        g_spec = identify_gpu("RX 6900 XT")
        c_spec = identify_cpu("Ryzen 7 7800X3D")
        m_itx_spec = identify_motherboard("ASUS ROG Strix B650E-I Gaming WiFi ITX")
        r_8stick_spec = identify_ram("Crucial DDR5 64GB (8x8GB) 5200MHz")
        r_2stick_spec = identify_ram("Kingston Fury DDR5 32GB (2x16GB) 6000MHz CL30")
        p_weak_spec = identify_psu("Seasonic 550W Bronze")
        p_strong_spec = identify_psu("Seasonic Focus 750W Gold")

        clean_ev = {"risk_score": 8, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}

        gpus = [{
            "id": "g1", "model": g_spec["model"], "spec": g_spec, "gpu": g_spec,
            "price": 16000.0, "fps_1440p": g_spec["fps_1440p"], "fps_1080p": g_spec["fps_1080p"],
            "vram_gb": g_spec["vram_gb"], "tdp_watts": g_spec["tdp_watts"],
            "discount_pct": compute_market_discount_pct(16000.0, g_spec), "url": "http://g1", "eval": clean_ev,
        }]
        cpus = [{
            "id": "c1", "model": c_spec["model"], "socket": "AM5", "spec": c_spec, "cpu": c_spec,
            "price": 12000.0, "fps_gaming": c_spec["fps_gaming"], "cores": 8, "threads": 16,
            "tdp_watts": c_spec["tdp_watts"], "discount_pct": 10.0, "url": "http://c1", "eval": clean_ev,
        }]
        mobos = [{
            "id": "m1", "model": m_itx_spec["model"], "socket": "AM5", "chipset": "B650E",
            "ddr_type": "DDR5", "vrm_tier": "S-Tier", "spec": m_itx_spec, "mobo": m_itx_spec,
            "price": 6500.0, "discount_pct": 10.0, "url": "http://m1", "eval": clean_ev,
        }]
        rams = [
            {
                "id": "r_8x", "model": "Crucial", "gen": "DDR5", "total_gb": 64, "speed_mhz": 5200,
                "spec": r_8stick_spec, "ram": r_8stick_spec, "price": 2500.0, "discount_pct": 25.0,
                "url": "http://r8", "eval": clean_ev,
            },
            {
                "id": "r_2x", "model": "Kingston", "gen": "DDR5", "total_gb": 32, "speed_mhz": 6000,
                "spec": r_2stick_spec, "ram": r_2stick_spec, "price": 3600.0, "discount_pct": 10.0,
                "url": "http://r2", "eval": clean_ev,
            },
        ]
        psus = [
            {
                "id": "p_550", "model": p_weak_spec["model"], "wattage": 550, "tier": "Tier A",
                "efficiency": "Bronze", "spec": p_weak_spec, "psu": p_weak_spec,
                "price": 1200.0, "discount_pct": 15.0, "url": "http://p550", "eval": clean_ev,
            },
            {
                "id": "p_750", "model": p_strong_spec["model"], "wattage": 750, "tier": "Tier A",
                "efficiency": "Gold", "spec": p_strong_spec, "psu": p_strong_spec,
                "price": 2200.0, "discount_pct": 10.0, "url": "http://p750", "eval": clean_ev,
            },
        ]

        builds = synthesize_builds(
            gpus, cpus, mobos, rams, psus,
            budget=45000.0, profile=resolve_mode("best"), top_n=3,
        )
        self.assertEqual(len(builds), 1)
        b = builds[0]
        # ITX 2-DIMM board MUST reject 8-stick kit and select 2x16GB kit!
        self.assertEqual(b["ram"]["id"], "r_2x")
        # 300W RX 6900 XT MUST reject 550W PSU and select 750W PSU!
        self.assertEqual(b["psu"]["id"], "p_750")
        self.assertGreater(score_build(b, 45000.0, resolve_mode("best")), 70.0)

    def test_bottleneck_rejects_8700k_with_3080ti(self):
        g_spec = identify_gpu("RTX 3080 Ti 12GB")
        c_old = identify_cpu("Core i7-8700K")
        c_mod = identify_cpu("Ryzen 5 7500F")
        m_old = identify_motherboard("Gigabyte Z390-M")
        m_mod = identify_motherboard("ASUS TUF B650-Plus")
        r_d4 = identify_ram("Kingston 16GB (2x8GB) DDR4 3200MHz")
        r_d5 = identify_ram("Kingston Fury DDR5 32GB (2 по 16) 6000MHz")
        p_spec = identify_psu("Seasonic Prime 750W Titanium")

        # Verify '2 по 16' Ukrainian dual-channel notation & mobile/dummy exclusions
        self.assertEqual((r_d5["total_gb"], r_d5["module_count"]), (32, 2))
        self.assertIsNone(identify_ram("Corsair Vengeance RGB DDR5 32GB 7200MHz Муляж"))
        self.assertIsNone(identify_cpu("Процесор Intel Core i7-13650hx (Q1LR)"))

        # Verify calibrated bottleneck FPS math
        eff_old_1440, _, ratio_old = compute_effective_build_fps(
            g_spec["fps_1440p"], g_spec["fps_1080p"], c_old["fps_gaming"]
        )
        eff_mod_1440, _, ratio_mod = compute_effective_build_fps(
            g_spec["fps_1440p"], g_spec["fps_1080p"], c_mod["fps_gaming"]
        )
        self.assertLess(ratio_old, 0.85)
        self.assertGreater(ratio_mod, 1.00)
        self.assertLess(eff_old_1440, eff_mod_1440 - 10.0)

        clean_ev = {"risk_score": 5, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}
        gpu_item = {
            "id": "g_3080ti", "model": g_spec["model"], "spec": g_spec, "gpu": g_spec,
            "price": 17000.0, "fps_1440p": g_spec["fps_1440p"], "fps_1080p": g_spec["fps_1080p"],
            "vram_gb": 12, "tdp_watts": 350, "discount_pct": 23.0, "url": "http://g", "eval": clean_ev,
        }
        cpu_8700k = {
            "id": "c_8700k", "model": c_old["model"], "socket": "LGA1151v2", "spec": c_old, "cpu": c_old,
            "price": 2500.0, "fps_gaming": c_old["fps_gaming"], "cores": 6, "threads": 12,
            "tdp_watts": 95, "discount_pct": 40.0, "url": "http://c_old", "eval": clean_ev,
        }
        cpu_7500f = {
            "id": "c_7500f", "model": c_mod["model"], "socket": "AM5", "spec": c_mod, "cpu": c_mod,
            "price": 5500.0, "fps_gaming": c_mod["fps_gaming"], "cores": 6, "threads": 12,
            "tdp_watts": 65, "discount_pct": 15.0, "url": "http://c_mod", "eval": clean_ev,
        }
        mobo_z390 = {
            "id": "m_z390", "model": m_old["model"], "socket": "LGA1151v2", "chipset": "Z390",
            "ddr_type": "DDR4", "vrm_tier": "A-Tier", "spec": m_old, "mobo": m_old,
            "price": 2000.0, "discount_pct": 40.0, "url": "http://m_old", "eval": clean_ev,
        }
        mobo_b650 = {
            "id": "m_b650", "model": m_mod["model"], "socket": "AM5", "chipset": "B650",
            "ddr_type": "DDR5", "vrm_tier": "A-Tier", "spec": m_mod, "mobo": m_mod,
            "price": 4500.0, "discount_pct": 20.0, "url": "http://m_mod", "eval": clean_ev,
        }
        ram_16 = {
            "id": "r_d4", "model": "Kingston", "gen": "DDR4", "total_gb": 16, "speed_mhz": 3200,
            "spec": r_d4, "ram": r_d4, "price": 1100.0, "discount_pct": 20.0, "url": "http://r4", "eval": clean_ev,
        }
        ram_32 = {
            "id": "r_d5", "model": "Kingston", "gen": "DDR5", "total_gb": 32, "speed_mhz": 6000,
            "spec": r_d5, "ram": r_d5, "price": 11000.0, "discount_pct": 0.0, "url": "http://r5", "eval": clean_ev,
        }
        psu_750 = {
            "id": "p_750", "model": p_spec["model"], "wattage": 750, "tier": "Tier A",
            "efficiency": "Titanium", "spec": p_spec, "psu": p_spec,
            "price": 1600.0, "discount_pct": 30.0, "url": "http://p", "eval": clean_ev,
        }

        prof_sweet = resolve_mode("sweet-spot")
        bad_build = {
            "gpu": gpu_item, "cpu": cpu_8700k, "mobo": mobo_z390, "ram": ram_16, "psu": psu_750,
            "total_cost": 24200.0,
        }
        good_build = {
            "gpu": gpu_item, "cpu": cpu_7500f, "mobo": mobo_b650, "ram": ram_32, "psu": psu_750,
            "total_cost": 39600.0,
        }
        self.assertGreater(
            score_build(good_build, 46000.0, prof_sweet),
            score_build(bad_build, 46000.0, prof_sweet) + 50.0,
        )

        builds = synthesize_builds(
            [gpu_item], [cpu_8700k, cpu_7500f], [mobo_z390, mobo_b650], [ram_16, ram_32], [psu_750],
            budget=46000.0, profile=prof_sweet, top_n=3,
        )
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0]["cpu"]["id"], "c_7500f")

    def test_ram_16gb_not_overweighted_in_gaming_modes(self):
        g_spec = identify_gpu("RX 6900 XT")
        c_spec = identify_cpu("Ryzen 5 9600X")
        m_spec = identify_motherboard("MSI B850")
        r_16 = identify_ram("Kingston Fury DDR5 16GB (2x8GB) 5600MHz")
        r_32 = identify_ram("Kingston Fury DDR5 32GB (2x16GB) 5600MHz")
        p_spec = identify_psu("Seasonic 750W Gold")
        clean_ev = {"risk_score": 4, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}

        base_parts = {
            "gpu": {"id": "g", "model": g_spec["model"], "spec": g_spec, "gpu": g_spec, "price": 16000.0,
                    "fps_1440p": 91.0, "fps_1080p": 114.0, "vram_gb": 16, "tdp_watts": 300, "discount_pct": 20.0, "eval": clean_ev},
            "cpu": {"id": "c", "model": c_spec["model"], "socket": "AM5", "spec": c_spec, "cpu": c_spec, "price": 6500.0,
                    "fps_gaming": 199.0, "cores": 6, "threads": 12, "tdp_watts": 65, "discount_pct": 25.0, "eval": clean_ev},
            "mobo": {"id": "m", "model": m_spec["model"], "socket": "AM5", "chipset": "B850", "ddr_type": "DDR5",
                     "vrm_tier": "A-Tier", "spec": m_spec, "mobo": m_spec, "price": 4500.0, "discount_pct": 20.0, "eval": clean_ev},
            "psu": {"id": "p", "model": p_spec["model"], "wattage": 750, "tier": "Tier A", "efficiency": "Gold",
                    "spec": p_spec, "psu": p_spec, "price": 1800.0, "discount_pct": 15.0, "eval": clean_ev},
        }
        ram16_item = {"id": "r16", "model": "Kingston", "gen": "DDR5", "total_gb": 16, "speed_mhz": 5600,
                      "spec": r_16, "ram": r_16, "price": 5000.0, "discount_pct": 0.0, "eval": clean_ev}
        ram32_expensive = {"id": "r32", "model": "Kingston", "gen": "DDR5", "total_gb": 32, "speed_mhz": 5600,
                           "spec": r_32, "ram": r_32, "price": 14000.0, "discount_pct": 0.0, "eval": clean_ev}

        build_16 = {**base_parts, "ram": ram16_item, "total_cost": 33800.0}
        build_32 = {**base_parts, "ram": ram32_expensive, "total_cost": 42800.0}

        # Gaming sweet-spot prefers 16GB at 5k over blowing 14k (30% of budget) on 32GB
        self.assertGreater(
            score_build(build_16, 46000.0, resolve_mode("sweet-spot")),
            score_build(build_32, 46000.0, resolve_mode("sweet-spot")),
        )
        # Workstation / future-proof (min_ram_gb=32) still prefers 32GB
        self.assertGreater(
            score_build(build_32, 46000.0, resolve_mode("future-proof")),
            score_build(build_16, 46000.0, resolve_mode("future-proof")),
        )

        # Single-channel 1x16GB RAM MUST be blocked in synthesize_builds in favor of 2x8GB dual-channel
        r_single_spec = identify_ram("Crucial DDR5 16GB 5600MHz", "Одна планка 16 ГБ")
        self.assertEqual(r_single_spec["module_count"], 1)
        ram16_single = {
            "id": "r16_1x", "model": "Crucial", "gen": "DDR5", "total_gb": 16, "speed_mhz": 5600,
            "spec": r_single_spec, "ram": r_single_spec, "price": 3500.0, "discount_pct": 30.0, "url": "http://r1", "eval": clean_ev,
        }
        ram16_dual = {**ram16_item, "url": "http://r2"}
        builds = synthesize_builds(
            [{**base_parts["gpu"], "url": "http://g"}],
            [{**base_parts["cpu"], "url": "http://c"}],
            [{**base_parts["mobo"], "url": "http://m"}],
            [ram16_single, ram16_dual],
            [{**base_parts["psu"], "url": "http://p"}],
            budget=46000.0, profile=resolve_mode("sweet-spot"), top_n=3,
        )
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0]["ram"]["id"], "r16")
        self.assertEqual(builds[0]["ram"]["spec"]["module_count"], 2)

    def test_x3d_gaming_dominance_and_monolithic_apu_calibration(self):
        # 1. Authoritative gaming hierarchy: 9800X3D > 7800X3D > 9700X > 7500F > 8700F (cut-down 16MB L3)
        c_9800x3d = CPU_DATABASE["RYZEN 7 9800X3D"]
        c_7800x3d = CPU_DATABASE["RYZEN 7 7800X3D"]
        c_9700x = CPU_DATABASE["RYZEN 7 9700X"]
        c_7500f = CPU_DATABASE["RYZEN 5 7500F"]
        c_8700f = CPU_DATABASE["RYZEN 7 8700F"]
        c_8400f = CPU_DATABASE["RYZEN 5 8400F"]

        self.assertGreater(c_9800x3d["fps_gaming"], c_7800x3d["fps_gaming"])
        self.assertGreater(c_7800x3d["fps_gaming"], c_9700x["fps_gaming"])
        self.assertGreater(c_9700x["fps_gaming"], c_7500f["fps_gaming"])
        self.assertGreater(c_7500f["fps_gaming"], c_8700f["fps_gaming"])
        self.assertGreater(c_8700f["fps_gaming"], c_8400f["fps_gaming"])

        # 2. X3D 1% lows and L3 cache size vs cut-down monolithic chips
        self.assertEqual(c_7800x3d["l3_cache_mb"], 96)
        self.assertEqual(c_8700f["l3_cache_mb"], 16)
        self.assertEqual(c_8700f["pcie_lanes_gpu"], 8)
        self.assertGreater(c_7800x3d["fps_1pct_low"], 175.0)
        self.assertLess(c_8700f["fps_1pct_low"], 115.0)

        # 3. 7800X3D real gaming watts (54W) makes it more efficient than standard 65W/105W parts
        self.assertEqual(c_7800x3d["gaming_watts"], 54)
        clean_ev = {"risk_score": 5, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}
        item_7800x3d = {
            "price": 12500.0,
            "cpu": c_7800x3d,
            "spec": c_7800x3d,
            "heuristic": clean_ev,
        }
        item_14700k = {
            "price": 13000.0,
            "cpu": CPU_DATABASE["CORE I7-14700K"],
            "spec": CPU_DATABASE["CORE I7-14700K"],
            "heuristic": clean_ev,
        }
        prof_eff = resolve_mode("efficiency")
        self.assertGreater(
            score_component("cpu", item_7800x3d, prof_eff),
            score_component("cpu", item_14700k, prof_eff),
        )

        # 4. In esports mode, 7800X3D outscores 9600X due to 182 FPS 1% low frame-time floor
        item_9600x = {
            "price": 8500.0,
            "cpu": CPU_DATABASE["RYZEN 5 9600X"],
            "spec": CPU_DATABASE["RYZEN 5 9600X"],
            "heuristic": clean_ev,
        }
        prof_esports = resolve_mode("esports")
        self.assertGreater(
            score_component("cpu", item_7800x3d, prof_esports),
            score_component("cpu", item_9600x, prof_esports),
        )

    def test_x3d_ram_latency_immunity_and_workstation_cinebench(self):
        c_7800x3d = CPU_DATABASE["RYZEN 7 7800X3D"]
        c_9600x = CPU_DATABASE["RYZEN 5 9600X"]

        # Tight 10.0ns vs loose 14.0ns DDR5 RAM
        eff_x3d_tight, _, _ = compute_effective_build_fps(
            100.0, 130.0, c_7800x3d["fps_gaming"],
            cpu_1pct_low=c_7800x3d["fps_1pct_low"],
            l3_cache_mb=c_7800x3d["l3_cache_mb"],
            ram_latency_ns=10.0,
        )
        eff_x3d_loose, _, _ = compute_effective_build_fps(
            100.0, 130.0, c_7800x3d["fps_gaming"],
            cpu_1pct_low=c_7800x3d["fps_1pct_low"],
            l3_cache_mb=c_7800x3d["l3_cache_mb"],
            ram_latency_ns=14.0,
        )
        eff_std_tight, _, _ = compute_effective_build_fps(
            100.0, 130.0, c_9600x["fps_gaming"],
            cpu_1pct_low=c_9600x["fps_1pct_low"],
            l3_cache_mb=c_9600x["l3_cache_mb"],
            ram_latency_ns=10.0,
        )
        eff_std_loose, _, _ = compute_effective_build_fps(
            100.0, 130.0, c_9600x["fps_gaming"],
            cpu_1pct_low=c_9600x["fps_1pct_low"],
            l3_cache_mb=c_9600x["l3_cache_mb"],
            ram_latency_ns=14.0,
        )

        loss_x3d = (eff_x3d_tight - eff_x3d_loose) / eff_x3d_tight
        loss_std = (eff_std_tight - eff_std_loose) / eff_std_tight
        # 96MB 3D V-Cache loses less than 1.0% from loose RAM; 32MB Zen 5 loses ~2.2% (>6x more)
        self.assertLess(loss_x3d, 0.010)
        self.assertGreater(loss_std, 0.020)
        self.assertGreater(loss_std, loss_x3d * 4.0)

        # Workstation multi-core mode (ai-workstation / creator-pro):
        # 32-thread / 41,800 CB R23 Ryzen 9 9950X vastly outscores 16-thread Ryzen 7 7800X3D
        c_9950x = CPU_DATABASE["RYZEN 9 9950X"]
        clean_ev = {"risk_score": 5, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}
        item_9950x = {"price": 22000.0, "cpu": c_9950x, "spec": c_9950x, "heuristic": clean_ev}
        item_7800x3d = {"price": 12500.0, "cpu": c_7800x3d, "spec": c_7800x3d, "heuristic": clean_ev}

        prof_ai = resolve_mode("ai-workstation")
        self.assertGreater(
            score_component("cpu", item_9950x, prof_ai),
            score_component("cpu", item_7800x3d, prof_ai),
        )

    def test_cpu_database_cyrillic_and_exclusion_filters(self):
        # Cyrillic homoglyphs and transliterations
        c_cyr_x3d = identify_cpu("Процесор AMD Ryzen 7 7800х3д")
        self.assertIsNotNone(c_cyr_x3d)
        self.assertEqual(c_cyr_x3d["model"], "RYZEN 7 7800X3D")

        c_cyr_9700x = identify_cpu("Процесор AMD Ryzen 7 9700х Box")
        self.assertIsNotNone(c_cyr_9700x)
        self.assertEqual(c_cyr_9700x["model"], "RYZEN 7 9700X")

        c_cyr_intel = identify_cpu("Intel Core i9 13900К")
        self.assertIsNotNone(c_cyr_intel)
        self.assertEqual(c_cyr_intel["model"], "CORE I9-13900K")

        # 2026 newly added SKUs
        c_9950x3d2 = identify_cpu("AMD Ryzen 9 9950X3D2 Box")
        self.assertIsNotNone(c_9950x3d2)
        self.assertEqual(c_9950x3d2["model"], "RYZEN 9 9950X3D2")

        c_7500x3d = identify_cpu("AMD Ryzen 5 7500 x3d Tray")
        self.assertIsNotNone(c_7500x3d)
        self.assertEqual(c_7500x3d["model"], "RYZEN 5 7500X3D")

        c_ultra_plus = identify_cpu("Intel Core Ultra 7 270K Plus")
        self.assertIsNotNone(c_ultra_plus)
        self.assertEqual(c_ultra_plus["model"], "CORE ULTRA 7 270K PLUS")

        # Reject combo bundles and mobile mutants
        self.assertIsNone(identify_cpu("Комплект Ryzen 7 5700X3D + B550 + 32GB"))
        self.assertIsNone(identify_cpu("i7-13650hx (Q1LR) мутант LGA1700"))
        # But preserve retail box "повний комплект"
        c_box = identify_cpu("Процесор Ryzen 7 7800X3D повний комплект з коробкою")
        self.assertIsNotNone(c_box)
        self.assertEqual(c_box["model"], "RYZEN 7 7800X3D")

    def test_vrm_penalty_for_100w_cpu_on_d_tier(self):
        g_spec = identify_gpu("RTX 3070 8GB")
        c_spec = identify_cpu("Ryzen 7 5800X3D")
        m_a320 = identify_motherboard("MSI A320-A Pro")
        m_b550 = identify_motherboard("MSI B550-A Pro")
        r_spec = identify_ram("Kingston 16GB (2x8GB) DDR4 3200MHz")
        p_spec = identify_psu("Seasonic 650W Gold")

        clean_ev = {"risk_score": 5, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}
        base_parts = {
            "gpu": {"id": "g", "model": g_spec["model"], "spec": g_spec, "price": 13000.0, "fps_1440p": 68.0, "eval": clean_ev},
            "cpu": {"id": "c", "model": c_spec["model"], "spec": c_spec, "price": 8300.0, "fps_gaming": 196.0, "cores": 8, "tdp_watts": 105, "eval": clean_ev},
            "ram": {"id": "r", "model": "Kingston", "gen": "DDR4", "total_gb": 16, "speed_mhz": 3200, "spec": r_spec, "price": 1400.0, "eval": clean_ev},
            "psu": {"id": "p", "model": p_spec["model"], "wattage": 650, "tier": "Tier A", "spec": p_spec, "price": 1600.0, "eval": clean_ev},
        }

        build_d_tier = {
            **base_parts,
            "mobo": {"id": "m_a320", "model": m_a320["model"], "socket": "AM4", "chipset": "A320", "ddr_type": "DDR4",
                     "vrm_tier": "D-Tier", "spec": m_a320, "price": 1300.0, "eval": clean_ev},
            "total_cost": 25600.0,
        }
        build_b_tier = {
            **base_parts,
            "mobo": {"id": "m_b550", "model": m_b550["model"], "socket": "AM4", "chipset": "B550", "ddr_type": "DDR4",
                     "vrm_tier": "B-Tier", "spec": m_b550, "price": 2500.0, "eval": clean_ev},
            "total_cost": 26800.0,
        }

        prof = resolve_mode("best")
        score_d = score_build(build_d_tier, 28000.0, prof)
        score_b = score_build(build_b_tier, 28000.0, prof)
        # B-Tier VRM board MUST beat D-tier board on 105W 5800X3D by at least 20 points!
        self.assertGreater(score_b, score_d + 20.0)

    def test_system_ai_inspector_and_4pillar_advisory(self):
        g_spec = identify_gpu("RX 6900 XT")
        c_spec = identify_cpu("Ryzen 7 7800X3D")
        m_spec = identify_motherboard("ASUS ROG X670E")
        r_spec = identify_ram("Kingston Fury DDR5 32GB (2x16GB) 6000MHz")
        p_spec = identify_psu("Seasonic Prime 750W Titanium")

        clean_ev = {"risk_score": 4, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": False, "is_ai_rejected": False}
        test_build = {
            "gpu": {"id": "g1", "model": g_spec["model"], "spec": g_spec, "price": 16000.0, "vram_gb": 16, "tdp_watts": 300,
                    "summary": {"id": "g1", "title": "RX 6900 XT 16GB", "price": 16000, "has_olx_delivery": True, "description": "Стан ідеальний."}, "eval": clean_ev},
            "cpu": {"id": "c1", "model": c_spec["model"], "spec": c_spec, "price": 12000.0, "socket": "AM5", "threads": 16, "tdp_watts": 120,
                    "summary": {"id": "c1", "title": "Ryzen 7 7800X3D", "price": 12000, "has_olx_delivery": True, "description": "Повний комплект."}, "eval": clean_ev},
            "mobo": {"id": "m1", "model": m_spec["model"], "spec": m_spec, "price": 6500.0, "socket": "AM5", "chipset": "X670E", "ddr_type": "DDR5", "vrm_tier": "S-Tier",
                     "summary": {"id": "m1", "title": "ASUS X670E", "price": 6500, "has_olx_delivery": True, "description": "Працює відмінно."}, "eval": clean_ev},
            "ram": {"id": "r1", "model": "Kingston", "spec": r_spec, "price": 7000.0, "gen": "DDR5", "total_gb": 32, "speed_mhz": 6000,
                    "summary": {"id": "r1", "title": "DDR5 32GB 2x16", "price": 7000, "has_olx_delivery": True, "description": "Без помилок."}, "eval": clean_ev},
            "psu": {"id": "p1", "model": p_spec["model"], "spec": p_spec, "price": 2000.0, "wattage": 750, "tier": "Tier A", "efficiency": "Titanium",
                    "summary": {"id": "p1", "title": "Seasonic 750W", "price": 2000, "has_olx_delivery": True, "description": "Всі кабелі в наявності."}, "eval": clean_ev},
            "total_cost": 43500.0,
            "surplus": 2500.0,
            "eff_fps_1440p": 100.0,
            "eff_fps_1080p": 125.0,
            "est_load_watts": 410,
        }

        inspector = SystemAIInspector(provider="auto")
        payload = inspector.build_system_payload(1, test_build)
        self.assertEqual(payload["build_id"], 1)
        self.assertEqual(payload["gpu"]["model"], "RX 6900 XT")
        self.assertEqual(payload["cpu"]["model"], "RYZEN 7 7800X3D")
        self.assertEqual(payload["mobo"]["vrm_tier"], "S-Tier")
        self.assertEqual(payload["psu"]["wattage"], 750)

        # Deterministic advisory fallback check
        det_adv = inspector._create_deterministic_advisory(test_build, mode="sweet-spot")
        self.assertEqual(det_adv["verdict"], "APPROVED")
        self.assertGreaterEqual(det_adv["synergy_rating"], 8.5)
        self.assertTrue(len(det_adv["compatibility_notes"]) >= 2)
        self.assertIn("VRM", det_adv["compatibility_notes"][0])
        self.assertIn("PSU", det_adv["compatibility_notes"][1])

    def test_component_locking_and_owned_hardware(self):
        # 1. Test parse_target_query for owned vs locked
        is_owned, query = parse_target_query("owned:RTX 3080")
        self.assertTrue(is_owned)
        self.assertEqual(query, "RTX 3080")

        is_owned, query = parse_target_query("Ryzen 5 7500F")
        self.assertFalse(is_owned)
        self.assertEqual(query, "Ryzen 5 7500F")

        is_owned, query = parse_target_query(None)
        self.assertFalse(is_owned)
        self.assertIsNone(query)

        # 2. Test matches_lock_query
        sample_card = {"model": "RTX 3080 10GB", "summary": {"title": "Asus TUF RTX 3080 10GB"}}
        self.assertTrue(matches_lock_query(sample_card, "3080"))
        self.assertTrue(matches_lock_query(sample_card, "rtx 3080"))
        self.assertFalse(matches_lock_query(sample_card, "4070"))

        # 3. Test spec resolution for owned hardware
        owned_gpu = resolve_owned_gpu("RTX 3080")
        self.assertTrue(owned_gpu["is_owned"])
        self.assertEqual(owned_gpu["price"], 0.0)
        self.assertEqual(owned_gpu["model"], "RTX 3080 10GB")
        self.assertEqual(owned_gpu["vram_gb"], 10)
        self.assertEqual(owned_gpu["tdp_watts"], 320)

        owned_cpu = resolve_owned_cpu("7800X3D")
        self.assertTrue(owned_cpu["is_owned"])
        self.assertEqual(owned_cpu["price"], 0.0)
        self.assertEqual(owned_cpu["socket"], "AM5")
        self.assertEqual(owned_cpu["l3_cache_mb"], 96)

        owned_mobo = resolve_owned_mobo("B550")
        self.assertTrue(owned_mobo["is_owned"])
        self.assertEqual(owned_mobo["price"], 0.0)
        self.assertEqual(owned_mobo["socket"], "AM4")
        self.assertEqual(owned_mobo["ddr_type"], "DDR4")

        owned_ram = resolve_owned_ram("32GB DDR5")
        self.assertTrue(owned_ram["is_owned"])
        self.assertEqual(owned_ram["price"], 0.0)
        self.assertEqual(owned_ram["gen"], "DDR5")
        self.assertEqual(owned_ram["spec"]["module_count"], 2)

        owned_psu = resolve_owned_psu("750W")
        self.assertTrue(owned_psu["is_owned"])
        self.assertEqual(owned_psu["price"], 0.0)
        self.assertEqual(owned_psu["wattage"], 750)

        # 4. Synthesizing builds with owned GPU
        c_spec = identify_cpu("Ryzen 7 7800X3D")
        m_spec = identify_motherboard("MSI B650 Tomahawk")
        r_spec = identify_ram("Kingston Fury DDR5 32GB (2x16GB) 6000MHz")
        p_spec = identify_psu("Seasonic Focus 750W Gold")
        clean_ev = {"risk_score": 0, "red_flags": [], "warnings": [], "audit": None, "is_ai_approved": True, "is_ai_rejected": False}

        gpus = [owned_gpu]
        cpus = [{
            "id": "c1", "model": c_spec["model"], "socket": "AM5", "spec": c_spec, "cpu": c_spec,
            "price": 12000.0, "fps_gaming": c_spec["fps_gaming"], "cores": 8, "threads": 16,
            "tdp_watts": c_spec["tdp_watts"], "discount_pct": 10.0, "url": "http://c1", "eval": clean_ev,
        }]
        mobos = [{
            "id": "m1", "model": m_spec["model"], "socket": "AM5", "chipset": "B650",
            "ddr_type": "DDR5", "vrm_tier": "A-Tier", "spec": m_spec, "mobo": m_spec,
            "price": 4500.0, "discount_pct": 10.0, "url": "http://m1", "eval": clean_ev,
        }]
        rams = [{
            "id": "r1", "model": "Kingston", "gen": "DDR5", "total_gb": 32, "speed_mhz": 6000,
            "spec": r_spec, "ram": r_spec, "price": 4000.0, "discount_pct": 10.0,
            "url": "http://r1", "eval": clean_ev,
        }]
        psus = [{
            "id": "p1", "model": p_spec["model"], "wattage": 750, "tier": "Tier A",
            "efficiency": "Gold", "spec": p_spec, "psu": p_spec,
            "price": 2500.0, "discount_pct": 10.0, "url": "http://p1", "eval": clean_ev,
        }]

        budget = 25000.0
        builds = synthesize_builds(
            gpus, cpus, mobos, rams, psus,
            budget=budget, profile=resolve_mode("best"), top_n=1,
        )
        self.assertEqual(len(builds), 1)
        b = builds[0]
        # Owned GPU price is 0.0 UAH
        self.assertEqual(b["gpu"]["price"], 0.0)
        self.assertTrue(b["gpu"]["is_owned"])
        # Total cost is strictly CPU + Mobo + RAM + PSU = 12000 + 4500 + 4000 + 2500 = 23000 UAH
        self.assertEqual(b["total_cost"], 23000.0)
        self.assertEqual(b["surplus"], 2000.0)
        # Score must be positive and strong
        self.assertGreater(b["build_score"], 60.0)

        # 5. Live run_build_optimizer with owned GPU
        live_builds = run_build_optimizer(
            budget=25000.0,
            mode="best",
            gpu="owned:RTX 3080",
            top_builds=1,
            no_ai=True,
            candidate_pool=SAMPLE_HERMETIC_PC_POOL,
        )
        self.assertGreaterEqual(len(live_builds), 1)
        top_live = live_builds[0]
        self.assertTrue(top_live["gpu"]["is_owned"])
        self.assertEqual(top_live["gpu"]["price"], 0.0)
        self.assertLessEqual(top_live["total_cost"], 25000.0)


class TestHumanReviewAndPlatformEstimator(unittest.TestCase):
    def test_estimate_cpu_platform_cost_am4_vs_am5(self):
        from extensions.pc.human_review import estimate_cpu_platform_cost
        from extensions.pc.cpu_database import identify_cpu

        c_am4 = identify_cpu("Ryzen 7 5700X3D")
        plat_am4 = estimate_cpu_platform_cost({
            "price": 6500.0, "model": c_am4["model"], "socket": c_am4["socket"],
            "spec": c_am4, "fps_gaming": c_am4["fps_gaming"],
        })
        self.assertEqual(plat_am4["socket"], "AM4")
        self.assertTrue(plat_am4["is_x3d"])
        self.assertEqual(plat_am4["platform_cost"], 3400.0)
        self.assertEqual(plat_am4["total_platform_cost"], 9900.0)
        self.assertAlmostEqual(plat_am4["platform_uah_per_fps"], 52.7, places=1)

        c_am5 = identify_cpu("Ryzen 5 7500F")
        plat_am5 = estimate_cpu_platform_cost({
            "price": 5000.0, "model": c_am5["model"], "socket": c_am5["socket"],
            "spec": c_am5, "fps_gaming": c_am5["fps_gaming"],
        })
        self.assertEqual(plat_am5["socket"], "AM5")
        self.assertFalse(plat_am5["is_x3d"])
        self.assertEqual(plat_am5["platform_cost"], 13000.0)
        self.assertEqual(plat_am5["total_platform_cost"], 18000.0)
        self.assertAlmostEqual(plat_am5["platform_uah_per_fps"], 102.9, places=1)

        # Dynamic pool-based platform estimation
        custom_mobos = [
            {"model": "ASUS PRIME B650M-A", "socket": "AM5", "price": 3500.0},
            {"model": "MSI PRO B650-S", "socket": "AM5", "price": 4000.0},
        ]
        custom_rams = [
            {"model": "Kingston DDR5", "gen": "DDR5", "total_gb": 32, "price": 2800.0},
        ]
        plat_custom = estimate_cpu_platform_cost(
            {"price": 5000.0, "model": c_am5["model"], "socket": "AM5", "spec": c_am5, "fps_gaming": c_am5["fps_gaming"]},
            mobo_pool=custom_mobos,
            ram_pool=custom_rams,
        )
        self.assertEqual(plat_custom["mobo_price"], 3500.0)
        self.assertEqual(plat_custom["ram_price"], 2800.0)
        self.assertEqual(plat_custom["total_platform_cost"], 11300.0)

    def test_human_validation_interactive_flow(self):
        from extensions.pc.human_review import run_human_validation_review

        gpus = [
            {"id": "g1", "model": "RTX 3080 Ti", "price": 17000.0, "fps_1440p": 91.0, "discount_pct": 23.0, "vram_gb": 12, "summary": {"title": "RTX 3080 Ti", "has_olx_delivery": True}},
            {"id": "g2", "model": "RX 6900 XT", "price": 15900.0, "fps_1440p": 91.0, "discount_pct": 22.0, "vram_gb": 16, "summary": {"title": "RX 6900 XT", "has_olx_delivery": True}},
        ]
        cpus = [
            {"id": "c1", "model": "Ryzen 7 5800X3D", "socket": "AM4", "price": 8300.0, "fps_gaming": 196.0, "discount_pct": 37.0, "summary": {"title": "Ryzen 7 5800X3D", "has_olx_delivery": True}},
            {"id": "c2", "model": "Ryzen 5 7500F", "socket": "AM5", "price": 5000.0, "fps_gaming": 175.0, "discount_pct": 15.0, "summary": {"title": "Ryzen 5 7500F", "has_olx_delivery": True}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "audit_ledger.json"
            led = AuditLedger(ledger_path=ledger_file)

            # Test 1: User approves g1 [y] and rejects g2 [n]; locks c1 [l]
            inputs = iter(["y", "n", "l", "s"])
            locked_g, locked_c, fg, fc = run_human_validation_review(
                gpus, cpus, budget=35000.0, ledger=led, input_func=lambda _: next(inputs), no_ai=True
            )

            self.assertIsNone(locked_g)
            self.assertIsNotNone(locked_c)
            self.assertEqual(locked_c["id"], "c1")
            # g1 was rejected -> g2 remains in filtered_gpus
            self.assertEqual(len(fg), 1)
            self.assertEqual(fg[0]["id"], "g2")
            # g1 is blacklisted in ledger
            rec = led.get_audit("g1")
            self.assertIsNotNone(rec)
            self.assertEqual(rec["verdict"], "REJECTED")
            self.assertEqual(rec["provider"], "human")

            # g2 was approved and saved in ledger
            rec_g2 = led.get_audit("g2")
            self.assertIsNotNone(rec_g2)
            self.assertEqual(rec_g2["verdict"], "APPROVED")
            self.assertEqual(rec_g2["provider"], "human")

            # c1 was locked and saved in ledger
            rec_c1 = led.get_audit("c1")
            self.assertIsNotNone(rec_c1)
            self.assertEqual(rec_c1["verdict"], "APPROVED")
            self.assertEqual(rec_c1["provider"], "human")

            # Test 2: Approve all [a]
            inputs_all = iter(["a", "a"])
            gpus_fresh = [
                {"id": "g1", "model": "RTX 3080 Ti", "price": 17000.0, "fps_1440p": 91.0, "discount_pct": 23.0, "vram_gb": 12, "summary": {"title": "RTX 3080 Ti", "has_olx_delivery": True}},
                {"id": "g2", "model": "RX 6900 XT", "price": 15900.0, "fps_1440p": 91.0, "discount_pct": 22.0, "vram_gb": 16, "summary": {"title": "RX 6900 XT", "has_olx_delivery": True}},
            ]
            cpus_fresh = [
                {"id": "c1", "model": "Ryzen 7 5800X3D", "socket": "AM4", "price": 8300.0, "fps_gaming": 196.0, "discount_pct": 37.0, "summary": {"title": "Ryzen 7 5800X3D", "has_olx_delivery": True}},
                {"id": "c2", "model": "Ryzen 5 7500F", "socket": "AM5", "price": 5000.0, "fps_gaming": 175.0, "discount_pct": 15.0, "summary": {"title": "Ryzen 5 7500F", "has_olx_delivery": True}},
            ]
            ledger_file2 = Path(tmp) / "audit_ledger2.json"
            led2 = AuditLedger(ledger_path=ledger_file2)
            locked_g2, locked_c2, fg2, fc2 = run_human_validation_review(
                gpus_fresh, cpus_fresh, budget=35000.0, ledger=led2, input_func=lambda _: next(inputs_all), no_ai=True
            )
            self.assertIsNone(locked_g2)
            self.assertIsNone(locked_c2)
            self.assertEqual(len(fg2), 2)
            self.assertEqual(len(fc2), 2)

            # c2 was auto-approved and saved in ledger
            rec_c2 = led2.get_audit("c2")
            self.assertIsNotNone(rec_c2)
            self.assertEqual(rec_c2["verdict"], "APPROVED")
            self.assertEqual(rec_c2["provider"], "human")

            # Test 3: Reject all surfaced proposals [n] -> falls back to remaining unrejected pool
            gpus3 = [
                {"id": "g1", "model": "RTX 3080 Ti", "price": 17000.0, "fps_1440p": 91.0, "discount_pct": 23.0, "vram_gb": 12, "summary": {"title": "RTX 3080 Ti", "has_olx_delivery": True}},
                {"id": "g2", "model": "RX 6900 XT", "price": 15900.0, "fps_1440p": 91.0, "discount_pct": 22.0, "vram_gb": 16, "summary": {"title": "RX 6900 XT", "has_olx_delivery": True}},
                {"id": "g3", "model": "RTX 3070", "price": 12000.0, "fps_1440p": 70.0, "discount_pct": 10.0, "vram_gb": 8, "summary": {"title": "RTX 3070", "has_olx_delivery": True}},
            ]
            cpus3 = [
                {"id": "c1", "model": "Ryzen 7 5800X3D", "socket": "AM4", "price": 8300.0, "fps_gaming": 196.0, "discount_pct": 37.0, "summary": {"title": "Ryzen 7 5800X3D", "has_olx_delivery": True}},
                {"id": "c2", "model": "Ryzen 5 7500F", "socket": "AM5", "price": 5000.0, "fps_gaming": 175.0, "discount_pct": 15.0, "summary": {"title": "Ryzen 5 7500F", "has_olx_delivery": True}},
                {"id": "c3", "model": "Core i5-12400F", "socket": "LGA1700", "price": 3800.0, "fps_gaming": 140.0, "discount_pct": 15.0, "summary": {"title": "Core i5-12400F", "has_olx_delivery": True}},
            ]
            ledger_file3 = Path(tmp) / "audit_ledger3.json"
            led3 = AuditLedger(ledger_path=ledger_file3)
            # 2 surfaced GPUs rejected ('n', 'n'), 2 surfaced CPUs rejected ('n', 'n')
            inputs_reject = iter(["n", "n", "n", "n"])
            locked_g3, locked_c3, fg3, fc3 = run_human_validation_review(
                gpus3, cpus3, budget=35000.0, ledger=led3, input_func=lambda _: next(inputs_reject), max_candidates=2, no_ai=True
            )
            self.assertIsNone(locked_g3)
            self.assertIsNone(locked_c3)
            # Surfaced proposals were rejected and excluded; remaining candidate g3 and c3 are open for synthesis
            self.assertEqual(len(fg3), 1)
            self.assertEqual(fg3[0]["id"], "g3")
            self.assertEqual(len(fc3), 1)
            self.assertEqual(fc3[0]["id"], "c2")
            self.assertEqual(led3.get_audit("g1")["verdict"], "REJECTED")
            self.assertEqual(led3.get_audit("c3")["verdict"], "REJECTED")

    def test_run_build_optimizer_with_human_review(self):
        # Live run with human_review=True and mocked input approving all ('a')
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            tmp_ledger = Path(tmp) / "audit_ledger.json"
            from audit_ledger import AuditLedger
            mock_ledger = AuditLedger(ledger_path=tmp_ledger)
            with patch("extensions.pc.build_optimizer.ledger", mock_ledger):
                builds = run_build_optimizer(
                    budget=35000.0,
                    mode="best",
                    top_builds=1,
                    no_ai=True,
                    human_review=True,
                    input_func=lambda _: "a",
                    candidate_pool=SAMPLE_HERMETIC_PC_POOL,
                )
                self.assertGreaterEqual(len(builds), 1)
                self.assertLessEqual(builds[0]["total_cost"], 35000.0)
                # Ensure 100% of components are human-validated (NEVER sneaking in unreviewed CLEAN parts)
                for part_key in ["gpu", "cpu", "mobo", "ram", "psu"]:
                    part = builds[0][part_key]
                    ai_ev = part.get("ai_eval") or {}
                    self.assertEqual(ai_ev.get("provider"), "human", f"{part_key} was not human-validated!")
                    self.assertEqual(ai_ev.get("verdict"), "APPROVED")

    def test_human_review_never_falls_back_to_unvalidated_clean_components(self):
        from unittest.mock import patch
        from extensions.pc.human_review import HumanReviewResult

        # Mock HumanReviewResult returning incompatible parts (AM4 CPU with LGA1700 Motherboard)
        mock_result = HumanReviewResult(
            final_gpus=[{"id": "g1", "model": "RTX 3060", "price": 8000.0, "discount_pct": 10.0, "fps_1440p": 50.0, "fps_1080p": 70.0, "vram_gb": 12, "tdp_watts": 170, "spec": {"vram_gb": 12, "tdp_w": 170}, "eval": {"risk_score": 0}, "ai_eval": {"provider": "human", "verdict": "APPROVED"}}],
            final_cpus=[{"id": "c1", "model": "Ryzen 5 5600", "socket": "AM4", "price": 3000.0, "discount_pct": 10.0, "fps_gaming": 130.0, "threads": 12, "tdp_watts": 65, "spec": {"tdp_w": 65, "l3_cache_mb": 32}, "eval": {"risk_score": 0}, "ai_eval": {"provider": "human", "verdict": "APPROVED"}}],
            final_mobos=[{"id": "m1", "model": "Z690", "socket": "LGA1700", "ddr_type": "DDR4", "price": 4000.0, "discount_pct": 10.0, "vrm_tier": "A-Tier", "spec": {"form_factor": "ATX"}, "eval": {"risk_score": 0}, "ai_eval": {"provider": "human", "verdict": "APPROVED"}}],
            final_rams=[{"id": "r1", "model": "16GB DDR4", "gen": "DDR4", "total_gb": 16, "price": 1500.0, "discount_pct": 10.0, "spec": {"module_count": 2, "latency_ns": 10.0}, "eval": {"risk_score": 0}, "ai_eval": {"provider": "human", "verdict": "APPROVED"}}],
            final_psus=[{"id": "p1", "model": "650W", "wattage": 650, "tier": "Tier B", "efficiency": "Gold", "price": 1800.0, "discount_pct": 10.0, "spec": {}, "eval": {"risk_score": 0}, "ai_eval": {"provider": "human", "verdict": "APPROVED"}}],
        )

        with patch("extensions.pc.build_optimizer.run_human_validation_review", return_value=mock_result):
            builds = run_build_optimizer(
                budget=25000.0,
                mode="value",
                top_builds=1,
                no_ai=True,
                human_review=True,
            )
            # Under --human-review, must NEVER sneak in clean parts from cache; must return []
            self.assertEqual(builds, [], "Optimizer must return [] rather than sneaking in unvalidated CLEAN parts")

    def test_human_only_enforced_strictly_under_human_review_flag_only(self):
        """
        Verifies:
        - When human_only=True (under --human-review flag), only provider='human' items are approved.
        - When human_only=False (under --ai-prescreen or normal), AI/script-approved items (provider='agy'/'ai') are accepted.
        """
        from extensions.pc.human_review import _is_item_approved
        from audit_ledger import AuditLedger
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_led = AuditLedger(ledger_path=Path(tmp) / "ledger.json")
            tmp_led.record_audit(
                "ai_item_1",
                category="gpu",
                verdict="APPROVED",
                confidence_score=95,
                reasons=["Verified by AI"],
                provider="agy",
                title="AI Approved GPU",
            )
            tmp_led.record_audit(
                "human_item_1",
                category="gpu",
                verdict="APPROVED",
                confidence_score=100,
                reasons=["Verified by human"],
                provider="human",
                title="Human Approved GPU",
            )

            ai_cand = {"id": "ai_item_1", "model": "RTX 3070", "summary": {"title": "AI Approved GPU"}}
            human_cand = {"id": "human_item_1", "model": "RTX 3080", "summary": {"title": "Human Approved GPU"}}

            # Under human_only=True (e.g. --human-review):
            self.assertTrue(_is_item_approved(tmp_led, human_cand, human_only=True))
            self.assertFalse(_is_item_approved(tmp_led, ai_cand, human_only=True))

            # Under human_only=False (e.g. --ai-prescreen or normal mode):
            self.assertTrue(_is_item_approved(tmp_led, human_cand, human_only=False))
            self.assertTrue(_is_item_approved(tmp_led, ai_cand, human_only=False))

    def test_select_top_gpu_deals_filters_legacy_and_low_fps_at_high_budget(self):
        from extensions.pc.human_review import select_top_gpu_deals
        from extensions.pc.modes import resolve_mode
        from extensions.pc.gpu_database import identify_gpu

        mode_best = resolve_mode("best")
        candidates = [
            {"id": "g_legacy", "model": "GTX 1080 TI", "price": 5499.0, "fps_1440p": 36.0, "discount_pct": 20.0, "vram_gb": 11, "spec": identify_gpu("GTX 1080 TI")},
            {"id": "g_mid", "model": "RTX 3080", "price": 15000.0, "fps_1440p": 84.0, "discount_pct": 15.0, "vram_gb": 10, "spec": identify_gpu("RTX 3080")},
            {"id": "g_high", "model": "RX 6900 XT", "price": 16000.0, "fps_1440p": 91.0, "discount_pct": 20.0, "vram_gb": 16, "spec": identify_gpu("RX 6900 XT")},
            {"id": "g_ultra", "model": "RTX 4070 TI", "price": 24000.0, "fps_1440p": 105.0, "discount_pct": 10.0, "vram_gb": 12, "spec": identify_gpu("RTX 4070 TI")},
        ]

        top_deals = select_top_gpu_deals(candidates, budget=46000.0, profile=mode_best, limit=3)
        surfaced_ids = [g["id"] for g in top_deals]

        self.assertNotIn("g_legacy", surfaced_ids, "GTX 1080 Ti must NEVER be surfaced for a 46,000 UAH 'best' build")
        self.assertEqual(len(top_deals), 3)


    def test_all_five_categories_human_review_and_ledger_bypass(self):
        from extensions.pc.human_review import run_human_validation_review, HumanReviewResult

        gpus = [{"id": f"g_{i}", "model": f"GPU {i}", "price": 15000.0, "fps_1440p": 90.0, "discount_pct": 20.0, "vram_gb": 16, "summary": {"title": f"GPU {i}"}} for i in range(3)]
        cpus = [{"id": f"c_{i}", "model": f"CPU {i}", "socket": "AM5", "price": 8000.0, "fps_gaming": 180.0, "discount_pct": 20.0, "summary": {"title": f"CPU {i}"}} for i in range(3)]
        mobos = [{"id": f"m_{i}", "model": f"MOBO {i}", "socket": "AM5", "ddr_type": "DDR5", "vrm_tier": "A-Tier", "price": 4000.0, "discount_pct": 20.0, "summary": {"title": f"MOBO {i}"}} for i in range(3)]
        rams = [{"id": f"r_{i}", "model": f"RAM {i}", "gen": "DDR5", "total_gb": 32, "speed_mhz": 6000, "price": 6000.0, "discount_pct": 20.0, "summary": {"title": f"RAM {i}"}} for i in range(3)]
        psus = [{"id": f"p_{i}", "model": f"PSU {i}", "wattage": 750, "tier": "Tier A", "price": 2000.0, "discount_pct": 20.0, "summary": {"title": f"PSU {i}"}} for i in range(3)]

        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "audit_ledger.json"
            led = AuditLedger(ledger_path=ledger_file)

            # Pass 1: Review and approve all components
            res1 = run_human_validation_review(
                gpu_list=gpus,
                cpu_list=cpus,
                mobo_list=mobos,
                ram_list=rams,
                psu_list=psus,
                budget=45000.0,
                ledger=led,
                input_func=lambda _: "y",
                max_candidates=3,
                target_approved=3,
                no_ai=True,
            )
            self.assertIsInstance(res1, HumanReviewResult)
            self.assertEqual(len(res1.final_gpus), 3)
            self.assertEqual(len(res1.final_cpus), 3)
            self.assertEqual(len(res1.final_mobos), 3)
            self.assertEqual(len(res1.final_rams), 3)
            self.assertEqual(len(res1.final_psus), 3)

            # Verify all items were recorded in AuditLedger
            for cat, items in [("gpu", gpus), ("cpu", cpus), ("mobo", mobos), ("ram", rams), ("psu", psus)]:
                for it in items:
                    rec = led.get_audit(it["id"])
                    self.assertIsNotNone(rec, f"Missing audit for {it['id']}")
                    self.assertEqual(rec["verdict"], "APPROVED")

            # Pass 2: Subsequent run with the SAME ledger must BYPASS prompts completely
            def should_not_be_called(prompt: str) -> str:
                self.fail(f"Interactive prompt was displayed despite items already approved in AuditLedger: {prompt}")

            res2 = run_human_validation_review(
                gpu_list=gpus,
                cpu_list=cpus,
                mobo_list=mobos,
                ram_list=rams,
                psu_list=psus,
                budget=45000.0,
                ledger=led,
                input_func=should_not_be_called,
                max_candidates=3,
                target_approved=3,
                no_ai=True,
            )
            self.assertEqual(len(res2.final_gpus), 3)
            self.assertEqual(len(res2.final_cpus), 3)
            self.assertEqual(len(res2.final_mobos), 3)
            self.assertEqual(len(res2.final_rams), 3)
            self.assertEqual(len(res2.final_psus), 3)

    def test_run_build_optimizer_default_top_builds_is_five(self):
        from extensions.pc.build_optimizer import build_arg_parser
        parser = build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual(args.top_builds, 5, "Default CLI --top-builds must be 5")
        self.assertFalse(args.ai_prescreen, "AI pre-screening must be disabled by default")
        self.assertFalse(args.ai_audit, "AI system audit must be disabled by default")
        args_ps = parser.parse_args(["--ai-prescreen"])
        self.assertTrue(args_ps.ai_prescreen)
        args_ps_alias = parser.parse_args(["--prescreen"])
        self.assertTrue(args_ps_alias.ai_prescreen)

    def test_ai_prescreen_filters_defective_proposals_before_human_review(self):
        from extensions.pc.human_review import pre_screen_proposals_with_ai

        class MockInspector:
            category = "gpu"
            provider_label = "Mock AI Inspector"

            def inspect_and_rank_batch(self, batch, sort_by="best", re_audit=False):
                approved = []
                rejected = []
                for item in batch:
                    title = (item.get("summary") or {}).get("title", "")
                    desc = (item.get("summary") or {}).get("description", "")
                    if "код 43" in title or "defect" in desc:
                        item["ai_eval"] = {
                            "verdict": "REJECTED",
                            "confidence_score": 99,
                            "reasons": ["Defective GPU: Error code 43"],
                        }
                        rejected.append(item)
                    else:
                        item["ai_eval"] = {
                            "verdict": "APPROVED",
                            "confidence_score": 90,
                            "reasons": ["Clean listing"],
                        }
                        approved.append(item)
                return {"approved": approved, "rejected": rejected}

        items = [
            {"id": "bad_gpu", "model": "RTX 3090 Broken", "price": 14000.0, "fps_1440p": 93.0, "summary": {"id": "bad_gpu", "title": "RTX 3090 код 43", "description": "неустанавлюетса драйвера"}},
            {"id": "good_gpu", "model": "RX 6900 XT", "price": 15900.0, "fps_1440p": 91.0, "summary": {"id": "good_gpu", "title": "RX 6900 XT 16GB", "description": "Ідеальний стан"}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_led = AuditLedger(ledger_path=Path(tmp) / "ledger.json")
            clean, rejected = pre_screen_proposals_with_ai(
                cat_name="gpu",
                cat_label="GPU",
                candidates=items,
                needed_count=2,
                inspector=MockInspector(),
                led=tmp_led,
            )
            # Defective proposal filtered out before human sees it!
            self.assertEqual(len(clean), 1)
            self.assertEqual(clean[0]["id"], "good_gpu")
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["id"], "bad_gpu")

    def test_ai_prescreen_does_not_trigger_human_review_chokehold(self):
        """Verifies --ai-prescreen on its own does NOT trigger human review loop or human-only restrictions."""
        from extensions.pc.build_optimizer import main as cli_main
        from unittest.mock import patch

        with patch("extensions.pc.build_optimizer.run_build_optimizer") as mock_opt:
            cli_main(["-b", "30000", "-M", "value", "--ai-prescreen"])
            mock_opt.assert_called_once()
            _, kwargs = mock_opt.call_args
            self.assertFalse(kwargs["human_review"], "--ai-prescreen alone must NOT enable human_review")
            self.assertFalse(kwargs["human_only"], "--ai-prescreen alone must NOT enforce human_only")
            self.assertTrue(kwargs["ai_prescreen"], "ai_prescreen flag must be passed to optimizer")

        with patch("extensions.pc.build_optimizer.run_build_optimizer") as mock_opt_hr:
            cli_main(["-b", "30000", "-M", "value", "--human-review"])
            mock_opt_hr.assert_called_once()
            _, kwargs_hr = mock_opt_hr.call_args
            self.assertTrue(kwargs_hr["human_review"], "--human-review must enable human_review")
            self.assertTrue(kwargs_hr["human_only"], "--human-review must enforce human_only")

    def test_legacy_sockets_pruned_in_value_mode_at_high_budget(self):
        """Verifies that at budget >= 25,000 UAH in value mode, dead LGA1151v2 sockets are excluded in favor of modern platforms."""
        builds = run_build_optimizer(
            budget=30000.0,
            mode="value",
            human_review=False,
            top_builds=5,
            candidate_pool=SAMPLE_HERMETIC_PC_POOL,
        )
        self.assertGreaterEqual(len(builds), 1)
        # Verify no LGA1151 or LGA1151v2 sockets in top builds
        for b in builds:
            c_sock = b["cpu"].get("socket", "")
            m_sock = b["mobo"].get("socket", "")
            self.assertNotIn(c_sock, ("LGA1151", "LGA1151v2", "LGA1150"))
            self.assertNotIn(m_sock, ("LGA1151", "LGA1151v2", "LGA1150"))

        # Verify top build is a high-utilization, modern performance build
        top = builds[0]
        self.assertGreater(top["eff_fps_1440p"], 50.0)
        self.assertGreater(top["total_cost"], 15000.0)

    def test_ultra_budget_pool_and_build_synthesis(self):
        """Verifies that ultra-budget builds (<= 10,000 UAH) populate entry-level GPUs (RX 580/GTX 1060) and synthesize valid builds."""
        builds = run_build_optimizer(
            budget=7000.0,
            mode="value",
            human_review=False,
            candidate_pool=SAMPLE_HERMETIC_PC_POOL,
        )
        self.assertGreaterEqual(len(builds), 1)
        top = builds[0]
        self.assertLessEqual(top["total_cost"], 7000.0)
        self.assertIn("gpu", top)
        self.assertIn("cpu", top)
        self.assertIn("mobo", top)
        self.assertIn("ram", top)
        self.assertIn("psu", top)

    def test_prime_k_motherboard_vrm_tier_detection(self):
        from extensions.pc.mobo_database import identify_motherboard
        m_b450 = identify_motherboard("Asus Prime B450M-K")
        self.assertIsNotNone(m_b450)
        assert m_b450 is not None
        self.assertEqual(m_b450["vrm_tier"], "C-Tier")

        m_h610 = identify_motherboard("ASUS Prime H610M-K D4")
        self.assertIsNotNone(m_h610)
        assert m_h610 is not None
        self.assertEqual(m_h610["vrm_tier"], "C-Tier")

        m_a320 = identify_motherboard("Asus Prime A320M-K")
        self.assertIsNotNone(m_a320)
        assert m_a320 is not None
        self.assertEqual(m_a320["vrm_tier"], "D-Tier")

    def test_delivery_refusal_patterns_sync(self):
        from scam_utils import DELIVERY_REFUSAL_RE
        self.assertTrue(bool(DELIVERY_REFUSAL_RE.search("Тільки самовивіз з квартири")))
        self.assertTrue(bool(DELIVERY_REFUSAL_RE.search("Без відправок поштою")))
        self.assertTrue(bool(DELIVERY_REFUSAL_RE.search("Поштою не відправляю")))
        self.assertTrue(bool(DELIVERY_REFUSAL_RE.search("Без пошти, зустріч у центрі")))
        self.assertFalse(bool(DELIVERY_REFUSAL_RE.search("Відправляю OLX доставкою Новою Поштою")))

    def test_resolve_photos_count_fallback(self):
        from scam_utils import resolve_photos_count
        summary_with_photos = {"id": "1", "photos": ["http://img1", "http://img2"]}
        summary_with_raw = {"id": "2", "raw": {"photos": ["http://img1", "http://img2", "http://img3"]}}
        detail_empty = {}
        self.assertEqual(resolve_photos_count(summary_with_photos, detail_empty), 2)
        self.assertEqual(resolve_photos_count(summary_with_raw, detail_empty), 3)

    def test_audit_ledger_category_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_led = AuditLedger(ledger_path=Path(tmp) / "ledger.json")
            tmp_led.record_audit(
                offer_id="99901",
                category="motherboard",
                verdict="APPROVED",
                confidence_score=95,
                reasons=["Test board"],
                title="B550 Board",
                price=2500.0,
            )
            # Querying by alias 'mobo' should find it
            audits_mobo = tmp_led.get_all_audits(category="mobo")
            self.assertEqual(len(audits_mobo), 1)
            self.assertEqual(audits_mobo[0]["id"], "99901")

            # Querying by 'motherboard' should also find it
            audits_full = tmp_led.get_all_audits(category="motherboard")
            self.assertEqual(len(audits_full), 1)

    def test_human_review_single_category(self):
        from extensions.pc.human_review import run_human_validation_review
        with tempfile.TemporaryDirectory() as tmp:
            tmp_led = AuditLedger(ledger_path=Path(tmp) / "ledger.json")
            mobo_sample = [
                {
                    "id": "m1",
                    "model": "ASUS TUF B550-PLUS",
                    "price": 3200.0,
                    "socket": "AM4",
                    "ddr_type": "DDR4",
                    "spec": {"socket": "AM4", "ddr_type": "DDR4", "vrm_tier": "A-Tier"},
                    "summary": {"id": "m1", "title": "ASUS TUF B550-PLUS AM4", "has_olx_delivery": True},
                }
            ]
            res = run_human_validation_review(
                gpu_list=None,
                cpu_list=None,
                mobo_list=mobo_sample,
                budget=20000.0,
                ledger=tmp_led,
                input_func=lambda _: "y",
                max_candidates=1,
                target_approved=1,
                no_ai=True,
            )
            self.assertEqual(len(res.final_mobos), 1)
            self.assertEqual(res.final_mobos[0]["id"], "m1")


    def test_market_client_normalize_category_and_cache_resolution(self):
        from market_client import normalize_category, CATEGORY_CACHE_FILES
        self.assertEqual(normalize_category("motherboards"), "mobo")
        self.assertEqual(normalize_category("motherboard"), "mobo")
        self.assertEqual(normalize_category("mobo"), "mobo")
        self.assertEqual(normalize_category("gpus"), "gpu")
        self.assertEqual(normalize_category("cpus"), "cpu")
        self.assertEqual(normalize_category("rams"), "ram")
        self.assertEqual(normalize_category("psus"), "psu")

    def test_delivery_refusal_detection(self):
        from provider_template import ProviderFeatureAdapter
        check = ProviderFeatureAdapter.check_delivery_refusal
        self.assertTrue(check("Без OLX доставки, тільки самовивіз", "olx.ua"))
        self.assertTrue(check("OLX доставка не працює", "olx.ua"))
        self.assertFalse(check("Відправляю Новою Поштою або OLX доставкою", "olx.ua"))

    def test_build_cost_exact_budget_boundary(self):
        # Verify builds that cost exactly the budget (total_cost == budget) are accepted
        from extensions.pc.modes import resolve_mode
        from extensions.pc.build_optimizer import synthesize_builds
        profile = resolve_mode("best")
        fake_gpu = {
            "id": "g1", "model": "RTX 3060", "price": 10000.0,
            "fps_1440p": 50.0, "fps_1080p": 70.0, "tdp": 170,
            "vram_gb": 12, "spec": {"tier": "RTX 3060"},
        }
        fake_cpu = {
            "id": "c1", "model": "Ryzen 5 5600", "price": 4000.0,
            "fps_gaming": 100.0, "socket": "AM4", "tdp": 65,
            "spec": {"socket": "AM4", "tdp": 65, "cores": 6, "threads": 12},
        }
        fake_mobo = {
            "id": "m1", "model": "B450M", "price": 2000.0,
            "socket": "AM4", "ddr_type": "DDR4", "chipset": "B450",
            "spec": {"socket": "AM4", "ddr_type": "DDR4", "vrm_tier": "B-Tier"},
        }
        fake_ram = {
            "id": "r1", "model": "16GB DDR4", "price": 1500.0,
            "gen": "DDR4", "ddr_type": "DDR4",
            "spec": {"generation": "DDR4", "module_count": 2, "capacity_gb": 16, "speed_mhz": 3200},
        }
        fake_psu = {
            "id": "p1", "model": "550W Bronze", "price": 1500.0,
            "watts": 550, "tier": "Tier C",
            "spec": {"wattage": 550, "tier": "Tier C"},
        }
        # Exact total sum: 10000 + 4000 + 2000 + 1500 + 1500 = 19000
        builds = synthesize_builds(
            gpus=[fake_gpu],
            cpus=[fake_cpu],
            mobos=[fake_mobo],
            rams=[fake_ram],
            psus=[fake_psu],
            budget=19000.0,
            profile=profile,
            top_n=1,
        )
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0]["total_cost"], 19000.0)
        self.assertEqual(builds[0]["surplus"], 0.0)

    def test_category_target_pools_expansion(self):
        """Verifies candidate pool size targets are expanded to 7 for GPU, CPU, MOBO and 5 for RAM, PSU."""
        from extensions.pc.human_review import DEFAULT_CATEGORY_TARGETS, select_top_gpu_deals, select_top_cpu_platform_deals, select_top_mobo_deals
        from extensions.pc.build_optimizer import _select_pareto_mobos

        self.assertEqual(DEFAULT_CATEGORY_TARGETS["gpu"], 7)
        self.assertEqual(DEFAULT_CATEGORY_TARGETS["cpu"], 7)
        self.assertEqual(DEFAULT_CATEGORY_TARGETS["mobo"], 7)
        self.assertEqual(DEFAULT_CATEGORY_TARGETS["ram"], 5)
        self.assertEqual(DEFAULT_CATEGORY_TARGETS["psu"], 5)

        # Standalone deal selectors default to limit=7 for GPU, CPU, and MOBO
        import inspect
        self.assertEqual(inspect.signature(select_top_gpu_deals).parameters["limit"].default, 7)
        self.assertEqual(inspect.signature(select_top_cpu_platform_deals).parameters["limit"].default, 7)
        self.assertEqual(inspect.signature(select_top_mobo_deals).parameters["limit"].default, 7)

        # Pareto mobo selector defaults to per_socket_ddr=7
        self.assertEqual(inspect.signature(_select_pareto_mobos).parameters["per_socket_ddr"].default, 7)

    def test_forced_undervolt_scam_vs_voluntary_enthusiast_undervolt(self):
        gpu_spec = identify_gpu("HP RTX 4070 Ti 12 GB")
        bad_uv = GPUScamDetector().analyze_listing(
            {"title": "HP rtx 4070 ti 12 gb", "price": 21000, "has_olx_delivery": True, "photos_count": 5},
            {"description": "Стан: На стокових частотах показує себе не стабільно. Щоб відеокарта нормально працювала, потрібно зафіксувати андервольтинг на 825 мілівольтах."},
            gpu_spec,
        )
        self.assertTrue(len(bad_uv["red_flags"]) > 0)
        self.assertTrue(is_listing_disqualified(bad_uv))

        clean_uv = GPUScamDetector().analyze_listing(
            {"title": "RTX 4070 Ti 12GB Gaming X Trio", "price": 25000, "has_olx_delivery": True, "photos_count": 6},
            {"description": "Карта в ідеальному стані, без майнінгу, розгонів чи андервольтингу. Користувався дбайливо, пломба на місці, будь-які тести."},
            gpu_spec,
        )
        self.assertEqual(clean_uv["red_flags"], [])
        self.assertFalse(is_listing_disqualified(clean_uv))

    def test_ram_inverted_combo_and_builder_efficiency_tiebreakers(self):
        # 1. 'DDR4 8x2(16)' must parse as 16GB (2x8GB), never falling through to 64GB
        ram_inv = identify_ram("Оперативна пам'ять DDR4 8x2(16) CL19 4800 Mhz Kingston HyperX")
        self.assertIsNotNone(ram_inv)
        self.assertEqual(ram_inv["total_gb"], 16)
        self.assertEqual(ram_inv["module_count"], 2)

        # 2. In 'best' and 'max-perf', identical GPU+CPU+VRM-tier build with a great deal Mobo/RAM beats an overpriced Mobo/RAM
        g_spec = identify_gpu("RX 6900 XT")
        c_spec = identify_cpu("Ryzen 7 5800X3D")
        m_spec = identify_motherboard("Gigabyte B550M")
        r_spec = identify_ram("Kingston Fury DDR4 16GB (2x8GB) 3200MHz CL16")
        p_spec = identify_psu("Seasonic Focus 750W Gold")
        clean_ev = {"risk_score": 5, "red_flags": [], "warnings": [], "audit": None}

        g_cand = {"id": "g", "model": g_spec["model"], "spec": g_spec, "price": 15500.0, "fps_1440p": 91.0, "fps_1080p": 114.0, "vram_gb": 16, "tdp_watts": 300, "discount_pct": 24.0, "eval": clean_ev}
        c_cand = {"id": "c", "model": c_spec["model"], "spec": c_spec, "socket": "AM4", "price": 8600.0, "fps_gaming": 196.0, "cores": 8, "threads": 16, "tdp_watts": 105, "discount_pct": 35.0, "eval": clean_ev}
        p_cand = {"id": "p", "model": p_spec["model"], "spec": p_spec, "wattage": 750, "tier": "Tier A", "efficiency": "Gold", "price": 2200.0, "discount_pct": 20.0, "eval": clean_ev}

        m_deal = {"id": "m_deal", "model": m_spec["model"], "spec": m_spec, "socket": "AM4", "ddr_type": "DDR4", "vrm_tier": "B-Tier", "price": 2000.0, "discount_pct": 50.0, "eval": clean_ev}
        m_overpriced = {"id": "m_over", "model": m_spec["model"], "spec": m_spec, "socket": "AM4", "ddr_type": "DDR4", "vrm_tier": "B-Tier", "price": 4700.0, "discount_pct": -10.0, "is_new": True, "condition": "new", "eval": clean_ev}
        r_deal = {"id": "r_deal", "model": "Kingston", "spec": r_spec, "gen": "DDR4", "total_gb": 16, "price": 1500.0, "discount_pct": 40.0, "eval": clean_ev}

        b_smart = {"gpu": g_cand, "cpu": c_cand, "mobo": m_deal, "ram": r_deal, "psu": p_cand, "total_cost": 29800.0}
        b_waste = {"gpu": g_cand, "cpu": c_cand, "mobo": m_overpriced, "ram": r_deal, "psu": p_cand, "total_cost": 32500.0}

        for mode_name in ("best", "max-perf", "sweet-spot"):
            prof = resolve_mode(mode_name)
            self.assertGreater(
                score_build(b_smart, 38000.0, prof),
                score_build(b_waste, 38000.0, prof),
                f"{mode_name} mode should prefer the cheaper B-Tier board with identical FPS and VRM tier",
            )

    def test_no_video_output_and_component_defect_disqualifications(self):
        from extensions.pc.mobo_scam_detector import MotherboardScamDetector

        gpu_spec = identify_gpu("PALIT RTX 3060 TI 8GB")
        # 1. Reversed 'картинки нема але вентиляторы крутиться'
        no_pic = GPUScamDetector().analyze_listing(
            {"title": "відеокарта PALIT RTX 3060TI 8GB(читати опис)", "price": 4990, "has_olx_delivery": True, "photos_count": 4},
            {"description": "Відеокарта нормально працювала, грав в ігри. Якщо підключити відеокарту до компа картинки нема але вентиляторы крутиться, відео карта тепла. В комплекті є коробка"},
            gpu_spec,
        )
        self.assertTrue(len(no_pic["red_flags"]) > 0)
        self.assertTrue(is_listing_disqualified(no_pic))

        # 2. Russian 'Не выводит изображение вскорее всего отвал чипа'
        bga_dead = GPUScamDetector().analyze_listing(
            {"title": "1060 6gb msi aero oc", "price": 2800, "has_olx_delivery": True, "photos_count": 3},
            {"description": "Не выводит изображение вскорее всего отвал чипа"},
            identify_gpu("MSI GTX 1060 6GB"),
        )
        self.assertTrue(len(bga_dead["red_flags"]) > 0)
        self.assertTrue(is_listing_disqualified(bga_dead))

        # 3. Torn socket pin ('задел один пин на сокете. В итоге вырвал')
        mobo_pin = MotherboardScamDetector().analyze_listing(
            {"title": "Asus Prime B460I-Plus", "price": 1150, "has_olx_delivery": True, "photos_count": 4},
            {"description": "Материнская плата была полностью рабочая, пока не полез менять термопасту и не задел один пин на сокете. В итоге вырвал."},
            identify_motherboard("Asus Prime B460I-Plus"),
        )
        self.assertTrue(len(mobo_pin["red_flags"]) > 0)
        self.assertTrue(is_listing_disqualified(mobo_pin))

        # 4. 'Детали на 2 фото' without explicit redirect is allowed; 'надам всі тести за проханням' is a positive trust signal
        clean_photo_and_tests = GPUScamDetector().analyze_listing(
            {"title": "RTX 4070 12GB", "price": 20000, "has_olx_delivery": True, "photos_count": 5},
            {"description": "Деталі на 2 фото. Надам всі тести за проханням."},
            identify_gpu("RTX 4070"),
        )
        self.assertEqual(clean_photo_and_tests["red_flags"], [])
        self.assertFalse(is_listing_disqualified(clean_photo_and_tests))
        self.assertTrue(any("tests offered" in ts.lower() for ts in clean_photo_and_tests["trust_signals"]))

        # Explicit off-platform redirect on photo #2 is still flagged
        redirect_photo = GPUScamDetector().analyze_listing(
            {"title": "RTX 4070 12GB", "price": 20000, "has_olx_delivery": True, "photos_count": 5},
            {"description": "Пишіть в телеграм на 2 фото"},
            identify_gpu("RTX 4070"),
        )
        self.assertTrue(len(redirect_photo["red_flags"]) > 0)
        self.assertTrue(is_listing_disqualified(redirect_photo))


if __name__ == "__main__":
    unittest.main()
