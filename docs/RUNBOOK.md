# Runbook — om4Themes

Operational guide for the weekly observatory pipeline. See `implementation-plan.md` §13 for workflow design and §7/§9 for caching and pin/canary details.

## What weekly runs do

Every Sunday 06:00 UTC (`cron: "0 6 * * 0"`) plus on-demand via **Actions → build → Run workflow**:

1. **Resolve Omarchy pin** — `python -m om4t resolve-pin` fetches `repos/omacom/omarchy/releases/latest`, excludes drafts/prereleases and tags younger than ~3 days, records `tag`+`commit_sha`+`pin_source` to `work/pin.json`. Override with `workflow_dispatch` input `omarchy_ref` (e.g. `v4.0.3`).
2. **Clone Omarchy** — `clone-omarchy --pin work/pin.json --dest work/omarchy` shallow-clones the resolved tag for use as the official renderer (`bin/omarchy-theme-set-templates`, `bin/omarchy-theme-color`, etc.).
3. **Canary gate** — `canary --omarchy-dir work/omarchy --workdir work` runs the full stage→sanitize→render pipeline against all 22 built-ins under `work/omarchy/themes/`. Every built-in must exit 0 and have no `{{...}}` placeholders remaining, grading ≥ L3. Failure = Class A (see below).
4. **Discover** — `discover --out work/manifest.json` merges GitHub topic `omarchy-theme` search + built-ins + `omacom/omarchy-site` registry + `data/sources.json` seeds, dedupes by `owner/repo`, excludes archived.
5. **Run** — `run --manifest work/manifest.json --omarchy-dir work/omarchy --workdir work` shallow-clones each candidate into `work/clones/`, applies `work/cache.json` SHA-skip (skip when SHA unchanged **and** `RULES_VERSION` and pin unchanged), runs static analysis + official-renderer verification + grading, writes `work/themes.json` and `work/cache.json`.
6. **Deploy** (gated on `analyze` success) — downloads `work/themes.json` artifact, copies `site/` to `_site/` (dropping any repo-local `site/data` sample — artifact is authoritative), writes artifact JSON to `_site/data/themes.json`, publishes via `configure-pages`/`upload-pages-artifact`/`deploy-pages`. On failure, GitHub Pages keeps the last-good deployment.
7. **Artifacts & caches** — `work/themes.json` + `work/logs/**` + `work/pin.json` uploaded as artifacts (even on failure via `if: always()`); `work/clones`, `work/omarchy`, `work/cache.json` cached via `actions/cache` with keys `rules_version + week` (skipped when `full_rescan: true`).

## Failure classes (§13.1)

| Class | What it means | Pipeline behavior | What you see |
|-------|---------------|-------------------|--------------|
| **Class A — pipeline breakage** | Canary failed, pin resolution failed, renderer-contract mismatch, `gh api` auth/search failure. The Omarchy contract changed or the infra broke. | `analyze` job hard-fails (exit 2 from `canary`). No deploy. `notify` job auto-files/comments a `pipeline-breakage` issue. | Red **build** run, no Pages deployment, new/commented GitHub issue with label `pipeline-breakage`. |
| **Class B — ecosystem shift** | Canary passes but community error rate > ~25% or level histogram swings materially vs previous run. Grades are *valid* — a new sanitization rule genuinely broke themes — but worth confirming. | Grades publish normally; `notify` (or manual triage) files an informational `ecosystem-shift` issue. | Green run, site updates, plus an `ecosystem-shift` issue to acknowledge. |
| **Per-theme errors** | One repo has broken TOML, clone failed, etc. | Isolated into the theme record's `error` field; counts toward `run.errors`. Never fails the run. | That card shows Level 0 with an error note; everything else grades normally. |

## Recovering from a `pipeline-breakage` issue

1. **Read the issue** — note the run link (`https://github.com/<owner>/<repo>/actions/runs/<id>`), resolved pin (`tag`, `sha`, `pin_source`), and log excerpt.
2. **Reproduce locally**:
   ```bash
   # create or reuse .venv
   python -m venv .venv && source .venv/bin/activate
   pip install -e ./analyzer
   GH_TOKEN=$(gh auth token) python -m om4t resolve-pin | tee work/pin.json
   python -m om4t clone-omarchy --pin work/pin.json --dest work/omarchy
   # canary should reproduce the Class A failure
   python -m om4t canary --omarchy-dir work/omarchy --workdir work
   # single-theme drill-down
   python -m om4t analyze-dir --omarchy-dir work/omarchy analyzer/tests/fixtures/themes/native-full
   ```
   Inspect `work/logs/` and the canary JSON output for the first failing built-in theme.
3. **Fix** — typically `analyzer/om4t/verify.py`, `static.py`, or `rules.py` needs updating to track the new Omarchy contract (e.g. new deny-list entry, template path change). Bump `RULES_VERSION` if the rubric changes.
4. **PR** — push a branch, open a PR, confirm `test` workflow is green (includes the golden built-in canary with the official renderer — requires network on the runner).
5. **Validate with an override** — **Actions → build → Run workflow** with `omarchy_ref: vX.Y.Z` (the suspect tag) and optionally `full_rescan: true`. Confirm the run goes green.
6. **Close the issue** — when `main` is green, close the `pipeline-breakage` issue with a comment linking the fix PR and the green run.

## Bumping `RULES_VERSION` and Omarchy pin policy

- **`RULES_VERSION`** (`analyzer/om4t/rules.py`, e.g. `2026.09.0`) — bump on any rubric change (new marker regex, badge probe, level definition). It is stored per theme (`compatibility.rules_version`) and part of the cache key; bumping forces re-analysis of every theme. CalVer `YYYY.MM.<patch>`.
- **Omarchy pin policy** — floating: each run resolves `latest` stable tag at runtime (maturity buffer `PIN_MATURITY_DAYS = 3`, drafts/prereleases excluded), never tracks branch HEAD. Every new resolved tag deliberately re-verifies the whole ecosystem. Pin is recorded per run (`omarchy.pin`, `pin_source`) and per theme (`tested_against`, `omarchy_commit`).
  - **Override input** `omarchy_ref` — set in manual dispatch to force-test a future release early or hold back on a suspect one (`workflow_dispatch` → `omarchy_ref: v4.0.2`). The `pin_source` becomes `override` in that run.
  - **To pin manually**: dispatch with `omarchy_ref` set, or edit `rules.py` if policy itself changes (e.g. maturity buffer).

## Acknowledging ecosystem-shift alerts

An `ecosystem-shift` issue is informational — data already published. Confirm the shift is expected (e.g. upstream added a new sanitizer deny entry that legitimately broke part of the ecosystem). Comment on the issue with your assessment and close it. If the shift was a pipeline bug, treat it as Class A: fix, re-run with `full_rescan: true`, and close.

## Blocklisting spam repos via `data/sources.json`

`data/sources.json` supports `blocklist` and `allowlist` arrays of `owner/repo`. To suppress a spam/fork/non-theme that polluted the topic search:

```json
{
  "blocklist": ["spam-owner/dotfiles-fork"],
  "allowlist": ["real-owner/real-theme-without-topic"]
}
```

Commit the change; the next weekly run (or manual dispatch) will exclude blocklisted repos during `discover`. No code change needed. Blocklisted repos still count as `discovered` in the previous run; after the next run they disappear from `themes.json`.

## Local dev quickstart

```bash
# venv + analyzer
python -m venv .venv && source .venv/bin/activate
pip install -e ./analyzer[dev]

# lint/type not enforced — run tests
python -m pytest analyzer/tests -q          # offline, 90 tests
python -m pytest analyzer/tests -q -k canary  # if any canary-named tests exist

# offline run over fixtures (no network, uses FakeRenderer)
python -m om4t discover --offline --out work/manifest.json
python -m om4t run --manifest work/manifest.json --workdir work --offline --fake-renderer
cat work/themes.json | jq '.run, .omarchy'

# online dry-run (limit 5, official renderer — needs GH_TOKEN + omarchy clone)
GH_TOKEN=$(gh auth token) python -m om4t resolve-pin | tee work/pin.json
python -m om4t clone-omarchy --pin work/pin.json --dest work/omarchy
python -m om4t discover --out work/manifest.json
python -m om4t run --manifest work/manifest.json --omarchy-dir work/omarchy --workdir work --limit 5

# serve the site locally (after a run has produced work/themes.json)
mkdir -p site/data && cp work/themes.json site/data/themes.json
python -m http.server --directory site 8000
# open http://localhost:8000

# single-theme debug
python -m om4t analyze-dir --fake analyzer/tests/fixtures/themes/native-full | jq .
python -m om4t analyze-dir --omarchy-dir work/omarchy analyzer/tests/fixtures/themes/native-full | jq .compatibility
```

Caches: delete `work/clones`, `work/omarchy`, `work/cache.json` for a full rescan, or pass `--limit` for fast iteration. CI respects the `full_rescan` dispatch input which skips `actions/cache` restore.

## Notification settings

- **Primary** — the `notify` job auto-files/comments an issue with label `pipeline-breakage` (`gh issue list/create/comment` using `${{ github.token }}`). It de-dupes: if an open issue with that label exists, it comments instead of spamming a new one. Every failed run's pin and run link are included.
- **Secondary (built-in)** — GitHub's own Actions notifications: **Settings → Notifications → Actions** must be enabled for the account that owns the workflow to receive email/web notifications on failed runs. No code needed — just document that it is on.
- **Optional external webhook** — hook point is the `notify` job; add a secret (e.g. `NTFY_URL`/`DISCORD_WEBHOOK`) and a `curl` step there if you want off-GitHub alerts (off by default in v1).
- **Artifacts for post-mortems** — every run uploads `work/themes.json` + `work/logs/**` even on failure; `work/pin.json` is also uploaded as artifact `pin` for the notify job to read.

## Useful links

- Workflow files: `.github/workflows/build.yml` (weekly + deploy), `.github/workflows/test.yml` (PR CI)
- Analyzer CLI: `python -m om4t --help` (subcommands `resolve-pin`, `clone-omarchy`, `canary`, `discover`, `run`, `analyze-dir`)
- Data schema: `implementation-plan.md` §14
- Spec: `spec.md`
