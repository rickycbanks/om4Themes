# om4Themes

Theme compatibility observatory for **Omarchy 4 / Quattro**.

om4Themes grades every discoverable Omarchy theme against the Quattro release, exposing compatibility levels (0–4), feature badges, and per-check reasoning via a static GitHub Pages site backed by a machine-readable `themes.json` database.

- **Spec:** [spec.md](./spec.md)
- **Implementation plan:** [implementation-plan.md](./implementation-plan.md)
- **Checklist:** [implementation-checklist.md](./implementation-checklist.md)

## Status

Phases 0–7 built locally — scaffold, schema/rules (`v2026.09.0`), discovery/fetch/caching, static analysis, headless verification with the official Omarchy renderer (floating pin + canary gate), grading, and static site are wired. Canary live-verified **22/22** built-ins against `omacom/omarchy` **v4.0.1**; weekly cron (`0 6 * * 0`) pending repo creation. Operational details in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

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
