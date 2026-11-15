"""
Comprehensive CPU Benchmark Database and Model Matcher (2026 Calibrated Edition).

Contains multi-dimensional benchmark & architectural telemetry across 125+ desktop CPUs:
  - `fps_gaming`    : 1080p multi-game geometric mean FPS (RTX 4090/5090 testbench; TechPowerUp / HUB / Tom's Hardware)
  - `fps_1pct_low`  : 1080p 1% low FPS (frametime consistency / micro-stutter resistance — highlights 3D V-Cache)
  - `cb_r23_multi`  : Cinebench R23 Multi-Core score (true workstation throughput without E-core / slow-Xeon distortion)
  - `l3_cache_mb`   : Total L3 cache in MB (96-192MB X3D vs 32-64MB desktop vs 16MB monolithic APU cut-downs)
  - `gaming_watts`  : Typical real-world gaming package power draw (W) vs peak all-core `tdp_watts`
  - `pcie_lanes_gpu`: Dedicated GPU PCIe lanes (16 standard vs x8 on 8700G/8700F/8400F and x4 on 8500G)
  - `market_used_min` / `market_used_max`: Calibrated Nov 2026 Ukrainian OLX market ranges (UAH)
"""

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

CPU_DATABASE: Dict[str, Dict[str, Any]] = {
    # ==================== AMD AM5 (Zen 5 & Zen 4 — 3D V-Cache) ====================
    "RYZEN 9 9950X3D2": {
        "fps_gaming": 262.0, "fps_1pct_low": 206.0, "cb_r23_multi": 42200, "l3_cache_mb": 192,
        "cores": 16, "threads": 32, "gaming_watts": 82, "tdp_watts": 200, "socket": "AM5", "brand": "AMD",
        "market_used_min": 31000, "market_used_max": 39500,
    },
    "RYZEN 7 9850X3D": {
        "fps_gaming": 261.0, "fps_1pct_low": 205.0, "cb_r23_multi": 24000, "l3_cache_mb": 96,
        "cores": 8, "threads": 16, "gaming_watts": 68, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 20500, "market_used_max": 26500,
    },
    "RYZEN 9 9950X3D": {
        "fps_gaming": 256.0, "fps_1pct_low": 199.0, "cb_r23_multi": 41800, "l3_cache_mb": 128,
        "cores": 16, "threads": 32, "gaming_watts": 76, "tdp_watts": 170, "socket": "AM5", "brand": "AMD",
        "market_used_min": 23500, "market_used_max": 30500,
    },
    "RYZEN 7 9800X3D": {
        "fps_gaming": 255.0, "fps_1pct_low": 198.0, "cb_r23_multi": 23300, "l3_cache_mb": 96,
        "cores": 8, "threads": 16, "gaming_watts": 65, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 17500, "market_used_max": 22500,
    },
    "RYZEN 9 9900X3D": {
        "fps_gaming": 238.0, "fps_1pct_low": 183.0, "cb_r23_multi": 33200, "l3_cache_mb": 128,
        "cores": 12, "threads": 24, "gaming_watts": 70, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 19500, "market_used_max": 25500,
    },
    "RYZEN 5 9600X3D": {
        "fps_gaming": 236.0, "fps_1pct_low": 184.0, "cb_r23_multi": 16500, "l3_cache_mb": 96,
        "cores": 6, "threads": 12, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 13000, "market_used_max": 17000,
    },
    "RYZEN 7 7800X3D": {
        "fps_gaming": 234.0, "fps_1pct_low": 182.0, "cb_r23_multi": 18400, "l3_cache_mb": 96,
        "cores": 8, "threads": 16, "gaming_watts": 54, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 12000, "market_used_max": 15800,
    },
    "RYZEN 9 7950X3D": {
        "fps_gaming": 229.0, "fps_1pct_low": 176.0, "cb_r23_multi": 36200, "l3_cache_mb": 128,
        "cores": 16, "threads": 32, "gaming_watts": 68, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 18500, "market_used_max": 25000,
    },
    "RYZEN 5 7600X3D": {
        "fps_gaming": 216.0, "fps_1pct_low": 168.0, "cb_r23_multi": 13800, "l3_cache_mb": 96,
        "cores": 6, "threads": 12, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 10500, "market_used_max": 14000,
    },
    "RYZEN 9 7900X3D": {
        "fps_gaming": 213.0, "fps_1pct_low": 163.0, "cb_r23_multi": 27800, "l3_cache_mb": 128,
        "cores": 12, "threads": 24, "gaming_watts": 64, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 14000, "market_used_max": 18500,
    },
    "RYZEN 5 7500X3D": {
        "fps_gaming": 210.0, "fps_1pct_low": 163.0, "cb_r23_multi": 13100, "l3_cache_mb": 96,
        "cores": 6, "threads": 12, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 8500, "market_used_max": 11500,
    },

    # ==================== AMD AM5 (Standard Zen 5 & Zen 4 — 32/64MB L3) ====================
    "RYZEN 9 9950X": {
        "fps_gaming": 200.0, "fps_1pct_low": 148.0, "cb_r23_multi": 41800, "l3_cache_mb": 64,
        "cores": 16, "threads": 32, "gaming_watts": 95, "tdp_watts": 170, "socket": "AM5", "brand": "AMD",
        "market_used_min": 19500, "market_used_max": 26000,
    },
    "RYZEN 7 9700X": {
        "fps_gaming": 195.0, "fps_1pct_low": 146.0, "cb_r23_multi": 20600, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 64, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 9000, "market_used_max": 12200,
    },
    "RYZEN 9 9900X": {
        "fps_gaming": 194.0, "fps_1pct_low": 144.0, "cb_r23_multi": 32800, "l3_cache_mb": 64,
        "cores": 12, "threads": 24, "gaming_watts": 85, "tdp_watts": 120, "socket": "AM5", "brand": "AMD",
        "market_used_min": 14000, "market_used_max": 18500,
    },
    "RYZEN 7 9700F": {
        "fps_gaming": 191.0, "fps_1pct_low": 143.0, "cb_r23_multi": 19800, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 62, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 8000, "market_used_max": 10800,
    },
    "RYZEN 9 7950X": {
        "fps_gaming": 190.0, "fps_1pct_low": 141.0, "cb_r23_multi": 37800, "l3_cache_mb": 64,
        "cores": 16, "threads": 32, "gaming_watts": 105, "tdp_watts": 170, "socket": "AM5", "brand": "AMD",
        "market_used_min": 13500, "market_used_max": 18000,
    },
    "RYZEN 5 9600X": {
        "fps_gaming": 187.0, "fps_1pct_low": 140.0, "cb_r23_multi": 16600, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 60, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 6800, "market_used_max": 9200,
    },
    "RYZEN 7 7700X": {
        "fps_gaming": 187.0, "fps_1pct_low": 140.0, "cb_r23_multi": 19800, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 78, "tdp_watts": 105, "socket": "AM5", "brand": "AMD",
        "market_used_min": 7800, "market_used_max": 10500,
    },
    "RYZEN 9 7900X": {
        "fps_gaming": 186.0, "fps_1pct_low": 138.0, "cb_r23_multi": 29000, "l3_cache_mb": 64,
        "cores": 12, "threads": 24, "gaming_watts": 95, "tdp_watts": 170, "socket": "AM5", "brand": "AMD",
        "market_used_min": 11000, "market_used_max": 14500,
    },
    "RYZEN 5 9600": {
        "fps_gaming": 184.0, "fps_1pct_low": 138.0, "cb_r23_multi": 16000, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 58, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 6200, "market_used_max": 8400,
    },
    "RYZEN 7 7700": {
        "fps_gaming": 182.0, "fps_1pct_low": 136.0, "cb_r23_multi": 18800, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 62, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 6500, "market_used_max": 9000,
    },
    "RYZEN 5 7600X": {
        "fps_gaming": 181.0, "fps_1pct_low": 135.0, "cb_r23_multi": 15200, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 72, "tdp_watts": 105, "socket": "AM5", "brand": "AMD",
        "market_used_min": 5800, "market_used_max": 7800,
    },
    "RYZEN 9 7900": {
        "fps_gaming": 181.0, "fps_1pct_low": 135.0, "cb_r23_multi": 25800, "l3_cache_mb": 64,
        "cores": 12, "threads": 24, "gaming_watts": 65, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 10800, "market_used_max": 14500,
    },
    "RYZEN 5 9500F": {
        "fps_gaming": 180.0, "fps_1pct_low": 135.0, "cb_r23_multi": 15400, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 56, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 5500, "market_used_max": 7500,
    },
    "RYZEN 5 7600": {
        "fps_gaming": 177.0, "fps_1pct_low": 133.0, "cb_r23_multi": 14500, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 58, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 5400, "market_used_max": 7400,
    },
    "RYZEN 5 7500F": {
        "fps_gaming": 175.0, "fps_1pct_low": 131.0, "cb_r23_multi": 14300, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 58, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 4500, "market_used_max": 6200,
    },
    "RYZEN 5 7400F": {
        "fps_gaming": 168.0, "fps_1pct_low": 126.0, "cb_r23_multi": 13600, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5000,
    },

    # ==================== AMD AM5 (8000G/8000F Monolithic 16MB L3 + PCIe x8/x4) ====================
    "RYZEN 7 8700G": {
        "fps_gaming": 156.0, "fps_1pct_low": 115.0, "cb_r23_multi": 17800, "l3_cache_mb": 16, "pcie_lanes_gpu": 8,
        "cores": 8, "threads": 16, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 9500, "market_used_max": 13000,
    },
    "RYZEN 7 8700F": {
        "fps_gaming": 153.0, "fps_1pct_low": 113.0, "cb_r23_multi": 17200, "l3_cache_mb": 16, "pcie_lanes_gpu": 8,
        "cores": 8, "threads": 16, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 4800, "market_used_max": 6600,
    },
    "RYZEN 5 8600G": {
        "fps_gaming": 148.0, "fps_1pct_low": 109.0, "cb_r23_multi": 13800, "l3_cache_mb": 16, "pcie_lanes_gpu": 8,
        "cores": 6, "threads": 12, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 6400, "market_used_max": 8500,
    },
    "RYZEN 5 8400F": {
        "fps_gaming": 145.0, "fps_1pct_low": 107.0, "cb_r23_multi": 13200, "l3_cache_mb": 16, "pcie_lanes_gpu": 8,
        "cores": 6, "threads": 12, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 3300, "market_used_max": 4600,
    },
    "RYZEN 5 8500G": {
        "fps_gaming": 130.0, "fps_1pct_low": 95.0, "cb_r23_multi": 12200, "l3_cache_mb": 16, "pcie_lanes_gpu": 4,
        "cores": 6, "threads": 12, "gaming_watts": 42, "tdp_watts": 65, "socket": "AM5", "brand": "AMD",
        "market_used_min": 5500, "market_used_max": 7800,
    },

    # ==================== AMD AM4 (3D V-Cache & Zen 3 / Zen 2 / Zen 1) ====================
    "RYZEN 7 5800X3D": {
        "fps_gaming": 196.0, "fps_1pct_low": 154.0, "cb_r23_multi": 14600, "l3_cache_mb": 96,
        "cores": 8, "threads": 16, "gaming_watts": 62, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 11000, "market_used_max": 15500,
    },
    "RYZEN 7 5700X3D": {
        "fps_gaming": 188.0, "fps_1pct_low": 147.0, "cb_r23_multi": 13600, "l3_cache_mb": 96,
        "cores": 8, "threads": 16, "gaming_watts": 58, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 8500, "market_used_max": 13500,
    },
    "RYZEN 5 5600X3D": {
        "fps_gaming": 184.0, "fps_1pct_low": 143.0, "cb_r23_multi": 11200, "l3_cache_mb": 96,
        "cores": 6, "threads": 12, "gaming_watts": 54, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 7500, "market_used_max": 11000,
    },
    "RYZEN 5 5500X3D": {
        "fps_gaming": 174.0, "fps_1pct_low": 135.0, "cb_r23_multi": 10400, "l3_cache_mb": 96,
        "cores": 6, "threads": 12, "gaming_watts": 52, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 7800, "market_used_max": 10800,
    },
    "RYZEN 9 5950X": {
        "fps_gaming": 158.0, "fps_1pct_low": 117.0, "cb_r23_multi": 28500, "l3_cache_mb": 64,
        "cores": 16, "threads": 32, "gaming_watts": 85, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 10500, "market_used_max": 14500,
    },
    "RYZEN 9 5900XT": {
        "fps_gaming": 157.0, "fps_1pct_low": 116.0, "cb_r23_multi": 27800, "l3_cache_mb": 64,
        "cores": 16, "threads": 32, "gaming_watts": 85, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 10500, "market_used_max": 14500,
    },
    "RYZEN 9 5900X": {
        "fps_gaming": 156.0, "fps_1pct_low": 115.0, "cb_r23_multi": 21500, "l3_cache_mb": 64,
        "cores": 12, "threads": 24, "gaming_watts": 82, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 8000, "market_used_max": 11500,
    },
    "RYZEN 7 5800XT": {
        "fps_gaming": 155.0, "fps_1pct_low": 114.0, "cb_r23_multi": 15600, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 72, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 6200, "market_used_max": 8500,
    },
    "RYZEN 7 5800X": {
        "fps_gaming": 153.0, "fps_1pct_low": 113.0, "cb_r23_multi": 15200, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 72, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 5800, "market_used_max": 8000,
    },
    "RYZEN 7 5700X": {
        "fps_gaming": 149.0, "fps_1pct_low": 111.0, "cb_r23_multi": 14600, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 5000, "market_used_max": 7000,
    },
    "RYZEN 5 5600XT": {
        "fps_gaming": 147.0, "fps_1pct_low": 110.0, "cb_r23_multi": 11600, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 54, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 4500, "market_used_max": 6000,
    },
    "RYZEN 5 5600X": {
        "fps_gaming": 145.0, "fps_1pct_low": 108.0, "cb_r23_multi": 11400, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 54, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 4300, "market_used_max": 5800,
    },
    "RYZEN 5 5600": {
        "fps_gaming": 142.0, "fps_1pct_low": 106.0, "cb_r23_multi": 11000, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5200,
    },
    "RYZEN 7 5700G": {
        "fps_gaming": 131.0, "fps_1pct_low": 96.0, "cb_r23_multi": 14000, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 5200, "market_used_max": 7500,
    },
    "RYZEN 7 5750G": {
        "fps_gaming": 131.0, "fps_1pct_low": 96.0, "cb_r23_multi": 14000, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 5200, "market_used_max": 7500,
    },
    "RYZEN 7 5700": {
        "fps_gaming": 128.0, "fps_1pct_low": 94.0, "cb_r23_multi": 13600, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 4200, "market_used_max": 5800,
    },
    "RYZEN 5 5600GT": {
        "fps_gaming": 128.0, "fps_1pct_low": 94.0, "cb_r23_multi": 11000, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 4500, "market_used_max": 6200,
    },
    "RYZEN 5 5600G": {
        "fps_gaming": 126.0, "fps_1pct_low": 93.0, "cb_r23_multi": 10800, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5400,
    },
    "RYZEN 5 5650G": {
        "fps_gaming": 126.0, "fps_1pct_low": 93.0, "cb_r23_multi": 10800, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5400,
    },
    "RYZEN 5 5500GT": {
        "fps_gaming": 123.0, "fps_1pct_low": 91.0, "cb_r23_multi": 10500, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 46, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5200,
    },
    "RYZEN 5 5500": {
        "fps_gaming": 120.0, "fps_1pct_low": 89.0, "cb_r23_multi": 10400, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 45, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2800, "market_used_max": 3900,
    },
    "RYZEN 7 4750G": {
        "fps_gaming": 112.0, "fps_1pct_low": 82.0, "cb_r23_multi": 11800, "l3_cache_mb": 8,
        "cores": 8, "threads": 16, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5500,
    },
    "RYZEN 5 4600G": {
        "fps_gaming": 104.0, "fps_1pct_low": 76.0, "cb_r23_multi": 9200, "l3_cache_mb": 8,
        "cores": 6, "threads": 12, "gaming_watts": 45, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2600, "market_used_max": 3700,
    },
    "RYZEN 5 4500": {
        "fps_gaming": 98.0, "fps_1pct_low": 72.0, "cb_r23_multi": 8800, "l3_cache_mb": 8,
        "cores": 6, "threads": 12, "gaming_watts": 45, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2300, "market_used_max": 3300,
    },
    "RYZEN 3 4300G": {
        "fps_gaming": 86.0, "fps_1pct_low": 63.0, "cb_r23_multi": 6200, "l3_cache_mb": 4,
        "cores": 4, "threads": 8, "gaming_watts": 38, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2200, "market_used_max": 3300,
    },
    "RYZEN 3 4100": {
        "fps_gaming": 86.0, "fps_1pct_low": 63.0, "cb_r23_multi": 6000, "l3_cache_mb": 4,
        "cores": 4, "threads": 8, "gaming_watts": 38, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1500, "market_used_max": 2300,
    },
    "RYZEN 9 3950X": {
        "fps_gaming": 131.0, "fps_1pct_low": 95.0, "cb_r23_multi": 22500, "l3_cache_mb": 64,
        "cores": 16, "threads": 32, "gaming_watts": 88, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 8500, "market_used_max": 12000,
    },
    "RYZEN 9 3900X": {
        "fps_gaming": 127.0, "fps_1pct_low": 92.0, "cb_r23_multi": 18400, "l3_cache_mb": 64,
        "cores": 12, "threads": 24, "gaming_watts": 82, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 5500, "market_used_max": 7800,
    },
    "RYZEN 7 3800XT": {
        "fps_gaming": 118.0, "fps_1pct_low": 86.0, "cb_r23_multi": 12800, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 72, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 4000, "market_used_max": 5600,
    },
    "RYZEN 7 3800X": {
        "fps_gaming": 116.0, "fps_1pct_low": 85.0, "cb_r23_multi": 12500, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 70, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3800, "market_used_max": 5300,
    },
    "RYZEN 7 3700X": {
        "fps_gaming": 113.0, "fps_1pct_low": 83.0, "cb_r23_multi": 12100, "l3_cache_mb": 32,
        "cores": 8, "threads": 16, "gaming_watts": 58, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 3500, "market_used_max": 5000,
    },
    "RYZEN 5 3600X": {
        "fps_gaming": 111.0, "fps_1pct_low": 81.0, "cb_r23_multi": 9500, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 56, "tdp_watts": 95, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2600, "market_used_max": 3700,
    },
    "RYZEN 5 3600": {
        "fps_gaming": 108.0, "fps_1pct_low": 79.0, "cb_r23_multi": 9200, "l3_cache_mb": 32,
        "cores": 6, "threads": 12, "gaming_watts": 52, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2300, "market_used_max": 3500,
    },
    "RYZEN 5 3500X": {
        "fps_gaming": 94.0, "fps_1pct_low": 66.0, "cb_r23_multi": 6800, "l3_cache_mb": 32,
        "cores": 6, "threads": 6, "gaming_watts": 48, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1900, "market_used_max": 2900,
    },
    "RYZEN 5 3400G": {
        "fps_gaming": 74.0, "fps_1pct_low": 53.0, "cb_r23_multi": 5400, "l3_cache_mb": 4,
        "cores": 4, "threads": 8, "gaming_watts": 45, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2100, "market_used_max": 3100,
    },
    "RYZEN 3 3300X": {
        "fps_gaming": 101.0, "fps_1pct_low": 72.0, "cb_r23_multi": 6600, "l3_cache_mb": 16,
        "cores": 4, "threads": 8, "gaming_watts": 46, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1800, "market_used_max": 2600,
    },
    "RYZEN 3 3200G": {
        "fps_gaming": 64.0, "fps_1pct_low": 45.0, "cb_r23_multi": 3900, "l3_cache_mb": 4,
        "cores": 4, "threads": 4, "gaming_watts": 40, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1100, "market_used_max": 1800,
    },
    "RYZEN 3 3100": {
        "fps_gaming": 90.0, "fps_1pct_low": 64.0, "cb_r23_multi": 5900, "l3_cache_mb": 16,
        "cores": 4, "threads": 8, "gaming_watts": 42, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1300, "market_used_max": 2000,
    },
    "RYZEN 7 2700X": {
        "fps_gaming": 91.0, "fps_1pct_low": 65.0, "cb_r23_multi": 10200, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 72, "tdp_watts": 105, "socket": "AM4", "brand": "AMD",
        "market_used_min": 2100, "market_used_max": 3100,
    },
    "RYZEN 7 2700": {
        "fps_gaming": 86.0, "fps_1pct_low": 61.0, "cb_r23_multi": 9400, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 58, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1700, "market_used_max": 2500,
    },
    "RYZEN 5 2600X": {
        "fps_gaming": 85.0, "fps_1pct_low": 61.0, "cb_r23_multi": 7600, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 60, "tdp_watts": 95, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1500, "market_used_max": 2300,
    },
    "RYZEN 5 2600": {
        "fps_gaming": 81.0, "fps_1pct_low": 58.0, "cb_r23_multi": 7200, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 52, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1300, "market_used_max": 2100,
    },
    "RYZEN 5 2400G": {
        "fps_gaming": 68.0, "fps_1pct_low": 48.0, "cb_r23_multi": 4800, "l3_cache_mb": 4,
        "cores": 4, "threads": 8, "gaming_watts": 44, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1500, "market_used_max": 2300,
    },
    "RYZEN 3 2200G": {
        "fps_gaming": 60.0, "fps_1pct_low": 42.0, "cb_r23_multi": 3500, "l3_cache_mb": 4,
        "cores": 4, "threads": 4, "gaming_watts": 38, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 800, "market_used_max": 1350,
    },
    "RYZEN 7 1800X": {
        "fps_gaming": 80.0, "fps_1pct_low": 56.0, "cb_r23_multi": 9000, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 68, "tdp_watts": 95, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1600, "market_used_max": 2400,
    },
    "RYZEN 7 1700X": {
        "fps_gaming": 78.0, "fps_1pct_low": 55.0, "cb_r23_multi": 8700, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 65, "tdp_watts": 95, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1500, "market_used_max": 2200,
    },
    "RYZEN 7 1700": {
        "fps_gaming": 75.0, "fps_1pct_low": 53.0, "cb_r23_multi": 8300, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 55, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1400, "market_used_max": 2100,
    },
    "RYZEN 5 1600X": {
        "fps_gaming": 72.0, "fps_1pct_low": 51.0, "cb_r23_multi": 6600, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 58, "tdp_watts": 95, "socket": "AM4", "brand": "AMD",
        "market_used_min": 1100, "market_used_max": 1800,
    },
    "RYZEN 5 1600": {
        "fps_gaming": 68.0, "fps_1pct_low": 48.0, "cb_r23_multi": 6300, "l3_cache_mb": 16,
        "cores": 6, "threads": 12, "gaming_watts": 50, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 950, "market_used_max": 1650,
    },
    "RYZEN 5 1500X": {
        "fps_gaming": 62.0, "fps_1pct_low": 44.0, "cb_r23_multi": 4500, "l3_cache_mb": 16,
        "cores": 4, "threads": 8, "gaming_watts": 45, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 700, "market_used_max": 1200,
    },
    "RYZEN 5 1400": {
        "fps_gaming": 58.0, "fps_1pct_low": 41.0, "cb_r23_multi": 4200, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 42, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 750, "market_used_max": 1300,
    },
    "RYZEN 3 1300X": {
        "fps_gaming": 55.0, "fps_1pct_low": 38.0, "cb_r23_multi": 3300, "l3_cache_mb": 8,
        "cores": 4, "threads": 4, "gaming_watts": 40, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 600, "market_used_max": 1000,
    },
    "RYZEN 3 1200": {
        "fps_gaming": 52.0, "fps_1pct_low": 36.0, "cb_r23_multi": 3100, "l3_cache_mb": 8,
        "cores": 4, "threads": 4, "gaming_watts": 38, "tdp_watts": 65, "socket": "AM4", "brand": "AMD",
        "market_used_min": 500, "market_used_max": 950,
    },

    # ==================== INTEL CORE ULTRA (LGA1851 — Arrow Lake & Refresh) ====================
    "CORE ULTRA 9 290K PLUS": {
        "fps_gaming": 202.0, "fps_1pct_low": 148.0, "cb_r23_multi": 40500, "l3_cache_mb": 36,
        "cores": 24, "threads": 24, "gaming_watts": 95, "tdp_watts": 200, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 20000, "market_used_max": 26500,
    },
    "CORE ULTRA 9 285K": {
        "fps_gaming": 195.0, "fps_1pct_low": 143.0, "cb_r23_multi": 38200, "l3_cache_mb": 36,
        "cores": 24, "threads": 24, "gaming_watts": 90, "tdp_watts": 200, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 18500, "market_used_max": 23500,
    },
    "CORE ULTRA 7 270K PLUS": {
        "fps_gaming": 196.0, "fps_1pct_low": 145.0, "cb_r23_multi": 37500, "l3_cache_mb": 36,
        "cores": 24, "threads": 24, "gaming_watts": 88, "tdp_watts": 180, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 14500, "market_used_max": 19000,
    },
    "CORE ULTRA 7 265K": {
        "fps_gaming": 189.0, "fps_1pct_low": 139.0, "cb_r23_multi": 34800, "l3_cache_mb": 30,
        "cores": 20, "threads": 20, "gaming_watts": 85, "tdp_watts": 180, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 12500, "market_used_max": 16800,
    },
    "CORE ULTRA 5 250K PLUS": {
        "fps_gaming": 183.0, "fps_1pct_low": 136.0, "cb_r23_multi": 27500, "l3_cache_mb": 28,
        "cores": 18, "threads": 18, "gaming_watts": 75, "tdp_watts": 150, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 8000, "market_used_max": 11500,
    },
    "CORE ULTRA 5 245K": {
        "fps_gaming": 177.0, "fps_1pct_low": 131.0, "cb_r23_multi": 25200, "l3_cache_mb": 24,
        "cores": 14, "threads": 14, "gaming_watts": 72, "tdp_watts": 150, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 7200, "market_used_max": 10500,
    },
    "CORE ULTRA 5 235": {
        "fps_gaming": 164.0, "fps_1pct_low": 121.0, "cb_r23_multi": 21500, "l3_cache_mb": 24,
        "cores": 14, "threads": 14, "gaming_watts": 58, "tdp_watts": 65, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 7500, "market_used_max": 11000,
    },
    "CORE ULTRA 5 230F": {
        "fps_gaming": 160.0, "fps_1pct_low": 119.0, "cb_r23_multi": 18200, "l3_cache_mb": 24,
        "cores": 10, "threads": 10, "gaming_watts": 55, "tdp_watts": 65, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 5200, "market_used_max": 7500,
    },
    "CORE ULTRA 5 225F": {
        "fps_gaming": 158.0, "fps_1pct_low": 117.0, "cb_r23_multi": 17800, "l3_cache_mb": 20,
        "cores": 10, "threads": 10, "gaming_watts": 55, "tdp_watts": 65, "socket": "LGA1851", "brand": "Intel",
        "market_used_min": 5400, "market_used_max": 7800,
    },

    # ==================== INTEL LGA1700 (12th / 13th / 14th Gen) ====================
    "CORE I9-14900K": {
        "fps_gaming": 208.0, "fps_1pct_low": 150.0, "cb_r23_multi": 38800, "l3_cache_mb": 36,
        "cores": 24, "threads": 32, "gaming_watts": 148, "tdp_watts": 253, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 17000, "market_used_max": 22500,
    },
    "CORE I9-14900": {
        "fps_gaming": 196.0, "fps_1pct_low": 142.0, "cb_r23_multi": 35000, "l3_cache_mb": 36,
        "cores": 24, "threads": 32, "gaming_watts": 115, "tdp_watts": 180, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 15000, "market_used_max": 19500,
    },
    "CORE I9-13900K": {
        "fps_gaming": 204.0, "fps_1pct_low": 148.0, "cb_r23_multi": 37500, "l3_cache_mb": 36,
        "cores": 24, "threads": 32, "gaming_watts": 142, "tdp_watts": 253, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 15000, "market_used_max": 20000,
    },
    "CORE I9-13900": {
        "fps_gaming": 192.0, "fps_1pct_low": 139.0, "cb_r23_multi": 33500, "l3_cache_mb": 36,
        "cores": 24, "threads": 32, "gaming_watts": 112, "tdp_watts": 180, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 13500, "market_used_max": 18000,
    },
    "CORE I9-12900K": {
        "fps_gaming": 180.0, "fps_1pct_low": 132.0, "cb_r23_multi": 27400, "l3_cache_mb": 30,
        "cores": 16, "threads": 24, "gaming_watts": 118, "tdp_watts": 200, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 11500, "market_used_max": 15500,
    },
    "CORE I9-12900": {
        "fps_gaming": 173.0, "fps_1pct_low": 127.0, "cb_r23_multi": 25000, "l3_cache_mb": 30,
        "cores": 16, "threads": 24, "gaming_watts": 95, "tdp_watts": 150, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 9800, "market_used_max": 13200,
    },
    "CORE I7-14700K": {
        "fps_gaming": 201.0, "fps_1pct_low": 146.0, "cb_r23_multi": 34500, "l3_cache_mb": 33,
        "cores": 20, "threads": 28, "gaming_watts": 130, "tdp_watts": 230, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 13000, "market_used_max": 17000,
    },
    "CORE I7-14700": {
        "fps_gaming": 186.0, "fps_1pct_low": 136.0, "cb_r23_multi": 31500, "l3_cache_mb": 33,
        "cores": 20, "threads": 28, "gaming_watts": 105, "tdp_watts": 165, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 12500, "market_used_max": 16500,
    },
    "CORE I7-13700K": {
        "fps_gaming": 197.0, "fps_1pct_low": 143.0, "cb_r23_multi": 30500, "l3_cache_mb": 30,
        "cores": 16, "threads": 24, "gaming_watts": 122, "tdp_watts": 220, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 12000, "market_used_max": 16000,
    },
    "CORE I7-13700": {
        "fps_gaming": 182.0, "fps_1pct_low": 133.0, "cb_r23_multi": 27800, "l3_cache_mb": 30,
        "cores": 16, "threads": 24, "gaming_watts": 98, "tdp_watts": 150, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 10500, "market_used_max": 14000,
    },
    "CORE I7-12700K": {
        "fps_gaming": 172.0, "fps_1pct_low": 127.0, "cb_r23_multi": 22800, "l3_cache_mb": 25,
        "cores": 12, "threads": 20, "gaming_watts": 98, "tdp_watts": 180, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 8000, "market_used_max": 10800,
    },
    "CORE I7-12700": {
        "fps_gaming": 166.0, "fps_1pct_low": 122.0, "cb_r23_multi": 21000, "l3_cache_mb": 25,
        "cores": 12, "threads": 20, "gaming_watts": 85, "tdp_watts": 140, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 7200, "market_used_max": 9600,
    },
    "CORE I5-14600K": {
        "fps_gaming": 188.0, "fps_1pct_low": 139.0, "cb_r23_multi": 24400, "l3_cache_mb": 24,
        "cores": 14, "threads": 20, "gaming_watts": 98, "tdp_watts": 181, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 9500, "market_used_max": 12800,
    },
    "CORE I5-13600K": {
        "fps_gaming": 185.0, "fps_1pct_low": 137.0, "cb_r23_multi": 23800, "l3_cache_mb": 24,
        "cores": 14, "threads": 20, "gaming_watts": 95, "tdp_watts": 181, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 8200, "market_used_max": 11000,
    },
    "CORE I5-14500": {
        "fps_gaming": 165.0, "fps_1pct_low": 121.0, "cb_r23_multi": 21200, "l3_cache_mb": 24,
        "cores": 14, "threads": 20, "gaming_watts": 72, "tdp_watts": 115, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 8200, "market_used_max": 10800,
    },
    "CORE I5-13500": {
        "fps_gaming": 162.0, "fps_1pct_low": 119.0, "cb_r23_multi": 20500, "l3_cache_mb": 24,
        "cores": 14, "threads": 20, "gaming_watts": 70, "tdp_watts": 115, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 7500, "market_used_max": 10200,
    },
    "CORE I5-12600K": {
        "fps_gaming": 164.0, "fps_1pct_low": 121.0, "cb_r23_multi": 17600, "l3_cache_mb": 20,
        "cores": 10, "threads": 16, "gaming_watts": 82, "tdp_watts": 150, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 6800, "market_used_max": 9200,
    },
    "CORE I5-12600": {
        "fps_gaming": 148.0, "fps_1pct_low": 110.0, "cb_r23_multi": 13000, "l3_cache_mb": 18,
        "cores": 6, "threads": 12, "gaming_watts": 58, "tdp_watts": 65, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 5200, "market_used_max": 7000,
    },
    "CORE I5-12500": {
        "fps_gaming": 144.0, "fps_1pct_low": 107.0, "cb_r23_multi": 12600, "l3_cache_mb": 18,
        "cores": 6, "threads": 12, "gaming_watts": 56, "tdp_watts": 65, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 4800, "market_used_max": 6400,
    },
    "CORE I5-14400F": {
        "fps_gaming": 152.0, "fps_1pct_low": 112.0, "cb_r23_multi": 16200, "l3_cache_mb": 20,
        "cores": 10, "threads": 16, "gaming_watts": 62, "tdp_watts": 95, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 6200, "market_used_max": 8200,
    },
    "CORE I5-13400F": {
        "fps_gaming": 149.0, "fps_1pct_low": 110.0, "cb_r23_multi": 15600, "l3_cache_mb": 20,
        "cores": 10, "threads": 16, "gaming_watts": 60, "tdp_watts": 95, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 5600, "market_used_max": 7400,
    },
    "CORE I5-12400F": {
        "fps_gaming": 141.0, "fps_1pct_low": 105.0, "cb_r23_multi": 12200, "l3_cache_mb": 18,
        "cores": 6, "threads": 12, "gaming_watts": 52, "tdp_watts": 65, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 4800, "market_used_max": 6600,
    },
    "CORE I3-14100F": {
        "fps_gaming": 125.0, "fps_1pct_low": 89.0, "cb_r23_multi": 9200, "l3_cache_mb": 12,
        "cores": 4, "threads": 8, "gaming_watts": 45, "tdp_watts": 60, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 3800, "market_used_max": 5500,
    },
    "CORE I3-13100F": {
        "fps_gaming": 121.0, "fps_1pct_low": 86.0, "cb_r23_multi": 8900, "l3_cache_mb": 12,
        "cores": 4, "threads": 8, "gaming_watts": 44, "tdp_watts": 60, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 3400, "market_used_max": 4800,
    },
    "CORE I3-12100F": {
        "fps_gaming": 115.0, "fps_1pct_low": 82.0, "cb_r23_multi": 8500, "l3_cache_mb": 12,
        "cores": 4, "threads": 8, "gaming_watts": 42, "tdp_watts": 60, "socket": "LGA1700", "brand": "Intel",
        "market_used_min": 3000, "market_used_max": 4400,
    },

    # ==================== INTEL LGA1200 (10th / 11th Gen) ====================
    "CORE I9-11900K": {
        "fps_gaming": 148.0, "fps_1pct_low": 108.0, "cb_r23_multi": 15600, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 115, "tdp_watts": 180, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 8000, "market_used_max": 11000,
    },
    "CORE I9-11900": {
        "fps_gaming": 142.0, "fps_1pct_low": 103.0, "cb_r23_multi": 14400, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 95, "tdp_watts": 125, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 7200, "market_used_max": 9800,
    },
    "CORE I9-10900K": {
        "fps_gaming": 146.0, "fps_1pct_low": 106.0, "cb_r23_multi": 16200, "l3_cache_mb": 20,
        "cores": 10, "threads": 20, "gaming_watts": 115, "tdp_watts": 180, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 7800, "market_used_max": 10800,
    },
    "CORE I9-10850K": {
        "fps_gaming": 144.0, "fps_1pct_low": 105.0, "cb_r23_multi": 15900, "l3_cache_mb": 20,
        "cores": 10, "threads": 20, "gaming_watts": 112, "tdp_watts": 180, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 7200, "market_used_max": 9800,
    },
    "CORE I9-10900": {
        "fps_gaming": 139.0, "fps_1pct_low": 101.0, "cb_r23_multi": 14800, "l3_cache_mb": 20,
        "cores": 10, "threads": 20, "gaming_watts": 92, "tdp_watts": 125, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 6800, "market_used_max": 9500,
    },
    "CORE I7-11700K": {
        "fps_gaming": 142.0, "fps_1pct_low": 103.0, "cb_r23_multi": 14800, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 105, "tdp_watts": 160, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 6500, "market_used_max": 8800,
    },
    "CORE I7-11700": {
        "fps_gaming": 136.0, "fps_1pct_low": 99.0, "cb_r23_multi": 13600, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 85, "tdp_watts": 115, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 5600, "market_used_max": 7600,
    },
    "CORE I7-10700K": {
        "fps_gaming": 136.0, "fps_1pct_low": 99.0, "cb_r23_multi": 12800, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 95, "tdp_watts": 150, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 6200, "market_used_max": 8400,
    },
    "CORE I7-10700": {
        "fps_gaming": 130.0, "fps_1pct_low": 94.0, "cb_r23_multi": 12000, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 78, "tdp_watts": 105, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 5500, "market_used_max": 7600,
    },
    "CORE I5-11600K": {
        "fps_gaming": 133.0, "fps_1pct_low": 97.0, "cb_r23_multi": 11200, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 82, "tdp_watts": 125, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 5000, "market_used_max": 6800,
    },
    "CORE I5-11600": {
        "fps_gaming": 128.0, "fps_1pct_low": 93.0, "cb_r23_multi": 10600, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 65, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 4500, "market_used_max": 6200,
    },
    "CORE I5-11500": {
        "fps_gaming": 125.0, "fps_1pct_low": 91.0, "cb_r23_multi": 10300, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 62, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 4200, "market_used_max": 5800,
    },
    "CORE I5-11400F": {
        "fps_gaming": 122.0, "fps_1pct_low": 89.0, "cb_r23_multi": 10000, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 60, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 3800, "market_used_max": 5300,
    },
    "CORE I5-10600K": {
        "fps_gaming": 123.0, "fps_1pct_low": 89.0, "cb_r23_multi": 9600, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 78, "tdp_watts": 125, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 3800, "market_used_max": 5200,
    },
    "CORE I5-10500": {
        "fps_gaming": 114.0, "fps_1pct_low": 83.0, "cb_r23_multi": 8600, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 55, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 3000, "market_used_max": 4200,
    },
    "CORE I5-10400F": {
        "fps_gaming": 110.0, "fps_1pct_low": 80.0, "cb_r23_multi": 8200, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 52, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 3000, "market_used_max": 4300,
    },
    "CORE I3-10105F": {
        "fps_gaming": 90.0, "fps_1pct_low": 64.0, "cb_r23_multi": 5700, "l3_cache_mb": 6,
        "cores": 4, "threads": 8, "gaming_watts": 42, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 1500, "market_used_max": 2400,
    },
    "CORE I3-10100F": {
        "fps_gaming": 88.0, "fps_1pct_low": 62.0, "cb_r23_multi": 5500, "l3_cache_mb": 6,
        "cores": 4, "threads": 8, "gaming_watts": 40, "tdp_watts": 65, "socket": "LGA1200", "brand": "Intel",
        "market_used_min": 1400, "market_used_max": 2300,
    },

    # ==================== INTEL LGA1151v2 (8th / 9th Gen) ====================
    "CORE I9-9900K": {
        "fps_gaming": 130.0, "fps_1pct_low": 93.0, "cb_r23_multi": 10800, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 95, "tdp_watts": 140, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 7500, "market_used_max": 10500,
    },
    "CORE I9-9900": {
        "fps_gaming": 124.0, "fps_1pct_low": 89.0, "cb_r23_multi": 10200, "l3_cache_mb": 16,
        "cores": 8, "threads": 16, "gaming_watts": 78, "tdp_watts": 95, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 5800, "market_used_max": 8000,
    },
    "CORE I7-9700K": {
        "fps_gaming": 116.0, "fps_1pct_low": 79.0, "cb_r23_multi": 7800, "l3_cache_mb": 12,
        "cores": 8, "threads": 8, "gaming_watts": 82, "tdp_watts": 125, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 3800, "market_used_max": 5500,
    },
    "CORE I7-9700": {
        "fps_gaming": 110.0, "fps_1pct_low": 75.0, "cb_r23_multi": 7400, "l3_cache_mb": 12,
        "cores": 8, "threads": 8, "gaming_watts": 68, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 3800, "market_used_max": 5500,
    },
    "CORE I5-9600K": {
        "fps_gaming": 102.0, "fps_1pct_low": 68.0, "cb_r23_multi": 5800, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 68, "tdp_watts": 95, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 2200, "market_used_max": 3400,
    },
    "CORE I5-9500": {
        "fps_gaming": 95.0, "fps_1pct_low": 63.0, "cb_r23_multi": 5400, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 52, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 1800, "market_used_max": 2700,
    },
    "CORE I5-9400F": {
        "fps_gaming": 91.0, "fps_1pct_low": 60.0, "cb_r23_multi": 5200, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 50, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 1900, "market_used_max": 2900,
    },
    "CORE I3-9100F": {
        "fps_gaming": 78.0, "fps_1pct_low": 50.0, "cb_r23_multi": 3600, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 40, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 800, "market_used_max": 1400,
    },
    "CORE I7-8700K": {
        "fps_gaming": 115.0, "fps_1pct_low": 81.0, "cb_r23_multi": 8100, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 78, "tdp_watts": 95, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 3500, "market_used_max": 5000,
    },
    "CORE I7-8700": {
        "fps_gaming": 108.0, "fps_1pct_low": 76.0, "cb_r23_multi": 7600, "l3_cache_mb": 12,
        "cores": 6, "threads": 12, "gaming_watts": 65, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 2900, "market_used_max": 4200,
    },
    "CORE I5-8600K": {
        "fps_gaming": 96.0, "fps_1pct_low": 64.0, "cb_r23_multi": 5500, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 65, "tdp_watts": 95, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 1800, "market_used_max": 2800,
    },
    "CORE I5-8500": {
        "fps_gaming": 89.0, "fps_1pct_low": 59.0, "cb_r23_multi": 5100, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 50, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 1500, "market_used_max": 2200,
    },
    "CORE I5-8400": {
        "fps_gaming": 85.0, "fps_1pct_low": 56.0, "cb_r23_multi": 4900, "l3_cache_mb": 9,
        "cores": 6, "threads": 6, "gaming_watts": 48, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 1400, "market_used_max": 2200,
    },
    "CORE I3-8100": {
        "fps_gaming": 70.0, "fps_1pct_low": 46.0, "cb_r23_multi": 3300, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 38, "tdp_watts": 65, "socket": "LGA1151v2", "brand": "Intel",
        "market_used_min": 550, "market_used_max": 1000,
    },

    # ==================== INTEL LGA1151 (6th / 7th Gen) ====================
    "CORE I7-7700K": {
        "fps_gaming": 85.0, "fps_1pct_low": 57.0, "cb_r23_multi": 5300, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 65, "tdp_watts": 91, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 2800, "market_used_max": 4500,
    },
    "CORE I7-7700": {
        "fps_gaming": 79.0, "fps_1pct_low": 53.0, "cb_r23_multi": 4900, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 52, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 2200, "market_used_max": 3300,
    },
    "CORE I5-7600K": {
        "fps_gaming": 72.0, "fps_1pct_low": 45.0, "cb_r23_multi": 3700, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 55, "tdp_watts": 91, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1300, "market_used_max": 2100,
    },
    "CORE I5-7600": {
        "fps_gaming": 69.0, "fps_1pct_low": 43.0, "cb_r23_multi": 3500, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 45, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1200, "market_used_max": 1900,
    },
    "CORE I5-7500": {
        "fps_gaming": 67.0, "fps_1pct_low": 42.0, "cb_r23_multi": 3400, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 44, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1200, "market_used_max": 1900,
    },
    "CORE I5-7400": {
        "fps_gaming": 63.0, "fps_1pct_low": 39.0, "cb_r23_multi": 3100, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 42, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1100, "market_used_max": 1800,
    },
    "CORE I3-7100": {
        "fps_gaming": 54.0, "fps_1pct_low": 33.0, "cb_r23_multi": 2300, "l3_cache_mb": 3,
        "cores": 2, "threads": 4, "gaming_watts": 32, "tdp_watts": 51, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 350, "market_used_max": 700,
    },
    "CORE I7-6700K": {
        "fps_gaming": 77.0, "fps_1pct_low": 52.0, "cb_r23_multi": 4900, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 62, "tdp_watts": 91, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 2100, "market_used_max": 3200,
    },
    "CORE I7-6700": {
        "fps_gaming": 71.0, "fps_1pct_low": 48.0, "cb_r23_multi": 4500, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 48, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1700, "market_used_max": 2600,
    },
    "CORE I5-6600K": {
        "fps_gaming": 67.0, "fps_1pct_low": 42.0, "cb_r23_multi": 3400, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 52, "tdp_watts": 91, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 1000, "market_used_max": 1650,
    },
    "CORE I5-6500": {
        "fps_gaming": 62.0, "fps_1pct_low": 39.0, "cb_r23_multi": 3100, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 42, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 850, "market_used_max": 1400,
    },
    "CORE I5-6400": {
        "fps_gaming": 58.0, "fps_1pct_low": 36.0, "cb_r23_multi": 2800, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 40, "tdp_watts": 65, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 650, "market_used_max": 1150,
    },
    "CORE I3-6100": {
        "fps_gaming": 50.0, "fps_1pct_low": 31.0, "cb_r23_multi": 2100, "l3_cache_mb": 3,
        "cores": 2, "threads": 4, "gaming_watts": 32, "tdp_watts": 51, "socket": "LGA1151", "brand": "Intel",
        "market_used_min": 400, "market_used_max": 850,
    },

    # ==================== LEGACY INTEL (LGA1150 / LGA1155) ====================
    "CORE I7-4790K": {
        "fps_gaming": 76.0, "fps_1pct_low": 50.0, "cb_r23_multi": 4400, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 65, "tdp_watts": 88, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 2300, "market_used_max": 3500,
    },
    "CORE I7-4770K": {
        "fps_gaming": 71.0, "fps_1pct_low": 47.0, "cb_r23_multi": 4100, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 62, "tdp_watts": 84, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 1700, "market_used_max": 2600,
    },
    "CORE I7-4770": {
        "fps_gaming": 68.0, "fps_1pct_low": 45.0, "cb_r23_multi": 3950, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 56, "tdp_watts": 84, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 1450, "market_used_max": 2250,
    },
    "CORE I5-4690K": {
        "fps_gaming": 61.0, "fps_1pct_low": 38.0, "cb_r23_multi": 3000, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 55, "tdp_watts": 88, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 900, "market_used_max": 1600,
    },
    "CORE I5-4590": {
        "fps_gaming": 56.0, "fps_1pct_low": 35.0, "cb_r23_multi": 2800, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 48, "tdp_watts": 84, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 700, "market_used_max": 1250,
    },
    "CORE I5-4570": {
        "fps_gaming": 54.0, "fps_1pct_low": 34.0, "cb_r23_multi": 2700, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 48, "tdp_watts": 84, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 550, "market_used_max": 1000,
    },
    "CORE I5-4460": {
        "fps_gaming": 52.0, "fps_1pct_low": 32.0, "cb_r23_multi": 2550, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 45, "tdp_watts": 84, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 500, "market_used_max": 950,
    },
    "CORE I7-3770K": {
        "fps_gaming": 63.0, "fps_1pct_low": 41.0, "cb_r23_multi": 3650, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 58, "tdp_watts": 77, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 1400, "market_used_max": 2300,
    },
    "CORE I7-3770": {
        "fps_gaming": 60.0, "fps_1pct_low": 39.0, "cb_r23_multi": 3500, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 54, "tdp_watts": 77, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 1200, "market_used_max": 1950,
    },
    "CORE I5-3570K": {
        "fps_gaming": 52.0, "fps_1pct_low": 32.0, "cb_r23_multi": 2500, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 50, "tdp_watts": 77, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 650, "market_used_max": 1200,
    },
    "CORE I7-2600K": {
        "fps_gaming": 58.0, "fps_1pct_low": 37.0, "cb_r23_multi": 3300, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 62, "tdp_watts": 95, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 900, "market_used_max": 1600,
    },
    "CORE I5-2500K": {
        "fps_gaming": 47.0, "fps_1pct_low": 29.0, "cb_r23_multi": 2250, "l3_cache_mb": 6,
        "cores": 4, "threads": 4, "gaming_watts": 55, "tdp_watts": 95, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 300, "market_used_max": 650,
    },

    # ==================== INTEL XEON (LGA2011-v3 / LGA2011 / LGA1150 / LGA1155) ====================
    "XEON E5-2699 V4": {
        "fps_gaming": 74.0, "fps_1pct_low": 50.0, "cb_r23_multi": 17500, "l3_cache_mb": 55,
        "cores": 22, "threads": 44, "gaming_watts": 95, "tdp_watts": 145, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 3500, "market_used_max": 6000,
    },
    "XEON E5-2696 V4": {
        "fps_gaming": 75.0, "fps_1pct_low": 51.0, "cb_r23_multi": 17800, "l3_cache_mb": 55,
        "cores": 22, "threads": 44, "gaming_watts": 95, "tdp_watts": 150, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 3500, "market_used_max": 5500,
    },
    "XEON E5-2683 V4": {
        "fps_gaming": 70.0, "fps_1pct_low": 47.0, "cb_r23_multi": 13200, "l3_cache_mb": 40,
        "cores": 16, "threads": 32, "gaming_watts": 80, "tdp_watts": 120, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 700, "market_used_max": 1500,
    },
    "XEON E5-2680 V4": {
        "fps_gaming": 69.0, "fps_1pct_low": 46.0, "cb_r23_multi": 12400, "l3_cache_mb": 35,
        "cores": 14, "threads": 28, "gaming_watts": 78, "tdp_watts": 120, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 500, "market_used_max": 1200,
    },
    "XEON E5-2697 V3": {
        "fps_gaming": 68.0, "fps_1pct_low": 45.0, "cb_r23_multi": 12000, "l3_cache_mb": 35,
        "cores": 14, "threads": 28, "gaming_watts": 92, "tdp_watts": 145, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 700, "market_used_max": 1400,
    },
    "XEON E5-2678 V3": {
        "fps_gaming": 65.0, "fps_1pct_low": 43.0, "cb_r23_multi": 10600, "l3_cache_mb": 30,
        "cores": 12, "threads": 24, "gaming_watts": 85, "tdp_watts": 120, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 600, "market_used_max": 1200,
    },
    "XEON E5-2670 V3": {
        "fps_gaming": 63.0, "fps_1pct_low": 42.0, "cb_r23_multi": 10000, "l3_cache_mb": 30,
        "cores": 12, "threads": 24, "gaming_watts": 82, "tdp_watts": 120, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 450, "market_used_max": 950,
    },
    "XEON E5-2666 V3": {
        "fps_gaming": 67.0, "fps_1pct_low": 45.0, "cb_r23_multi": 9800, "l3_cache_mb": 25,
        "cores": 10, "threads": 20, "gaming_watts": 88, "tdp_watts": 135, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 550, "market_used_max": 1100,
    },
    "XEON E5-2640 V3": {
        "fps_gaming": 57.0, "fps_1pct_low": 38.0, "cb_r23_multi": 7200, "l3_cache_mb": 20,
        "cores": 8, "threads": 16, "gaming_watts": 65, "tdp_watts": 90, "socket": "LGA2011-v3", "brand": "Intel",
        "market_used_min": 350, "market_used_max": 750,
    },
    "XEON E5-2650 V2": {
        "fps_gaming": 49.0, "fps_1pct_low": 32.0, "cb_r23_multi": 5600, "l3_cache_mb": 20,
        "cores": 8, "threads": 16, "gaming_watts": 68, "tdp_watts": 95, "socket": "LGA2011", "brand": "Intel",
        "market_used_min": 250, "market_used_max": 600,
    },
    "XEON E3-1270 V3": {
        "fps_gaming": 67.0, "fps_1pct_low": 44.0, "cb_r23_multi": 3900, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 55, "tdp_watts": 80, "socket": "LGA1150", "brand": "Intel",
        "market_used_min": 900, "market_used_max": 1600,
    },
    "XEON E3-1270 V2": {
        "fps_gaming": 59.0, "fps_1pct_low": 38.0, "cb_r23_multi": 3400, "l3_cache_mb": 8,
        "cores": 4, "threads": 8, "gaming_watts": 50, "tdp_watts": 69, "socket": "LGA1155", "brand": "Intel",
        "market_used_min": 700, "market_used_max": 1300,
    },
}

# Order within each numeric anchor matters: specific suffixes (X3D2, X3D, PLUS, XT, K, KF, KS, G, F) precede base names!
_RYZEN_PFX = r"\b(?:(?:ryzen(?:\s*(?:3|5|7|9))?|r(?:3|5|7|9))(?:\s+pro)?\s*)"

MATCH_PATTERNS = [
    # AMD Ryzen 9000 (AM5)
    (_RYZEN_PFX + r"9950[\s.]*x3d2\b", "RYZEN 9 9950X3D2"),
    (_RYZEN_PFX + r"9950[\s.]*x3d\b", "RYZEN 9 9950X3D"),
    (_RYZEN_PFX + r"9950[\s.]*x\b", "RYZEN 9 9950X"),
    (_RYZEN_PFX + r"9900[\s.]*x3d\b", "RYZEN 9 9900X3D"),
    (_RYZEN_PFX + r"9900[\s.]*x\b", "RYZEN 9 9900X"),
    (_RYZEN_PFX + r"9850[\s.]*x3d\b", "RYZEN 7 9850X3D"),
    (_RYZEN_PFX + r"9800[\s.]*x3d\b", "RYZEN 7 9800X3D"),
    (_RYZEN_PFX + r"9700[\s.]*x\b", "RYZEN 7 9700X"),
    (_RYZEN_PFX + r"9700[\s.]*f\b", "RYZEN 7 9700F"),
    (_RYZEN_PFX + r"9600[\s.]*x3d\b", "RYZEN 5 9600X3D"),
    (_RYZEN_PFX + r"9600[\s.]*x\b", "RYZEN 5 9600X"),
    (_RYZEN_PFX + r"9600\b", "RYZEN 5 9600"),
    (_RYZEN_PFX + r"9500[\s.]*f\b", "RYZEN 5 9500F"),

    # AMD Ryzen 7000 & 8000 (AM5)
    (_RYZEN_PFX + r"7950[\s.]*x3d\b", "RYZEN 9 7950X3D"),
    (_RYZEN_PFX + r"7950[\s.]*x\b", "RYZEN 9 7950X"),
    (_RYZEN_PFX + r"7900[\s.]*x3d\b", "RYZEN 9 7900X3D"),
    (_RYZEN_PFX + r"7900[\s.]*x\b", "RYZEN 9 7900X"),
    (_RYZEN_PFX + r"7900\b", "RYZEN 9 7900"),
    (_RYZEN_PFX + r"7800[\s.]*x3d\b", "RYZEN 7 7800X3D"),
    (_RYZEN_PFX + r"7700[\s.]*x\b", "RYZEN 7 7700X"),
    (_RYZEN_PFX + r"7700\b", "RYZEN 7 7700"),
    (_RYZEN_PFX + r"8700[\s.]*g\b", "RYZEN 7 8700G"),
    (_RYZEN_PFX + r"8700[\s.]*f\b", "RYZEN 7 8700F"),
    (_RYZEN_PFX + r"7600[\s.]*x3d\b", "RYZEN 5 7600X3D"),
    (_RYZEN_PFX + r"7600[\s.]*x\b", "RYZEN 5 7600X"),
    (_RYZEN_PFX + r"7600\b", "RYZEN 5 7600"),
    (r"(?:\bamd\s+|" + _RYZEN_PFX + r")7500[\s.]*x3d\b", "RYZEN 5 7500X3D"),
    (_RYZEN_PFX + r"7500[\s.]*f\b", "RYZEN 5 7500F"),
    (_RYZEN_PFX + r"7400[\s.]*f\b", "RYZEN 5 7400F"),
    (_RYZEN_PFX + r"8600[\s.]*g\b", "RYZEN 5 8600G"),
    (_RYZEN_PFX + r"8400[\s.]*f\b", "RYZEN 5 8400F"),
    (_RYZEN_PFX + r"8500[\s.]*g\b", "RYZEN 5 8500G"),

    # AMD Ryzen 5000 & 4000 (AM4)
    (_RYZEN_PFX + r"5800[\s.]*x3d\b", "RYZEN 7 5800X3D"),
    (_RYZEN_PFX + r"5700[\s.]*x3d\b", "RYZEN 7 5700X3D"),
    (_RYZEN_PFX + r"5950[\s.]*x\b", "RYZEN 9 5950X"),
    (_RYZEN_PFX + r"5900[\s.]*xt\b", "RYZEN 9 5900XT"),
    (_RYZEN_PFX + r"5900[\s.]*x\b", "RYZEN 9 5900X"),
    (_RYZEN_PFX + r"5800[\s.]*xt\b", "RYZEN 7 5800XT"),
    (_RYZEN_PFX + r"5800[\s.]*x\b", "RYZEN 7 5800X"),
    (_RYZEN_PFX + r"5750[\s.]*g(?:e)?\b", "RYZEN 7 5750G"),
    (_RYZEN_PFX + r"5700[\s.]*x\b", "RYZEN 7 5700X"),
    (_RYZEN_PFX + r"5700[\s.]*g(?:e)?\b", "RYZEN 7 5700G"),
    (_RYZEN_PFX + r"5700\b", "RYZEN 7 5700"),
    (_RYZEN_PFX + r"5600[\s.]*x3d\b", "RYZEN 5 5600X3D"),
    (_RYZEN_PFX + r"5600[\s.]*xt\b", "RYZEN 5 5600XT"),
    (_RYZEN_PFX + r"5600[\s.]*x\b", "RYZEN 5 5600X"),
    (_RYZEN_PFX + r"5600[\s.]*gt\b", "RYZEN 5 5600GT"),
    (_RYZEN_PFX + r"5600[\s.]*g(?:e)?\b", "RYZEN 5 5600G"),
    (_RYZEN_PFX + r"5650[\s.]*g(?:e)?\b", "RYZEN 5 5650G"),
    (_RYZEN_PFX + r"5600\b", "RYZEN 5 5600"),
    (_RYZEN_PFX + r"5500[\s.]*x3d\b", "RYZEN 5 5500X3D"),
    (_RYZEN_PFX + r"5500[\s.]*gt\b", "RYZEN 5 5500GT"),
    (_RYZEN_PFX + r"5500\b", "RYZEN 5 5500"),
    (_RYZEN_PFX + r"4750[\s.]*g(?:e)?\b", "RYZEN 7 4750G"),
    (_RYZEN_PFX + r"4650[\s.]*g(?:e)?\b", "RYZEN 5 4600G"),
    (_RYZEN_PFX + r"4600[\s.]*g\b", "RYZEN 5 4600G"),
    (_RYZEN_PFX + r"4500\b", "RYZEN 5 4500"),
    (_RYZEN_PFX + r"4300[\s.]*g(?:e)?\b", "RYZEN 3 4300G"),
    (_RYZEN_PFX + r"4100\b", "RYZEN 3 4100"),

    # AMD Ryzen 3000, 2000, 1000 (AM4)
    (_RYZEN_PFX + r"3950[\s.]*x\b", "RYZEN 9 3950X"),
    (_RYZEN_PFX + r"3900[\s.]*x(?:t)?\b", "RYZEN 9 3900X"),
    (_RYZEN_PFX + r"3800[\s.]*xt\b", "RYZEN 7 3800XT"),
    (_RYZEN_PFX + r"3800[\s.]*x\b", "RYZEN 7 3800X"),
    (_RYZEN_PFX + r"3700[\s.]*x\b", "RYZEN 7 3700X"),
    (_RYZEN_PFX + r"3600[\s.]*x(?:t)?\b", "RYZEN 5 3600X"),
    (_RYZEN_PFX + r"3600\b", "RYZEN 5 3600"),
    (_RYZEN_PFX + r"3500[\s.]*x?\b", "RYZEN 5 3500X"),
    (_RYZEN_PFX + r"3400[\s.]*g\b", "RYZEN 5 3400G"),
    (_RYZEN_PFX + r"3300[\s.]*x\b", "RYZEN 3 3300X"),
    (_RYZEN_PFX + r"3200[\s.]*g\b", "RYZEN 3 3200G"),
    (_RYZEN_PFX + r"3100\b", "RYZEN 3 3100"),
    (_RYZEN_PFX + r"2700[\s.]*x\b", "RYZEN 7 2700X"),
    (_RYZEN_PFX + r"2700\b", "RYZEN 7 2700"),
    (_RYZEN_PFX + r"2600[\s.]*x\b", "RYZEN 5 2600X"),
    (_RYZEN_PFX + r"2600\b", "RYZEN 5 2600"),
    (_RYZEN_PFX + r"2400[\s.]*g\b", "RYZEN 5 2400G"),
    (_RYZEN_PFX + r"2200[\s.]*g\b", "RYZEN 3 2200G"),
    (_RYZEN_PFX + r"1800[\s.]*x\b", "RYZEN 7 1800X"),
    (_RYZEN_PFX + r"1700[\s.]*x\b", "RYZEN 7 1700X"),
    (_RYZEN_PFX + r"1700\b", "RYZEN 7 1700"),
    (_RYZEN_PFX + r"1600[\s.]*x\b", "RYZEN 5 1600X"),
    (_RYZEN_PFX + r"1600\b", "RYZEN 5 1600"),
    (_RYZEN_PFX + r"1500[\s.]*x\b", "RYZEN 5 1500X"),
    (_RYZEN_PFX + r"1400\b", "RYZEN 5 1400"),
    (_RYZEN_PFX + r"1300[\s.]*x\b", "RYZEN 3 1300X"),
    (_RYZEN_PFX + r"1200\b", "RYZEN 3 1200"),

    # Intel Core Ultra (LGA1851)
    (r"\b(?:ultra\s*9|core\s*ultra\s*9)[\s-]*290\s*(?:k|kf)?(?:\s*plus)?\b", "CORE ULTRA 9 290K PLUS"),
    (r"\b(?:ultra\s*9|core\s*ultra\s*9)[\s-]*285\s*(?:k|kf|t)?\b", "CORE ULTRA 9 285K"),
    (r"\b(?:ultra\s*7|core\s*ultra\s*7)[\s-]*270\s*(?:k|kf)?(?:\s*plus)?\b", "CORE ULTRA 7 270K PLUS"),
    (r"\b(?:ultra\s*7|core\s*ultra\s*7)[\s-]*265\s*(?:k|kf|f|t)?\b", "CORE ULTRA 7 265K"),
    (r"\b(?:ultra\s*5|core\s*ultra\s*5)[\s-]*250\s*(?:k|kf)?(?:\s*plus)?\b", "CORE ULTRA 5 250K PLUS"),
    (r"\b(?:ultra\s*5|core\s*ultra\s*5)[\s-]*245\s*(?:k|kf)?\b", "CORE ULTRA 5 245K"),
    (r"\b(?:ultra\s*5|core\s*ultra\s*5)[\s-]*235\s*(?:t)?\b", "CORE ULTRA 5 235"),
    (r"\b(?:ultra\s*5|core\s*ultra\s*5)[\s-]*230\s*(?:f)?\b", "CORE ULTRA 5 230F"),
    (r"\b(?:ultra\s*5|core\s*ultra\s*5)[\s-]*225\s*(?:f)?\b", "CORE ULTRA 5 225F"),

    # Intel 14th Gen (LGA1700)
    (r"\b(?:core\s*)?i9[\s-]*14900\s*(?:k|kf|ks)\b", "CORE I9-14900K"),
    (r"\b(?:core\s*)?i9[\s-]*14900\s*(?:f|t)?\b", "CORE I9-14900"),
    (r"\b(?:core\s*)?i7[\s-]*14700\s*(?:k|kf)\b", "CORE I7-14700K"),
    (r"\b(?:core\s*)?i7[\s-]*14700\s*(?:f|t)?\b", "CORE I7-14700"),
    (r"\b(?:core\s*)?i5[\s-]*14600\s*(?:k|kf)\b", "CORE I5-14600K"),
    (r"\b(?:core\s*)?i5[\s-]*14500\s*(?:t)?\b", "CORE I5-14500"),
    (r"\b(?:core\s*)?i5[\s-]*14400\s*(?:f)?\b", "CORE I5-14400F"),
    (r"\b(?:core\s*)?i3[\s-]*14100\s*(?:f)?\b", "CORE I3-14100F"),

    # Intel 13th Gen (LGA1700)
    (r"\b(?:core\s*)?i9[\s-]*13900\s*(?:k|kf|ks)\b", "CORE I9-13900K"),
    (r"\b(?:core\s*)?i9[\s-]*13900\s*(?:f|t)?\b", "CORE I9-13900"),
    (r"\b(?:core\s*)?i7[\s-]*13700\s*(?:k|kf)\b", "CORE I7-13700K"),
    (r"\b(?:core\s*)?i7[\s-]*13700\s*(?:f|t)?\b", "CORE I7-13700"),
    (r"\b(?:core\s*)?i5[\s-]*13600\s*(?:k|kf)\b", "CORE I5-13600K"),
    (r"\b(?:core\s*)?i5[\s-]*13500\s*(?:t)?\b", "CORE I5-13500"),
    (r"\b(?:core\s*)?i5[\s-]*13400\s*(?:f)?\b", "CORE I5-13400F"),
    (r"\b(?:core\s*)?i3[\s-]*13100\s*(?:f)?\b", "CORE I3-13100F"),

    # Intel 12th Gen (LGA1700)
    (r"\b(?:core\s*)?i9[\s-]*12900\s*(?:k|kf|ks)\b", "CORE I9-12900K"),
    (r"\b(?:core\s*)?i9[\s-]*12900\s*(?:f|t)?\b", "CORE I9-12900"),
    (r"\b(?:core\s*)?i7[\s-]*12700\s*(?:k|kf)\b", "CORE I7-12700K"),
    (r"\b(?:core\s*)?i7[\s-]*12700\s*(?:f|t)?\b", "CORE I7-12700"),
    (r"\b(?:core\s*)?i5[\s-]*12600\s*(?:k|kf)\b", "CORE I5-12600K"),
    (r"\b(?:core\s*)?i5[\s-]*12600\b", "CORE I5-12600"),
    (r"\b(?:core\s*)?i5[\s-]*12500\b", "CORE I5-12500"),
    (r"\b(?:core\s*)?i5[\s-]*12400\s*(?:f)?\b", "CORE I5-12400F"),
    (r"\b(?:core\s*)?i3[\s-]*12100\s*(?:f)?\b", "CORE I3-12100F"),

    # Intel 11th & 10th Gen (LGA1200)
    (r"\b(?:core\s*)?i9[\s-]*11900\s*(?:k|kf)\b", "CORE I9-11900K"),
    (r"\b(?:core\s*)?i9[\s-]*11900\s*(?:f)?\b", "CORE I9-11900"),
    (r"\b(?:core\s*)?i9[\s-]*10900\s*(?:k|kf)\b", "CORE I9-10900K"),
    (r"\b(?:core\s*)?i9[\s-]*10850\s*(?:k|kf)\b", "CORE I9-10850K"),
    (r"\b(?:core\s*)?i9[\s-]*10900\s*(?:f)?\b", "CORE I9-10900"),
    (r"\b(?:core\s*)?i7[\s-]*11700\s*(?:k|kf)\b", "CORE I7-11700K"),
    (r"\b(?:core\s*)?i7[\s-]*11700\s*(?:f)?\b", "CORE I7-11700"),
    (r"\b(?:core\s*)?i7[\s-]*10700\s*(?:k|kf)\b", "CORE I7-10700K"),
    (r"\b(?:core\s*)?i7[\s-]*10700\s*(?:f)?\b", "CORE I7-10700"),
    (r"\b(?:core\s*)?i5[\s-]*11600\s*(?:k|kf)\b", "CORE I5-11600K"),
    (r"\b(?:core\s*)?i5[\s-]*11600\b", "CORE I5-11600"),
    (r"\b(?:core\s*)?i5[\s-]*11500\b", "CORE I5-11500"),
    (r"\b(?:core\s*)?i5[\s-]*11400\s*(?:f)?\b", "CORE I5-11400F"),
    (r"\b(?:core\s*)?i5[\s-]*10600\s*(?:k|kf)\b", "CORE I5-10600K"),
    (r"\b(?:core\s*)?i5[\s-]*10500\b", "CORE I5-10500"),
    (r"\b(?:core\s*)?i5[\s-]*10400\s*(?:f)?\b", "CORE I5-10400F"),
    (r"\b(?:core\s*)?i3[\s-]*10105\s*(?:f)?\b", "CORE I3-10105F"),
    (r"\b(?:core\s*)?i3[\s-]*10100\s*(?:f)?\b", "CORE I3-10100F"),

    # Intel 9th & 8th Gen (LGA1151v2)
    (r"\b(?:core\s*)?i9[\s-]*9900\s*(?:k|kf|ks)\b", "CORE I9-9900K"),
    (r"\b(?:core\s*)?i9[\s-]*9900\b", "CORE I9-9900"),
    (r"\b(?:core\s*)?i7[\s-]*9700\s*(?:k|kf)\b", "CORE I7-9700K"),
    (r"\b(?:core\s*)?i7[\s-]*9700\s*(?:f)?\b", "CORE I7-9700"),
    (r"\b(?:core\s*)?i5[\s-]*9600\s*(?:k|kf)\b", "CORE I5-9600K"),
    (r"\b(?:core\s*)?i5[\s-]*9500\b", "CORE I5-9500"),
    (r"\b(?:core\s*)?i5[\s-]*9400\s*(?:f)?\b", "CORE I5-9400F"),
    (r"\b(?:core\s*)?i3[\s-]*9100\s*(?:f)?\b", "CORE I3-9100F"),
    (r"\b(?:core\s*)?i7[\s-]*8700\s*(?:k)\b", "CORE I7-8700K"),
    (r"\b(?:core\s*)?i7[\s-]*8700\b", "CORE I7-8700"),
    (r"\b(?:core\s*)?i5[\s-]*8600\s*(?:k)\b", "CORE I5-8600K"),
    (r"\b(?:core\s*)?i5[\s-]*8500\b", "CORE I5-8500"),
    (r"\b(?:core\s*)?i5[\s-]*8400\b", "CORE I5-8400"),
    (r"\b(?:core\s*)?i3[\s-]*8100\b", "CORE I3-8100"),

    # Intel 7th & 6th Gen (LGA1151)
    (r"\b(?:core\s*)?i7[\s-]*7700\s*(?:k)\b", "CORE I7-7700K"),
    (r"\b(?:core\s*)?i7[\s-]*7700\b", "CORE I7-7700"),
    (r"\b(?:core\s*)?i5[\s-]*7600\s*(?:k)\b", "CORE I5-7600K"),
    (r"\b(?:core\s*)?i5[\s-]*7600\b", "CORE I5-7600"),
    (r"\b(?:core\s*)?i5[\s-]*7500\b", "CORE I5-7500"),
    (r"\b(?:core\s*)?i5[\s-]*7400\b", "CORE I5-7400"),
    (r"\b(?:core\s*)?i3[\s-]*7100\b", "CORE I3-7100"),
    (r"\b(?:core\s*)?i7[\s-]*6700\s*(?:k)\b", "CORE I7-6700K"),
    (r"\b(?:core\s*)?i7[\s-]*6700\b", "CORE I7-6700"),
    (r"\b(?:core\s*)?i5[\s-]*6600\s*(?:k)\b", "CORE I5-6600K"),
    (r"\b(?:core\s*)?i5[\s-]*6500\b", "CORE I5-6500"),
    (r"\b(?:core\s*)?i5[\s-]*6400\b", "CORE I5-6400"),
    (r"\b(?:core\s*)?i3[\s-]*6100\b", "CORE I3-6100"),

    # Intel LGA1150 / LGA1155
    (r"\b(?:core\s*)?i7[\s-]*4790\s*(?:k)\b", "CORE I7-4790K"),
    (r"\b(?:core\s*)?i7[\s-]*4770\s*(?:k)\b", "CORE I7-4770K"),
    (r"\b(?:core\s*)?i7[\s-]*4770\b", "CORE I7-4770"),
    (r"\b(?:core\s*)?i5[\s-]*4690\s*(?:k)\b", "CORE I5-4690K"),
    (r"\b(?:core\s*)?i5[\s-]*4590\b", "CORE I5-4590"),
    (r"\b(?:core\s*)?i5[\s-]*4570\b", "CORE I5-4570"),
    (r"\b(?:core\s*)?i5[\s-]*4460\b", "CORE I5-4460"),
    (r"\b(?:core\s*)?i7[\s-]*3770\s*(?:k)\b", "CORE I7-3770K"),
    (r"\b(?:core\s*)?i7[\s-]*3770\b", "CORE I7-3770"),
    (r"\b(?:core\s*)?i5[\s-]*3570\s*(?:k)\b", "CORE I5-3570K"),
    (r"\b(?:core\s*)?i7[\s-]*2600\s*(?:k)?\b", "CORE I7-2600K"),
    (r"\b(?:core\s*)?i5[\s-]*2500\s*(?:k)?\b", "CORE I5-2500K"),

    # Intel Xeon
    (r"\b(?:xeon\s*)?e5[\s-]*2699\s*v4\b", "XEON E5-2699 V4"),
    (r"\b(?:xeon\s*)?e5[\s-]*2696\s*v4\b", "XEON E5-2696 V4"),
    (r"\b(?:xeon\s*)?e5[\s-]*2683\s*v4\b", "XEON E5-2683 V4"),
    (r"\b(?:xeon\s*)?e5[\s-]*2680\s*v4\b", "XEON E5-2680 V4"),
    (r"\b(?:xeon\s*)?e5[\s-]*2697\s*v3\b", "XEON E5-2697 V3"),
    (r"\b(?:xeon\s*)?e5[\s-]*2678\s*v3\b", "XEON E5-2678 V3"),
    (r"\b(?:xeon\s*)?e5[\s-]*2670\s*v3\b", "XEON E5-2670 V3"),
    (r"\b(?:xeon\s*)?e5[\s-]*2666\s*v3\b", "XEON E5-2666 V3"),
    (r"\b(?:xeon\s*)?e5[\s-]*2640\s*v3\b", "XEON E5-2640 V3"),
    (r"\b(?:xeon\s*)?e5[\s-]*2650\s*v2\b", "XEON E5-2650 V2"),
    (r"\b(?:xeon\s*)?e3[\s-]*1270\s*v3\b", "XEON E3-1270 V3"),
    (r"\b(?:xeon\s*)?e3[\s-]*1270\s*v2\b", "XEON E3-1270 V2"),
]

# Patterns that indicate the ad is an accessory, full PC/laptop, combo bundle, or BGA/ES mutant (not a standalone retail CPU)
PURE_ACCESSORY_PATTERNS = [
    r"\bкулер\s+для\s+процесор\w*\b",
    r"\bбаштов\w+\s+кулер\b",
    r"\bбашня\s+для\s+процесор\w*\b",
    r"\bпорожн\w+\s+коробк\w*\b",
    r"\bкоробка\s+від\b",
    r"\bbox\s+only\b",
    r"\bводян\w+\s+охолодженн\w*\b",
    r"\bрід\w+\s+охолодженн\w*\b",
    r"\bсистема\s+водяного\b",
    r"\bтільки\s+кулер\b",
    r"\bбез\s+процесор\w*\b",
    r"\bбрелок\b",
    r"\bкріпленн\w*\b",
    r"\bкреплен\w*\b",
    r"\bрамка\s+для\b",
    r"\bтермопаст\w*\b",
    r"\bскальпатор\b",
    r"\bколекція\s+процесор\w*\b",
    r"\bлот\s+з\s+\d+",
    r"\bноутбук\w*\b",
    r"\bсистемний\s+блок\b",
    r"\bігровий\s+комп\b",
    # CPU + Motherboard / RAM combo bundles (belong in mobo --bundle-only, not standalone CPU)
    r"(?<!повний\s)(?<!коробочний\s)\bкомплект\s+(?:пк|материн|плат|на\s+|am[45]|lga|s1\d+|i[3579]|і[3579]|ryzen|райзен|r[3579]|р[3579]|xeon|[a-zа-яіїє]*\d{3,5})",
    r"\+\s*(?:материн\w*|плат\w*|asus|msi|gigabyte|asrock|[abxzh]\d{3}[a-z]*|\d+\s*(?:gb|гб)\s*ddr)",
    # Mobile laptop BGA chips & Chinese mutant / ES engineering samples
    r"\b\d{4,5}(?:hx|hk|hs|h|u|mq|hq|qm)\b",
    r"\b(?:мутант\w*|инженерн\w*|інженерн\w*)\b",
    r"\b(?:es|qs)\s*\(?q[0-9a-z]{3}\)?\b",
    r"\bqtj[012]\b",
    r"\(\s*q[0-9a-z]{3}\s*\)",
]


# Enrich CPU_DATABASE entries with derived defaults, risk classification, and median price
for _cpu_name, _cpu_spec in CPU_DATABASE.items():
    _cpu_spec.setdefault("is_x3d", "X3D" in _cpu_name)
    _cpu_spec.setdefault("pcie_lanes_gpu", 16)
    _cpu_spec.setdefault("l3_cache_mb", 96 if "X3D" in _cpu_name else 32)
    _cpu_spec.setdefault(
        "fps_1pct_low",
        round(_cpu_spec["fps_gaming"] * (0.775 if "X3D" in _cpu_name else 0.73), 1),
    )
    _cpu_spec.setdefault("cb_r23_multi", _cpu_spec["threads"] * 950)
    _cpu_spec.setdefault("tdp_watts", 65)
    _cpu_spec.setdefault("gaming_watts", max(35, int(_cpu_spec["tdp_watts"] * 0.72)))
    _cpu_spec.setdefault(
        "market_used_median",
        (_cpu_spec["market_used_min"] + _cpu_spec["market_used_max"]) // 2,
    )
    if _cpu_name in ("CORE I9-14900K", "CORE I9-13900K", "CORE I7-14700K", "CORE I7-13700K"):
        _cpu_spec.setdefault("risk_level", "MEDIUM")
        _cpu_spec.setdefault(
            "risk_notes",
            "Raptor Lake unlocked SKU: verify zero Vmin voltage degradation / BSOD history in Unreal Engine 5.",
        )
    elif _cpu_spec["socket"].startswith("LGA2011"):
        _cpu_spec.setdefault("risk_level", "MEDIUM")
        _cpu_spec.setdefault(
            "risk_notes",
            "Retired datacenter Xeon platform: low single-core IPC and often paired with recycled X99/X79 boards.",
        )
    elif _cpu_spec["pcie_lanes_gpu"] < 16:
        _cpu_spec.setdefault("risk_level", "LOW")
        _cpu_spec.setdefault(
            "risk_notes",
            f"Monolithic 16MB L3 silicon with PCIe x{_cpu_spec['pcie_lanes_gpu']} GPU lanes (reduced discrete GPU bandwidth vs 32MB Zen 4/5).",
        )
    else:
        _cpu_spec.setdefault("risk_level", "LOW")
        _cpu_spec.setdefault("risk_notes", "Solid desktop silicon reliability.")

_SEO_COMPARISON_RE = re.compile(
    r"(?:\(\s*(?:не|аналог|краще|лучше|обмін|обмен)[^)]*\))"
    r"|(?:\b(?:не|аналог|краще\s+ніж|лучше\s+чем|обмін\s+на|обмен\s+на)\s+(?:ryzen|core|i[3579]|r[3579]|xeon)?[\s\d/,\-xkfgt3dv]+)"
)
_EXCLUSION_RE = re.compile("|".join(PURE_ACCESSORY_PATTERNS))
_BUNDLE_SAFE_CPU_EXCLUSION_RE = re.compile(
    "|".join(
        pat for pat in PURE_ACCESSORY_PATTERNS
        if not pat.startswith((r"(?<!повний", r"\+\s*(?:материн", r"\bсистемний\s+блок", r"\bігровий\s+комп"))
    )
)
_CYRILLIC_CPU_TRANS = str.maketrans({
    "і": "i", "к": "k", "х": "x", "с": "c", "е": "e", "а": "a", "р": "p", "о": "o", "т": "t",
})
_TOKEN_TYPOS_RE = re.compile(r"\b(?:райзен|рейзен|rayzen|razen)\b")
_X3D_CYR_RE = re.compile(r"[xх]\s*3\s*[dд](?=2?\b)")
_MODEL_CYR_SUFFIX_RE = re.compile(r"(\b[iіrр][3579]|\d{3,5}\s*)[ікхфтсяceakxfts]+\b")
_NUM_SCAN_RE = re.compile(r"\d{3,5}")

_PATTERNS_BY_ANCHOR: Dict[str, List[Tuple[re.Pattern, str]]] = {}
for _pat, _model in MATCH_PATTERNS:
    _nums = _NUM_SCAN_RE.findall(_pat)
    if _nums:
        _PATTERNS_BY_ANCHOR.setdefault(_nums[0], []).append((re.compile(_pat), _model))


def _normalize_cpu_tokens(text_l: str) -> str:
    """Normalizes common Ukrainian/Russian CPU transliterations & Cyrillic homoglyphs around SKU numbers."""
    s = _TOKEN_TYPOS_RE.sub("ryzen", text_l)
    s = _X3D_CYR_RE.sub("x3d", s)
    s = s.replace("кор ай", "core i").replace("cori", "core i")
    s = _MODEL_CYR_SUFFIX_RE.sub(lambda m: m.group(0).translate(_CYRILLIC_CPU_TRANS), s)
    return s


def _scan_cpu_text(text: str) -> Optional[Tuple[str, bool]]:
    anchors = set(_NUM_SCAN_RE.findall(text))
    if not anchors:
        return None
    best_pos = 10**9
    best_model: Optional[str] = None
    distinct = set()
    for anchor in anchors:
        sub = _PATTERNS_BY_ANCHOR.get(anchor)
        if sub:
            for cre, model in sub:
                m = cre.search(text)
                if m:
                    distinct.add(model)
                    if m.start() < best_pos:
                        best_pos = m.start()
                        best_model = model
                    break
    if best_model is None:
        return None
    return best_model, (len(distinct) >= 3)


@lru_cache(maxsize=8192)
def _identify_cpu_cached(title: str, desc_head: str, allow_bundles: bool = False) -> Optional[Tuple[str, bool]]:
    title_l = title.lower()
    excl_re = _BUNDLE_SAFE_CPU_EXCLUSION_RE if allow_bundles else _EXCLUSION_RE
    if excl_re.search(title_l):
        return None

    clean_title = _normalize_cpu_tokens(_SEO_COMPARISON_RE.sub(" ", title_l))
    res = _scan_cpu_text(clean_title)
    if res:
        return res

    if desc_head:
        clean_desc = _normalize_cpu_tokens(_SEO_COMPARISON_RE.sub(" ", desc_head.lower()))
        res_desc = _scan_cpu_text(clean_desc)
        if res_desc:
            return res_desc[0], False

    return None


def identify_cpu(title: str, description: str = "", allow_bundles: bool = False) -> Optional[Dict[str, Any]]:
    """
    Identifies CPU model at C-regex speed using anchor-indexed left-to-right token precedence,
    filtering out accessories, full PCs/laptops, CPU+Mobo bundles, BGA/ES mutants, and SEO spam.
    """
    if not title:
        return None
    res = _identify_cpu_cached(title, (description or "")[:300], allow_bundles=allow_bundles)
    if not res:
        return None
    model_name, is_multi_sku = res
    specs = CPU_DATABASE.get(model_name)
    if not specs:
        return None
    out = {"model": model_name, **specs}
    if is_multi_sku:
        out["multi_model_spam"] = True
    return out
