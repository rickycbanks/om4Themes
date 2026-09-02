# om4Themes — Implementation Checklist

> Companion to [implementation-plan.md](./implementation-plan.md). Section references (§) point into the plan.

## Phase 0 — Scaffold
- [ ] `git init`, `.gitignore` (`work/`, `__pycache__/`, `.venv/`), README.md, LICENSE (pick)
- [ ] Create `analyzer/` package skeleton, `site/` placeholder, `data/sources.json` stub
- [ ] Enable GitHub Pages (deployment source: Actions) in repo settings
- [ ] `.github/workflows/build.yml` skeleton: `workflow_dispatch` → deploy placeholder site
- [ ] Verify the placeholder is live on `*.github.io`
- [ ] `.github/workflows/test.yml` skeleton running pytest (empty suite green)

## Phase 1 — Schema & rules
- [ ] `schema.py`: dataclasses per plan §14 + JSON serialization/validation
- [ ] `rules.py`: `RULES_VERSION = "2026.09.0"`, `OMARCHY_REPO = "omacom/omarchy"`, floating-pin config (`PIN_MATURITY_DAYS = 3`, empty default override)
- [ ] Canonical color-key table (incl. `orange`, `brown`) + legacy-alias table (reference only; the oracle is `omarchy-theme-color`)
- [ ] Legacy marker table, hard vs soft (plan §10)
- [ ] Badge probe table (plan §10)
- [ ] Review one golden `themes.json` record end-to-end; freeze v1 schema

## Phase 2 — Discovery & fetch
- [ ] `discover.py`: topic search via `gh api --paginate` + built-in themes + registry scrape + `sources.json` seeds; dedupe; archived excluded; fork policy
- [ ] `fetch.py`: shallow clones into a cache-friendly root; SHA recording; sparse-checkout content probe
- [ ] `actions/cache` wiring (key = week + manifest hash; restore/save steps for clones + previous results)
- [ ] Skip logic: unchanged SHA AND unchanged `RULES_VERSION`/resolved pin → carry previous grade (new Omarchy release ⇒ deliberate full re-verify)
- [ ] 403/429 + `Retry-After` backoff helper; unit-tested with a mock transport
- [ ] One real run against GitHub: manifest of ≥250 repos in <10 min

## Phase 3 — Static analyzer
- [ ] `colors.toml` parse + validate (`tomllib`; mode resolution; core keys via `omarchy-theme-color --all`)
- [ ] Legacy marker grep (hard vs soft; referenced-by-README/install-script heuristic)
- [ ] Feature probes → badge set
- [ ] Wire `omarchy-theme-colors-from-alacritty` detection/synthesis
- [ ] Synthetic fixtures: `broken-toml`, `no-palette`, `alacritty-only`, `native-minimal`, `native-full`, `waybar-required`, `stale-waybar-junk`, `lua-dependent`
- [ ] pytest green; decision-tree unit tests over all fixtures

## Phase 4 — Headless verification
- [ ] Release resolution (§9.1): `gh api …/releases/latest`, drafts/prereleases excluded, ~3-day maturity buffer, `omarchy_ref` dispatch override; record tag + SHA + `pin_source`
- [ ] Canary gate (§9.2): all 22 built-ins must render clean and grade ≥ L3 at the resolved pin, else hard-fail before any community theme is graded
- [ ] Read `bin/omarchy-theme-set-templates` source; confirm exact env-var/PATH contract (plan §9 open item)
- [ ] Locate Omarchy's theme-staging test under `test/`; copy its assertions
- [ ] `verify.py`: stage → sanitize (deny list) → synthesize-if-needed → render → assert no `{{ }}` remains
- [ ] Capture per-theme stripped-file list into checks/warnings
- [ ] Integration test: all 22 built-in themes render clean (golden check in `test.yml`)
- [ ] Legacy fixture converts → L1; broken fixture fails cleanly → L0 with reasons

## Phase 5 — Grading
- [ ] `grade.py`: decision tree exactly per plan §8; ordered reasons; warnings never demote
- [ ] `build_db.py` → `themes.json` (schema §14); per-theme error isolation; run summary counts
- [ ] Full dry run over real data; sanity-review the level distribution (expect a large L0/L1 tail)
- [ ] Distribution-shift detector: level histogram + error-rate vs previous run → Class B alert threshold (plan §13.1)
- [ ] Manually grade 10 sampled themes; reconcile against CI results

## Phase 6 — Site
- [ ] `index.html` + `styles.css`: card grid, level chip (emoji + label + color), badge row, why-panel
- [ ] `app.js`: fetch `themes.json`; filters (level, mode, official, creator, text) AND-combined; URL-hash state; sorting
- [ ] Preview images from `raw.githubusercontent.com` at the recorded SHA; lazy-load; placeholder fallback
- [ ] Accessibility pass: keyboard, `aria-live` count, contrast, color-not-alone
- [ ] Empty/error state when `themes.json` is missing
- [ ] Deploy assembles `site/` + `data/themes.json` into the Pages artifact via `build.yml`

## Phase 7 — Hardening & automation
- [ ] Weekly cron `0 6 * * 0` + `workflow_dispatch` inputs `full_rescan`, `omarchy_ref`
- [ ] Gated deploy (analyze success only); last-good preserved on failure; log/JSON artifact bundle
- [ ] Failure classes wired (§13.1): Class A hard-fails with no deploy; Class B publishes + informational alert; per-theme errors isolated
- [ ] Auto-issue (§13.2): `notify` job files/comments `pipeline-breakage` issue on failure (`issues: write`); dedupe open issues
- [ ] Confirm GitHub Actions notification routing is on for the account (Settings → Notifications → Actions); document in runbook
- [ ] Failure drill: break the canary on a branch → verify red run + issue filed + live site untouched
- [ ] Re-verify Pages action versions + Search API secondary rate limits (plan §13)
- [ ] Runbook: recover from a pipeline breakage (read the `pipeline-breakage` issue → fix analyzer → re-run with `omarchy_ref` → close issue), bump `RULES_VERSION`, confirm/ack an `ecosystem-shift` alert, blocklist spam repos
- [ ] Two consecutive clean weekly runs observed
- [ ] v1 ship: README screenshots, announce to the Omarchy community

## Deferred backlog
- [ ] Visual-verification VM badge tier
- [ ] Grade history / trend charts (committed data branch)
- [ ] Embeddable README grade badges + public JSON API docs
- [ ] Webhook re-grade on repo push
- [ ] Custom domain
- [ ] External alert webhook (ntfy/Discord/Matrix) — hook point already specified in plan §13.2
