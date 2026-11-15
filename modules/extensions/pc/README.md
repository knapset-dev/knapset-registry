# Omniforge PC Hardware Extension (`pc`)

This directory contains the `pc` domain extension for [Omniforge](https://github.com/omniforge-dev/omniforge). It screens second-hand and outlet PC component listings from normalized marketplace payloads (such as OLX, Telemart, eBay, and Blocket), matches messy seller titles against reference hardware databases, filters out defective or incompatible parts, and composes complete 5-part builds (`CPU + Motherboard + RAM + GPU + PSU`) within a budget.

---

## What it does

### 1. Component databases and title matching

Each of the five component categories has a reference database and a listing analyzer:

- **GPU (`gpu_database.py`, `gpu_analyzer.py`, `gpu_scam_detector.py`)**:
  - Matches ~90 GPU models (GTX 10-series through RTX 40-series, RX 500 through RX 7000, Intel Arc) with 1080p/1440p raster and ray-tracing scores, VRAM, TDP, and historical used-price ranges.
  - Disambiguates variants where chip or VRAM size changes performance: `RTX 3060 8GB` vs `12GB`, `GTX 1060 3GB` vs `6GB`, `RX 580 4GB` vs `8GB` vs `2048SP`.
  - Rejects laptop GPUs, eGPUs, mining-only P106/CMP boards, waterblocks, coolers, empty boxes, and buy-out / trade-in ads.
- **CPU (`cpu_database.py`, `cpu_analyzer.py`)**:
  - Covers AM4, AM5, LGA1200, and LGA1700 processors with gaming and productivity scores, socket, TDP, integrated-graphics flags (`has_igpu`), and cooler inclusion.
  - Rejects Xeon server bundles, laptop mobile CPUs, delidded/broken-pin chips (bent or missing pins), and engineering samples (`ES`, `QHV`, `QTB`).
- **Motherboard (`mobo_database.py`, `mobo_analyzer.py`)**:
  - Extracts socket (`AM4`, `AM5`, `LGA1200`, `LGA1700`), chipset (`A320`–`X670E`, `H410`–`Z790`), memory generation (`DDR4` vs `DDR5` on dual-memory LGA1700 boards), form factor (`ATX`, `mATX`, `ITX`), and VRM tier (`1`–`5`).
  - Filters out boards with bent LGA pins, dead memory slots/channels, dead PCIe/LAN/audio, or missing BIOS chips.
- **RAM (`ram_database.py`, `ram_analyzer.py`)**:
  - Identifies `DDR4` and `DDR5` kits, total capacity, stick count (`1x16GB`, `2x8GB`, `2x16GB`, `4x8GB`), speed (`MT/s`), and CAS latency (`CL`).
  - Classifies physical module type into five values (`UDIMM`, `SODIMM`, `ECC_REG`, `ECC_UDIMM`, `UNKNOWN`) using manufacturer part numbers, JEDEC type codes, and multilingual text rules (details below).
- **PSU (`psu_database.py`, `psu_analyzer.py`)**:
  - Extracts wattage (`400W`–`1600W`), 80 PLUS certification, modularity, form factor (`ATX`, `SFX`), and PSU safety tier (`Tier A` through `Tier F / Fire Hazard`).
  - Penalizes modular units sold with missing cables, noisy/rattling fans, or broken warranty seals.

### 2. Build optimizer (`build_optimizer.py` and `layout.py`)

Given a budget in UAH and a build mode (`gaming-1080p`, `gaming-1440p`, `workstation`, `budget`, `quiet`, `compact-itx`, `upgrade-path`), `PCBuildOptimizer`:

1. Loads candidates for all five slots from SQLite (`omniforge_market.db`) or JSON caches, converting non-UAH prices through `CurrencyService`.
2. Drops items with critical defect flags, incompatible form factors (`SODIMM`, `ECC_REG`, legacy `DDR1`/`DDR2`/`DDR3`), or PSU fire-hazard ratings (`Tier F`).
3. Enforces hard compatibility across slots:
   - `CPU.socket == Motherboard.socket`
   - `RAM.generation == Motherboard.ram_type` (`DDR4` vs `DDR5`)
   - `RAM.form_factor in ("UDIMM", "ECC_UDIMM", "UNKNOWN")` (never `SODIMM` or `ECC_REG`)
   - `ECC_UDIMM` is rejected on consumer Intel chipsets (`H610`, `B660`, `B760`, `Z690`, `Z790`, etc.)
   - `Motherboard.vrm_tier` sufficient for `CPU.tdp_w`
   - `PSU.wattage >= (CPU.tdp_w + GPU.tdp_w) * 1.35 + 100`
   - `APU` mode (`budget <= 12000` with no dedicated GPU) requires `CPU.has_igpu == True`
4. Evaluates up to 40,000 candidate combinations across single-GPU, APU, and multi-generation platform templates (`AM4`, `AM5`, `LGA1200`, `LGA1700`) and returns the highest-scoring build along with per-part risk scores and warnings.

### 3. Prebuilt PC evaluator (`prebuilt_evaluator.py`)

Takes a free-text description of a complete used PC plus its asking price, parses out the CPU, GPU, RAM, motherboard, PSU, storage, and case, looks up live median component prices in the local cache, and outputs a **Build vs. Buy** verdict (`STRONG BUY`, `FAIR PRICE`, `OVERPRICED`, or `AVOID / BUILD YOURSELF`) with a line-by-line parts breakdown.

### 4. Market audit pipeline (`audit_pipeline.py`)

`python3 main.py pc audit` runs all cached GPU listings through a 4-stage pipeline (`Ingest -> Normalize -> Screen -> Price & Score`) and writes `data/audit_ledger.json` and `data/audit_summary.md`, recording the exact rejection reason or fair-value delta for every offer.

---

## RAM form-factor classification (`ram_database.py`)

Used RAM listings on OLX frequently omit whether a stick is desktop `UDIMM`, laptop `SO-DIMM`, or server `RDIMM`, or paste other products at the bottom of the description. `extract_form_factor()` and `_identify_ram_cached()` classify modules into five values:

| Value | Meaning | Optimizer behavior |
| :--- | :--- | :--- |
| `UDIMM` | Standard 288-pin desktop unbuffered DIMM | Allowed (`+0` risk). |
| `ECC_UDIMM` | Unbuffered ECC 288-pin DIMM (e.g., SK hynix `HMA...U7...`, Samsung `M391...`, Kingston `KVR...E...`, Micron `MTA9ASF...AZ` / `MTA18ASF...AZ`, or `"ECC support"` / `"ECC UDIMM"`) | Allowed on compatible platforms with a **`+25` risk penalty** and a warning note; rejected on Intel consumer chipsets. |
| `UNKNOWN` | Listing has no form-factor signal, or title and description contradict each other on the same module | Allowed as a last resort with a **`+15` risk penalty**, a warning note, and `"confirm_with_seller": True`. |
| `SODIMM` | 260/262-pin laptop memory | **Hard-blocked** from desktop builds. |
| `ECC_REG` | Registered (`RDIMM`) or Load-Reduced (`LRDIMM`) server memory | **Hard-blocked** from consumer desktop builds. |

### Ordering and safeguards in the classifier

1. **Unicode lookalike normalization on a scratch copy**: Converts Cyrillic homoglyph characters in `SO-DIMM` tokens on a local copy of the string before regex matching, without mutating the listing title or description seen by scam detectors or the UI.
2. **Negation stripping**:
   - Strips device targets inside negated clauses in both word orders (e.g., `"not for laptop"`, `"not for desktop"` across supported languages), preserving surrounding part numbers and positive markers in the same sentence.
   - Neutralizes negated ECC phrases (`"without ECC"`, `"non-ECC"`, and localized equivalents) and DDR5 chip-level `"on-die ECC"` before checking `ECC_UDIMM` text patterns, so ordinary non-ECC desktop sticks and DDR5 kits are not misclassified as `ECC_UDIMM`.
3. **JEDEC speed bins vs. module type suffixes**:
   - JEDEC speed-bin letters (`PC4-2666V`, `PC4-2400T`, `PC4-2933Y`, `PC4-2133P`, `PC4-3200AA`) apply to desktop, laptop, and server modules alike and are **not** treated as server markers.
   - Only full JEDEC labels carrying registered or load-reduced module type suffixes (`PC4-2400T-RE1`, `PC4-2666V-RB2`, `PC4-2133P-RA0`, `PC4-2933Y-LR...`) or explicit `RDIMM` / `LRDIMM` / `ECC REG` / `M393` / `HMA...R` / `MTA...PZ` markers are classified as `ECC_REG`. Unrelated retail SKUs ending in `-RB` (such as PNY `SSD7CS900-250-RB`) are not matched.
4. **Part numbers before prose**:
   - Checks manufacturer part numbers (`_PART_SODIMM_RE`, `_PART_ECC_UDIMM_RE`, `_PART_UDIMM_RE`) and explicit `SO-DIMM` / `UDIMM` / `RDIMM` tokens before checking generic compatibility boilerplate, so a title with a clear part number is not overridden by generic shop descriptions.
5. **Cross-product cutoff and title-vs-description conflict resolution**:
   - Truncates description text at cross-selling headers ("also available", "see other listings") before running prose form-factor checks, while still scanning the full description for manufacturer part numbers.
   - Evaluates the title first and the description second. If both yield non-`UNKNOWN` form factors that disagree:
     - When a manufacturer part number is present in either the title or description (e.g., `KVR219S6/4` or `KVR24N17S8/8` paired with conflicting `UDIMM`/`SODIMM` text), the contradiction concerns the module itself and resolves to **`UNKNOWN`**.
     - When no part number is present and the title carries an explicit marker (e.g., `"RAM for laptop"`), the title wins over loose description text.

### Classifier Behavior Overview

On multi-thousand-listing secondary market samples where sellers omit form-factor labels, the majority of consumer DDR4/DDR5 modules classify as `UDIMM`, with `SODIMM` and `ECC_REG` hard-blocked and conflicting or ambiguous offers falling back to `UNKNOWN` for manual verification.

---

## Known limitations

1. **Precision/Recall Validation**:
   Measuring true classification precision and recall requires a hand-labeled evaluation set rather than aggregate unlabeled predictions.
2. **Aggressive cross-product cutoff**:
   Cutting the description at multi-item seller footers ("also available" / cross-selling sections) prevents unrelated inventory from polluting the form factor, though any legitimate form-factor note written after such a footer will be ignored unless identified by a part number.

---

## CLI commands (`python3 main.py pc ...`)

| Command | Example |
| :--- | :--- |
| `pc build` | `python3 main.py pc build -b 30000 -m gaming-1080p` |
| `pc modes` | `python3 main.py pc modes` |
| `pc search` | `python3 main.py pc search -s gpu --max-price 12000` |
| `pc gpu` | `python3 main.py pc gpu --max-price 12000 --min-vram 8` |
| `pc cpu` | `python3 main.py pc cpu --socket AM4 --max-price 5000` |
| `pc mobo` | `python3 main.py pc mobo --socket AM4` |
| `pc ram` | `python3 main.py pc ram --type DDR4 --min-gb 16` |
| `pc psu` | `python3 main.py pc psu --min-watts 650` |
| `pc prebuilt` | `python3 main.py pc prebuilt "i5-12400F, RTX 4060, 16GB DDR4" -p 26000` |
| `pc audit` | `python3 main.py pc audit` |
