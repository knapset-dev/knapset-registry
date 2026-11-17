#!/usr/bin/env python3
"""
Submission Validator & AST Security Scanner for Module Registry.

Validates Pull Requests submitting new or modified modules:
- JSON manifest schema and SemVer compliance
- Static AST security analysis (zero dangerous syscalls, reflection escapes, write calls, SSRF)
- Checksum (SHA256) computation and verification
- Subsystem interface contract validation (Duck typing)
- Pure Python Standard Library enforcement (zero external pip packages)
Zero third-party dependencies.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union


ALLOWED_SUBSYSTEMS: Set[str] = {
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

BANNED_MODULES: Set[str] = {
    # System process execution & sandboxing escapes
    "subprocess",
    "pty",
    "posix",
    "ctypes",
    "winreg",
    "msvcrt",
    "multiprocessing",
    "importlib",
    "runpy",
    "code",
    "codeop",
    "webbrowser",
    "builtins",
    "sysconfig",
    "compileall",
    "pkgutil",
    # Unsafe serialization & bytecode manipulation
    "pickle",
    "shelve",
    "marshal",
    # Heap, stack frame & debugger escapes
    "inspect",
    "gc",
    "dis",
    "pdb",
    # Host filesystem mutation & manipulation
    "shutil",
    "tempfile",
    # Raw networking & listener backdoors (only urllib/http.client allowed in online providers)
    "socket",
    "socketserver",
    "http.server",
    "xmlrpc",
    "ftplib",
    "telnetlib",
    "smtplib",
    "poplib",
    "imaplib",
}

BANNED_OS_ATTRS: Set[str] = {
    # System process execution
    "system",
    "popen",
    "kill",
    "killpg",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    # Destructive & mutative filesystem modifications
    "rmdir",
    "removedirs",
    "remove",
    "unlink",
    "chmod",
    "chown",
    "lchmod",
    "lchown",
    "rename",
    "replace",
    "truncate",
    "symlink",
    "symlink_to",
    "link",
    "hardlink_to",
    "mkdir",
    "makedirs",
    "touch",
    # Privilege escalation & environment alteration
    "setuid",
    "seteuid",
    "setgid",
    "setegid",
    "putenv",
    # Process exit & debugging callbacks
    "exit",
    "_getframe",
    "settrace",
    "setprofile",
    # Shutil destruction & copying
    "rmtree",
    "move",
    "copy",
    "copy2",
    "copyfile",
    "copytree",
    "copymode",
    "copystat",
    "unpack_archive",
}

BANNED_BUILTIN_CALLS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "input",
    "_getframe",
    "exit",
    "quit",
}

BANNED_DUNDERS: Set[str] = {
    # Python object reflection
    "__class__",
    "__subclasses__",
    "__mro__",
    "__bases__",
    "__base__",
    "__globals__",
    "__builtins__",
    "__code__",
    "__closure__",
    "__func__",
    "__self__",
    "__loader__",
    "__spec__",
    "__dict__",
    "__getattribute__",
    "__reduce__",
    "__reduce_ex__",
    # Frame introspection attributes
    "f_globals",
    "f_builtins",
    "f_locals",
    "f_back",
    "f_code",
}

OFFLINE_SUBSYSTEMS: Set[str] = {
    "scam_analyser",
    "component_analyser",
    "build_composer",
}

NETWORK_MODULES: Set[str] = {
    "socket",
    "urllib",
    "http",
    "ftplib",
    "smtplib",
    "telnetlib",
    "asyncio",
    "xmlrpc",
    "ssl",
    "poplib",
    "imaplib",
    "nntplib",
    "selectors",
}

CORE_ALLOWED_MODULES: Set[str] = {
    "app_paths",
    "currency",
    "info_providers",
    "scam_analyser",
    "component_analyser",
    "build_composer",
    "ai_providers",
    "marketplace",
    "domain_layout",
    "domain_weights",
    "set_synthesizer",
    "provider_template",
    "extensions",
    "analyzer_core",
    "market_client",
    "audit_ledger",
    "ai_inspector",
    "scam_utils",
    "extension_registry",
    "olx_client",
    "audit_pipeline",
}


def _resolve_const_str(node: ast.AST) -> Optional[str]:
    """Statically resolves constant strings, concatenation, and basic f-strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_const_str(node.left)
        right = _resolve_const_str(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = []
        for val in node.values:
            s = _resolve_const_str(val)
            if s is not None:
                parts.append(s)
            else:
                return None
        return "".join(parts)
    if isinstance(node, ast.FormattedValue):
        return _resolve_const_str(node.value)
    return None


@dataclass
class ValidationReport:
    name: str
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    computed_sha256: str = ""
    methods_found: List[str] = field(default_factory=list)


class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self, subsystem: Optional[str] = None) -> None:
        self.subsystem = (subsystem or "").strip().lower()
        self.violations: List[str] = []
        self.warnings: List[str] = []
        self.stdlib_names = getattr(sys, "stdlib_module_names", frozenset())
        self.methods_found: List[str] = []

    def _check_module_name(self, mod_name: str, lineno: int) -> None:
        base_mod = mod_name.split(".")[0]
        if not base_mod:
            return

        if base_mod in BANNED_MODULES:
            self.violations.append(f"Line {lineno}: Banned module import '{mod_name}'")
            return

        if self.subsystem in OFFLINE_SUBSYSTEMS and base_mod in NETWORK_MODULES:
            self.violations.append(
                f"Line {lineno}: Subsystem '{self.subsystem}' must be offline; network module '{base_mod}' is prohibited"
            )
            return

        if self.stdlib_names:
            if base_mod not in self.stdlib_names and base_mod not in CORE_ALLOWED_MODULES:
                self.violations.append(
                    f"Line {lineno}: External dependency '{base_mod}' detected. Modules must use Python Standard Library only"
                )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module_name(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level > 0:
            self.generic_visit(node)
            return

        if node.module:
            self._check_module_name(node.module, node.lineno)
            # Check prohibited imports from os, sys, shutil
            if node.module in ("os", "sys", "shutil"):
                for alias in node.names:
                    if (
                        alias.name in BANNED_OS_ATTRS
                        or alias.name in BANNED_BUILTIN_CALLS
                        or alias.name in BANNED_DUNDERS
                        or alias.name in ("modules", "path", "_getframe", "settrace", "setprofile", "exit")
                    ):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited direct import of '{alias.name}' from {node.module}"
                        )
                    elif alias.name == "environ" and self.subsystem in OFFLINE_SUBSYSTEMS:
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited direct import of 'environ' from os in offline subsystem '{self.subsystem}'"
                        )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            val = node.value.strip().lower()
            if any(val.startswith(p) for p in ("file://", "ftp://", "gopher://", "dict://", "ldap://")):
                self.violations.append(
                    f"Line {node.lineno}: Prohibited dangerous URL scheme in literal '{node.value}'"
                )
            elif any(p in val for p in ("169.254.169.254", "http://169.254.", "https://169.254.")):
                self.violations.append(
                    f"Line {node.lineno}: Prohibited cloud metadata service endpoint in string literal"
                )
            elif self.subsystem == "info_providers" and any(
                val.startswith(p) for p in ("http://127.", "http://localhost", "http://0.0.0.0", "http://[::1]")
            ):
                self.violations.append(
                    f"Line {node.lineno}: Prohibited loopback address in marketplace info provider"
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.methods_found.append(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check open() calls whether as a builtin Name('open') or Attribute(attr='open')
        is_open_call = False
        mode_node = None
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            is_open_call = True
            if len(node.args) >= 2:
                mode_node = node.args[1]
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            is_open_call = True
            if len(node.args) >= 1:
                mode_node = node.args[0]

        if is_open_call:
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode_node = kw.value
                    break

            if mode_node is not None:
                mode_str = _resolve_const_str(mode_node)
                if mode_str is None:
                    if self.subsystem not in ("extension", "extensions"):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited dynamic/non-constant mode in open() call. Marketplace plugins must specify constant read-only modes."
                        )
                elif any(c in mode_str for c in ("w", "a", "x", "+")):
                    if self.subsystem not in ("extension", "extensions"):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited write mode '{mode_str}' in open() call. Marketplace plugins are read-only."
                        )

        if isinstance(node.func, ast.Name):
            func_id = node.func.id
            if func_id in BANNED_BUILTIN_CALLS:
                if func_id == "input" and self.subsystem in ("extension", "extensions"):
                    pass
                else:
                    self.violations.append(f"Line {node.lineno}: Prohibited builtin call '{func_id}()'")
            elif func_id in ("setattr", "delattr"):
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in ("os", "sys", "builtins", "__builtins__"):
                    self.violations.append(
                        f"Line {node.lineno}: Prohibited dynamic tampering with '{node.args[0].id}' via {func_id}()"
                    )
            elif func_id == "getattr" and len(node.args) >= 2:
                resolved_attr = _resolve_const_str(node.args[1])
                if resolved_attr:
                    if (
                        resolved_attr in BANNED_OS_ATTRS
                        or resolved_attr in BANNED_BUILTIN_CALLS
                        or resolved_attr in BANNED_DUNDERS
                    ):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited dynamic call '{resolved_attr}' via getattr"
                        )
                else:
                    if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in ("os", "sys", "builtins", "__builtins__"):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited dynamic obfuscated attribute access on '{node.args[0].id}' via getattr()"
                        )
                    else:
                        self.warnings.append(
                            f"Line {node.lineno}: Dynamic call to getattr() with non-constant attribute name requires scrutiny"
                        )

        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in BANNED_OS_ATTRS:
                if attr_name == "replace":
                    is_fs_replace = False
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in ("os", "Path"):
                        is_fs_replace = True
                    elif isinstance(node.func.value, ast.Attribute) and node.func.value.attr in ("os", "Path"):
                        is_fs_replace = True
                    if is_fs_replace:
                        self.violations.append(f"Line {node.lineno}: Prohibited filesystem call 'replace()'")
                elif attr_name in ("mkdir", "makedirs") and self.subsystem in ("extension", "extensions"):
                    pass
                else:
                    self.violations.append(f"Line {node.lineno}: Prohibited system/filesystem call '{attr_name}()'")
            elif attr_name in BANNED_BUILTIN_CALLS:
                if not (attr_name == "compile" and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"):
                    self.violations.append(f"Line {node.lineno}: Prohibited dynamic execution '{attr_name}()'")
            elif attr_name in ("write_text", "write_bytes"):
                if self.subsystem not in ("extension", "extensions"):
                    self.violations.append(
                        f"Line {node.lineno}: Prohibited filesystem modification '{attr_name}()'. Marketplace plugins are read-only."
                    )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in BANNED_DUNDERS:
            self.violations.append(f"Line {node.lineno}: Prohibited access to reflection attribute '{node.attr}'")

        if isinstance(node.value, ast.Name) and node.value.id == "sys":
            if node.attr in ("modules", "path"):
                self.violations.append(f"Line {node.lineno}: Prohibited inspection or tampering with 'sys.{node.attr}'")

        if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr == "environ":
            if self.subsystem in OFFLINE_SUBSYSTEMS:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited access to 'os.environ' in offline subsystem '{self.subsystem}'"
                )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                if (
                    isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "os"
                    and target.value.attr == "environ"
                ):
                    self.violations.append(
                        f"Line {node.lineno}: Prohibited mutation of environment variable through 'os.environ'"
                    )
            elif isinstance(target, ast.Attribute):
                if isinstance(target.value, ast.Name):
                    if target.value.id == "os" and target.attr == "environ":
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited reassignment of 'os.environ'"
                        )
                    elif target.value.id == "sys" and target.attr in (
                        "stdout", "stderr", "stdin", "modules", "path"
                    ):
                        self.violations.append(
                            f"Line {node.lineno}: Prohibited reassignment of 'sys.{target.attr}'"
                        )
        self.generic_visit(node)


def compute_directory_hash(dir_path: Path) -> str:
    """Computes a deterministic SHA256 hash of all files in a directory package."""
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


def validate_module_manifest(manifest_path: Path, repo_root: Path) -> ValidationReport:
    """Validates manifest schema, AST code security, checksums, and subsystem contract."""
    name = manifest_path.stem
    report = ValidationReport(name=name, is_valid=True)

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        report.is_valid = False
        report.violations.append(f"Malformed JSON in manifest: {e}")
        return report

    # 1. Schema check
    req_fields = ["name", "subsystem", "version", "source_type", "download_url"]
    for f in req_fields:
        if f not in data or not str(data[f]).strip():
            report.violations.append(f"Missing required field '{f}' in manifest")

    mod_name = str(data.get("name", "")).strip().lower()
    if not re.match(r"^[a-zA-Z0-9_-]+$", mod_name):
        report.violations.append(f"Invalid name '{mod_name}'. Must match ^[a-zA-Z0-9_-]+$")

    subsystem = str(data.get("subsystem", "")).strip().lower()
    if subsystem not in ALLOWED_SUBSYSTEMS:
        report.violations.append(f"Invalid subsystem '{subsystem}'. Must be one of {ALLOWED_SUBSYSTEMS}")

    source_type = str(data.get("source_type", "single_file"))
    if source_type not in ("single_file", "directory"):
        report.violations.append(f"Invalid source_type '{source_type}'. Must be 'single_file' or 'directory'")

    version = str(data.get("version", ""))
    if not re.match(r"^v?\d+(\.\d+)*", version):
        report.violations.append(f"Invalid SemVer '{version}'")

    # Dependency specifications check
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list):
        report.violations.append("Field 'dependencies' must be a list of strings")
    else:
        for dep in dependencies:
            if not isinstance(dep, str):
                report.violations.append(f"Invalid dependency entry '{dep}': must be a string")
                continue
            dep_match = re.match(r"^([a-zA-Z0-9_-]+)(\s*(>=|<=|==|>|<)?\s*v?\d+(\.\d+)*)?$", dep.strip())
            if not dep_match:
                report.violations.append(
                    f"Invalid dependency specification '{dep}'. Must match name with optional operator (e.g. 'helper>=1.0.0')"
                )
            elif dep_match.group(1).lower() == mod_name:
                report.violations.append(f"Module '{mod_name}' cannot depend on itself: '{dep}'")

    # 2. Locate payload
    payload_rel = data.get("download_url", "")
    payload_path = repo_root / payload_rel if payload_rel else None
    if not payload_path or not payload_path.exists():
        # Fallback to local sibling
        if source_type == "single_file":
            payload_path = manifest_path.parent / f"{mod_name}.py"
        else:
            payload_path = manifest_path.parent / mod_name

    if not payload_path.exists():
        report.violations.append(f"Payload not found at '{payload_rel}' or '{payload_path}'")
        report.is_valid = False
        return report

    # Symlink defense
    if payload_path.is_symlink():
        report.violations.append("Security violation: payload cannot be a symlink")
    if payload_path.is_dir():
        for item in payload_path.rglob("*"):
            if item.is_symlink():
                report.violations.append(f"Security violation: symlink '{item.name}' forbidden in directory package")

    # 3. Checksum verification
    if source_type == "single_file" and payload_path.is_file():
        computed_sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()
        report.computed_sha256 = computed_sha
        declared_sha = data.get("sha256")
        if declared_sha and declared_sha.lower() != computed_sha.lower():
            report.violations.append(f"SHA256 mismatch! Declared: {declared_sha}, Computed: {computed_sha}")
    elif source_type == "directory" and payload_path.is_dir():
        computed_sha = compute_directory_hash(payload_path)
        report.computed_sha256 = computed_sha
        declared_sha = data.get("sha256")
        if declared_sha and declared_sha.lower() != computed_sha.lower():
            report.violations.append(f"Directory SHA256 mismatch! Declared: {declared_sha}, Computed: {computed_sha}")

    # 4. AST Security Analysis
    py_files = [payload_path] if source_type == "single_file" else list(payload_path.rglob("*.py"))
    visitor = _SecurityVisitor(subsystem=subsystem)

    for pyf in py_files:
        try:
            tree = ast.parse(pyf.read_text(encoding="utf-8"), filename=pyf.name)
            visitor.visit(tree)
        except SyntaxError as se:
            report.violations.append(f"SyntaxError in {pyf.name}:{se.lineno}: {se.msg}")

    report.violations.extend(visitor.violations)
    report.warnings.extend(visitor.warnings)
    report.methods_found = list(set(visitor.methods_found))

    # 5. Subsystem Contract Verification (Duck Typing)
    required_contracts = {
        "info_providers": "adapt_item",
        "scam_analyser": "analyze",
        "component_analyser": "identify",
        "build_composer": "compose",
        "ai_providers": ["complete", "call"],
    }
    expected = required_contracts.get(subsystem)
    if expected:
        if isinstance(expected, list):
            if not any(m in report.methods_found for m in expected):
                report.violations.append(
                    f"Subsystem contract failure: '{subsystem}' module must implement at least one of {expected}"
                )
        else:
            if expected not in report.methods_found:
                report.violations.append(
                    f"Subsystem contract failure: '{subsystem}' module must implement '{expected}()'"
                )

    report.is_valid = len(report.violations) == 0
    return report


def generate_markdown_summary(reports: List[ValidationReport]) -> str:
    """Formats validation results as a GitHub PR comment."""
    total = len(reports)
    passed = sum(1 for r in reports if r.is_valid)
    failed = total - passed

    lines = [
        "## Knapset Registry — Automated PR Validation",
        "",
        f"**Status**: {'[PASS] All Checks Passed' if failed == 0 else '[FAIL] Security or Contract Violations Detected'}",
        f"- **Modules Scanned**: {total}",
        f"- **Passed**: {passed}",
        f"- **Violations**: {failed}",
        "",
        "### Module Inspection Ledger",
        "",
        "| Module | Subsystem / File | Status | Computed SHA256 | Contract Check |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in reports:
        status_badge = "[PASS]" if r.is_valid else "[FAIL]"
        sha_preview = f"`{r.computed_sha256[:12]}...`" if r.computed_sha256 else "—"
        methods = ", ".join(r.methods_found) if r.methods_found else "None"
        lines.append(f"| **{r.name}** | Manifest | {status_badge} | {sha_preview} | `{methods}` |")

    lines.append("")

    for r in reports:
        if not r.is_valid or r.warnings:
            lines.append(f"#### Detailed Findings: `{r.name}`")
            if r.violations:
                lines.append("**Violations:**")
                for v in r.violations:
                    lines.append(f"- [FAIL] {v}")
            if r.warnings:
                lines.append("**Warnings:**")
                for w in r.warnings:
                    lines.append(f"- [WARN] {w}")
            lines.append("")

    lines.append("---")
    lines.append("*Automated scan executed by `scripts/validate_submission.py` (Zero pip dependencies).*")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate module manifests and security in registry")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Repo root")
    parser.add_argument("--files", nargs="*", help="Specific manifest file paths to validate")
    parser.add_argument("--markdown-out", help="Path to write GitHub PR markdown summary")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    modules_dir = repo_root / "modules"

    manifest_paths: List[Path] = []
    if args.files:
        for f in args.files:
            p = Path(f)
            if p.is_file() and p.name.endswith(".json") and p.name != "registry.json":
                manifest_paths.append(p.resolve())
    else:
        # Scan all manifests in modules/
        for p in modules_dir.rglob("*.json"):
            if p.name != "registry.json" and "flash_chips" not in p.name:
                if p.parent.name in ALLOWED_SUBSYSTEMS:
                    manifest_paths.append(p)

    reports = []
    for mf in sorted(manifest_paths):
        rep = validate_module_manifest(mf, repo_root)
        reports.append(rep)
        status_icon = "OK" if rep.is_valid else "FAIL"
        print(f"[{status_icon}] {rep.name}: {'PASSED' if rep.is_valid else 'FAILED'}")
        for v in rep.violations:
            print(f"    [ERROR] {v}")
        for w in rep.warnings:
            print(f"    [WARN] {w}")

    if args.markdown_out:
        out_p = Path(args.markdown_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(generate_markdown_summary(reports), encoding="utf-8")
        print(f"Markdown report written to {out_p}")

    all_passed = all(r.is_valid for r in reports)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
