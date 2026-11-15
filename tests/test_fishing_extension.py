"""
Unit Tests for Fishing Tackle Set Synthesizer Extension.
"""

from __future__ import annotations

import sys
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

from extensions.fishing import FishingDomainExtension
from set_synthesizer import synthesize_domain_sets


class TestFishingPresetCompatibility(unittest.TestCase):
    def setUp(self):
        self.fishing_ext = FishingDomainExtension()
        self.layout = self.fishing_ext.get_layout()
        self.rules = {r.name: r for r in self.layout.compatibility_rules}

    def test_rod_bait_test_rule(self):
        rule = self.rules["rod_bait_test"]

        ultralight_rod = {"spec": {"test_min_g": 1.0, "test_max_g": 7.0}}
        micro_jig = {"spec": {"weight_g": 3.5}}
        heavy_cage = {"spec": {"weight_g": 90.0}}

        # Ultralight + MicroJig (3.5g in [1..7]) -> OK
        ok1, reason1 = rule.evaluate({"rod": ultralight_rod, "bait": micro_jig})
        self.assertTrue(ok1)
        self.assertIsNone(reason1)

        # Ultralight + Heavy Feeder Cage (90g > 7g) -> Incompatible
        ok2, reason2 = rule.evaluate({"rod": ultralight_rod, "bait": heavy_cage})
        self.assertFalse(ok2)
        self.assertIn("exceeds", reason2)

    def test_rod_reel_balance_rule(self):
        rule = self.rules["rod_reel_balance"]

        ultralight_rod = {"spec": {"power_class": "Ultralight", "test_max_g": 7.0}}
        reel_2000 = {"spec": {"spool_size": 2000}}
        reel_5000 = {"spec": {"spool_size": 5000}}

        # Ultralight + 2000 spool -> Balanced
        ok1, _ = rule.evaluate({"rod": ultralight_rod, "reel": reel_2000})
        self.assertTrue(ok1)

        # Ultralight + 5000 spool -> Oversized / unbalanced
        ok2, reason2 = rule.evaluate({"rod": ultralight_rod, "reel": reel_5000})
        self.assertFalse(ok2)
        self.assertIn("Tackle imbalance", reason2)

    def test_line_drag_safety_rule(self):
        rule = self.rules["line_drag_safety"]

        reel_light = {"spec": {"drag_kg": 5.0}}
        line_light = {"spec": {"test_kg": 4.5}}
        line_monster = {"spec": {"test_kg": 25.0}}

        # 4.5kg line on 5kg drag -> Safe
        ok1, _ = rule.evaluate({"reel": reel_light, "line": line_light})
        self.assertTrue(ok1)

        # 25kg line on 5kg drag (5x drag) -> Dangerous gear strain
        ok2, reason2 = rule.evaluate({"reel": reel_light, "line": line_monster})
        self.assertFalse(ok2)
        self.assertIn("dangerously exceeds reel drag", reason2)


class TestFishingSynthesis(unittest.TestCase):
    def test_synthesize_fishing_sets(self):
        fishing_ext = FishingDomainExtension()
        layout = fishing_ext.get_layout()
        w_reg = fishing_ext.get_weights_registry()
        scorer = fishing_ext.get_scorer()
        candidates = fishing_ext.load_candidates(budget=6000.0)

        profile = w_reg.resolve_profile("spinning-light")
        sets = synthesize_domain_sets(
            layout=layout,
            scorer=scorer,
            profile=profile,
            candidate_pool=candidates,
            budget=6000.0,
            top_n=5,
        )

        self.assertGreater(len(sets), 0)
        top = sets[0]
        comps = top["components"]

        # Validate sections present
        self.assertIn("rod", comps)
        self.assertIn("reel", comps)
        self.assertIn("line", comps)
        self.assertIn("bait", comps)
        self.assertIn("tackle", comps)

        # Validate total cost <= budget
        self.assertLessEqual(top["total_cost"], 6000.0)

        # Validate rules satisfied on top set
        valid, errs = layout.validate_combination(comps)
        self.assertTrue(valid, f"Validation errors on top set: {errs}")

        # In spinning-light mode, top rod should be light/ultralight
        power = comps["rod"]["spec"]["power_class"]
        self.assertIn(power, ("Light", "Ultralight", "Medium-Light"))


if __name__ == "__main__":
    unittest.main()
