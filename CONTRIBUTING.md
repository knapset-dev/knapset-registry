# Contributing to OmniForge Registry

Thank you for contributing to the open module registry! This guide outlines how to create, test, and submit your plugins.

---

## Submission Guidelines

1. **Pure Python Standard Library**: Modules must rely strictly on standard library modules (`json`, `re`, `urllib.request`, `math`, `hashlib`, etc.). No third-party packages from PyPI are permitted.
2. **Deterministic & Read-Only**: Analytical modules must never write to host files or spawn processes.
3. **Packaging Types**:
   - **Single-File (`.py`)**: For self-contained logic without external assets.
   - **Directory Package (`folder/__init__.py`)**: If your plugin requires packaged JSON datasets, heuristics, or dictionaries.
4. **Subsystem Contract**: Your class must implement the interface expected by its subsystem.

---

## Step-by-Step Contribution Workflow

### 1. Choose Subsystem & Domain
Place your code inside `modules/<subsystem>/`:
- `modules/info_providers/<name>.py`
- `modules/scam_analyser/<name>.py` (or folder)
- `modules/component_analyser/<name>.py`
- `modules/build_composer/<name>.py`
- `modules/ai_providers/<name>.py`

### 2. Create the Manifest (`<name>.json`)
Alongside your code, create a manifest file `modules/<subsystem>/<name>.json`:

```json
{
  "name": "my_scanner",
  "subsystem": "scam_analyser",
  "domain": "laptops",
  "version": "1.0.0",
  "author": "your_github_username",
  "description": "Detects counterfeit batteries and soldered RAM defects in used laptops",
  "min_app_version": "1.0.0",
  "trust_level": "community",
  "source_type": "single_file",
  "download_url": "modules/scam_analyser/my_scanner.py",
  "tags": ["laptop", "battery", "scam"],
  "env_keys": [],
  "dependencies": []
}
```

### 3. Validate Locally Before Submitting PR
Run the registry validation suite locally:

```bash
# Validate your submission
python3 scripts/validate_submission.py

# Compile and check the index
python3 scripts/build_index.py
```

### 4. Submit Pull Request
Push your changes to your fork and submit a PR to `main`.
The automated GitHub Actions bot will:
- Run AST security scanner.
- Verify checksums and compute deterministic hashes.
- Validate subsystem duck typing.
- Post an inspection summary comment on your PR.
