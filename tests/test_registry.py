"""
Unit Tests for Hardware Market Registry Tools.

Tests:
- Submission validation and AST security checks
- SHA256 calculation for single files and directory packages
- Subsystem contract verification
- Master index compilation and consistency
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_index import compile_registry, compute_directory_hash, compute_file_hash
from scripts.validate_submission import validate_module_manifest


class TestRegistryTools(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="registry_test_")
        self.root = Path(self.tmp_dir)

        # Setup standard directory structure
        for sub in [
            "modules/info_providers",
            "modules/scam_analyser",
            "modules/component_analyser",
            "modules/build_composer",
            "modules/ai_providers",
            "bundles",
            "scripts",
        ]:
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_valid_single_file_module_passes(self):
        mod_file = self.root / "modules/scam_analyser/safe_mod.py"
        mod_file.write_text(
            "class SafeAnalyser:\n"
            "    name = 'safe_mod'\n"
            "    def analyze(self, item, detail=None, spec=None):\n"
            "        return {'risk_score': 0}\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/scam_analyser/safe_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "safe_mod",
                "subsystem": "scam_analyser",
                "domain": "hardware_pc",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/safe_mod.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertTrue(rep.is_valid, rep.violations)
        self.assertEqual(len(rep.violations), 0)
        self.assertEqual(rep.computed_sha256, compute_file_hash(mod_file))

    def test_malicious_code_rejected(self):
        mod_file = self.root / "modules/info_providers/bad_mod.py"
        mod_file.write_text(
            "import subprocess\n"
            "class BadProvider:\n"
            "    def adapt_item(self, raw):\n"
            "        subprocess.run(['ls'])\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/info_providers/bad_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "bad_mod",
                "subsystem": "info_providers",
                "domain": "hardware_pc",
                "version": "1.0.0",
                "author": "Hacker",
                "source_type": "single_file",
                "download_url": "modules/info_providers/bad_mod.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("subprocess" in v for v in rep.violations))

    def test_pickle_and_gc_rejected(self):
        mod_file = self.root / "modules/scam_analyser/pickle_mod.py"
        mod_file.write_text(
            "import pickle\n"
            "class PickleAnalyser:\n"
            "    def analyze(self, item, detail=None, spec=None):\n"
            "        return pickle.loads(b'...')\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/scam_analyser/pickle_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "pickle_mod",
                "subsystem": "scam_analyser",
                "domain": "hardware_pc",
                "version": "1.0.0",
                "author": "Hacker",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/pickle_mod.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("pickle" in v for v in rep.violations))

    def test_frame_introspection_and_dynamic_getattr_rejected(self):
        mod_file = self.root / "modules/build_composer/frame_mod.py"
        mod_file.write_text(
            "import os\n"
            "class FrameComposer:\n"
            "    def compose(self, pool, budget):\n"
            "        fn = ''.join(['s', 'y', 's', 't', 'e', 'm'])\n"
            "        getattr(os, fn)('ls')\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/build_composer/frame_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "frame_mod",
                "subsystem": "build_composer",
                "domain": "general",
                "version": "1.0.0",
                "author": "Hacker",
                "source_type": "single_file",
                "download_url": "modules/build_composer/frame_mod.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("obfuscated attribute" in v for v in rep.violations))

    def test_file_write_attempt_rejected(self):
        mod_file = self.root / "modules/build_composer/writer_mod.py"
        mod_file.write_text(
            "class WriterComposer:\n"
            "    def compose(self, pool, budget):\n"
            "        open('/tmp/evil.txt', 'w').write('bad')\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/build_composer/writer_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "writer_mod",
                "subsystem": "build_composer",
                "domain": "general",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/build_composer/writer_mod.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("write mode" in v for v in rep.violations))

    def test_missing_contract_rejected(self):
        mod_file = self.root / "modules/scam_analyser/incomplete.py"
        mod_file.write_text(
            "class IncompleteModule:\n"
            "    name = 'incomplete'\n"
            "    def wrong_method(self):\n"
            "        pass\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/scam_analyser/incomplete.json"
        manifest_file.write_text(
            json.dumps({
                "name": "incomplete",
                "subsystem": "scam_analyser",
                "domain": "hardware_pc",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/incomplete.py",
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("contract failure" in v for v in rep.violations))

    def test_directory_package_hash_and_validation(self):
        pkg_dir = self.root / "modules/scam_analyser/dir_pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text(
            "class DirAnalyser:\n"
            "    def analyze(self, item, detail=None, spec=None):\n"
            "        return {'risk': 0}\n",
            encoding="utf-8",
        )
        (pkg_dir / "data.json").write_text('{"key": "val"}\n', encoding="utf-8")

        expected_hash = compute_directory_hash(pkg_dir)

        manifest_file = self.root / "modules/scam_analyser/dir_pkg.json"
        manifest_file.write_text(
            json.dumps({
                "name": "dir_pkg",
                "subsystem": "scam_analyser",
                "domain": "hardware_pc",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "directory",
                "download_url": "modules/scam_analyser/dir_pkg",
                "sha256": expected_hash,
            }),
            encoding="utf-8",
        )

        rep = validate_module_manifest(manifest_file, self.root)
        self.assertTrue(rep.is_valid, rep.violations)
        self.assertEqual(rep.computed_sha256, expected_hash)

    def test_compile_registry_builds_valid_json(self):
        # Create one module and one bundle
        mod_file = self.root / "modules/scam_analyser/test_mod.py"
        mod_file.write_text(
            "class TestMod:\n"
            "    def analyze(self, item, detail=None, spec=None): return {}\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/scam_analyser/test_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "test_mod",
                "subsystem": "scam_analyser",
                "domain": "general",
                "version": "1.0.0",
                "author": "Author",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/test_mod.py",
            }),
            encoding="utf-8",
        )

        bundle_file = self.root / "bundles/sample.json"
        bundle_file.write_text(
            json.dumps({
                "name": "sample",
                "description": "Sample bundle",
                "modules": ["test_mod"],
            }),
            encoding="utf-8",
        )

        compiled = compile_registry(self.root, write=True)
        self.assertEqual(len(compiled["modules"]), 1)
        self.assertEqual(compiled["modules"][0]["name"], "test_mod")
        self.assertIsNotNone(compiled["modules"][0]["sha256"])
        self.assertEqual(len(compiled["bundles"]), 1)

        # Check compiled file written to disk
        reg_file = self.root / "registry.json"
        self.assertTrue(reg_file.is_file())

    def test_pathlib_open_write_and_dynamic_mode_rejected(self):
        # 1. Path.open with write mode
        mod_file = self.root / "modules/build_composer/path_writer.py"
        mod_file.write_text(
            "from pathlib import Path\n"
            "class PathComposer:\n"
            "    def compose(self, pool, budget):\n"
            "        p = Path('/tmp/test')\n"
            "        f = p.open('w')\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/build_composer/path_writer.json"
        manifest_file.write_text(
            json.dumps({
                "name": "path_writer",
                "subsystem": "build_composer",
                "domain": "general",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/build_composer/path_writer.py",
            }),
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("write mode" in v for v in rep.violations))

        # 2. Dynamic mode variable in open
        mod_file.write_text(
            "class DynamicOpenComposer:\n"
            "    def compose(self, pool, budget):\n"
            "        m = 'w'\n"
            "        open('/tmp/test', m)\n",
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("non-constant mode" in v for v in rep.violations))

    def test_socket_and_shutil_rejected(self):
        mod_file = self.root / "modules/info_providers/socket_mod.py"
        mod_file.write_text(
            "import socket\n"
            "class SocketProvider:\n"
            "    def adapt_item(self, raw):\n"
            "        s = socket.socket()\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/info_providers/socket_mod.json"
        manifest_file.write_text(
            json.dumps({
                "name": "socket_mod",
                "subsystem": "info_providers",
                "domain": "general",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/info_providers/socket_mod.py",
            }),
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("socket" in v for v in rep.violations))

    def test_dependency_specs_validation(self):
        mod_file = self.root / "modules/scam_analyser/dep_mod.py"
        mod_file.write_text(
            "class DepAnalyser:\n"
            "    def analyze(self, item, detail=None, spec=None):\n"
            "        return {}\n",
            encoding="utf-8",
        )
        manifest_file = self.root / "modules/scam_analyser/dep_mod.json"

        # Valid dependencies
        manifest_file.write_text(
            json.dumps({
                "name": "dep_mod",
                "subsystem": "scam_analyser",
                "domain": "general",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/dep_mod.py",
                "dependencies": ["base_helper>=1.2.0", "core_util==2.0.0"],
            }),
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertTrue(rep.is_valid)

        # Self-dependency rejected
        manifest_file.write_text(
            json.dumps({
                "name": "dep_mod",
                "subsystem": "scam_analyser",
                "domain": "general",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "single_file",
                "download_url": "modules/scam_analyser/dep_mod.py",
                "dependencies": ["dep_mod>=1.0.0"],
            }),
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("cannot depend on itself" in v for v in rep.violations))

    def test_extension_directory_package_validation_and_compilation(self):
        ext_dir = self.root / "modules" / "extensions" / "my_rig"
        ext_dir.mkdir(parents=True)
        (ext_dir / "__init__.py").write_text("domain_id = 'my_rig'\n", encoding="utf-8")
        (ext_dir / "layout.py").write_text("# layout\n", encoding="utf-8")

        manifest_file = self.root / "modules" / "extensions" / "my_rig.json"
        manifest_file.write_text(
            json.dumps({
                "name": "my_rig",
                "subsystem": "extension",
                "domain": "custom",
                "version": "1.0.0",
                "author": "Tester",
                "source_type": "directory",
                "download_url": "modules/extensions/my_rig",
            }),
            encoding="utf-8",
        )
        rep = validate_module_manifest(manifest_file, self.root)
        self.assertTrue(rep.is_valid, rep.violations)
        self.assertEqual(len(rep.violations), 0)

        compiled = compile_registry(self.root, write=False)
        mod = next((m for m in compiled["modules"] if m["name"] == "my_rig"), None)
        self.assertIsNotNone(mod)
        self.assertEqual(mod["subsystem"], "extension")
        self.assertEqual(mod["source_type"], "directory")
        self.assertEqual(mod["sha256"], compute_directory_hash(ext_dir))

    def test_component_analyser_and_ai_provider_reference_modules(self):
        ssd_manifest = REPO_ROOT / "modules" / "component_analyser" / "nvme_ssd_analyser.json"
        ai_manifest = REPO_ROOT / "modules" / "ai_providers" / "mistral_provider.json"

        rep_ssd = validate_module_manifest(ssd_manifest, REPO_ROOT)
        self.assertTrue(rep_ssd.is_valid, rep_ssd.violations)

        rep_ai = validate_module_manifest(ai_manifest, REPO_ROOT)
        self.assertTrue(rep_ai.is_valid, rep_ai.violations)

        knapset_core = REPO_ROOT.parent / "knapset"
        if str(knapset_core) not in sys.path:
            sys.path.insert(0, str(knapset_core))

        from modules.component_analyser.nvme_ssd_analyser import NVMeSSDAnalyser
        from modules.ai_providers.mistral_provider import MistralAIProvider

        specs = NVMeSSDAnalyser().identify("Samsung 990 Pro 2TB M.2 NVMe")
        self.assertIsNotNone(specs)
        self.assertEqual(specs["capacity_gb"], 2000)
        self.assertEqual(specs["interface"], "PCIe 4.0 x4")

        provider = MistralAIProvider()
        res = provider.complete("Inspect GPU")
        self.assertEqual(res["verdict"], "ERROR")


if __name__ == "__main__":
    unittest.main()
