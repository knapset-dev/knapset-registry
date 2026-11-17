"""
Prebuilt PC Evaluator & Market Comparator.
Domain: hardware_pc
Subsystem: component_analyser

Evaluates ready-made PC listings (from OLX or pasted text) against fair market part values,
detects risks (fire-hazard PSUs, CPU bottlenecks, obsolete sockets), and runs head-to-head
duels against the best market alternatives (prebuilts or DIY synthesized builds).
Zero external dependencies (Python Standard Library only).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from component_analyser.base import BaseComponentAnalyser
from currency import canonical_currency, convert_currency, format_price, get_active_currency
from market_client import INTEL_DATA_DIR, MarketClient, load_market_cache, normalize_category


@dataclass
class PrebuiltSpecs:
    title: str = ""
    description: str = ""
    price: float = 0.0
    currency: str = "UAH"
    url: str = ""
    gpu: Optional[Dict[str, Any]] = None
    cpu: Optional[Dict[str, Any]] = None
    mobo: Optional[Dict[str, Any]] = None
    ram: Optional[Dict[str, Any]] = None
    psu: Optional[Dict[str, Any]] = None
    storage: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.0
    missing_components: List[str] = field(default_factory=list)
    raw_matches: Dict[str, str] = field(default_factory=dict)


class PrebuiltEvaluator(BaseComponentAnalyser):
    name = "prebuilt_evaluator"
    title = "Prebuilt PC Evaluator & Comparator"
    domain = "hardware_pc"
    category = "evaluation"
    version = "1.0.0"
    author = "Core Team"
    description = (
        "Parses ready-made PC listings, computes fair part values from market cache, "
        "detects hardware hazards/bottlenecks, and runs Prebuilt vs DIY Duels."
    )
    min_app_version = "1.0.0"
    tags = ["pc", "prebuilt", "evaluator", "comparator", "duel", "olx"]

    def __init__(self) -> None:
        self._init_helpers()

    def _init_helpers(self) -> None:
        """Safely imports hardware identification helpers and mode scoring engine from extensions.pc."""
        try:
            from extensions.pc.gpu_database import identify_gpu
            self._identify_gpu = identify_gpu
        except Exception:
            self._identify_gpu = None

        try:
            from extensions.pc.cpu_database import identify_cpu
            self._identify_cpu = identify_cpu
        except Exception:
            self._identify_cpu = None

        try:
            from extensions.pc.mobo_database import identify_motherboard
            self._identify_mobo = identify_motherboard
        except Exception:
            self._identify_mobo = None

        try:
            from extensions.pc.ram_database import identify_ram
            self._identify_ram = identify_ram
        except Exception:
            self._identify_ram = None

        try:
            from extensions.pc.psu_database import identify_psu
            self._identify_psu = identify_psu
        except Exception:
            self._identify_psu = None

        try:
            from extensions.pc.modes import resolve_mode, score_build
            self._resolve_mode = resolve_mode
            self._score_build = score_build
        except Exception:
            self._resolve_mode = None
            self._score_build = None

    def identify(self, title: str, description: str = "") -> Optional[Dict[str, Any]]:
        """
        Parses title and description to extract all constituent components of a prebuilt PC.
        Returns a structured dictionary of specifications and confidence rating.
        """
        specs = self.parse_specs(title=title, description=description)
        if specs.confidence_score < 0.15:
            return None
        return {
            "title": specs.title,
            "price": specs.price,
            "confidence_score": specs.confidence_score,
            "gpu": specs.gpu,
            "cpu": specs.cpu,
            "mobo": specs.mobo,
            "ram": specs.ram,
            "psu": specs.psu,
            "storage": specs.storage,
            "missing_components": specs.missing_components,
            "raw_matches": specs.raw_matches,
        }

    def parse_specs(self, title: str, description: str = "", price: Optional[float] = None) -> PrebuiltSpecs:
        """Extracts individual PC parts from listing title, description, and price."""
        combined_text = f"{title}\n{description}".strip()
        specs = PrebuiltSpecs(title=title, description=description, price=price or 0.0)

        # 1. Price extraction if not provided
        if not specs.price:
            p_match = re.search(
                r"(?:\$\s*(\d{2,6})|\b(\d{1,3}(?:[ \s]\d{3})*|\d{2,7})(?:\.00)?\s*(грн|uah|₴|usdt|usd|\$))\b",
                combined_text,
                re.I,
            )
            if p_match:
                if p_match.group(1):
                    clean_p = re.sub(r"[^\d]", "", p_match.group(1))
                    specs.currency = "USD"
                else:
                    clean_p = re.sub(r"[^\d]", "", p_match.group(2))
                    unit_tok = (p_match.group(3) or "UAH").lower()
                    specs.currency = "USDT" if unit_tok == "usdt" else ("USD" if unit_tok in ("usd", "$") else "UAH")
                try:
                    specs.price = float(clean_p)
                except ValueError:
                    specs.price = 0.0
            else:
                p_match2 = re.search(r"(?:ціна|price|вартість|коштує)[:\s]*(\d{2,7})\b", combined_text, re.I)
                if p_match2:
                    clean_p = re.sub(r"[^\d]", "", p_match2.group(1))
                    try:
                        specs.price = float(clean_p)
                        specs.currency = "UAH" if specs.price >= 4500.0 else get_active_currency()
                    except ValueError:
                        specs.price = 0.0
        else:
            # Explicit price passed in: infer UAH if >= 4500 or if text mentions грн/₴
            if re.search(r"\b(?:usdt)\b", combined_text, re.I) and specs.price < 4500.0:
                specs.currency = "USDT"
            elif (re.search(r"(?:\b(?:usd)\b|\$)", combined_text, re.I)) and specs.price < 4500.0:
                specs.currency = "USD"
            elif specs.price >= 4500.0 or re.search(r"(?:грн|uah|₴)", combined_text, re.I):
                specs.currency = "UAH"
            else:
                specs.currency = get_active_currency()

        # 2. GPU Identification
        if self._identify_gpu:
            try:
                specs.gpu = self._identify_gpu(title, description, allow_bundles=True)
            except TypeError:
                specs.gpu = self._identify_gpu(title, description)
            if specs.gpu:
                specs.raw_matches["gpu"] = specs.gpu.get("model", specs.gpu.get("matched_model", "Unknown GPU"))
        if not specs.gpu:
            # Fallback simple GPU pattern
            gpu_re = re.search(r"\b(rtx\s*\d{3,4}(?:\s*ti|\s*super)?|gtx\s*\d{3,4}(?:\s*ti|\s*super)?|rx\s*\d{3,4}(?:\s*xt)?)\b", combined_text, re.I)
            if gpu_re:
                specs.raw_matches["gpu"] = gpu_re.group(1).upper()
                specs.gpu = {"model": gpu_re.group(1).upper(), "fps_1080p": 50.0, "fps_1440p": 35.0, "brand": "Generic"}

        # 3. CPU Identification
        if self._identify_cpu:
            try:
                specs.cpu = self._identify_cpu(title, description, allow_bundles=True)
            except TypeError:
                specs.cpu = self._identify_cpu(title, description)
            if specs.cpu:
                specs.raw_matches["cpu"] = specs.cpu.get("model", specs.cpu.get("matched_model", "Unknown CPU"))
        if not specs.cpu:
            cpu_re = re.search(r"\b(i[3579][-\s]\d{3,5}[a-z]?|ryzen\s*[3579]\s*\d{4}[a-z3d]*|xeon\s*[a-z0-9\-]+)\b", combined_text, re.I)
            if cpu_re:
                specs.raw_matches["cpu"] = cpu_re.group(1).upper()
                specs.cpu = {"model": cpu_re.group(1).upper(), "gaming_index": 100.0, "socket": "Unknown"}

        # 4. Motherboard Identification
        if self._identify_mobo:
            try:
                specs.mobo = self._identify_mobo(title, description, allow_bundles=True)
            except TypeError:
                specs.mobo = self._identify_mobo(title, description)
            if specs.mobo:
                specs.raw_matches["mobo"] = specs.mobo.get("model", specs.mobo.get("chipset", "Motherboard"))
        if not specs.mobo:
            mobo_re = re.search(r"\b([abzhx]\d{2,3}[m]?(?:\s*pro|\s*gaming|\s*plus)?)\b", combined_text, re.I)
            if mobo_re:
                specs.raw_matches["mobo"] = mobo_re.group(1).upper()
                specs.mobo = {"chipset": mobo_re.group(1).upper(), "vrm_tier": "C-Tier"}

        # 5. RAM Identification (prioritize explicit RAM mention over VRAM)
        ram_explicit = re.search(r"\b(\d{1,3})\s*(?:gb|гб)\s*(?:ddr[345]|ram|озу|пам'?ять)\b", combined_text, re.I)
        if ram_explicit:
            cap = int(ram_explicit.group(1))
            if cap in (4, 8, 12, 16, 24, 32, 48, 64, 128):
                gen = "DDR5" if "ddr5" in combined_text.lower() else ("DDR3" if "ddr3" in combined_text.lower() else "DDR4")
                specs.ram = {"total_gb": cap, "capacity_gb": cap, "generation": gen}
                specs.raw_matches["ram"] = f"{cap}GB {gen}"
        elif self._identify_ram:
            specs.ram = self._identify_ram(title, description)
            if specs.ram:
                cap = specs.ram.get("total_gb", specs.ram.get("capacity_gb", 16))
                specs.ram["capacity_gb"] = cap
                specs.raw_matches["ram"] = f"{cap}GB {specs.ram.get('generation', 'DDR4')}"

        # 6. PSU Identification
        if self._identify_psu:
            specs.psu = self._identify_psu(title, description)
            if specs.psu:
                specs.raw_matches["psu"] = f"{specs.psu.get('wattage', 500)}W {specs.psu.get('tier', 'C-Tier')}"
        if not specs.psu:
            psu_re = re.search(r"\b(\d{3,4})\s*(?:w|вт|watt)\b", combined_text, re.I)
            if psu_re:
                w = int(psu_re.group(1))
                if 300 <= w <= 1600:
                    tier = "F-Tier" if any(b in combined_text.lower() for b in ("vx", "kcas", "gamemax")) else "C-Tier"
                    specs.psu = {"wattage": w, "tier": tier}
                    specs.raw_matches["psu"] = f"{w}W ({tier})"

        # 7. Storage Identification (explicit SSD/HDD patterns, avoiding GPU VRAM match)
        storage_re = re.search(
            r"(?:(?:ssd|ссд|m\.2|nvme|hdd|хдд|диск)\s*(\d+)\s*(gb|гб|tb|тб)|\b(\d+)\s*(gb|гб|tb|тб)\s*(?:ssd|ссд|m\.2|nvme|hdd|хдд)\b)",
            combined_text,
            re.I,
        )
        if storage_re:
            size_val = int(storage_re.group(1) or storage_re.group(3))
            unit = (storage_re.group(2) or storage_re.group(4) or "").lower()
            if "t" in unit or "т" in unit:
                size_val *= 1024
            st_type = "NVMe" if any(k in combined_text.lower() for k in ("nvme", "m.2", "m2")) else "SSD"
            specs.storage = {"capacity_gb": size_val, "type": st_type}
            specs.raw_matches["storage"] = f"{size_val}GB {st_type}"
        else:
            specs.storage = {"capacity_gb": 512, "type": "SSD (Default)"}
            specs.raw_matches["storage"] = "512GB SSD (Default)"

        # Confidence & Missing Parts
        present_count = 0
        for comp_name, comp_val in [("gpu", specs.gpu), ("cpu", specs.cpu), ("mobo", specs.mobo), ("ram", specs.ram), ("psu", specs.psu)]:
            if comp_val:
                present_count += 1
            else:
                specs.missing_components.append(comp_name)

        specs.confidence_score = round(present_count / 5.0, 2)
        return specs

    def fetch_ad(self, target: str) -> Dict[str, Any]:
        """Resolves target input (URL, local ad ID, or text) into raw listing data."""
        clean_target = target.strip()
        # 1. URL / ID resolution against local market store/cache
        if clean_target.startswith(("http://", "https://")):
            id_m = re.search(r"ID([a-zA-Z0-9]+)", clean_target)
            if id_m:
                try:
                    client = MarketClient(provider="olx")
                    det = client.get_offer_details(id_m.group(1))
                    if det:
                        return det
                except Exception:
                    pass

        # 2. Check cached prebuilts by ID or title match
        cached_prebuilts, _, _ = load_market_cache("prebuilt")
        for ad in cached_prebuilts:
            if str(ad.get("id")) == clean_target:
                return ad
            if clean_target.lower() in str(ad.get("title", "")).lower():
                return ad

        # 3. Direct raw text payload
        return {"title": clean_target[:80], "description": clean_target, "price": 0.0, "url": ""}

    def calculate_fair_value(self, specs: PrebuiltSpecs) -> Dict[str, Any]:
        """Calculates fair market value of all components using local market cache medians."""
        parts_value: Dict[str, Dict[str, Any]] = {}
        total_fair = 0.0

        # GPU
        gpu_name = specs.raw_matches.get("gpu", "Unknown GPU")
        gpu_price = 0.0
        if specs.gpu:
            gpu_price = float(specs.gpu.get("market_used_min", 0) + specs.gpu.get("market_used_max", 0)) / 2.0
        if gpu_price <= 0:
            gpu_price = 7500.0  # conservative modern median
        parts_value["gpu"] = {"name": gpu_name, "market_price": gpu_price}
        total_fair += gpu_price

        # CPU
        cpu_name = specs.raw_matches.get("cpu", "Unknown CPU")
        cpu_price = 0.0
        if specs.cpu:
            cpu_price = float(specs.cpu.get("market_used_min", 0) + specs.cpu.get("market_used_max", 0)) / 2.0
        if cpu_price <= 0:
            cpu_price = 3200.0
        parts_value["cpu"] = {"name": cpu_name, "market_price": cpu_price}
        total_fair += cpu_price

        # Motherboard
        mobo_name = specs.raw_matches.get("mobo", "Motherboard")
        mobo_price = 2200.0
        if specs.mobo and "vrm_tier" in specs.mobo:
            tier = specs.mobo["vrm_tier"]
            mobo_price = 4500.0 if "A-Tier" in tier or "S-Tier" in tier else 2200.0
        parts_value["mobo"] = {"name": mobo_name, "market_price": mobo_price}
        total_fair += mobo_price

        # RAM
        ram_name = specs.raw_matches.get("ram", "16GB RAM")
        ram_gb = specs.ram.get("capacity_gb", 16) if specs.ram else 16
        ram_price = (ram_gb / 8.0) * 750.0  # ~750 UAH per 8GB DDR4
        parts_value["ram"] = {"name": ram_name, "market_price": ram_price}
        total_fair += ram_price

        # PSU
        psu_name = specs.raw_matches.get("psu", "500W PSU")
        psu_price = 1200.0
        if specs.psu:
            w = specs.psu.get("wattage", 500)
            psu_price = (w / 100.0) * 220.0
        parts_value["psu"] = {"name": psu_name, "market_price": psu_price}
        total_fair += psu_price

        # Storage & Case
        st_name = specs.raw_matches.get("storage", "512GB SSD")
        st_price = 1100.0
        parts_value["storage"] = {"name": st_name, "market_price": st_price}
        total_fair += st_price

        parts_value["case"] = {"name": "PC Case & Fans", "market_price": 900.0}
        total_fair += 900.0

        curr = canonical_currency(getattr(specs, "currency", "UAH") or "UAH")
        if curr != "UAH":
            for p_data in parts_value.values():
                p_data["market_price"] = convert_currency(float(p_data["market_price"]), "UAH", curr)
            total_fair = sum(float(p["market_price"]) for p in parts_value.values())

        asking = specs.price if specs.price > 0 else total_fair
        markup_uah = asking - total_fair
        markup_pct = (markup_uah / total_fair * 100) if total_fair > 0 else 0.0

        return {
            "parts": parts_value,
            "total_fair_value": round(total_fair, 2),
            "asking_price": round(asking, 2),
            "markup_uah": round(markup_uah, 2),
            "markup_pct": round(markup_pct, 1),
            "currency": curr,
        }

    def detect_risks(self, specs: PrebuiltSpecs) -> List[Dict[str, str]]:
        """Detects hardware hazards, severe bottlenecks, and deceptive seller tactics."""
        risks = []
        full_text = f"{specs.title} {specs.description}".lower()

        # 1. PSU Hazard
        if specs.psu and specs.psu.get("tier") == "F-Tier":
            risks.append({
                "severity": "CRITICAL",
                "title": "Fire-Hazard Power Supply Detected",
                "desc": "Listing contains an F-Tier unit (Aerocool VX / Kcas / Gamemax) known for high failure rates and zero over-voltage protection.",
            })
        elif "vx-500" in full_text or "kcas" in full_text:
            risks.append({
                "severity": "CRITICAL",
                "title": "Unsafe Power Supply (Aerocool VX/Kcas)",
                "desc": "Dangerous low-end PSU with volatile 12V rails. Immediate replacement recommended.",
            })

        # 2. Obsolete / Dead-End Platform
        cpu_sock = (specs.cpu.get("socket") or "").upper() if specs.cpu else ""
        is_obsolete_sock = cpu_sock in ("LGA1155", "LGA1156", "LGA775", "LGA1366", "AM3+", "AM3", "AM2+", "FM2+", "FM1")
        is_obsolete_name = any(w in full_text for w in (
            "lga1155", "lga1156", "am3+", "am2+", "ddr3", "xeon e5-26",
            "i7 3770", "i7-3770", "i5 3570", "i5-3570", "i5 2500", "i5-2500", "i7 2600", "i7-2600",
            "phenom", "fx-8350", "fx-6300",
        ))
        if is_obsolete_sock or is_obsolete_name:
            risks.append({
                "severity": "WARNING",
                "title": "Obsolete Platform / Zero Upgrade Path",
                "desc": f"Built on 10+ year old architecture ({cpu_sock or 'DDR3'}/ancient socket). Zero modern CPU upgrade path.",
            })

        # 3. CPU/GPU Severe Bottleneck
        if specs.gpu and specs.cpu:
            gpu_fps = specs.gpu.get("fps_1080p", 60.0)
            cpu_idx = specs.cpu.get("gaming_index", 100.0)
            if gpu_fps >= 100.0 and cpu_idx < 80.0:
                risks.append({
                    "severity": "WARNING",
                    "title": "Severe CPU Bottleneck",
                    "desc": f"The CPU ({specs.raw_matches.get('cpu')}) is too weak for the GPU ({specs.raw_matches.get('gpu')}). The GPU will run under-utilized in games.",
                })

        # 4. Deceptive Marketing
        if "8 ядер 16 потоков" in full_text and ("xeon" in full_text or "x79" in full_text or "x99" in full_text):
            risks.append({
                "severity": "CAUTION",
                "title": "Deceptive Marketing (Old Server Hardware)",
                "desc": "Marketed as 'Fast 8-core 16-thread gaming monster', but uses recycled decommissioned server hardware with low IPC.",
            })

        return risks

    def find_best_alternative(
        self,
        budget: float,
        mode: str = "all",
        vendor: Optional[str] = None,
        retail: bool = False,
        currency: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the single best alternative offer or DIY synthesized build under the target budget.
        """
        if budget <= 0:
            return None

        target_curr = canonical_currency(currency or get_active_currency())
        active_curr = get_active_currency()

        # Alternative A: DIY Synthesis from PC Builder
        if mode != "prebuilt-only":
            try:
                from extension_registry import get_extension
                pc_ext = get_extension("pc")
                if pc_ext:
                    budget_in_active = convert_currency(budget, target_curr, active_curr)
                    candidate_pool = pc_ext.load_candidates(budget=budget_in_active)
                    sorter = pc_ext.get_sorter()
                    synth_mode = mode if mode not in ("all", "prebuilt-only", "diy-only") else ("sweet-spot" if not vendor else "best")
                    builds = sorter.sort_and_synthesize(
                        candidate_pool=candidate_pool,
                        budget=budget_in_active,
                        mode=synth_mode,
                        top_n=1,
                    )
                    if builds:
                        b = builds[0]
                        gpu_m = b.get("gpu", {}).get("model", "GPU")
                        cpu_m = b.get("cpu", {}).get("model", "CPU")
                        raw_b_cost = float(b.get("total_cost", budget_in_active))
                        b_cost_in_target = convert_currency(raw_b_cost, active_curr, target_curr)
                        return {
                            "type": "DIY_BUILD",
                            "title": f"Custom DIY: {gpu_m} + {cpu_m}",
                            "price": b_cost_in_target,
                            "currency": target_curr,
                            "fps_1080p": b.get("eff_fps_1080p", 80),
                            "fps_1440p": b.get("eff_fps_1440p", 60),
                            "score": b.get("build_score", 85.0),
                            "psu_tier": b.get("psu", {}).get("tier", "Tier A"),
                        }
            except Exception:
                pass

        # Alternative B: Best Ready-Made Prebuilt on the Market
        if mode != "diy-only":
            prebuilts, _, _ = load_market_cache("prebuilt")
            valid = []
            budget_uah = convert_currency(budget, target_curr, "UAH")
            for pb in prebuilts:
                p_cost = float(pb.get("price", 0))
                if 0 < p_cost <= budget_uah * 1.05:
                    valid.append(pb)
            if valid:
                valid.sort(key=lambda x: float(x.get("price", 0)), reverse=True)
                top_pb = valid[0]
                pb_price_target = convert_currency(float(top_pb.get("price", budget_uah)), "UAH", target_curr)
                return {
                    "type": "PREBUILT_MARKET",
                    "title": top_pb.get("title", "Market Prebuilt Listing"),
                    "price": pb_price_target,
                    "currency": target_curr,
                    "url": top_pb.get("url", ""),
                    "fps_1080p": 72.0,
                    "score": 85.0,
                }

        return None

    def _specs_to_build(self, specs: PrebuiltSpecs, val: Dict[str, Any]) -> Dict[str, Any]:
        """Packs parsed specs and fair part valuations into the 5-component dict expected by score_build."""
        parts = val.get("parts", {})

        # GPU
        g_raw = dict(specs.gpu or {})
        g_price = parts.get("gpu", {}).get("market_price", 7500.0)
        g_fps1080 = float(g_raw.get("fps_1080p", 60.0))
        g_fps1440 = float(g_raw.get("fps_1440p", max(35.0, g_fps1080 * 0.70)))
        g_vram = float(g_raw.get("vram_gb", 8.0))
        g_tdp = float(g_raw.get("tdp_watts", 180.0))
        g_risk = g_raw.get("risk_level", "MEDIUM")
        g = {
            "price": g_price,
            "fps_1080p": g_fps1080,
            "fps_1440p": g_fps1440,
            "vram_gb": g_vram,
            "tdp_watts": g_tdp,
            "risk_level": g_risk,
            "model": specs.raw_matches.get("gpu", g_raw.get("model", "GPU")),
            "spec": dict(g_raw, vram_gb=g_vram, risk_level=g_risk),
        }

        # CPU
        c_raw = dict(specs.cpu or {})
        c_price = parts.get("cpu", {}).get("market_price", 3200.0)
        c_gaming = float(c_raw.get("gaming_index", 100.0))
        c_threads = int(c_raw.get("threads", 12))
        c_sock = c_raw.get("socket", "Unknown")
        c_tdp = float(c_raw.get("tdp_watts", 65.0))
        c = {
            "price": c_price,
            "fps_gaming": c_gaming,
            "threads": c_threads,
            "socket": c_sock,
            "tdp_watts": c_tdp,
            "model": specs.raw_matches.get("cpu", c_raw.get("model", "CPU")),
            "spec": dict(c_raw, threads=c_threads, socket=c_sock, fps_gaming=c_gaming, tdp_watts=c_tdp),
        }

        # Motherboard
        m_raw = dict(specs.mobo or {})
        m_price = parts.get("mobo", {}).get("market_price", 2200.0)
        m_tier = m_raw.get("vrm_tier", "C-Tier")
        m = {
            "price": m_price,
            "vrm_tier": m_tier,
            "model": specs.raw_matches.get("mobo", m_raw.get("chipset", "Motherboard")),
            "spec": dict(m_raw, vrm_tier=m_tier),
        }

        # RAM
        r_raw = dict(specs.ram or {})
        r_price = parts.get("ram", {}).get("market_price", 1500.0)
        r_gb = int(r_raw.get("capacity_gb", r_raw.get("total_gb", 16)))
        r_gen = r_raw.get("generation", "DDR4")
        r = {
            "price": r_price,
            "total_gb": r_gb,
            "gen": r_gen,
            "spec": dict(r_raw, total_gb=r_gb, generation=r_gen, latency_ns=10.0),
        }

        # PSU
        p_raw = dict(specs.psu or {})
        p_price = parts.get("psu", {}).get("market_price", 1200.0)
        p_w = int(p_raw.get("wattage", 500))
        raw_t = str(p_raw.get("tier", "Tier C")).lower()
        if "a" in raw_t:
            p_tier = "Tier A"
        elif "b" in raw_t:
            p_tier = "Tier B"
        elif "c" in raw_t:
            p_tier = "Tier C"
        elif "d" in raw_t:
            p_tier = "Tier D"
        else:
            p_tier = "Tier F"
        p = {
            "price": p_price,
            "wattage": p_w,
            "tier": p_tier,
            "spec": dict(p_raw, wattage=p_w, tier=p_tier),
        }

        total_cost = float(val.get("asking_price") or specs.price or val.get("total_fair_value") or 1.0)
        curr = val.get("currency") or getattr(specs, "currency", "UAH") or "UAH"
        for comp in (g, c, m, r, p):
            comp["currency"] = curr
        return {
            "gpu": g,
            "cpu": c,
            "mobo": m,
            "ram": r,
            "psu": p,
            "total_cost": total_cost,
            "currency": curr,
        }

    def _build_matchups(
        self,
        specs_a: PrebuiltSpecs,
        specs_b: PrebuiltSpecs,
        build_a: Dict[str, Any],
        build_b: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Compares individual components and assigns winning markers."""
        matchups = []

        # 1. GPU
        g_a = build_a["gpu"]
        g_b = build_b["gpu"]
        name_a = specs_a.raw_matches.get("gpu", g_a.get("model", "GPU A"))
        name_b = specs_b.raw_matches.get("gpu", g_b.get("model", "GPU B"))
        fps_a = g_a.get("fps_1080p", 50.0)
        fps_b = g_b.get("fps_1080p", 50.0)
        vram_a = g_a.get("vram_gb", 8)
        vram_b = g_b.get("vram_gb", 8)

        if fps_a > fps_b * 1.04:
            g_lead = "A"
        elif fps_b > fps_a * 1.04:
            g_lead = "B"
        else:
            g_lead = "TIE"

        matchups.append({
            "category": "GPU (Graphics Card)",
            "a": f"{name_a} (~{fps_a:.0f} FPS, {vram_a:.0f}GB)",
            "b": f"{name_b} (~{fps_b:.0f} FPS, {vram_b:.0f}GB)",
            "leader": g_lead,
        })

        # 2. CPU
        c_a = build_a["cpu"]
        c_b = build_b["cpu"]
        c_name_a = specs_a.raw_matches.get("cpu", c_a.get("model", "CPU A"))
        c_name_b = specs_b.raw_matches.get("cpu", c_b.get("model", "CPU B"))
        c_idx_a = c_a.get("fps_gaming", 100.0)
        c_idx_b = c_b.get("fps_gaming", 100.0)
        th_a = c_a.get("threads", 12)
        th_b = c_b.get("threads", 12)

        if c_idx_a > c_idx_b * 1.05:
            c_lead = "A"
        elif c_idx_b > c_idx_a * 1.05:
            c_lead = "B"
        else:
            c_lead = "TIE"

        matchups.append({
            "category": "CPU (Processor)",
            "a": f"{c_name_a} ({th_a} threads)",
            "b": f"{c_name_b} ({th_b} threads)",
            "leader": c_lead,
        })

        # 3. Motherboard
        m_a = build_a["mobo"]
        m_b = build_b["mobo"]
        m_name_a = specs_a.raw_matches.get("mobo", m_a.get("model", "Mobo A"))
        m_name_b = specs_b.raw_matches.get("mobo", m_b.get("model", "Mobo B"))
        t_a = m_a.get("vrm_tier", "C-Tier")
        t_b = m_b.get("vrm_tier", "C-Tier")
        m_ranks = {"S-Tier": 5, "A-Tier": 4, "B-Tier": 3, "C-Tier": 2, "D-Tier": 1}
        r_a = m_ranks.get(t_a, 2)
        r_b = m_ranks.get(t_b, 2)
        m_lead = "A" if r_a > r_b else ("B" if r_b > r_a else "TIE")

        matchups.append({
            "category": "Motherboard",
            "a": f"{m_name_a} ({t_a})",
            "b": f"{m_name_b} ({t_b})",
            "leader": m_lead,
        })

        # 4. RAM
        r_a_ram = build_a["ram"]
        r_b_ram = build_b["ram"]
        gb_a = r_a_ram.get("total_gb", 16)
        gb_b = r_b_ram.get("total_gb", 16)
        gen_a = r_a_ram.get("gen", "DDR4")
        gen_b = r_b_ram.get("gen", "DDR4")
        ram_val_a = gb_a * (1.5 if gen_a == "DDR5" else 1.0)
        ram_val_b = gb_b * (1.5 if gen_b == "DDR5" else 1.0)
        r_lead = "A" if ram_val_a > ram_val_b else ("B" if ram_val_b > ram_val_a else "TIE")

        matchups.append({
            "category": "RAM (Memory)",
            "a": f"{gb_a}GB {gen_a}",
            "b": f"{gb_b}GB {gen_b}",
            "leader": r_lead,
        })

        # 5. PSU
        p_a = build_a["psu"]
        p_b = build_b["psu"]
        w_a = p_a.get("wattage", 500)
        w_b = p_b.get("wattage", 500)
        tier_a = p_a.get("tier", "Tier C")
        tier_b = p_b.get("tier", "Tier C")
        p_ranks = {"Tier A": 5, "Tier B": 4, "Tier C": 3, "Tier D": 2, "Tier F": 0}
        pr_a = p_ranks.get(tier_a, 2)
        pr_b = p_ranks.get(tier_b, 2)
        if pr_a > pr_b:
            p_lead = "A"
        elif pr_b > pr_a:
            p_lead = "B"
        elif w_a > w_b:
            p_lead = "A"
        elif w_b > w_a:
            p_lead = "B"
        else:
            p_lead = "TIE"

        matchups.append({
            "category": "Power Supply (PSU)",
            "a": f"{w_a}W ({tier_a})",
            "b": f"{w_b}W ({tier_b})",
            "leader": p_lead,
        })

        # 6. Storage
        st_a = specs_a.storage or {}
        st_b = specs_b.storage or {}
        st_gb_a = st_a.get("capacity_gb", 512)
        st_gb_b = st_b.get("capacity_gb", 512)
        st_t_a = st_a.get("type", "SSD")
        st_t_b = st_b.get("type", "SSD")
        s_score_a = st_gb_a * (1.2 if "nvme" in st_t_a.lower() else 1.0)
        s_score_b = st_gb_b * (1.2 if "nvme" in st_t_b.lower() else 1.0)
        st_lead = "A" if s_score_a > s_score_b else ("B" if s_score_b > s_score_a else "TIE")

        matchups.append({
            "category": "Storage (SSD/HDD)",
            "a": f"{st_gb_a}GB {st_t_a}",
            "b": f"{st_gb_b}GB {st_t_b}",
            "leader": st_lead,
        })

        return matchups

    def evaluate(
        self,
        target_input: str,
        mode: str = "sweet-spot",
        vendor: Optional[str] = None,
        retail: bool = False,
        budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete evaluation: parses listing, calculates fair part values,
        detects risks, scores under active mode, and runs head-to-head comparison vs the best market alternative.
        """
        # Resolve active mode profile
        profile = None
        if self._resolve_mode:
            try:
                profile = self._resolve_mode(mode if mode not in ("all", "prebuilt-only", "diy-only") else "sweet-spot")
            except Exception:
                profile = None

        raw_ad = self.fetch_ad(target_input)
        effective_budget = budget or float(raw_ad.get("price", 0.0))
        specs = self.parse_specs(
            title=raw_ad.get("title", ""),
            description=raw_ad.get("description", ""),
            price=effective_budget,
        )
        if raw_ad.get("url"):
            specs.url = raw_ad["url"]

        val = self.calculate_fair_value(specs)
        risks = self.detect_risks(specs)

        # Hook into active mode scoring
        build = self._specs_to_build(specs, val)
        mode_score = 50.0
        if self._score_build and profile:
            try:
                mode_score = round(self._score_build(build, val["asking_price"], profile), 1)
            except Exception:
                mode_score = 50.0

        alternative = self.find_best_alternative(
            budget=val["asking_price"],
            mode=mode,
            vendor=vendor,
            retail=retail,
            currency=val.get("currency"),
        )

        # Compute Verdict
        markup_pct = val["markup_pct"]
        has_critical_risk = any(r["severity"] == "CRITICAL" for r in risks)

        if has_critical_risk:
            verdict = "DANGEROUS"
            verdict_badge = "[CRITICAL] DANGEROUS / CRITICAL HAZARD"
            recommendation = "Not recommended: critical PSU safety hazard or hardware incompatibility detected."
        elif markup_pct <= -15.0:
            verdict = "SUPER_DEAL"
            verdict_badge = "[GOOD] SUPER DEAL (Below Market Value)"
            recommendation = f"Great deal! Priced {abs(markup_pct):.0f}% below the combined market value of its parts."
        elif markup_pct <= 8.0:
            verdict = "FAIR_PRICE"
            verdict_badge = "[FAIR] FAIR MARKET PRICE"
            recommendation = "Fairly priced in line with individual component market values plus reasonable assembly margin."
        else:
            verdict = "OVERPRICED"
            verdict_badge = f"[HIGH] OVERPRICED (+{markup_pct:.0f}%)"
            curr_val = val.get("currency", "UAH")
            recommendation = f"Seller markup is +{markup_pct:.0f}% (+{format_price(val['markup_uah'], curr_val)}). Negotiate the price or build DIY."

        return {
            "specs": specs,
            "valuation": val,
            "risks": risks,
            "alternative": alternative,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "recommendation": recommendation,
            "mode": {
                "name": profile.name if profile else mode,
                "title": profile.title if profile else mode,
                "score": mode_score,
            },
        }

    def compare_duo(
        self,
        target_a: str,
        target_b: str,
        mode: str = "sweet-spot",
        budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Runs a direct head-to-head comparison duel between two PC listings or specs.
        Evaluates component matchups, fair market valuations, detected hazards,
        and scores both under the active optimization mode.
        """
        profile = None
        if self._resolve_mode:
            try:
                profile = self._resolve_mode(mode if mode != "all" else "sweet-spot")
            except Exception:
                profile = None

        ad_a = self.fetch_ad(target_a)
        ad_b = self.fetch_ad(target_b)

        eff_budget_a = budget or float(ad_a.get("price", 0.0))
        eff_budget_b = budget or float(ad_b.get("price", 0.0))

        specs_a = self.parse_specs(
            title=ad_a.get("title", ""),
            description=ad_a.get("description", ""),
            price=eff_budget_a,
        )
        if ad_a.get("url"):
            specs_a.url = ad_a["url"]

        specs_b = self.parse_specs(
            title=ad_b.get("title", ""),
            description=ad_b.get("description", ""),
            price=eff_budget_b,
        )
        if ad_b.get("url"):
            specs_b.url = ad_b["url"]

        val_a = self.calculate_fair_value(specs_a)
        val_b = self.calculate_fair_value(specs_b)

        risks_a = self.detect_risks(specs_a)
        risks_b = self.detect_risks(specs_b)

        build_a = self._specs_to_build(specs_a, val_a)
        build_b = self._specs_to_build(specs_b, val_b)

        score_a = 50.0
        score_b = 50.0
        if self._score_build and profile:
            try:
                score_a = round(self._score_build(build_a, val_a["asking_price"], profile), 1)
            except Exception:
                score_a = 50.0
            try:
                score_b = round(self._score_build(build_b, val_b["asking_price"], profile), 1)
            except Exception:
                score_b = 50.0

        matchups = self._build_matchups(specs_a, specs_b, build_a, build_b)

        crit_a = any(r["severity"] == "CRITICAL" for r in risks_a)
        crit_b = any(r["severity"] == "CRITICAL" for r in risks_b)

        mode_name_display = profile.name if profile else mode

        if crit_a and not crit_b:
            winner = "B"
            winner_badge = "WINNER: OPTION B"
            reason = f"Option A has a critical safety hazard ({risks_a[0]['title']}). Option B is safe to purchase."
        elif crit_b and not crit_a:
            winner = "A"
            winner_badge = "WINNER: OPTION A"
            reason = f"Option B has a critical safety hazard ({risks_b[0]['title']}). Option A is safe to purchase."
        elif abs(score_a - score_b) <= 1.5:
            winner = "TIE"
            winner_badge = "EVEN MATCH (TIE)"
            reason = f"Both PCs offer comparable overall value ({score_a} vs {score_b} points under '{mode_name_display}' mode)."
        elif score_a > score_b:
            winner = "A"
            diff = round(score_a - score_b, 1)
            winner_badge = "WINNER: OPTION A"
            reason = f"Option A leads by +{diff} points under '{mode_name_display}' mode across performance, price, and reliability."
        else:
            winner = "B"
            diff = round(score_b - score_a, 1)
            winner_badge = "WINNER: OPTION B"
            reason = f"Option B leads by +{diff} points under '{mode_name_display}' mode across performance, price, and reliability."

        return {
            "is_duo": True,
            "target_a": target_a,
            "target_b": target_b,
            "specs_a": specs_a,
            "specs_b": specs_b,
            "valuation_a": val_a,
            "valuation_b": val_b,
            "risks_a": risks_a,
            "risks_b": risks_b,
            "score_a": score_a,
            "score_b": score_b,
            "mode_name": mode_name_display,
            "mode_title": profile.title if profile else mode,
            "matchups": matchups,
            "winner": winner,
            "winner_badge": winner_badge,
            "winner_reason": reason,
        }

    def render_cli(self, report: Dict[str, Any]) -> None:
        """Renders an attractive, aligned terminal Duel Card report."""
        if report.get("is_duo"):
            self._render_duo_cli(report)
            return

        specs: PrebuiltSpecs = report["specs"]
        val = report["valuation"]
        risks = report["risks"]
        alt = report.get("alternative")
        badge = report["verdict_badge"]
        rec = report["recommendation"]
        mode_data = report.get("mode")

        curr = val.get("currency") or getattr(specs, "currency", "UAH") or "UAH"
        print("\n" + "═" * 80)
        print("  KNAPSET PREBUILT EVALUATOR & MARKET DUEL")
        print("═" * 80)
        print(f"  Listing       : {specs.title[:65]}")
        if specs.url:
            print(f"  Link          : {specs.url}")
        print(f"  Asking Price  : {format_price(val['asking_price'], curr):>12}")
        markup_sign = "+" if val["markup_uah"] >= 0 else ""
        print(f"  Fair Value    : {format_price(val['total_fair_value'], curr):>12}  (Margin: {markup_sign}{format_price(val['markup_uah'], curr)} / {val['markup_pct']:+.1f}%)")
        if mode_data:
            m_score = float(mode_data.get("score", 0.0))
            bar_len = 20
            bar = int(min(100.0, max(0.0, m_score)) / 100.0 * bar_len)
            prog = "#" * bar + "-" * (bar_len - bar)
            print(f"  Mode Score [{mode_data.get('name', '').upper()} / {mode_data.get('title', '')}]: {m_score:.1f}/100 [{prog}]")
        print("─" * 80)

        # 1. Component Breakdown
        print("  Detected Components & Fair Market Valuation:")
        w_part = 14
        w_name = 38
        w_cost = 14
        print(f"  │ {'Section':<{w_part}} │ {'Detected Component':<{w_name}} │ {'Market Price':>{w_cost}} │")
        print(f"  ├─{'─'*w_part}─┼─{'─'*w_name}─┼─{'─'*w_cost}─┤")
        for p_key, p_data in val["parts"].items():
            k_disp = p_key.upper()
            n_disp = p_data["name"][:w_name]
            c_disp = format_price(p_data["market_price"], curr)
            print(f"  │ {k_disp:<{w_part}} │ {n_disp:<{w_name}} │ {c_disp:>{w_cost}} │")
        print(f"  └─{'─'*w_part}─┴─{'─'*w_name}─┴─{'─'*w_cost}─┘")

        # 2. Risks
        if risks:
            print("\n  [WARN] Risk Factors & Warnings:")
            for r in risks:
                sev = r["severity"]
                color_tag = "[CRITICAL]" if sev == "CRITICAL" else ("[WARN]" if sev == "WARNING" else "[INFO]")
                print(f"    {color_tag} [{r['title']}]: {r['desc']}")
        else:
            print("\n  [OK] No critical hardware risks detected in this build.")

        # 3. Duel (Prebuilt vs Alternative)
        if alt:
            print(f"\n  DUEL: PREBUILT vs BEST MARKET ALTERNATIVE (Budget: ~{format_price(val['asking_price'], curr)}):")
            print("  ┌" + "─" * 36 + "┬" + "─" * 38 + "┐")
            print(f"  │ {'PREBUILT LISTING':<34} │ {'RECOMMENDED ALTERNATIVE':<36} │")
            print("  ├" + "─" * 36 + "┼" + "─" * 38 + "┤")
            pb_gpu = specs.raw_matches.get("gpu", "N/A")[:32]
            pb_cpu = specs.raw_matches.get("cpu", "N/A")[:32]
            pb_fps = f"~{specs.gpu.get('fps_1080p', 50):.0f} FPS" if specs.gpu else "~50 FPS"

            alt_title = alt.get("title", "")[:36]
            alt_fps = f"~{alt.get('fps_1080p', 80):.0f} FPS"
            alt_cost = format_price(alt.get("price", val["asking_price"]), curr)

            print(f"  │ GPU: {pb_gpu:<29} │ {alt_title:<36} │")
            print(f"  │ CPU: {pb_cpu:<29} │ FPS 1080p: {alt_fps:<25} │")
            print(f"  │ Est. FPS: {pb_fps:<24} │ Price: {alt_cost:<29} │")
            print("  └" + "─" * 36 + "┴" + "─" * 38 + "┘")

        # 4. Verdict
        print("\n" + "═" * 80)
        print(f"  VERDICT: {badge}")
        print(f"     {rec}")
        print("═" * 80 + "\n")

    def _render_duo_cli(self, report: Dict[str, Any]) -> None:
        """Renders the 3-tier Head-to-Head Duel Card comparing two listings."""
        s_a: PrebuiltSpecs = report["specs_a"]
        s_b: PrebuiltSpecs = report["specs_b"]
        v_a = report["valuation_a"]
        v_b = report["valuation_b"]
        r_a = report["risks_a"]
        r_b = report["risks_b"]
        score_a = report["score_a"]
        score_b = report["score_b"]
        mode_name = report["mode_name"]
        mode_title = report["mode_title"]

        print("\n" + "═" * 86)
        print("  KNAPSET HEAD-TO-HEAD PREBUILT DUEL & COMPARATOR")
        print("═" * 86)
        print(f"  Evaluation Mode: {mode_name.upper()} ({mode_title})")
        print(f"  [A] {s_a.title[:76]}")
        print(f"  [B] {s_b.title[:76]}")
        print("─" * 86)

        # Tier 1: Matchup Table
        w_cat = 20
        w_col = 26
        w_lead = 8
        print("  COMPONENT MATCHUP:")
        print(f"  │ {'Component':<{w_cat}} │ {'Option A':<{w_col}} │ {'Option B':<{w_col}} │ {'Leader':^{w_lead}} │")
        print(f"  ├─{'─'*w_cat}─┼─{'─'*w_col}─┼─{'─'*w_col}─┼─{'─'*w_lead}─┤")
        for m in report["matchups"]:
            cat = m["category"][:w_cat]
            ca = m["a"][:w_col]
            cb = m["b"][:w_col]
            lead_tag = "[+] A" if m["leader"] == "A" else ("[+] B" if m["leader"] == "B" else "[=] TIE")
            print(f"  │ {cat:<{w_cat}} │ {ca:<{w_col}} │ {cb:<{w_col}} │ {lead_tag:^{w_lead}} │")
        print(f"  └─{'─'*w_cat}─┴─{'─'*w_col}─┴─{'─'*w_col}─┴─{'─'*w_lead}─┘")

        # Tier 2: Financials & Risks
        print("\n  FINANCIAL VALUATION & MARGIN:")
        f_cat = 28
        f_col = 24
        print(f"  │ {'Metric':<{f_cat}} │ {'Option A':>{f_col}} │ {'Option B':>{f_col}} │")
        print(f"  ├─{'─'*f_cat}─┼─{'─'*f_col}─┼─{'─'*f_col}─┤")
        curr_a = v_a.get("currency", "UAH")
        curr_b = v_b.get("currency", "UAH")
        ask_a_str = format_price(v_a["asking_price"], curr_a)
        ask_b_str = format_price(v_b["asking_price"], curr_b)
        fair_a_str = format_price(v_a["total_fair_value"], curr_a)
        fair_b_str = format_price(v_b["total_fair_value"], curr_b)
        sign_a = "+" if v_a["markup_uah"] >= 0 else ""
        sign_b = "+" if v_b["markup_uah"] >= 0 else ""
        diff_a_str = f"{sign_a}{format_price(v_a['markup_uah'], curr_a)} ({v_a['markup_pct']:+.1f}%)"
        diff_b_str = f"{sign_b}{format_price(v_b['markup_uah'], curr_b)} ({v_b['markup_pct']:+.1f}%)"
        print(f"  │ {'Asking Price':<{f_cat}} │ {ask_a_str:>{f_col}} │ {ask_b_str:>{f_col}} │")
        print(f"  │ {'Fair Hardware Value':<{f_cat}} │ {fair_a_str:>{f_col}} │ {fair_b_str:>{f_col}} │")
        print(f"  │ {'Seller Margin / Markup':<{f_cat}} │ {diff_a_str:>{f_col}} │ {diff_b_str:>{f_col}} │")
        print(f"  └─{'─'*f_cat}─┴─{'─'*f_col}─┴─{'─'*f_col}─┘")

        if r_a or r_b:
            print("\n  [WARN] RISK FACTORS:")
            if r_a:
                print("    Option A:")
                for r in r_a:
                    tag = "[CRITICAL]" if r["severity"] == "CRITICAL" else "[WARN]"
                    print(f"      {tag} [{r['title']}]: {r['desc']}")
            else:
                print("    Option A: [OK] Clean build (no critical risks)")

            if r_b:
                print("    Option B:")
                for r in r_b:
                    tag = "[CRITICAL]" if r["severity"] == "CRITICAL" else "[WARN]"
                    print(f"      {tag} [{r['title']}]: {r['desc']}")
            else:
                print("    Option B: [OK] Clean build (no critical risks)")

        # Tier 3: Active Mode Score & Grand Verdict
        bar_len = 20
        bar_a = int(min(100.0, max(0.0, score_a)) / 100.0 * bar_len)
        bar_b = int(min(100.0, max(0.0, score_b)) / 100.0 * bar_len)
        prog_a = "#" * bar_a + "-" * (bar_len - bar_a)
        prog_b = "#" * bar_b + "-" * (bar_len - bar_b)

        print(f"\n  ACTIVE MODE SCORE [{mode_name.upper()}]:")
        print(f"    Option A: {score_a:>5.1f} / 100  [{prog_a}]")
        print(f"    Option B: {score_b:>5.1f} / 100  [{prog_b}]")

        print("\n" + "═" * 86)
        print(f"  {report['winner_badge']}")
        print(f"     {report['winner_reason']}")
        print("═" * 86 + "\n")

import argparse


def _cli_prog() -> str:
    exe = Path(sys.argv[0]).name if sys.argv else ""
    return exe if exe in ("ks", "knapset") else "python3 main.py"


def main(argv: Optional[List[str]] = None, prog: Optional[str] = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)

    # 1. Intercept "vs" / "проти" separator if supplied as token
    clean_args: List[str] = []
    explicit_vs: Optional[str] = None
    i = 0
    while i < len(args_list):
        tok = args_list[i]
        if tok.lower() in ("vs", "проти") and i + 1 < len(args_list) and not args_list[i + 1].startswith("-"):
            explicit_vs = args_list[i + 1]
            i += 2
            continue
        clean_args.append(tok)
        i += 1

    parser = argparse.ArgumentParser(
        prog=prog or f"{_cli_prog()} pc compare",
        description="Head-to-head comparison duel of prebuilt PC listings vs market alternatives or other prebuilts with active mode scoring.",
    )
    parser.add_argument("target", nargs="?", default=None, help="First listing URL, cached ID, or spec text")
    parser.add_argument("target_b", nargs="?", default=None, help="Second listing URL, cached ID, or spec text")
    parser.add_argument("--vs", dest="vs_flag", default=None, help="Explicit second target to compare against")
    parser.add_argument("--mode", "-M", "-m", type=str, default="sweet-spot", help="Optimization profile mode (default: sweet-spot; options: best, value, safe, max-perf, esports, etc.)")
    parser.add_argument("--budget", "-b", type=float, default=None, help="Override budget / price point in UAH")
    parser.add_argument("--prebuilt-only", action="store_true", help="Compare strictly against other ready-made prebuilts")
    parser.add_argument("--diy-only", action="store_true", help="Compare strictly against custom DIY component builds")
    parser.add_argument("--vendor", "-V", type=str, default=None, help="Filter comparison alternatives by vendor (e.g. nvidia, amd, intel)")
    parser.add_argument("--retail", "-r", action="store_true", help="Compare against brand new retail store component prices")
    parser.add_argument("--no-ai", action="store_true", help="Bypass LLM semantic audit and run purely offline heuristic analysis")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args(clean_args)

    if not args.target:
        print("\nKnapset Prebuilt Evaluator & Head-to-Head Duel Comparator")
        print("═" * 84)
        print("Usage:")
        print(f"  • Single target duel vs market  : {prog} <target> [-M mode]")
        print(f"  • Head-to-head duel (A vs B)    : {prog} <target_a> vs <target_b> [-M mode]\n")
        print("Examples:")
        print(f"  {prog} 'Ryzen 5 3600, RTX 2060 Super, $450' -M sweet-spot")
        print(f"  {prog} 'i5 10400F, RTX 3060, $500' vs 'Ryzen 5600, RX 6700 XT, $560' -M value")
        print(f"  {prog} 'https://olx.ua/d/ad1' vs 'https://olx.ua/d/ad2' -M safe")
        print(f"  {prog} 'Ryzen 3600, GTX 1660, $350' --budget 400\n")
        return

    target_a = args.target
    target_b = explicit_vs or args.vs_flag or args.target_b

    # Check if target_a contains inline ' vs ' or ' проти '
    if not target_b:
        for sep in (" vs ", " VS ", " проти "):
            if sep in target_a:
                parts = target_a.split(sep, 1)
                target_a = parts[0].strip()
                target_b = parts[1].strip()
                break

    evaluator = PrebuiltEvaluator()

    if target_b:
        report = evaluator.compare_duo(
            target_a=target_a,
            target_b=target_b,
            mode=args.mode,
            budget=args.budget,
        )
    else:
        single_mode = "prebuilt-only" if args.prebuilt_only else ("diy-only" if args.diy_only else args.mode)
        report = evaluator.evaluate(
            target_input=target_a,
            mode=single_mode,
            vendor=args.vendor,
            retail=args.retail,
            budget=args.budget,
        )

    if args.json:
        import dataclasses
        def _json_serialize(obj: Any) -> Any:
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            return str(obj)
        print(json.dumps(report, default=_json_serialize, indent=2, ensure_ascii=False))
        return

    evaluator.render_cli(report)


if __name__ == "__main__":
    main()
