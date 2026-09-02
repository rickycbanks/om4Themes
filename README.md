# om4Themes

Theme compatibility observatory for **Omarchy 4 / Quattro**.

om4Themes grades every discoverable Omarchy theme against the Quattro release, exposing compatibility levels (0–4), feature badges, and per-check reasoning via a static GitHub Pages site backed by a machine-readable `themes.json` database.

- **Spec:** [spec.md](./spec.md)
- **Implementation plan:** [implementation-plan.md](./implementation-plan.md)
- **Checklist:** [implementation-checklist.md](./implementation-checklist.md)

## Status

Phase 0–1 complete — repo scaffold, placeholder site, versioned rule tables (`analyzer/om4t/rules.py` v2026.09.0) and JSON schema (`analyzer/om4t/schema.py`).

Later phases (discovery → verification → grading → site) will replace the placeholder site and wire the weekly GitHub Actions pipeline.

## How to run tests

```bash
cd analyzer
python -m pytest tests/ -q
```

Or from the repository root:

```bash
python -m pytest analyzer/tests -q
```

Requires Python ≥3.11. Optional dev install:

```bash
pip install -e ./analyzer[dev]
```
