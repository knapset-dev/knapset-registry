#!/usr/bin/env python3
"""
Registry Master Index Compiler.

Scans modules/ and bundles/ directories, validates manifests, computes deterministic
SHA256 checksums, and compiles the consolidated registry.json file.
Zero third-party dependencies (Python Standard Library only).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Tuple


ALLOWED_SUBSYSTEMS = {
    "info_providers",
    "scam_analyser",
    "component_analyser",
    "build_composer",
    "ai_providers",
    "extension",
    "extensions",
    "preset",
    "presets",
}


def list_directory_files(dir_path: Path) -> List[str]:
    """Returns sorted relative POSIX file paths in a directory package."""
    if not dir_path.is_dir():
        return []
    rels: List[str] = []
    for item in dir_path.rglob("*"):
        if item.is_file() and "__pycache__" not in item.parts and not item.name.endswith((".pyc", ".pyo")):
            rels.append(item.relative_to(dir_path).as_posix())
    rels.sort()
    return rels


def compute_directory_hash(dir_path: Path) -> str:
    """Computes a deterministic SHA256 hash of all files in a directory package."""
    if not dir_path.is_dir():
        return ""
    files = []
    for item in dir_path.rglob("*"):
        if item.is_file() and "__pycache__" not in item.parts and not item.name.endswith((".pyc", ".pyo")):
            rel = item.relative_to(dir_path).as_posix()
            files.append((rel, item))
    files.sort(key=lambda x: x[0])
    h = hashlib.sha256()
    for rel_path, fpath in files:
        h.update(rel_path.encode("utf-8"))
        h.update(fpath.read_bytes())
    return h.hexdigest()


def compute_file_hash(file_path: Path) -> str:
    """Computes SHA256 hash of a single file."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def compile_registry(repo_root: Path, write: bool = True) -> Dict[str, Any]:
    """Compiles registry.json from modules/ and bundles/ folders."""
    modules_dir = repo_root / "modules"
    bundles_dir = repo_root / "bundles"

    modules: List[Dict[str, Any]] = []
    bundles: List[Dict[str, Any]] = []

    # 1. Process module manifests
    if modules_dir.is_dir():
        for manifest_file in sorted(modules_dir.rglob("*.json")):
            if manifest_file.name == "registry.json" or "flash_chips" in manifest_file.name:
                continue
            # Directory package metadata vs inside assets
            if manifest_file.parent.name in ALLOWED_SUBSYSTEMS:
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"Error reading manifest {manifest_file}: {e}", file=sys.stderr)
                    continue

                mod_name = data.get("name", "").strip().lower()
                subsystem = data.get("subsystem", "").strip().lower()
                source_type = data.get("source_type", "single_file")

                # Resolve payload path
                payload_rel = data.get("download_url", "")
                payload_path = repo_root / payload_rel if payload_rel else None
                if not payload_path or not payload_path.exists():
                    # Fallback to local sibling
                    if source_type == "single_file":
                        payload_path = manifest_file.parent / f"{mod_name}.py"
                    else:
                        payload_path = manifest_file.parent / mod_name

                # Auto-compute / verify sha256
                if payload_path and payload_path.exists():
                    if source_type == "single_file" and payload_path.is_file():
                        computed_sha = compute_file_hash(payload_path)
                        data["sha256"] = computed_sha
                    elif source_type == "directory" and payload_path.is_dir():
                        computed_sha = compute_directory_hash(payload_path)
                        data["sha256"] = computed_sha
                        data["files"] = list_directory_files(payload_path)

                # Standardize relative download_url
                if payload_path and payload_path.exists():
                    data["download_url"] = payload_path.relative_to(repo_root).as_posix()

                # Ensure required fields
                data.setdefault("dependencies", [])
                data.setdefault("env_keys", [])
                data.setdefault("tags", [])
                data.setdefault("trust_level", "community")

                modules.append(data)

    # 2. Process bundle manifests
    if bundles_dir.is_dir():
        for b_file in sorted(bundles_dir.glob("*.json")):
            try:
                b_data = json.loads(b_file.read_text(encoding="utf-8"))
                b_data.setdefault("tags", [])
                b_data.setdefault("modules", [])
                bundles.append(b_data)
            except Exception as e:
                print(f"Error reading bundle {b_file}: {e}", file=sys.stderr)

    modules.sort(key=lambda m: (m.get("subsystem", ""), m.get("name", "")))
    bundles.sort(key=lambda b: b.get("name", ""))

    compiled = {
        "version": "1.0.0",
        "name": "knapset-registry",
        "description": "Official open module & extension registry for Knapset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "modules": modules,
        "bundles": bundles,
    }

    if write:
        out_file = repo_root / "registry.json"
        tmp_file = repo_root / "registry.json.tmp"
        tmp_file.write_text(json.dumps(compiled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_file.replace(out_file)
        print(f"Successfully compiled registry.json ({len(modules)} modules, {len(bundles)} bundles)")

    return compiled


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile Hardware Market Registry index")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Repository root path")
    parser.add_argument("--check", action="store_true", help="Check if registry.json is up-to-date without writing")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.check:
        current_file = root / "registry.json"
        if not current_file.exists():
            print("registry.json does not exist. Run build_index.py to create it.", file=sys.stderr)
            sys.exit(1)
        current = json.loads(current_file.read_text(encoding="utf-8"))
        generated = compile_registry(root, write=False)

        # Ignore generated_at timestamp for comparison
        current_meta = {k: current.get(k) for k in ("version", "name", "description")}
        gen_meta = {k: generated.get(k) for k in ("version", "name", "description")}
        current_mods = current.get("modules", [])
        gen_mods = generated.get("modules", [])
        current_bundles = current.get("bundles", [])
        gen_bundles = generated.get("bundles", [])

        if current_meta != gen_meta or current_mods != gen_mods or current_bundles != gen_bundles:
            print("registry.json is out-of-date! Run python3 scripts/build_index.py to refresh.", file=sys.stderr)
            sys.exit(1)
        print("registry.json is up-to-date.")
    else:
        compile_registry(root, write=True)


if __name__ == "__main__":
    main()
