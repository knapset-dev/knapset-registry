# Contributing to Knapset Registry

Thank you for contributing to the open module registry! This guide outlines how to create, test, and submit presets, themes, and plugins.

---

## Submission Guidelines

1. **Declarative first**: Prefer pure JSON presets and themes. No third-party packages are ever permitted.
2. **Python plugins** (optional) must use the standard library only and never write host files or spawn processes.
3. **Packaging**:
   - **Theme**: a single JSON file in `modules/themes/files/<name>.json` plus a manifest `modules/themes/<name>.json`.
   - **Preset**: a directory `modules/presets/<name>/` (with `preset.json` and sample data) plus a manifest `modules/presets/<name>.json`.

---

## Step-by-Step Contribution Workflow

### 1. Create the Manifest
Example theme manifest `modules/themes/my_theme.json`:

```json
{
  "name": "my_theme",
  "subsystem": "themes",
  "domain": "ui",
  "version": "1.0.0",
  "author": "your_github_username",
  "description": "My TUI color theme",
  "source_type": "single_file",
  "download_url": "modules/themes/files/my_theme.json",
  "tags": ["theme", "dark"]
}
```

### 2. Validate Locally Before Submitting PR
Run the registry validation suite locally:

```bash
python3 scripts/validate_submission.py
python3 scripts/build_index.py
```

### 3. Submit Pull Request
Push your changes to your fork and submit a PR to `main`.
The automated GitHub Actions bot will:
- Run AST security scanner.
- Verify checksums and compute deterministic hashes.
- Validate subsystem duck typing.
- Post an inspection summary comment on your PR.
