"""
GPU Benchmark Database and High-Speed Model Matcher (2025-2026 Calibrated).

Contains relative gaming FPS (1080p Ultra and 1440p Ultra) across modern AAA suites,
TDP wattage, VRAM specifications, architectural risk assessments, and market price
ranges (UAH), including NVIDIA Blackwell (RTX 50), Ada (RTX 40), Ampere (RTX 30),
Turing, Pascal, AMD RDNA 4 (RX 9000), RDNA 3 (RX 7000), RDNA 2 (RX 6000), Polaris,
and Intel Arc Battlemage / Alchemist.
"""

import re
from functools import lru_cache
from typing import Optional, Dict, Any, List, Tuple

GPU_DATABASE: Dict[str, Dict[str, Any]] = {
    # --- NVIDIA BLACKWELL (RTX 50-series) ---
    "RTX 5090": {
        "fps_1080p": 210.0, "fps_1440p": 198.0, "vram_gb": 32, "tdp_watts": 575, "brand": "Nvidia",
        "market_used_min": 95000, "market_used_max": 145000,
        "risk_level": "LOW", "risk_notes": "Flagship Blackwell 32GB GDDR7. Beware stripped 'No GPU/VRAM' donor PCB scams!"
    },
    "RTX 5080": {
        "fps_1080p": 168.0, "fps_1440p": 148.0, "vram_gb": 16, "tdp_watts": 360, "brand": "Nvidia",
        "market_used_min": 46000, "market_used_max": 62000,
        "risk_level": "LOW", "risk_notes": "Modern Blackwell GDDR7 architecture, DLSS 4 MFG, zero mining history."
    },
    "RTX 5070 TI": {
        "fps_1080p": 152.0, "fps_1440p": 130.0, "vram_gb": 16, "tdp_watts": 300, "brand": "Nvidia",
        "market_used_min": 36000, "market_used_max": 47000,
        "risk_level": "LOW", "risk_notes": "Blackwell 16GB GDDR7 1440p/4K sweet spot, DLSS 4."
    },
    "RTX 5070": {
        "fps_1080p": 132.0, "fps_1440p": 106.0, "vram_gb": 12, "tdp_watts": 250, "brand": "Nvidia",
        "market_used_min": 25000, "market_used_max": 34000,
        "risk_level": "LOW", "risk_notes": "Modern Blackwell 12GB GDDR7, efficient 250W TDP, DLSS 4."
    },
    "RTX 5060 TI 16GB": {
        "fps_1080p": 106.0, "fps_1440p": 83.0, "vram_gb": 16, "tdp_watts": 180, "brand": "Nvidia",
        "market_used_min": 19500, "market_used_max": 25500,
        "risk_level": "LOW", "risk_notes": "Blackwell 16GB GDDR7, strong longevity for 1440p and local AI."
    },
    "RTX 5060 TI 8GB": {
        "fps_1080p": 102.0, "fps_1440p": 76.0, "vram_gb": 8, "tdp_watts": 180, "brand": "Nvidia",
        "market_used_min": 16500, "market_used_max": 21500,
        "risk_level": "LOW", "risk_notes": "Blackwell GDDR7, zero mining history, 8GB VRAM ceiling in ultra textures."
    },
    "RTX 5060": {
        "fps_1080p": 90.0, "fps_1440p": 66.0, "vram_gb": 8, "tdp_watts": 145, "brand": "Nvidia",
        "market_used_min": 13500, "market_used_max": 18000,
        "risk_level": "LOW", "risk_notes": "Efficient 145W GDDR7 mainstream card with DLSS 4."
    },

    # --- NVIDIA ADA LOVELACE (RTX 40-series) ---
    "RTX 4090": {
        "fps_1080p": 165.0, "fps_1440p": 150.0, "vram_gb": 24, "tdp_watts": 450, "brand": "Nvidia",
        "market_used_min": 60000, "market_used_max": 85000,
        "risk_level": "LOW", "risk_notes": "Modern Ada 24GB flagship. Inspect 12VHPWR connector & verify GPU core is intact."
    },
    "RTX 4080 SUPER": {
        "fps_1080p": 145.0, "fps_1440p": 128.0, "vram_gb": 16, "tdp_watts": 320, "brand": "Nvidia",
        "market_used_min": 38000, "market_used_max": 48000,
        "risk_level": "LOW", "risk_notes": "Modern Ada architecture, zero ETH mining history, full DX12U feature set."
    },
    "RTX 4080": {
        "fps_1080p": 142.0, "fps_1440p": 125.0, "vram_gb": 16, "tdp_watts": 320, "brand": "Nvidia",
        "market_used_min": 35000, "market_used_max": 45000,
        "risk_level": "LOW", "risk_notes": "Modern Ada architecture, zero ETH mining history, full DX12U feature set."
    },
    "RTX 4070 TI SUPER": {
        "fps_1080p": 130.0, "fps_1440p": 112.0, "vram_gb": 16, "tdp_watts": 285, "brand": "Nvidia",
        "market_used_min": 30000, "market_used_max": 38000,
        "risk_level": "LOW", "risk_notes": "Modern Ada architecture, 16GB VRAM sweet spot, zero ETH mining history."
    },
    "RTX 4070 TI": {
        "fps_1080p": 124.0, "fps_1440p": 104.0, "vram_gb": 12, "tdp_watts": 285, "brand": "Nvidia",
        "market_used_min": 25000, "market_used_max": 32000,
        "risk_level": "LOW", "risk_notes": "Modern Ada architecture, zero ETH mining history."
    },
    "RTX 4070 SUPER": {
        "fps_1080p": 120.0, "fps_1440p": 98.0, "vram_gb": 12, "tdp_watts": 220, "brand": "Nvidia",
        "market_used_min": 23000, "market_used_max": 29500,
        "risk_level": "LOW", "risk_notes": "High efficiency 220W Ada card, zero ETH mining history."
    },
    "RTX 4070": {
        "fps_1080p": 108.0, "fps_1440p": 85.0, "vram_gb": 12, "tdp_watts": 200, "brand": "Nvidia",
        "market_used_min": 18500, "market_used_max": 24500,
        "risk_level": "LOW", "risk_notes": "Modern Ada architecture, very low 200W power draw, zero ETH mining history."
    },
    "RTX 4060 TI 16GB": {
        "fps_1080p": 88.0, "fps_1440p": 68.0, "vram_gb": 16, "tdp_watts": 165, "brand": "Nvidia",
        "market_used_min": 15500, "market_used_max": 20500,
        "risk_level": "LOW", "risk_notes": "Large 16GB buffer, 165W TDP, great for local AI & 1440p."
    },
    "RTX 4060 TI 8GB": {
        "fps_1080p": 87.0, "fps_1440p": 66.0, "vram_gb": 8, "tdp_watts": 160, "brand": "Nvidia",
        "market_used_min": 13500, "market_used_max": 18000,
        "risk_level": "LOW", "risk_notes": "Zero ETH mining history, 160W TDP, 8GB VRAM limits heavy 1440p textures."
    },
    "RTX 4060": {
        "fps_1080p": 75.0, "fps_1440p": 55.0, "vram_gb": 8, "tdp_watts": 115, "brand": "Nvidia",
        "market_used_min": 10500, "market_used_max": 14000,
        "risk_level": "LOW", "risk_notes": "Ultra-efficient 115W TDP, DLSS 3 frame gen, zero mining history."
    },

    # --- NVIDIA AMPERE (RTX 30-series) ---
    "RTX 3090 TI": {
        "fps_1080p": 122.0, "fps_1440p": 100.0, "vram_gb": 24, "tdp_watts": 450, "brand": "Nvidia",
        "market_used_min": 27000, "market_used_max": 37000,
        "risk_level": "MEDIUM", "risk_notes": "Single-sided 2GB GDDR6X modules (cooler than 3090), heavy 450W power draw."
    },
    "RTX 3090": {
        "fps_1080p": 116.0, "fps_1440p": 93.0, "vram_gb": 24, "tdp_watts": 350, "brand": "Nvidia",
        "market_used_min": 22000, "market_used_max": 30000,
        "risk_level": "HIGH", "risk_notes": "Double-sided GDDR6X ran 100C+ in mining. Verify rear VRAM thermal pads."
    },
    "RTX 3080 TI": {
        "fps_1080p": 114.0, "fps_1440p": 91.0, "vram_gb": 12, "tdp_watts": 350, "brand": "Nvidia",
        "market_used_min": 18500, "market_used_max": 25500,
        "risk_level": "HIGH", "risk_notes": "Hot GDDR6X memory during 2021-2022 mining. Check thermal pad service."
    },
    "RTX 3080 12GB": {
        "fps_1080p": 108.0, "fps_1440p": 85.0, "vram_gb": 12, "tdp_watts": 350, "brand": "Nvidia",
        "market_used_min": 16500, "market_used_max": 22500,
        "risk_level": "HIGH", "risk_notes": "GDDR6X wear; verify hotspot & memory junction temperatures."
    },
    "RTX 3080 10GB": {
        "fps_1080p": 105.0, "fps_1440p": 82.0, "vram_gb": 10, "tdp_watts": 320, "brand": "Nvidia",
        "market_used_min": 14000, "market_used_max": 19500,
        "risk_level": "HIGH", "risk_notes": "Extensively mined in 2020-2022. Hot GDDR6X VRAM; check junction temps."
    },
    "RTX 3070 TI": {
        "fps_1080p": 96.0, "fps_1440p": 74.0, "vram_gb": 8, "tdp_watts": 290, "brand": "Nvidia",
        "market_used_min": 12500, "market_used_max": 17000,
        "risk_level": "HIGH", "risk_notes": "Hot 290W GDDR6X on 8GB buffer. High mining exposure."
    },
    "RTX 3070": {
        "fps_1080p": 88.0, "fps_1440p": 68.0, "vram_gb": 8, "tdp_watts": 220, "brand": "Nvidia",
        "market_used_min": 10500, "market_used_max": 15000,
        "risk_level": "MEDIUM", "risk_notes": "Cooler standard GDDR6 (220W), solid 1080p/1440p DLSS performer."
    },
    "RTX 3060 TI": {
        "fps_1080p": 80.0, "fps_1440p": 60.0, "vram_gb": 8, "tdp_watts": 200, "brand": "Nvidia",
        "market_used_min": 8800, "market_used_max": 12500,
        "risk_level": "HIGH", "risk_notes": "Avoid early 2020-2021 Hynix X005 GDDR6 batches; Samsung/GDDR6X revisions are safe."
    },
    "RTX 3060 12GB": {
        "fps_1080p": 63.0, "fps_1440p": 45.0, "vram_gb": 12, "tdp_watts": 170, "brand": "Nvidia",
        "market_used_min": 7800, "market_used_max": 11000,
        "risk_level": "LOW", "risk_notes": "Generous 12GB VRAM, reliable Samsung/Micron GDDR6, 170W TDP."
    },
    "RTX 3060 8GB": {
        "fps_1080p": 54.0, "fps_1440p": 38.0, "vram_gb": 8, "tdp_watts": 170, "brand": "Nvidia",
        "market_used_min": 6800, "market_used_max": 9200,
        "risk_level": "LOW", "risk_notes": "Cut-down 128-bit memory bus (17% slower than 12GB version)."
    },
    "RTX 3050": {
        "fps_1080p": 44.0, "fps_1440p": 30.0, "vram_gb": 8, "tdp_watts": 130, "brand": "Nvidia",
        "market_used_min": 5200, "market_used_max": 7800,
        "risk_level": "LOW", "risk_notes": "Low 130W power draw, zero ETH mining history."
    },

    # --- NVIDIA TURING (RTX 20 & GTX 16) ---
    "RTX 2080 TI": {
        "fps_1080p": 85.0, "fps_1440p": 63.0, "vram_gb": 11, "tdp_watts": 250, "brand": "Nvidia",
        "market_used_min": 10000, "market_used_max": 14000,
        "risk_level": "MEDIUM", "risk_notes": "11GB VRAM, supports DLSS & Mesh Shaders. Avoid 2018 Micron VRAM batches."
    },
    "RTX 2080 SUPER": {
        "fps_1080p": 74.0, "fps_1440p": 54.0, "vram_gb": 8, "tdp_watts": 250, "brand": "Nvidia",
        "market_used_min": 8500, "market_used_max": 12000,
        "risk_level": "MEDIUM", "risk_notes": "Turing architecture with DLSS support."
    },
    "RTX 2080": {
        "fps_1080p": 69.0, "fps_1440p": 49.0, "vram_gb": 8, "tdp_watts": 215, "brand": "Nvidia",
        "market_used_min": 7800, "market_used_max": 10800,
        "risk_level": "MEDIUM", "risk_notes": "Turing architecture, moderate age & mining exposure."
    },
    "RTX 2070 SUPER": {
        "fps_1080p": 66.0, "fps_1440p": 47.0, "vram_gb": 8, "tdp_watts": 215, "brand": "Nvidia",
        "market_used_min": 7200, "market_used_max": 10000,
        "risk_level": "MEDIUM", "risk_notes": "Reliable Turing TU104 silicon; supports DLSS."
    },
    "RTX 2070": {
        "fps_1080p": 58.0, "fps_1440p": 41.0, "vram_gb": 8, "tdp_watts": 175, "brand": "Nvidia",
        "market_used_min": 6300, "market_used_max": 8800,
        "risk_level": "MEDIUM", "risk_notes": "Turing architecture with DLSS support."
    },
    "RTX 2060 SUPER": {
        "fps_1080p": 57.0, "fps_1440p": 40.0, "vram_gb": 8, "tdp_watts": 175, "brand": "Nvidia",
        "market_used_min": 5800, "market_used_max": 8200,
        "risk_level": "MEDIUM", "risk_notes": "8GB buffer keeps it viable for 1080p DLSS gaming."
    },
    "RTX 2060": {
        "fps_1080p": 48.0, "fps_1440p": 34.0, "vram_gb": 6, "tdp_watts": 160, "brand": "Nvidia",
        "market_used_min": 4800, "market_used_max": 7000,
        "risk_level": "MEDIUM", "risk_notes": "6GB VRAM buffer requires medium textures in modern games."
    },
    "GTX 1660 TI": {
        "fps_1080p": 42.0, "fps_1440p": 29.0, "vram_gb": 6, "tdp_watts": 120, "brand": "Nvidia",
        "market_used_min": 4000, "market_used_max": 5800,
        "risk_level": "LOW", "risk_notes": "120W Turing without RT/DLSS. Solid ultra-budget 1080p esports card."
    },
    "GTX 1660 SUPER": {
        "fps_1080p": 41.0, "fps_1440p": 28.0, "vram_gb": 6, "tdp_watts": 125, "brand": "Nvidia",
        "market_used_min": 3800, "market_used_max": 5500,
        "risk_level": "LOW", "risk_notes": "Efficient 125W TDP budget 1080p card."
    },
    "GTX 1660": {
        "fps_1080p": 35.0, "fps_1440p": 24.0, "vram_gb": 6, "tdp_watts": 120, "brand": "Nvidia",
        "market_used_min": 3300, "market_used_max": 4800,
        "risk_level": "LOW", "risk_notes": "Entry-level 1080p card."
    },
    "GTX 1650 SUPER": {
        "fps_1080p": 32.0, "fps_1440p": 21.0, "vram_gb": 4, "tdp_watts": 100, "brand": "Nvidia",
        "market_used_min": 2800, "market_used_max": 4200,
        "risk_level": "MEDIUM", "risk_notes": "4GB VRAM limit causes stuttering in modern AAA games."
    },

    # --- NVIDIA PASCAL (GTX 10-series) ---
    "GTX 1080 TI": {
        "fps_1080p": 52.0, "fps_1440p": 36.0, "vram_gb": 11, "tdp_watts": 250, "brand": "Nvidia",
        "market_used_min": 5500, "market_used_max": 8000,
        "risk_level": "HIGH", "risk_notes": "8+ yrs old, lacks Mesh Shaders & DLSS, aging VRM/capacitors."
    },
    "GTX 1080": {
        "fps_1080p": 38.0, "fps_1440p": 26.0, "vram_gb": 8, "tdp_watts": 180, "brand": "Nvidia",
        "market_used_min": 4000, "market_used_max": 5800,
        "risk_level": "HIGH", "risk_notes": "No Mesh Shaders or DLSS; 8+ years of thermal aging."
    },
    "GTX 1070 TI": {
        "fps_1080p": 35.0, "fps_1440p": 24.0, "vram_gb": 8, "tdp_watts": 180, "brand": "Nvidia",
        "market_used_min": 3500, "market_used_max": 5000,
        "risk_level": "HIGH", "risk_notes": "Legacy Pascal architecture; struggles in DX12 Ultimate titles."
    },
    "GTX 1070": {
        "fps_1080p": 31.0, "fps_1440p": 21.0, "vram_gb": 8, "tdp_watts": 150, "brand": "Nvidia",
        "market_used_min": 3000, "market_used_max": 4500,
        "risk_level": "HIGH", "risk_notes": "Legacy Pascal architecture; 8+ years old."
    },
    "GTX 1060 6GB": {
        "fps_1080p": 22.0, "fps_1440p": 14.0, "vram_gb": 6, "tdp_watts": 120, "brand": "Nvidia",
        "market_used_min": 2200, "market_used_max": 3400,
        "risk_level": "HIGH", "risk_notes": "Legacy 1080p esports/light gaming only."
    },

    # --- AMD RDNA 4 (RX 9000-series) ---
    "RX 9070 XT": {
        "fps_1080p": 150.0, "fps_1440p": 128.0, "vram_gb": 16, "tdp_watts": 304, "brand": "AMD",
        "market_used_min": 29000, "market_used_max": 39000,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 4 16GB architecture with FSR 4 hardware ML upscaling."
    },
    "RX 9070": {
        "fps_1080p": 136.0, "fps_1440p": 113.0, "vram_gb": 16, "tdp_watts": 220, "brand": "AMD",
        "market_used_min": 25000, "market_used_max": 33500,
        "risk_level": "LOW", "risk_notes": "Superb efficiency (220W), 16GB VRAM, RDNA 4 + FSR 4."
    },
    "RX 9060 XT 16GB": {
        "fps_1080p": 102.0, "fps_1440p": 79.0, "vram_gb": 16, "tdp_watts": 182, "brand": "AMD",
        "market_used_min": 16500, "market_used_max": 22000,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 4 16GB value card, FSR 4 support, zero mining history."
    },
    "RX 9060 XT 8GB": {
        "fps_1080p": 96.0, "fps_1440p": 71.0, "vram_gb": 8, "tdp_watts": 150, "brand": "AMD",
        "market_used_min": 13500, "market_used_max": 18000,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 4 8GB card, low 150W TDP."
    },

    # --- AMD RDNA 3 (RX 7000-series) ---
    "RX 7900 XTX": {
        "fps_1080p": 155.0, "fps_1440p": 134.0, "vram_gb": 24, "tdp_watts": 355, "brand": "AMD",
        "market_used_min": 31000, "market_used_max": 43000,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 flagship, huge 24GB VRAM, zero ETH mining history."
    },
    "RX 7900 XT": {
        "fps_1080p": 138.0, "fps_1440p": 116.0, "vram_gb": 20, "tdp_watts": 315, "brand": "AMD",
        "market_used_min": 26000, "market_used_max": 34000,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 20GB card, zero ETH mining history."
    },
    "RX 7900 GRE": {
        "fps_1080p": 121.0, "fps_1440p": 99.0, "vram_gb": 16, "tdp_watts": 260, "brand": "AMD",
        "market_used_min": 21000, "market_used_max": 27500,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 architecture, 16GB VRAM."
    },
    "RX 7800 XT": {
        "fps_1080p": 112.0, "fps_1440p": 89.0, "vram_gb": 16, "tdp_watts": 263, "brand": "AMD",
        "market_used_min": 18500, "market_used_max": 24500,
        "risk_level": "LOW", "risk_notes": "Popular modern 1440p card; 16GB VRAM sweet spot."
    },
    "RX 7700 XT": {
        "fps_1080p": 98.0, "fps_1440p": 76.0, "vram_gb": 12, "tdp_watts": 245, "brand": "AMD",
        "market_used_min": 15500, "market_used_max": 20500,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 card, 12GB VRAM."
    },
    "RX 7600 XT": {
        "fps_1080p": 76.0, "fps_1440p": 55.0, "vram_gb": 16, "tdp_watts": 190, "brand": "AMD",
        "market_used_min": 11500, "market_used_max": 15500,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 with 16GB buffer."
    },
    "RX 7600": {
        "fps_1080p": 73.0, "fps_1440p": 52.0, "vram_gb": 8, "tdp_watts": 165, "brand": "AMD",
        "market_used_min": 9200, "market_used_max": 12800,
        "risk_level": "LOW", "risk_notes": "Modern RDNA 3 budget card, zero ETH mining history."
    },

    # --- AMD RDNA 2 (RX 6000-series) ---
    "RX 6950 XT": {
        "fps_1080p": 122.0, "fps_1440p": 96.0, "vram_gb": 16, "tdp_watts": 335, "brand": "AMD",
        "market_used_min": 19000, "market_used_max": 26000,
        "risk_level": "MEDIUM", "risk_notes": "RDNA 2 flagship, high 335W power spikes (use quality 750W+ PSU)."
    },
    "RX 6900 XT": {
        "fps_1080p": 114.0, "fps_1440p": 91.0, "vram_gb": 16, "tdp_watts": 300, "brand": "AMD",
        "market_used_min": 17000, "market_used_max": 23500,
        "risk_level": "MEDIUM", "risk_notes": "16GB VRAM, modern DX12U feature set."
    },
    "RX 6800 XT": {
        "fps_1080p": 108.0, "fps_1440p": 84.0, "vram_gb": 16, "tdp_watts": 300, "brand": "AMD",
        "market_used_min": 14500, "market_used_max": 19500,
        "risk_level": "MEDIUM", "risk_notes": "Outstanding 1440p value; 16GB VRAM."
    },
    "RX 6800": {
        "fps_1080p": 97.0, "fps_1440p": 74.0, "vram_gb": 16, "tdp_watts": 250, "brand": "AMD",
        "market_used_min": 12500, "market_used_max": 17000,
        "risk_level": "MEDIUM", "risk_notes": "Very power efficient (250W); 16GB VRAM."
    },
    "RX 6750 XT": {
        "fps_1080p": 87.0, "fps_1440p": 66.0, "vram_gb": 12, "tdp_watts": 250, "brand": "AMD",
        "market_used_min": 11500, "market_used_max": 15500,
        "risk_level": "LOW", "risk_notes": "Released mid-2022 right as ETH mining ended; very low mining exposure."
    },
    "RX 6700 XT": {
        "fps_1080p": 82.0, "fps_1440p": 62.0, "vram_gb": 12, "tdp_watts": 230, "brand": "AMD",
        "market_used_min": 10000, "market_used_max": 14000,
        "risk_level": "MEDIUM", "risk_notes": "Solid 12GB 1440p workhorse."
    },
    "RX 6700": {
        "fps_1080p": 74.0, "fps_1440p": 55.0, "vram_gb": 10, "tdp_watts": 175, "brand": "AMD",
        "market_used_min": 9000, "market_used_max": 12500,
        "risk_level": "LOW", "risk_notes": "10GB VRAM, efficient 175W TDP, low mining exposure."
    },
    "RX 6650 XT": {
        "fps_1080p": 69.0, "fps_1440p": 49.0, "vram_gb": 8, "tdp_watts": 180, "brand": "AMD",
        "market_used_min": 7800, "market_used_max": 10800,
        "risk_level": "LOW", "risk_notes": "Released May 2022; minimal mining exposure."
    },
    "RX 6600 XT": {
        "fps_1080p": 66.0, "fps_1440p": 47.0, "vram_gb": 8, "tdp_watts": 160, "brand": "AMD",
        "market_used_min": 7200, "market_used_max": 9800,
        "risk_level": "MEDIUM", "risk_notes": "Efficient 160W 1080p RDNA 2 card."
    },
    "RX 6600": {
        "fps_1080p": 57.0, "fps_1440p": 40.0, "vram_gb": 8, "tdp_watts": 132, "brand": "AMD",
        "market_used_min": 5800, "market_used_max": 8200,
        "risk_level": "LOW", "risk_notes": "Ultra-cool 132W TDP modern RDNA 2 budget champion."
    },

    # --- INTEL ARC (Battlemage & Alchemist) ---
    "ARC B580": {
        "fps_1080p": 86.0, "fps_1440p": 67.0, "vram_gb": 12, "tdp_watts": 190, "brand": "Intel",
        "market_used_min": 11000, "market_used_max": 14800,
        "risk_level": "LOW", "risk_notes": "Modern Battlemage 12GB VRAM, XeSS 2, requires ReBAR enabled."
    },
    "ARC B570": {
        "fps_1080p": 76.0, "fps_1440p": 58.0, "vram_gb": 10, "tdp_watts": 150, "brand": "Intel",
        "market_used_min": 9500, "market_used_max": 12800,
        "risk_level": "LOW", "risk_notes": "Modern Battlemage 10GB VRAM, requires ReBAR enabled."
    },
    "ARC A770": {
        "fps_1080p": 68.0, "fps_1440p": 51.0, "vram_gb": 16, "tdp_watts": 225, "brand": "Intel",
        "market_used_min": 8500, "market_used_max": 12500,
        "risk_level": "LOW", "risk_notes": "16GB VRAM Alchemist card; requires Resizeable BAR."
    },
    "ARC A750": {
        "fps_1080p": 62.0, "fps_1440p": 45.0, "vram_gb": 8, "tdp_watts": 225, "brand": "Intel",
        "market_used_min": 6500, "market_used_max": 9200,
        "risk_level": "LOW", "risk_notes": "Budget DX12 card; requires Resizeable BAR."
    },

    # --- AMD RDNA 1 & POLARIS ---
    "RX 5700 XT": {
        "fps_1080p": 59.0, "fps_1440p": 42.0, "vram_gb": 8, "tdp_watts": 225, "brand": "AMD",
        "market_used_min": 5200, "market_used_max": 7300,
        "risk_level": "HIGH", "risk_notes": "Heavily mined in 2020-2022; lacks DX12U Mesh Shaders."
    },
    "RX 5700": {
        "fps_1080p": 52.0, "fps_1440p": 37.0, "vram_gb": 8, "tdp_watts": 180, "brand": "AMD",
        "market_used_min": 4500, "market_used_max": 6300,
        "risk_level": "HIGH", "risk_notes": "Heavily mined in 2020-2022."
    },
    "RX 5600 XT": {
        "fps_1080p": 47.0, "fps_1440p": 32.0, "vram_gb": 6, "tdp_watts": 150, "brand": "AMD",
        "market_used_min": 4000, "market_used_max": 5600,
        "risk_level": "MEDIUM", "risk_notes": "6GB VRAM buffer limit."
    },
    "RX 590": {
        "fps_1080p": 26.0, "fps_1440p": 17.0, "vram_gb": 8, "tdp_watts": 225, "brand": "AMD",
        "market_used_min": 2200, "market_used_max": 3600,
        "risk_level": "CRITICAL", "risk_notes": "EXTREME MINING HAZARD (2018-2022). EOL drivers, high power draw."
    },
    "RX 580": {
        "fps_1080p": 24.0, "fps_1440p": 16.0, "vram_gb": 8, "tdp_watts": 185, "brand": "AMD",
        "market_used_min": 2000, "market_used_max": 3400,
        "risk_level": "CRITICAL", "risk_notes": "EXTREME MINING HAZARD. 95%+ mined 3-5 yrs, EOL drivers."
    },
    "RX 570": {
        "fps_1080p": 21.0, "fps_1440p": 14.0, "vram_gb": 8, "tdp_watts": 150, "brand": "AMD",
        "market_used_min": 1700, "market_used_max": 2700,
        "risk_level": "CRITICAL", "risk_notes": "EXTREME MINING HAZARD (2017-2022). EOL drivers."
    },
    "RX 480": {
        "fps_1080p": 22.0, "fps_1440p": 15.0, "vram_gb": 8, "tdp_watts": 150, "brand": "AMD",
        "market_used_min": 1700, "market_used_max": 2700,
        "risk_level": "CRITICAL", "risk_notes": "9+ years old; dual crypto boom wear."
    },
    "RX 470": {
        "fps_1080p": 19.0, "fps_1440p": 13.0, "vram_gb": 8, "tdp_watts": 120, "brand": "AMD",
        "market_used_min": 1400, "market_used_max": 2300,
        "risk_level": "CRITICAL", "risk_notes": "9+ years old; heavy 2017 mining wear."
    },
}

# Ordered so longer suffixes (e.g. TI SUPER > TI > SUPER > base) win at the SAME start index,
# while combined regex scanning guarantees EARLIEST token position in the title wins!
MATCH_PATTERNS: List[Tuple[str, str]] = [
    # RTX 50
    (r"\b(?:rtx\s*)?5090\b", "RTX 5090"),
    (r"\b(?:rtx\s*)?5080\b", "RTX 5080"),
    (r"\b(?:rtx\s*)?5070\s*ti\b", "RTX 5070 TI"),
    (r"\b(?:rtx\s*)?5070\b", "RTX 5070"),
    (r"\b(?:rtx\s*)?5060\s*ti\b.{0,28}?\b16\s*g(?:b|б)?\b", "RTX 5060 TI 16GB"),
    (r"\b(?:rtx\s*)?5060\s*ti\b", "RTX 5060 TI 8GB"),
    (r"\b(?:rtx\s*)?5060\b", "RTX 5060"),

    # RTX 40
    (r"\b(?:rtx\s*)?4090\b", "RTX 4090"),
    (r"\b(?:rtx\s*)?4080\s*super\b", "RTX 4080 SUPER"),
    (r"\b(?:rtx\s*)?4080\b", "RTX 4080"),
    (r"\b(?:rtx\s*)?4070\s*ti\s*super\b", "RTX 4070 TI SUPER"),
    (r"\b(?:rtx\s*)?4070\s*ti\b", "RTX 4070 TI"),
    (r"\b(?:rtx\s*)?4070\s*super\b", "RTX 4070 SUPER"),
    (r"\b(?:rtx\s*)?4070\b", "RTX 4070"),
    (r"\b(?:rtx\s*)?4060\s*ti\b.{0,28}?\b16\s*g(?:b|б)?\b", "RTX 4060 TI 16GB"),
    (r"\b(?:rtx\s*)?4060\s*ti\b", "RTX 4060 TI 8GB"),
    (r"\b(?:rtx\s*)?4060\b", "RTX 4060"),

    # RTX 30
    (r"\b(?:rtx\s*)?3090\s*ti\b", "RTX 3090 TI"),
    (r"\b(?:rtx\s*)?3090\b", "RTX 3090"),
    (r"\b(?:rtx\s*)?3080\s*ti\b", "RTX 3080 TI"),
    (r"\b(?:rtx\s*)?3080\b.{0,28}?\b12\s*g(?:b|б)?\b", "RTX 3080 12GB"),
    (r"\b(?:rtx\s*)?3080\b", "RTX 3080 10GB"),
    (r"\b(?:rtx\s*)?3070\s*ti\b", "RTX 3070 TI"),
    (r"\b(?:rtx\s*)?3070\b", "RTX 3070"),
    (r"\b(?:rtx\s*)?3060\s*ti\b", "RTX 3060 TI"),
    (r"\b(?:rtx\s*)?3060\b.{0,28}?\b8\s*g(?:b|б)?\b", "RTX 3060 8GB"),
    (r"\b(?:rtx\s*)?3060\b", "RTX 3060 12GB"),
    (r"\b(?:rtx\s*)?3050\b", "RTX 3050"),

    # RTX 20 & GTX 16
    (r"\b(?:rtx\s*)?2080\s*ti\b", "RTX 2080 TI"),
    (r"\b(?:rtx\s*)?2080\s*super\b", "RTX 2080 SUPER"),
    (r"\b(?:rtx\s*)?2080\b", "RTX 2080"),
    (r"\b(?:rtx\s*)?2070\s*super\b", "RTX 2070 SUPER"),
    (r"\b(?:rtx\s*)?2070\b", "RTX 2070"),
    (r"\b(?:rtx\s*)?2060\s*super\b", "RTX 2060 SUPER"),
    (r"\b(?:rtx\s*)?2060\b", "RTX 2060"),
    (r"\b(?:gtx\s*)?1660\s*ti\b", "GTX 1660 TI"),
    (r"\b(?:gtx\s*)?1660\s*super\b", "GTX 1660 SUPER"),
    (r"\b(?:gtx\s*)?1660\b", "GTX 1660"),
    (r"\b(?:gtx\s*)?1650\s*super\b", "GTX 1650 SUPER"),

    # GTX 10
    (r"\b(?:gtx\s*)?1080\s*ti\b", "GTX 1080 TI"),
    (r"\b(?:gtx\s*)?1080\b", "GTX 1080"),
    (r"\b(?:gtx\s*)?1070\s*ti\b", "GTX 1070 TI"),
    (r"\b(?:gtx\s*)?1070\b", "GTX 1070"),
    (r"\b(?:gtx\s*)?1060\b.{0,24}?\b6\s*g(?:b|б)?\b", "GTX 1060 6GB"),
    (r"\b(?:gtx\s*)?1060\b(?!.{0,20}?\b3\s*g(?:b|б)?\b)", "GTX 1060 6GB"),

    # RX 9000
    (r"\b(?:rx\s*)?9070\s*xt\b", "RX 9070 XT"),
    (r"\b(?:rx\s*)?9070\b", "RX 9070"),
    (r"\b(?:rx\s*)?9060\s*xt\b.{0,28}?\b16\s*g(?:b|б)?\b", "RX 9060 XT 16GB"),
    (r"\b(?:rx\s*)?9060\s*xt\b.{0,28}?\b8\s*g(?:b|б)?\b", "RX 9060 XT 8GB"),
    (r"\b(?:rx\s*)?9060\s*xt\b", "RX 9060 XT 16GB"),

    # RX 7000
    (r"\b(?:rx\s*)?7900\s*xtx\b", "RX 7900 XTX"),
    (r"\b(?:rx\s*)?7900\s*xt\b", "RX 7900 XT"),
    (r"\b(?:rx\s*)?7900\s*gre\b", "RX 7900 GRE"),
    (r"\b(?:rx\s*)?7800\s*xt\b", "RX 7800 XT"),
    (r"\b(?:rx\s*)?7700\s*xt\b", "RX 7700 XT"),
    (r"\b(?:rx\s*)?7600\s*xt\b", "RX 7600 XT"),
    (r"(?<!ryzen\s5\s)(?<!райзен\s5\s)(?<!r5\s)(?<!i5-)(?<!i5\s)\b(?:rx\s*|radeon\s*)7600\b", "RX 7600"),

    # RX 6000
    (r"\b(?:rx\s*)?6950\s*xt\b", "RX 6950 XT"),
    (r"\b(?:rx\s*)?6900\s*xt\b", "RX 6900 XT"),
    (r"\b(?:rx\s*)?6800\s*xt\b", "RX 6800 XT"),
    (r"\b(?:rx\s*)?6800\b", "RX 6800"),
    (r"\b(?:rx\s*)?6750\s*xt\b", "RX 6750 XT"),
    (r"\b(?:rx\s*)?6700\s*xt\b", "RX 6700 XT"),
    (r"(?<!i7-)(?<!i7\s)(?<!і7-)(?<!і7\s)\b(?:rx\s*|radeon\s*)6700\b", "RX 6700"),
    (r"\b(?:rx\s*)?6650\s*xt\b", "RX 6650 XT"),
    (r"\b(?:rx\s*)?6600\s*xt\b", "RX 6600 XT"),
    (r"(?<!i5-)(?<!i5\s)(?<!і5-)(?<!і5\s)\b(?:rx\s*|radeon\s*)6600\b", "RX 6600"),

    # Intel Arc
    (r"\b(?:arc\s*)?b580\b", "ARC B580"),
    (r"\b(?:arc\s*)?b570\b", "ARC B570"),
    (r"\barc\s*a770\b", "ARC A770"),
    (r"\barc\s*a750\b", "ARC A750"),

    # RX 5000 & Polaris
    (r"\b(?:rx\s*)?5700\s*xt\b", "RX 5700 XT"),
    (r"(?<!ryzen\s7\s)(?<!райзен\s7\s)(?<!r7\s)\b(?:rx\s*|radeon\s*)5700\b", "RX 5700"),
    (r"(?<!ryzen\s5\s)(?<!райзен\s5\s)(?<!ryzen\s)(?<!r5\s)\b(?:rx\s*)?5600\s*xt\b", "RX 5600 XT"),
    (r"\brx\s*590\b", "RX 590"),
    (r"\brx\s*580\b", "RX 580"),
    (r"\brx\s*570\b", "RX 570"),
    (r"\brx\s*480\b", "RX 480"),
    (r"\brx\s*470\b", "RX 470"),
]

# Non-GPU accessories, stripped shells, and boxes
EXCLUSION_KEYWORDS = [
    r"\bкулер\b",
    r"\bвентилятор\w*\b",
    r"\bохолодження\s+(?:для|від|на)\b",
    r"\bсистема\s+охолодження\b",
    r"\bрадіатор\s+(?:для|від|на)\b",
    r"\bкожух\b",
    r"\bкоробк\w*\b",
    r"\bbox\s+only\b",
    r"\bonly\s+box\b",
    r"\bводяне\s+блок\b",
    r"\bводоблок\b",
    r"\bwaterblock\b",
    r"\bтермопрокладк\w*\b",
    r"\bбекплейт\b",
    r"\bперехідник\b",
    r"\bшлейф\b",
    r"\bрайзер\b",
    r"\briser\b",
    r"\bчохол\b",
    r"\bпідставк\w*\b",
    r"\bкронштейн\b",
    r"\bбез\s+відеокарти\b",
    r"\bбез\s+чіп[ау]\b",
    r"\bбез\s+чип[ау]\b",
    r"\bбез\s+гпу\b",
    r"\bбез\s+gpu\b",
    r"\bбез\s+vram\b",
    r"\bno\s+gpu\b",
    r"\bno\s+vram\b",
    r"\bno\s+core\b",
    r"\bwithout\s+gpu\b",
    r"\bплата\s+без\b",
    r"\bноутбук\w*\b",
    r"\bкомп['’]?ютер\b",
    r"\bсистемний\s+блок\b",
]

# Pre-compute market median on all GPU entries
for _gpu_spec in GPU_DATABASE.values():
    _gpu_spec.setdefault(
        "market_used_median",
        (_gpu_spec["market_used_min"] + _gpu_spec["market_used_max"]) // 2,
    )

# Strip negative SEO comparison spam before model matching, e.g. "(не rtx 3060 3070 1080ti)"
_SEO_COMPARISON_RE = re.compile(
    r"(?:\(\s*(?:не|аналог|краще|лучше|обмін|обмен)[^)]*\))"
    r"|(?:\b(?:не|аналог|краще\s+ніж|лучше\s+чем|обмін\s+на|обмен\s+на)\s+(?:rtx|gtx|rx|arc)?[\s\d/,\-xtisupergb]+)"
)

_EXCLUSION_RE = re.compile("|".join(EXCLUSION_KEYWORDS))
_BUNDLE_SAFE_EXCLUSION_RE = re.compile(
    "|".join(
        kw for kw in EXCLUSION_KEYWORDS
        if kw not in (r"\bкомп['’]?ютер\b", r"\bсистемний\s+блок\b", r"\bкулер\b", r"\bкоробк\w*\b")
    )
    + r"|\bкоробк\w*\s+(?:від|для|без)\b"
)
_NUM_SCAN_RE = re.compile(r"\d{3,4}")
_PATTERNS_BY_ANCHOR: Dict[str, List[Tuple[re.Pattern, str]]] = {}
for _pat, _model in MATCH_PATTERNS:
    _nums = _NUM_SCAN_RE.findall(_pat)
    if _nums:
        _PATTERNS_BY_ANCHOR.setdefault(_nums[0], []).append((re.compile(_pat), _model))


def _scan_gpu_text(text: str) -> Optional[Tuple[str, bool]]:
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
def _identify_gpu_cached(title: str, desc_head: str, allow_bundles: bool = False) -> Optional[Tuple[str, bool]]:
    title_l = title.lower()
    excl_re = _BUNDLE_SAFE_EXCLUSION_RE if allow_bundles else _EXCLUSION_RE
    if excl_re.search(title_l):
        return None

    res = _scan_gpu_text(_SEO_COMPARISON_RE.sub(" ", title_l))
    if res:
        return res

    if desc_head:
        res_desc = _scan_gpu_text(_SEO_COMPARISON_RE.sub(" ", desc_head.lower()))
        if res_desc:
            return res_desc[0], False

    return None


def identify_gpu(title: str, description: str = "", allow_bundles: bool = False) -> Optional[Dict[str, Any]]:
    """
    Identifies GPU model at C-regex speed using anchor-indexed left-to-right token precedence,
    filtering out accessories, stripped donor shells, and SEO comparison spam.
    """
    if not title:
        return None
    res = _identify_gpu_cached(title, (description or "")[:300], allow_bundles=allow_bundles)
    if not res:
        return None
    model_name, is_multi_sku = res
    specs = GPU_DATABASE.get(model_name)
    if not specs:
        return None
    out = {"model": model_name, **specs}
    if is_multi_sku:
        out["multi_model_spam"] = True
    return out
