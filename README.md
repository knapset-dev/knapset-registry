# Knapset Registry

`knapset-registry` is the official plugin and domain-extension repository for [Knapset](https://github.com/knapset-dev/knapset). Knapset's core repository stays domain-agnostic (shipping only the minimal `template` domain); concrete domain logic across different verticals (PC hardware, fishing tackle, custom adapters, and defect analyzers) lives here and is installed on demand via `python3 main.py market install <id>`.

---

## Contents of `registry.json`

| ID | Type | Domain | Status | Files | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`fishing`** | `domain_extension` | `fishing` | **Reference** | `modules/extensions/fishing/` | 4-slot fishing setup builder (`rod`, `reel`, `line`, `lure`) checking casting-weight overlap, rod/reel action balance, and line breaking strength vs reel drag. |
| **`pc`** | `domain_extension` | `pc` | **Production** | `modules/extensions/pc/` | Full PC hardware analyzer and build optimizer (GPU, CPU, Motherboard, RAM, PSU, bundles, and prebuilt evaluator). See [`modules/extensions/pc/README.md`](modules/extensions/pc/README.md). |
| **`reball_detector`** | `scam_analyser` | `hardware_pc` | **Standalone plugin** | `modules/scam_analyser/reball_detector.py` | Regex heuristic that flags GPU listings mentioning BGA reballing, chip heating/reflowing, flux residue, or modified mining vBIOS. |
| **`ssd_wear_detector`** | `scam_analyser` | `hardware_pc` | **Standalone plugin** | `modules/scam_analyser/ssd_wear_detector/` | Flags used SSD listings that hide S.M.A.R.T. health, have critical bad blocks, or show Chia plotting / heavy TBW wear. |
| **`sample_provider`** | `info_provider` | `general` | **Stub / Example** | `modules/info_providers/sample_provider.py` | Example `BaseInfoProvider` skeleton returning a deterministic sample listing. |
| **`value_composer`** | `build_composer` | `hardware_pc` | **Stub / Example** | `modules/build_composer/value_composer.py` | Example `BaseBuildComposer` skeleton returning a static sample build dictionary. |
| **`nvme_ssd_analyser`** | `component_analyser` | `hardware_pc` | **Reference** | `modules/component_analyser/nvme_ssd_analyser.py` | Identifies NVMe M.2 SSD models, capacities, read speeds, and PCIe interfaces from listing text. |
| **`mistral_provider`** | `ai_providers` | `general` | **Reference** | `modules/ai_providers/mistral_provider.py` | Pure stdlib HTTPS client for Mistral AI chat completions (`MISTRAL_API_KEY`). |

### Bundles (`bundles/`)

- **`photo-kit.json`** — minimal example bundle containing `sample_provider`.
- **`pc-starter.json`** — lean PC starter bundle (`pc`, `sample_provider`, `reball_detector`, `value_composer`).
- **`pc-starter-kit.json`** — complete PC starter kit adding `ssd_wear_detector` alongside the 4 starter modules.

> **Note on standalone plugin wiring**: In the current architecture, `domain_extension` packages (`fishing`, `pc`) execute their own self-contained screening and synthesis pipelines when invoked via `python3 main.py <domain> ...`. Standalone `scam_analyser` and `build_composer` plugins register into Knapset's plugin registries independently.

---

## Using this registry with Knapset

### From GitHub (default in Knapset)

Knapset points to `https://raw.githubusercontent.com/knapset-dev/knapset-registry/main/registry.json` by default:

```bash
cd /path/to/knapset
python3 main.py module search
python3 main.py module install fishing
python3 main.py module install pc
```

### From a local checkout (for development)

If you are editing files in `knapset-registry` locally and want Knapset to install from your working tree:

```bash
export KNAPSET_REGISTRY_URL="file:///absolute/path/to/knapset-registry/registry.json"
python3 main.py market install <extension-id>
```

---

## Integrity and verification

Single-file modules in `registry.json` carry a `"sha256"` field checked by Knapset's `MarketplaceClient` before installation. If you edit a single-file module (`reball_detector.py`, `sample_provider.py`, `value_composer.py`), update its hash in `registry.json`:

```bash
sha256sum modules/scam_analyser/reball_detector.py
```

Multi-file directory packages (`pc`, `fishing`, `ssd_wear_detector`) list `"files": [...]` in `registry.json` and are checked with Python's `ast.parse()` during installation to reject unauthorized system imports.

---

## Running tests

The test suite in `tests/` (`83` tests total) verifies registry security validation and bundled domain extensions:

- `test_registry.py` (`13` tests): AST sandbox enforcement (`open` write bans, reflection/socket/pickle blocking), deterministic SHA-256 checksums, dependency specs, and index compilation (`registry.json`).
- `test_fishing_extension.py` (`4` tests): Multi-slot fishing setup compatibility rules (rod/reel action balance, casting-weight overlap, line/drag safety) and set synthesis.
- `test_pc_extension.py` (`43` tests) & `test_ram_form_factor.py` (`23` tests): Component databases, risk heuristics, combinatorial build optimization, and form-factor classification (details in [`modules/extensions/pc/README.md`](modules/extensions/pc/README.md)).

Because extensions import core base classes (`domain_layout`, `domain_weights`) from `knapset`, either keep `knapset` as a sibling directory (`../knapset`) or pass it on `PYTHONPATH`:

```bash
PYTHONPATH="/path/to/knapset:." python3 -m unittest discover -s tests -v
```
