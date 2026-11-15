import unittest
import sys
import os
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent / "modules" / "extensions" / "pc"
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ram_database import extract_form_factor, identify_ram
from layout import create_pc_layout


class TestRamFormFactorRigorous(unittest.TestCase):
    def test_impact_brand_classified_as_sodimm(self):
        """Kingston Fury Impact and HyperX Impact must always classify as SODIMM, never desktop UDIMM."""
        self.assertEqual(extract_form_factor("Kingston Fury Impact DDR4 16GB"), "SODIMM")
        self.assertEqual(extract_form_factor("HyperX Impact 8GB DDR4 2400MHz"), "SODIMM")
        self.assertEqual(extract_form_factor("Fury Impact 32GB 3200MHz"), "SODIMM")

    def test_laptop_signal_overrides_weak_desktop_line(self):
        """When a line like Vengeance, Ballistix, or Ripjaws is accompanied by laptop/SODIMM markers, SODIMM wins."""
        self.assertEqual(extract_form_factor("Corsair Vengeance SODIMM 16GB DDR4"), "SODIMM")
        self.assertEqual(extract_form_factor("G.Skill Ripjaws SO-DIMM DDR4 3200"), "SODIMM")
        self.assertEqual(extract_form_factor("Crucial Ballistix для ноутбука 16GB"), "SODIMM")

    def test_manufacturer_part_numbers(self):
        """Part numbers must decisively distinguish desktop UDIMM from laptop SODIMM."""
        # Samsung
        self.assertEqual(extract_form_factor("Samsung M378A1K43CB2-CTD 8GB"), "UDIMM")
        self.assertEqual(extract_form_factor("Samsung M471A1K43CB1-CTD 8GB"), "SODIMM")
        # SK Hynix
        self.assertEqual(extract_form_factor("SK hynix HMA81GU6CJR8N-VK 8GB"), "UDIMM")
        self.assertEqual(extract_form_factor("SK hynix HMA81GS6AFR8N-VK 8GB"), "SODIMM")
        # Crucial
        self.assertEqual(extract_form_factor("Crucial CT8G4DFRA32A 8GB DDR4"), "UDIMM")
        self.assertEqual(extract_form_factor("Crucial CT8G4SFRA32A 8GB DDR4"), "SODIMM")
        self.assertEqual(extract_form_factor("Crucial Pro CP2K48G56C46U5 96GB Kit"), "UDIMM")
        # Kingston
        self.assertEqual(extract_form_factor("Kingston KVR26N19S8/8 8GB"), "UDIMM")
        self.assertEqual(extract_form_factor("Kingston KVR26S19S8/8 8GB"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston KF432C16BB/16 16GB"), "UDIMM")
        self.assertEqual(extract_form_factor("Kingston KF432S20IB/16 16GB"), "SODIMM")

    def test_dual_target_conflicting_mentions_yield_unknown(self):
        """Listings mentioning both desktop and laptop targets must yield UNKNOWN, not UDIMM."""
        self.assertEqual(extract_form_factor("Оперативна пам'ять 16GB DDR4 для ПК та ноутбука"), "UNKNOWN")
        self.assertEqual(extract_form_factor("RAM 8GB DDR4 desktop / laptop"), "UNKNOWN")
        self.assertEqual(extract_form_factor("Планка 16GB для комп'ютера або ноута"), "UNKNOWN")

    def test_no_marker_yields_unknown(self):
        """Unmarked listings with no product line or form factor indicator must be UNKNOWN."""
        self.assertEqual(extract_form_factor("Пам'ять 16GB DDR4 3200MHz"), "UNKNOWN")
        self.assertEqual(extract_form_factor("DDR5 32GB 6000MHz"), "UNKNOWN")
        self.assertEqual(extract_form_factor("Goodram 8GB 2666"), "UNKNOWN")

    def test_explicit_desktop_markers(self):
        """Explicit desktop markers and lines without laptop keywords yield UDIMM."""
        self.assertEqual(extract_form_factor("Kingston Fury Beast 16GB DDR4 3200"), "UDIMM")
        self.assertEqual(extract_form_factor("G.Skill Trident Z5 32GB DDR5"), "UDIMM")
        self.assertEqual(extract_form_factor("16GB DDR4 DIMM для ПК"), "UDIMM")

    def test_server_ecc_reg(self):
        """Server ECC registered memory must classify as ECC_REG."""
        self.assertEqual(extract_form_factor("Samsung 32GB 2Rx4 PC4-2400T ECC REG"), "ECC_REG")
        self.assertEqual(extract_form_factor("Hynix 64GB DDR4 2666V LRDIMM серверна"), "ECC_REG")

    def test_samsung_m474_ecc_sodimm_not_misclassified_as_server_ecc(self):
        """Samsung M474 is an ECC SO-DIMM (laptop/small-form-factor).

        Must classify as SODIMM even if ECC or server keywords are mentioned.
        """
        self.assertEqual(
            extract_form_factor("16 GB Samsung M474A2K43BB1-CPBQ модуль пам'яті 16 ГБ DDR4 SO-DIMM (ECC)"),
            "SODIMM",
        )
        self.assertEqual(
            extract_form_factor("Samsung M474A2K43BB1 16GB DDR4 ECC REG"),
            "SODIMM",
        )

    def test_ecc_udimm_unbuffered_classification(self):
        """Hynix U7 (HMA...U7), Samsung M391, and Kingston KVR..E are unbuffered ECC UDIMMs.

        Must classify as ECC_UDIMM, not plain UDIMM.
        """
        self.assertEqual(extract_form_factor("SK hynix 8GB DDR4 2133 HMA41GU7AFR8N-TF"), "ECC_UDIMM")
        self.assertEqual(extract_form_factor("Samsung 16GB DDR4 3200 M391A2G43BB2-CWE"), "ECC_UDIMM")
        self.assertEqual(extract_form_factor("Kingston ValueRAM 8GB KVR16E11/8"), "ECC_UDIMM")

    def test_dimm_inside_sodimm_does_not_misclassify_as_desktop(self):
        """A title with SO-DIMM and no part number must never trigger desktop UDIMM."""
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 SO-DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Crucial 8GB DDR4 SODIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("DDR4 16GB SO-DIMM для ноутбука"), "SODIMM")

    def test_sodimm_spaced_dotted_and_cyrillic_lookalikes(self):
        """Verifies spaced, dotted, and Cyrillic lookalikes without part numbers are strictly SODIMM."""
        # Spaced and dotted variants
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 SO DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 so-dimm"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 SODIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 S.O.DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 S.O. DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 S.O.-DIMM"), "SODIMM")
        # Cyrillic lookalikes (Cyrillic 'О', 'С', 'ДИММ')
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 SО-DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 SО DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 S.О.DIMM"), "SODIMM")
        self.assertEqual(extract_form_factor("Crucial 16GB DDR4 СО ДИММ"), "SODIMM")
        self.assertEqual(extract_form_factor("Crucial 16GB DDR4 со-димм"), "SODIMM")

    def test_cyrillic_preposition_c_near_dimm_negative_cases(self):
        """Phrases containing Cyrillic preposition 'с' near DIMM (e.g. 'с радиатором', 'с коробкой')
        must NOT falsely match as SODIMM and must remain valid desktop UDIMM.
        """
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 DIMM с радиатором"), "UDIMM")
        self.assertEqual(extract_form_factor("Crucial 8GB DDR4 DIMM с коробкой"), "UDIMM")
        self.assertEqual(extract_form_factor("16GB DDR4 DIMM с подсветкой"), "UDIMM")
        self.assertEqual(extract_form_factor("G.Skill Ripjaws 32GB DDR4 DIMM с гарантией"), "UDIMM")
        self.assertEqual(extract_form_factor("DIMM с оптового склада DDR4 16GB"), "UDIMM")
        self.assertEqual(extract_form_factor("Kingston 16GB DDR4 DIMM с одним модулем"), "UDIMM")

    def test_explicit_markers_and_part_numbers_override_dual_target_rule(self):
        """Explicit SO-DIMM, RDIMM/ECC, and part numbers must be checked before dual-target mentions."""
        # Explicit SO-DIMM in title overrides dual mention
        self.assertEqual(
            extract_form_factor("Crucial 8GB SO-DIMM для ноутбуків та компактних ПК"),
            "SODIMM",
        )
        # Explicit RDIMM in title overrides dual mention
        self.assertEqual(
            extract_form_factor("Samsung 32GB RDIMM для серверів та робочих станцій ПК"),
            "ECC_REG",
        )
        # Part-number signature overrides dual mention
        self.assertEqual(
            extract_form_factor("Samsung M471A1K43CB1-CTD 8GB для комп'ютера або ноута"),
            "SODIMM",
        )

    def test_kompaktnykh_does_not_falsely_match_computer_pattern(self):
        """Word 'компактних' must NOT trigger desktop computer pattern."""
        self.assertEqual(
            extract_form_factor("RAM 8GB DDR4 SO-DIMM для компактних систем"),
            "SODIMM",
        )

    def test_negated_phrases_treated_separately(self):
        """Negated phrases ('не підходить для', 'не підійде') must be neutralized and not trigger matches.
        Tests both word orders and confirms 'not for sale' is unaffected.
        """
        # Order 1: negation before device nouns ("не підходить для ПК", "не для ноутбука")
        self.assertEqual(
            extract_form_factor("16GB DDR4 не підходить для ПК або ноутбуків, серверна пам'ять RDIMM"),
            "ECC_REG",
        )
        self.assertEqual(
            extract_form_factor("Kingston 16GB DDR4 DIMM (не для ноутбука!)"),
            "UDIMM",
        )
        self.assertEqual(
            extract_form_factor("не підходить для ПК HMA41GU7AFR8N"),
            "ECC_UDIMM",  # Part number HMA...U7 preserved and not deleted!
        )

        # Order 2: negation after device nouns ("десктоп (для ноутбука не підійде)")
        self.assertEqual(
            extract_form_factor("Crucial 16GB DDR4 десктоп (для ноутбука не підійде)"),
            "UDIMM",
        )
        self.assertEqual(
            extract_form_factor("Оперативна пам'ять 16GB DDR4 (для ПК не підходить), тільки серверна RDIMM"),
            "ECC_REG",
        )

        # English 'not for' should only match device words, not unrelated phrases like 'not for sale'
        self.assertEqual(
            extract_form_factor("Kingston 16GB DDR4 DIMM (sample, not for sale)"),
            "UDIMM",
        )

        # Exact phrasing: 'Kingston DIMM не для ноутбука' must leave UDIMM intact
        self.assertEqual(
            extract_form_factor("Kingston DIMM не для ноутбука"),
            "UDIMM",
        )

    def test_identify_ram_weighs_title_first_and_resolves_disagreeing_evidence(self):
        """identify_ram weighs title first:
        - Unlabelled title gets form factor from description.
        - Cutoff phrases ('також є', 'в наявності також') trim unrelated products in description.
        - Clear explicit title wins over loose/unrelated description mentions.
        - When evidence directly pertains to the same module (e.g. part number in title contradicted by description),
          resolves to UNKNOWN.
        """
        # 1. Unlabelled title, description specifies SODIMM -> SODIMM
        res1 = identify_ram("Kingston 16GB DDR4 3200MHz", "Пам'ять SO-DIMM для ноутбука")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["form_factor"], "SODIMM")

        # 2. Goodram case: Explicit title ("для ноутбуків"), description lists other desktop products after cutoff -> SODIMM
        res_goodram = identify_ram(
            "Goodram 8GB DDR4 для ноутбуків",
            "Пам'ять 8GB DDR4 в ідеалі. Також є комплект для ПК Kingston 32GB DDR4.",
        )
        self.assertIsNotNone(res_goodram)
        self.assertEqual(res_goodram["form_factor"], "SODIMM")

        # 3. Explicit title ("SO-DIMM") wins over loose unrelated description mention
        res_explicit = identify_ram("Crucial 8GB DDR4 SO-DIMM", "В наявності також пам'ять UDIMM для настільного ПК")
        self.assertIsNotNone(res_explicit)
        self.assertEqual(res_explicit["form_factor"], "SODIMM")

        # 4. Weak title line (Fury Beast) with contradictory description -> UNKNOWN
        res_weak = identify_ram("Kingston Fury Beast 16GB DDR4 3200", "Оригінальний модуль пам'яті SO-DIMM для ноутбука")
        self.assertIsNotNone(res_weak)
        self.assertEqual(res_weak["form_factor"], "UNKNOWN")
        self.assertIn("AMBIGUOUS FORM FACTOR", res_weak["risk_notes"])

        # 5. Part number in title contradicts description about the same module -> UNKNOWN
        res_pn_conflict = identify_ram("Samsung M471A1K43CB1-CTD 8GB DDR4", "Модуль пам'яті UDIMM для стаціонарного комп'ютера ПК")
        self.assertIsNotNone(res_pn_conflict)
        self.assertEqual(res_pn_conflict["form_factor"], "UNKNOWN")
        self.assertIn("AMBIGUOUS FORM FACTOR", res_pn_conflict["risk_notes"])

        # 6. Title has NO part number, but description contains a part number contradicting the title -> UNKNOWN
        # (e.g. Title claims desktop 'для ПК', but description gives a laptop SODIMM part number M471)
        res_desc_pn_conflict = identify_ram("Оперативна пам'ять DDR4 8GB для комп'ютера ПК", "Партномер модуля: Samsung M471A1K43CB1-CTD")
        self.assertIsNotNone(res_desc_pn_conflict)
        self.assertEqual(res_desc_pn_conflict["form_factor"], "UNKNOWN")
        self.assertIn("AMBIGUOUS FORM FACTOR", res_desc_pn_conflict["risk_notes"])

        # 7. Useful accessory text after 'також є' (e.g. 'також є гарантія', 'також є коробка') is preserved and not cut off
        res_warranty = identify_ram("Kingston 16GB DDR4 3200MHz DIMM", "Відмінний стан, також є гарантія від магазину на 6 місяців та коробка.")
        self.assertIsNotNone(res_warranty)
        self.assertEqual(res_warranty["form_factor"], "UDIMM")

    def test_speed_bins_do_not_misclassify_as_server_ecc(self):
        """JEDEC speed bins (PC4-2666V, PC4-2400T, PC4-2933Y) must not misclassify desktop or laptop RAM as server ECC."""
        # Samsung M378 desktop UDIMM with PC4-2666V
        self.assertEqual(
            extract_form_factor("Samsung 8GB DDR4 PC4-2666V M378A1K43CB2-CTD для стационарного ПК"),
            "UDIMM",
        )
        # SK Hynix desktop UDIMM with PC4-2400T
        self.assertEqual(
            extract_form_factor("SK hynix 8GB DDR4 PC4-2400T HMA81GU6CJR8N-VK для стационарного ПК"),
            "UDIMM",
        )
        # SK Hynix laptop SO-DIMM with PC4-2666V
        self.assertEqual(
            extract_form_factor("SK hynix 8GB DDR4 PC4-2666V HMA81GS6AFR8N-VK SO-DIMM"),
            "SODIMM",
        )

        # Real JEDEC registered / load-reduced suffixes (-RE, -RC, etc.) must still classify as ECC_REG
        self.assertEqual(
            extract_form_factor("Samsung 16GB DDR4 PC4-2666V-RE1 M393A2K40BB1-CTD"),
            "ECC_REG",
        )
        self.assertEqual(
            extract_form_factor("SK hynix 32GB DDR4 PC4-2400T-RC0 HMA42GR7AFR4N"),
            "ECC_REG",
        )

    def test_micron_mta9asf_and_error_correction_classified_as_ecc_udimm(self):
        """Micron MTA9ASF...AZ unbuffered ECC modules and modules with error correction phrases classify as ECC_UDIMM."""
        # Micron MTA9ASF...AZ part number (AZ = UDIMM, 72-bit bus width = ECC)
        self.assertEqual(
            extract_form_factor("Micron 8GB DDR4 MTA9ASF1G72AZ-32EE1"),
            "ECC_UDIMM",
        )
        # Desktop module described as with error correction
        self.assertEqual(
            extract_form_factor("Crucial DDR4 16GB DIMM с поддержкой коррекции ошибок"),
            "ECC_UDIMM",
        )
        self.assertEqual(
            extract_form_factor("Crucial DDR4 16GB DIMM з підтримкою корекції помилок"),
            "ECC_UDIMM",
        )

    def test_negated_ecc_and_on_die_ecc_do_not_falsely_trigger_ecc_udimm(self):
        """Negated ECC ('без підтримки ECC', 'без поддержки', 'non-ecc', 'without ecc') and DDR5 on-die ECC stay UDIMM."""
        # SK hynix with explicit non-ECC text
        self.assertEqual(
            extract_form_factor("SK hynix 8GB DDR4 PC4-2666V HMA81GU6CJR8N-VK для стационарного ПК (без поддержки ECC)"),
            "UDIMM",
        )
        # Ukrainian 'без підтримки корекції помилок'
        self.assertEqual(
            extract_form_factor("Crucial DDR4 16GB DIMM без підтримки корекції помилок"),
            "UDIMM",
        )
        # English 'without ECC'
        self.assertEqual(
            extract_form_factor("Samsung DDR4 8GB DIMM without ECC support"),
            "UDIMM",
        )
        # DDR4 non-ecc unbuffered
        self.assertEqual(
            extract_form_factor("G.Skill DDR4 16GB non-ecc unbuffered DIMM"),
            "UDIMM",
        )
        # DDR5 On-Die ECC marketing descriptions must not become ECC_UDIMM
        self.assertEqual(
            extract_form_factor("Kingston FURY Beast DDR5 32GB 6000MHz (unbuffered, on-die ECC для максимальної стабільності)"),
            "UDIMM",
        )
        self.assertEqual(
            extract_form_factor("Оперативна пам’ять KINGBANK DDR5 RGB 32GB (2×16GB) 6400 MHz DIMM з On-Die ECC"),
            "UDIMM",
        )

    def test_negative_registered_suffix_tokens(self):
        """Tokens ending in -ra, -rb, -r, -l or words like x-ray must NOT misclassify desktop memory as server ECC_REG."""
        self.assertEqual(
            extract_form_factor("Desktop PC x-ray DDR4 16GB DIMM"),
            "UDIMM",
        )
        self.assertEqual(
            extract_form_factor("Crucial Ballistix DDR4 16GB CT8G4DFRA32A"),
            "UDIMM",
        )
        self.assertEqual(
            extract_form_factor("SSD PNY CS900 250GB SSD7CS900-250-RB"),
            "UNKNOWN",
        )

    def test_part_number_and_explicit_text_conflict_resolves_to_unknown(self):
        """Contradiction between part number and explicit form-factor text (KVR...S as UDIMM, KVR...N as SODIMM) -> UNKNOWN."""
        # KVR219S6/4 has SODIMM part number (S), but text states UDIMM
        self.assertEqual(
            extract_form_factor("Kingston 4GB KVR219S6/4 DDR4 UDIMM"),
            "UNKNOWN",
        )
        # KVR24N17S8/8 has desktop UDIMM part number (N), but text states SO-DIMM
        self.assertEqual(
            extract_form_factor("Kingston 8GB KVR24N17S8/8 DDR4 SO-DIMM"),
            "UNKNOWN",
        )

    def test_layout_ram_row_formatter_flags_unknown(self):
        """Row formatter in layout must show '[? Confirm DIMM]' when form factor is UNKNOWN."""
        layout = create_pc_layout()
        ram_sec = next(s for s in layout.sections if s.id == "ram")
        row_fn = ram_sec.row_formatter

        disc_dummy = lambda d: "0%"
        # UDIMM
        row_udimm = row_fn({"model": "Kingston Fury", "price": 2000, "spec": {"form_factor": "UDIMM", "module_count": 2}}, disc_dummy)
        self.assertNotIn("Confirm", row_udimm[3])

        # UNKNOWN
        row_unknown = row_fn({"model": "Generic RAM", "price": 1500, "spec": {"form_factor": "UNKNOWN", "module_count": 2}}, disc_dummy)
        self.assertIn("Confirm DIMM", row_unknown[3])

    def test_layout_compatibility_rule_pins_behavior(self):
        """Layout rule ram_desktop_form_factor:
        - UDIMM passes cleanly.
        - UNKNOWN passes (with warning/review advisory, not silently dropped).
        - SODIMM and ECC_REG fail compatibility validation.
        """
        layout = create_pc_layout()
        rule_map = {r.name: r for r in layout.compatibility_rules}
        self.assertIn("ram_desktop_form_factor", rule_map)
        rule = rule_map["ram_desktop_form_factor"]

        # UDIMM passes
        valid, msg = rule.validator({"ram": {"form_factor": "UDIMM"}})
        self.assertTrue(valid)
        self.assertIsNone(msg)

        # UNKNOWN passes (allowed to reach human review / seller confirmation)
        valid, msg = rule.validator({"ram": {"form_factor": "UNKNOWN"}})
        self.assertTrue(valid)
        self.assertIsNone(msg)

        # SODIMM fails
        valid, msg = rule.validator({"ram": {"form_factor": "SODIMM"}})
        self.assertFalse(valid)
        self.assertIn("SODIMM", msg)

        # ECC_REG fails
        valid, msg = rule.validator({"ram": {"form_factor": "ECC_REG"}})
        self.assertFalse(valid)
        self.assertIn("ECC_REG", msg)


if __name__ == "__main__":
    unittest.main()
