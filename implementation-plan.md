# om4Themes — Implementation Plan

> Companion to [spec.md](./spec.md). Checklist: [implementation-checklist.md](./implementation-checklist.md).
> Status: draft v2 — 2026-09-02 (floating-pin + canary + alerting revision). Facts about Omarchy 4 ("Quattro") verified against `omacom/omarchy` on 2026-09-02.

## 1. Product summary

om4Themes is a static GitHub Pages site — a *theme compatibility observatory* — that grades every discoverable Omarchy theme against Omarchy 4 (Quattro) on a weekly schedule via a GitHub Actions workflow. Each theme card shows its preview, a link to the repo, a compatibility level (0–4 per the spec rubric), feature badges, and the per-check reasoning behind its grade.

**Pipeline:** discover (GitHub topic + registries) → shallow-clone → static analysis → headless verification with the official Omarchy renderer (latest stable release, resolved at runtime) → grade → JSON database → static site → GitHub Pages.

**Non-goals (v1):** visual VM verification, user submissions/auth, trend-history charts, custom domain (add later), and recreating omarchythemes.com's gallery-only experience — our differentiator is the automated grading plus machine-readable data.

## 2. Verified corrections to the spec

Research against primary sources (2026-09-02) confirmed the spec is directionally right, with these corrections:

| # | Spec claim | Verified reality | Impact on implementation |
|---|---|---|---|
| 1 | Links split between `omacom/omarchy` and `basecamp/omarchy`, with `utm_source=chatgpt.com` artifacts | Canonical repo is **`omacom/omarchy`**; current branch `quattro`; `utm_*` params are chat-client artifacts | Pin everything to `omacom/omarchy` |
| 2 | "Omarchy 4.0.1 / v4.0.0 released Aug 14 2026 at commit f002044" | v4.0.0 "The Quattro Release" (14 Aug 2026) is real; **latest is v4.0.2 (31 Aug 2026, security fixes)** | CI resolves the **latest stable tag at runtime** (§9.1); v4.0.2 was current at plan time |
| 3 | Palette key list (24 keys) | Canonical `colors.toml` also includes **`orange` and `brown`**; legacy aliases are formally supported by `bin/omarchy-theme-color` (`bg`/`fg` short forms, `color0`–`color15`, `purple`→`magenta`, `theme_type`→`mode`, `cursor`→`bright_foreground`, `orange` falls back to `yellow`, `brown` auto-derived) | Do NOT re-implement palette resolution — invoke `omarchy-theme-color` as the oracle |
| 4 | `shell.toml` / `shell.<section>.toml` | Shipped themes carry **`shell.lock.toml`** (generated lock tokens); an author-supplied `shell.toml` override is merged at render time | Feature detection should match `shell*.toml` |
| 5 | Sanitization "strips .lua, terminal configs, vscode.json" | Confirmed deny list in `bin/omarchy-theme-set` (`stage_installed_theme`): **all `*.lua`** (hyprland.lua, gum_env.lua, neovim.lua), **terminal configs** (alacritty.toml, foot.ini, ghostty.conf, kitty.conf), **vscode.json**; symlinks never followed; everything else kept | Grading must evaluate the theme **as installed**, not as authored |
| 6 | "official Omarchy code" renderer | Concrete headless entrypoint: **`bin/omarchy-theme-set-templates`** with `OMARCHY_PATH` + a throwaway `HOME`; Omarchy's own `test/cli` defines "renders cleanly" as **no `{{ … }}` placeholders remaining** | Levels 2+ are CI-feasible; copy `test/cli` as the blueprint |
| 7 | Legacy conversion from `alacritty.toml` | Real script: **`bin/omarchy-theme-colors-from-alacritty`** (parses `[colors.*]` into a fresh colors.toml; invoked during staging when colors.toml is missing) | Level 1 is exactly "this script succeeds + render passes" |
| 8 | "the official source of themes" | Three real sources: the **omarchy.org/themes registry** (`omacom/omarchy-site`, PR-based), the **22 built-in themes** in `themes/`, and the **GitHub topic `omarchy-theme`** (~267 public repos, verified); `aorumbayev/awesome-omarchy` as a curated secondary | Discovery = topic search + registry + built-ins + curated seeds |
| 9 | "recreating omarchythemes.com" | It exists (251 themes, filterable gallery, **no compatibility grading**) | Our differentiator: grades, per-check reasons, badges, JSON output |
| 10 | Old state paths | Quattro moved `~/.config/omarchy/current` → `~/.local/state/omarchy/current` (migrations ship in the repo); Quattro replaced Waybar/Walker/Mako/SwayOSD/hyprlock/hypridle/swaybg with Quickshell and Hyprland `.conf` → Lua | Static analyzer greps for exactly these markers |

## 3. Architecture

```
┌──────────────────────── GitHub Actions (weekly + manual) ────────────────────────┐
│                                                                                  │
│  discover ──► fetch ──► static-analyze ──► headless-verify ──► grade ──► JSON     │
│  (gh api     (shallow   (Python: files,   (latest omacom/     (decision  │       │
│   search +    clones +   colors.toml,     omarchy stable:     tree +     │       │
│   seeds)      cache)     legacy markers,  stage+sanitize,     reasons)   │       │
│                          feature probes)   render, assert)               ▼       │
│                                          site/ (static HTML/CSS/JS, no build step)│
└──────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
                                    GitHub Pages
```

Components:

1. **`analyzer/` (Python 3.12, stdlib only)** — the heart.
   - `discover.py` — GitHub topic search (`topic:omarchy-theme`), merged with `data/sources.json` seeds (registry themes, awesome-omarchy, built-ins); dedupe; drop archived; emit candidate manifest.
   - `fetch.py` — shallow-clone (`--depth 1`) each candidate; record commit SHA; `actions/cache`-friendly layout under one workdir.
   - `static.py` — file detection, TOML parse/validate (via `tomllib` + the `omarchy-theme-color` oracle), legacy-marker grep, feature probes.
   - `verify.py` — stage the theme the way `omarchy-theme-set` does (apply the sanitization deny list), run `omarchy-theme-colors-from-alacritty` if needed, run `omarchy-theme-set-templates` with a fake `$HOME`, assert a clean render.
   - `grade.py` — decision tree (§8) → level + label + ordered check reasons + warnings + badges.
   - `rules.py` — versioned rule constants (marker regexes, key lists, Omarchy pin). Bump `RULES_VERSION` on any rubric change.
   - `build_db.py` — assemble `themes.json` (§14).
2. **`site/`** — `index.html`, `app.js`, `styles.css`. No framework, no build step. Fetches `data/themes.json` at runtime; all filtering client-side.
3. **`.github/workflows/build.yml`** — weekly cron + `workflow_dispatch`; jobs: `analyze` → `deploy-pages` (gated).
4. **`.github/workflows/test.yml`** — PR/CI: pytest + integration check that all 22 built-in Omarchy themes grade ≥ L3.
5. **`tests/fixtures/`** — synthetic theme repos (one per rubric edge case) + the built-in themes fetched from the pinned Omarchy clone as canonical positive fixtures.

## 4. Repo layout

```
om4Themes/
├── spec.md
├── implementation-plan.md
├── implementation-checklist.md
├── README.md
├── .github/workflows/
│   ├── build.yml                     # weekly pipeline + Pages deploy
│   └── test.yml                      # analyzer tests on PR
├── analyzer/
│   ├── pyproject.toml                # dev deps: pytest only; runtime stdlib-only
│   ├── om4t/
│   │   ├── __init__.py
│   │   ├── rules.py                  # RULES_VERSION, markers, key lists, pin strategy
│   │   ├── schema.py                 # dataclasses + JSON validation
│   │   ├── discover.py  fetch.py  static.py  verify.py  grade.py  build_db.py
│   └── tests/
│       ├── test_static.py  test_grade.py  test_verify.py  test_discover.py
│       └── fixtures/themes/…         # synthetic repos (see §11)
├── data/
│   ├── sources.json                  # curated seeds, allow/block lists
│   └── (themes.json generated at build time, not committed in v1)
└── site/
    ├── index.html  app.js  styles.css
    └── data/themes.json              # placed by the workflow into the artifact
```

## 5. Tech choices & rationale

| Decision | Choice | Rationale |
|---|---|---|
| Analyzer language | Python 3.12, stdlib only (`tomllib`, `subprocess`, `urllib`) + `gh` CLI for API calls | No heavy deps; both preinstalled on runners; Omarchy's own scripts are bash and we invoke them as subprocesses (oracle, not re-implementation) |
| Palette resolution / rendering | Call the pinned Omarchy scripts (`omarchy-theme-color`, `omarchy-theme-colors-from-alacritty`, `omarchy-theme-set-templates`) | The spec's own advice: future-proof by using official code; avoids maintaining our private idea of "valid" |
| Site | Vanilla HTML/CSS/JS, no build step | ~270 themes fit one JSON (~1–2 MB); zero supply-chain surface; trivially reviewable |
| Filtering | Client-side over the full `themes.json` | Static hosting; instant filter UX |
| Data publishing | `themes.json` shipped inside the Pages artifact | One atomic deploy unit; no CORS/versioning issues |
| Omarchy version | **Floating pin:** resolve the latest stable release tag at runtime (exclude drafts/prereleases, ≥3-day maturity buffer), overridable via `workflow_dispatch` input `omarchy_ref`; resolved tag + commit SHA recorded per run and per theme | Omarchy is Arch-based and ships fast (v4.0.1/4.0.2 within two weeks; sanitization rules changed post-release) — grades must track what users actually run; auditability is preserved via `tested_against`/`omarchy_commit` |
| Rules versioning | `RULES_VERSION` (CalVer, e.g. `2026.09.0`) stored in every theme result | Spec's "moving target" requirement — never store a bare boolean/level; rules change deliberately, while the Omarchy pin floats automatically (§9.1) |

## 6. Discovery

Sources merged and deduped by `owner/repo`:

1. **Topic search:** `gh api --paginate search/repositories?q=topic:omarchy-theme+is:public` (~267 repos, verified). Secondary: `topic:omarchy` filtered to repos containing `colors.toml` or `alacritty.toml` on the default branch (cheap content probe — prefer sparse-checkout over the code-search API to stay inside search rate limits).
2. **Built-in themes:** `omacom/omarchy/themes/*` at the resolved tag → 22 official themes, marked `official: true`.
3. **Registry:** `omacom/omarchy-site`'s themes page (figure blocks reference source repos) → community themes with an official listing; marked `registry: true`.
4. **Seeds:** `data/sources.json` — hand-curated URLs (awesome-omarchy entries, known theme authors) + a **blocklist** (spam/forks) + an **allowlist** (force-include non-topic repos).

Rules: exclude archived/disabled repos; exclude forks of already-included repos unless allowlisted; cap v1 at ~400 repos per run.

## 7. Fetch & rate-limit strategy

- **Git clones do not count against REST API limits** — prefer `git clone --depth 1 --single-branch` for all content inspection. ~270 shallow clones ≈ a few minutes.
- REST budget: `GITHUB_TOKEN` = 1,000 requests/hour per repository; Search API ≈ 30 requests/min authenticated. Discovery needs only a handful of paginated search calls; per-repo REST calls are avoided entirely.
- **Caching:** `actions/cache` keyed on `run_week + manifest_hash`; per-repo entries validated against last-known SHA stored in a cache manifest — skip re-analysis when the SHA is unchanged **and** `RULES_VERSION`/resolved Omarchy pin are unchanged (carry the previous grade record forward, preserving its original `analyzed_at`). When a new Omarchy release is resolved, every theme is *deliberately* re-verified — that is the point of the observatory, and a full pass over ~270 shallow-cloned themes is minutes, not hours.
- Backoff: honor `Retry-After` on 403/429; exponential retry (max 3). Re-verify Search API *secondary* rate limits during implementation (§13).
- If budget tightens later: move to a GitHub App installation token (5k+/hr) — out of scope for v1.

## 8. Grading decision tree (rules v2026.09.0)

Inputs (all machine-computed):

- `colors_toml_valid` — root `colors.toml` parses; `mode` resolves (directly or via `theme_type`); core keys resolve via `omarchy-theme-color --all`.
- `alacritty_convertible` — no valid colors.toml, but `omarchy-theme-colors-from-alacritty` produces one without error.
- `render_clean` — after staging + sanitization (§9), `omarchy-theme-set-templates` exits 0 and no `{{…}}` remains in any rendered output (assertion copied from Omarchy's `test/cli`).
- `legacy_hard` — the theme *requires* removed components to express itself: README/install scripts reference Waybar/Walker/Mako/SwayOSD/hyprlock config as the theme's implementation, require a `hyprland.conf` override, or require `~/.config/omarchy/current` (old state path).
- `legacy_soft` — stale Omarchy 3 files present but the colors.toml works standalone → **warning only, never auto-fail** (explicit spec rule: "a repo may simply contain stale junk").
- `modern_conventions` — customization beyond colors uses current mechanisms (`shell*.toml`, semantic tokens); the theme's appearance does not depend on files the sanitizer strips (`*.lua`, terminal configs, `vscode.json`).
- `install_sim_clean` — the full pipeline (stage → sanitize → synthesize-if-needed → render) completes with no *appearance-affecting* file stripped.

Tree (first match wins):

```
L0  if not (colors_toml_valid or alacritty_convertible)   # nothing usable at all
L0  if legacy_hard and not colors_toml_valid              # fundamentally Om3-dependent
L0  if colors_toml_valid and not render_clean             # broken under the official renderer
L1  if alacritty_convertible and render_clean             # legacy layer only; ceiling = 1
L2  if colors_toml_valid and render_clean                 # native palette renders
L3  if L2 and not legacy_hard and no blocking legacy_soft # + nothing required is legacy
        and modern_conventions                            # + designed around Quattro
L4  if L3 and install_sim_clean against OMARCHY_TAG       # verified end-to-end by this CI
```

Every grade stores an **ordered reason list** (the spec's "why it got its rating"), e.g. `Native colors.toml ✓ · Quattro renderer ✓ · No legacy Waybar dependency ✓ · No old state-path references ✓ · Custom Quickshell styling ✓`.

**Badges (orthogonal to level):** `transparency` (fill/border alpha keys, `rgba(`), `rounded-ui` (corner-radius tokens), `custom-borders` (border width/alpha tokens), `gradient-borders`, `light-mode` (`mode = "light"`), `custom-shell` (`shell.toml` override), `unlock-theme` (`unlock.png`/`preview-unlock.png`), `icons` (`icons.theme`), `wallpapers` (`backgrounds/` count), `preview` (`preview.png`). Plus a `headless-verified` badge for every L4 (all CI-verified themes get it in v1; visual verification deferred).

## 9. Headless verification protocol

### 9.1 Release resolution (floating pin)

At the start of each run:

1. Resolve the target Omarchy version: `gh api repos/omacom/omarchy/releases/latest` → tag + commit SHA. Exclude drafts/prereleases; ignore a tag younger than ~3 days (maturity buffer — v4.0.1/4.0.2 were same-week security fixes, so brand-new tags are still settling). Never track branch HEAD: tags are what users actually run; the dev branch can be mid-flux.
2. Allow override via the `workflow_dispatch` input `omarchy_ref` — force-test a future release early, or hold back on a suspect one.
3. Record the resolved tag/SHA + `pin_source: "latest" | "override"` in the run metadata and every theme result (`tested_against`, `omarchy_commit`).

### 9.2 Canary gate (before any community theme is graded)

1. Run the full stage → sanitize → render pipeline against all 22 built-in themes at the resolved pin.
2. Every built-in must render clean and grade ≥ L3 — they ship *with* that release, so any other result means **our pipeline broke, not the ecosystem**.
3. Canary failure = **hard-fail the analyze job** (Class A, §13.1): no grades published, Pages keeps the last-good site, alert fired (§13.2). We never "degrade gracefully" by publishing garbage.

### 9.3 Per-theme protocol

Per theme, in a throwaway directory:

1. `git clone --depth 1 --branch <resolved-tag> omacom/omarchy` once per run → `$OM` (cached).
2. Stage the candidate into `$STAGE/theme` the way `omarchy-theme-set`'s `stage_installed_theme` does: copy regular files only (never follow symlinks), **drop the deny list** (`*.lua`, `alacritty.toml`, `foot.ini`, `ghostty.conf`, `kitty.conf`, `vscode.json`), and record what was dropped.
3. If the staged dir has no `colors.toml` but has `alacritty.toml`: run `$OM/bin/omarchy-theme-colors-from-alacritty` (mirrors `stage_installed_colors_from_alacritty`).
4. Run `OMARCHY_PATH=$OM HOME=$STAGE $OM/bin/omarchy-theme-set-templates`; capture exit code + output.
5. Assert: exit 0; `rg -q '\{\{[^}]+\}\}'` matches nothing in rendered output; `omarchy-theme-color --all` resolves; optionally `omarchy-theme-osc` emits 16 OSC sequences.
6. Record `tested_against: <resolved-tag>`, `omarchy_commit`, `analyzed_at`.

**To confirm during implementation (Phase 4):** read `bin/omarchy-theme-set-templates` source to pin down its exact env-var/PATH contract, and locate Omarchy's theme-staging test under `test/` (research saw it referenced but couldn't fetch the exact path). Both are checklist items.

## 10. Feature & legacy detection (static)

Versioned in `rules.py` as declarative tables (path globs + regexes + hard/soft classification), not code paths — so rule updates are diffable and version-bumpable:

- **Legacy markers (hard):** `waybar/**`, `mako*`/`walker*`/`swayosd*`/`hyprlock*` configs, `hyprland.conf`, regex `~/\.config/omarchy/current`, pre-Quattro `~/.local/share/omarchy` assumptions — *when referenced by README/install scripts as required*.
- **Legacy markers (soft → warning):** the same paths present but unreferenced (stale junk).
- **Native markers:** `colors.toml`, `shell*.toml`, `preview.png`, `unlock.png`, `backgrounds/`, `icons.theme`.
- **Badge probes:** `*-fill-alpha`, `*-border-alpha`, `corner`-family tokens, border-gradient definitions, `rgba\(`, `mode\s*=\s*"light"`.

## 11. Testing strategy

- **Unit (pytest):** TOML validation, each marker regex, decision-tree edge cases over synthetic fixtures: `broken-toml`, `no-palette`, `alacritty-only`, `native-minimal`, `native-full`, `waybar-required`, `stale-waybar-junk`, `lua-dependent`.
- **Golden fixtures:** all 22 built-in Omarchy themes (at the resolved pin) must grade **≥ L3** and render clean — the spec's "canonical positive fixtures" and the production canary (§9.2).
- **Snapshot:** `themes.json` for the fixture set; any diff requires explicit review → catches accidental rule regressions.
- **Integration (CI job):** full pipeline against fixtures; network limited to the pinned clones.
- **Dry-run mode:** `--limit N --offline` for local development.

## 12. Website spec

- **Layout:** header (title, counts, last-built stamp, rules/Omarchy versions), filter bar, card grid.
- **Cards:** preview image (theme's `preview.png` via `raw.githubusercontent.com` at the recorded SHA, lazy-loaded, alt text), repo name + creator, star count, level chip (color + label + emoji from the spec — never color alone), badge row, GitHub link.
- **Expandable "why" panel:** ordered check reasons from `checks[]` + warnings.
- **Filters (AND-combined, URL-hash-encoded for shareable links):** compatibility level (multi-select 0–4), mode (dark/light), official (built-in/registry), creator (dropdown generated from data), free-text search. Sort: level desc, stars desc.
- **Accessibility:** real form controls, `aria-live` result count, keyboard operable, 4.5:1 contrast, respects `prefers-reduced-motion`.
- **Data:** `site/data/themes.json` fetched at load; graceful empty/error state if missing.

## 13. GitHub Actions workflow design

`build.yml`:

```yaml
on:
  schedule: [{ cron: "0 6 * * 0" }]        # weekly, Sunday 06:00 UTC
  workflow_dispatch:
    inputs:
      full_rescan: { type: boolean, default: false }
      omarchy_ref: { type: string, default: "", description: "Force an Omarchy tag; empty = latest stable" }
permissions: { contents: read, pages: write, id-token: write, issues: write }
jobs:
  analyze:   # ubuntu-latest; checkout; caches (omarchy clone + theme clones + results);
             # resolve latest stable (§9.1) → CANARY GATE (§9.2) → discover → fetch →
             # static → verify → grade; upload themes.json artifact; HARD-FAILS on Class A (§13.1)
  deploy:    # needs: analyze; actions/configure-pages → assemble site/ + data/themes.json
             # → actions/upload-pages-artifact → actions/deploy-pages
  notify:    # needs: analyze; if: failure() → file/comment `pipeline-breakage` issue (§13.2)
```

- **Failure policy:** see §13.1 — pipeline breakage is a *loud hard fail*, never silent degradation; **deploy is gated on analyze success** → GitHub Pages automatically keeps the last-good deployment when a weekly run fails.

### 13.1 Failure classes

- **Class A — pipeline breakage** (canary failure, release-resolution failure, renderer-contract mismatch, discovery/API-auth failure): the analyze job **fails loudly and immediately**. No deploy → Pages keeps the last-good site → alert fires (§13.2). This is the "the Omarchy contract changed and the pipeline needs a manual update" signal; we deliberately do *not* paper over it with partial or degraded data.
- **Class B — ecosystem shift** (canary passes, but community-theme error rate exceeds ~25%, or the level histogram swings materially vs the previous run): the grades are *valid data* — e.g. a new sanitization rule genuinely broke part of the ecosystem — so publish them, and also file an **informational** alert so the shift can be confirmed as expected rather than silently accepted.
- **Per-theme errors** (one repo's broken TOML, a failed clone): isolated into the JSON `error` field; never fail the run.

### 13.2 Alerting

1. **GitHub Actions notifications** — failed workflow runs surface as GitHub notifications to the account that owns the workflow (Settings → Notifications → Actions); zero code, documented in the runbook.
2. **Auto-filed issue (primary channel)** — the `notify` job runs on `failure()` and files an issue via `gh issue create` with label `pipeline-breakage`, containing: resolved Omarchy tag/SHA + `pin_source`, which canary/systemic check failed, the first failing built-in theme, a renderer log excerpt, and a run link. **Deduplicated:** if an open `pipeline-breakage` issue exists, comment on it instead of creating a new one (a multi-week breakage must not spam weekly issues). Class B alerts use the same mechanism with an `ecosystem-shift` label and "informational — data published" wording.
3. **Optional external webhook** (ntfy.email / Discord / Matrix via a repo secret) for notification outside GitHub — off by default in v1; the `notify` job is the hook point.
- Every run uploads `themes.json` + per-theme logs as a workflow artifact for post-mortems, even on failure.
- `test.yml` on PR: pytest + the built-in-themes golden check.
- **Re-verify at implementation time:** current major versions of `actions/configure-pages` / `upload-pages-artifact` / `deploy-pages`, and Search API secondary-rate-limit docs (research flagged both as not freshly confirmed).

## 14. Data schema (`themes.json`, schema_version 1)

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-02T06:12:33Z",
  "rules_version": "2026.09.0",
  "omarchy": { "repo": "omacom/omarchy", "pin": "v4.0.2", "pin_source": "latest", "commit": "…" },
  "run": { "discovered": 267, "analyzed": 265, "errors": 2, "skipped_unchanged": 180 },
  "themes": [
    {
      "id": "some-owner/rose-pine-custom",
      "repo_url": "https://github.com/some-owner/rose-pine-custom",
      "creator": "some-owner",
      "description": "…", "stars": 42, "topics": ["omarchy-theme"],
      "default_branch": "main", "commit_sha": "abc1234…",
      "official": false, "registry": true,
      "preview": "https://raw.githubusercontent.com/…/preview.png",
      "mode": "dark",
      "compatibility": {
        "family": "omarchy-4", "level": 3, "label": "quattro-native",
        "tested_against": "v4.0.2", "omarchy_commit": "…",
        "analyzed_at": "2026-09-02T06:12:33Z", "rules_version": "2026.09.0"
      },
      "checks": [
        { "id": "colors_toml_valid", "passed": true, "note": null },
        { "id": "renderer_clean", "passed": true, "note": null },
        { "id": "no_required_legacy", "passed": true, "note": null },
        { "id": "modern_conventions", "passed": true, "note": "shell.toml present" },
        { "id": "install_sim_clean", "passed": false, "note": "neovim.lua dropped by sanitizer" }
      ],
      "badges": ["transparency", "rounded-ui", "wallpapers"],
      "palette": { "missing_canonical": [], "resolved_via_alias": ["cursor"] },
      "warnings": ["stale waybar/style.css present but unreferenced"],
      "error": null
    }
  ]
}
```

Note the spec's versioning requirement: a level is never stored bare — always with `family`, `tested_against`, `omarchy_commit`, `rules_version`, `analyzed_at`.

## 15. Phased delivery

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Repo scaffold, Pages enabled, workflow skeleton deploying a placeholder site | Site live on `*.github.io` via manual dispatch |
| 1 | `schema.py` + `rules.py` v2026.09.0 + golden example JSON reviewed | Schema + rubric frozen for v1 |
| 2 | Discovery + fetch + caching | Weekly run produces the full candidate manifest with SHAs in <10 min |
| 3 | Static analyzer + unit tests | pytest green across all synthetic fixtures |
| 4 | Headless verification against the resolved Omarchy release | Floating pin resolves correctly with override; canary gate passes on all 22 built-ins and hard-fails on a simulated break; legacy fixture converts; broken fixture fails cleanly |
| 5 | Grader + full `themes.json` | Every discovered theme has level + reasons + badges; level distribution sanity-reviewed |
| 6 | Site | Filters, cards, why-panel, a11y pass; deployed from the weekly workflow |
| 7 | Hardening + automation | Cron live; backoff + error isolation proven; failure drill passes (broken canary → red run + issue filed + site untouched); runbook written |

## 16. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Sanitization asymmetry — themes look fine to their author but lose appearance when installed | Grade **as installed** (§9); surface stripped files as check notes + warnings |
| Omarchy 4 keeps evolving (staging/security changes, new template set) | Floating pin re-verifies the whole ecosystem on every new release (§9.1); `RULES_VERSION` bumps stay deliberate; golden fixtures re-run on every pin change |
| Rate limits (1k/hr REST; search 30/min; secondary limits) | Clone-based content inspection; paginated search once per run; cache + SHA-skip; backoff |
| Topic repos include non-themes (rice dotfiles, waybar packs) | Content probe (`colors.toml`/`alacritty.toml` presence) + blocklist; they naturally grade L0/L1 anyway, which is itself data |
| Renderer contract differs from research findings | Phase 4 task: read `omarchy-theme-set-templates` source and confirm the env contract before relying on it |
| New Omarchy release breaks the pipeline | Canary gate catches it before any grade ships (§9.2) → Class A hard fail + auto-filed issue (§13.2); Pages keeps last-good; runbook drives the fix |
| Weekly full-scan runtime grows with the topic | SHA-based skip means steady-state runs only re-analyze changed repos; matrix chunking deferred until needed |
| Bad deploy bricks the site | Deploy gated on analyze success; Pages keeps last-good; artifact rollback via re-run |

## 17. Deferred / open questions

- Visual verification (disposable VM boots, sets theme, screenshots shell) → future badge tier, not a v1 level.
- Committing `themes.json` history to a data branch for trend charts.
- Custom domain (the spec's `omarchythemes.com` is taken by the existing gallery — pick our own).
- Whether to include `topic:omarchy` repos lacking `topic:omarchy-theme`.
- Per-theme "re-grade on repo push" webhook trigger (vs weekly only).
- A documented JSON/API + embeddable grade badges for theme READMEs (natural community-growth feature; strong v2 candidate).
