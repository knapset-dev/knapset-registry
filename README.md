# Knapset Registry

`knapset-registry` is the official preset and theme repository for [Knapset v2](https://github.com/knapset-dev/knapset). Presets are declarative JSON (plus small sample datasets); themes are single JSON files for the TUI. Both install on demand with `ks reg`.

---

## Contents of `registry.json`

| ID | Type | Description |
| :--- | :--- | :--- |
| **`pc_build`** | `presets` | 4-slot PC build optimizer (CPU, motherboard, GPU, PSU) with reference matching, limits, and compatibility rules (`solve`). |
| **`fishing_tackle`** | `presets` | 4-slot fishing setup (`rod`, `reel`, `line`, `lure`) with compatibility rules (`solve`). |
| **`meal_prep`** | `presets` | Bounded knapsack daily meal-prep basket hitting protein & fiber goals under budget/calorie caps (`basket`). |
| **`cloud_vms`** | `presets` | Cloud VM price-performance ranker with Reference DB CPU benchmark enrichment (`rank`). |
| **`camera_kit`** | `presets` | 4-slot camera kit optimizer (`body`, `lens`, `tripod`, `bag`) enforcing mount compatibility & payload/weight caps (`solve`). |
| **`nord`**, **`catppuccin-mocha`**, **`gruvbox-dark`**, **`tokyo-night`**, **`soft-dark-pink`** | `themes` | TUI color themes (named ANSI, 256-color, or `#RRGGBB`). |

### Bundles (`bundles/`)

- **`starter-presets.json`** — `pc_build`, `fishing_tackle`, `meal_prep`, `cloud_vms`, `camera_kit`, and `soft-dark-pink`.

---

## Using this registry with Knapset

```bash
ks reg search
ks reg search --type theme
ks reg install preset:pc_build
ks reg install theme:nord --use
```

By default Knapset reads `https://raw.githubusercontent.com/knapset-dev/knapset-registry/main/registry.json`. A sibling `../knapset-registry` checkout is picked up automatically, or point at any directory/URL:

```bash
ks reg search --registry /absolute/path/to/knapset-registry
export KNAPSET_REGISTRY=/absolute/path/to/knapset-registry
```

---

## Integrity and verification

Every entry in `registry.json` carries a `sha256`. Directory packages (presets) hash all files; single-file items (themes) hash the file. Regenerate and check the index with:

```bash
python3 scripts/build_index.py
python3 scripts/build_index.py --check
python3 scripts/validate_submission.py
```

Python plugin submissions (if any) are additionally AST-scanned for unsafe imports and calls.

---

## Running tests

```bash
python3 -m unittest discover tests -v
```

`tests/test_registry.py` covers the AST sandbox rules, SHA-256 hashing, dependency specs, and index compilation.
