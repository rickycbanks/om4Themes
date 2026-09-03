"use strict";

// om4Themes — vanilla filterable observatory
// Fetches data/themes.json, renders cards + filters + hash state.

const LEVEL_META = {
  0: { label: "incompatible", emoji: "❌", color: "#e5484d" },
  1: { label: "legacy-compatible", emoji: "🟠", color: "#f76b15" },
  2: { label: "quattro-compatible", emoji: "🟡", color: "#f5d90a" },
  3: { label: "quattro-native", emoji: "🟢", color: "#46a758" },
  4: { label: "quattro-verified", emoji: "💚", color: "#3ecf8e" },
};

const BADGE_LABELS = {
  "transparency": "Transparency",
  "rounded-ui": "Rounded UI",
  "custom-borders": "Custom Borders",
  "gradient-borders": "Gradient Borders",
  "light-mode": "Light Mode",
  "custom-shell": "Custom Shell",
  "unlock-theme": "Unlock Theme",
  "icons": "Icons",
  "wallpapers": "Wallpapers",
  "preview": "Preview",
  "headless-verified": "Headless Verified",
};

function humanizeBadge(id) {
  if (!id) return "";
  // Handle wallpapers count form like "wallpapers:3" or "wallpapers (3)"
  const m = id.match(/^wallpapers[:\s]*\(?(\d+)\)?$/i);
  if (m) return `${m[1]} Wallpapers`;
  // Also if badge id is wallpapers and note contains count we handle outside; here just id
  if (BADGE_LABELS[id]) return BADGE_LABELS[id];
  // fallback: replace dashes/underscores, Title Case
  return id.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeBadgeWithNote(badgeId, note) {
  if (badgeId === "wallpapers" && note) {
    const n = note.match(/(\d+)\s*wallpapers?|\bbackgrounds\/\D*(\d+)/i);
    if (n) {
      const count = n[1] || n[2];
      if (count) return `${count} Wallpapers`;
    }
    // Try count in badgeId itself if note not helpful
    if (/^\d+$/.test(note.trim())) return `${note.trim()} Wallpapers`;
  }
  return humanizeBadge(badgeId);
}

// Global state
let allThemes = [];
let dbMeta = null;

const els = {};

// Helpers
function repoShortName(id) {
  if (!id) return "Unknown";
  const parts = id.split("/");
  return parts[parts.length - 1];
}

function initialsFromId(id) {
  const name = repoShortName(id);
  // Take first two alphanumeric chars
  const cleaned = name.replace(/[^a-z0-9]/gi, "").toUpperCase();
  if (cleaned.length >= 2) return cleaned.slice(0, 2);
  if (cleaned.length === 1) return cleaned + "•";
  return "TH";
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Header stats
function renderHeader(db) {
  const total = db.themes ? db.themes.length : 0;
  const gen = db.generated_at || "";
  const rules = db.rules_version || "—";
  const pin = (db.omarchy && db.omarchy.pin) || "—";
  const pinSource = (db.omarchy && db.omarchy.pin_source) || "";
  const commit = (db.omarchy && db.omarchy.commit) || "";
  document.getElementById("stat-total").textContent = String(total);
  document.getElementById("stat-generated").textContent = gen ? formatDate(gen) : "—";
  document.getElementById("stat-generated").title = gen || "";
  document.getElementById("stat-rules").textContent = rules;
  document.getElementById("stat-pin").textContent = pin;
  document.getElementById("stat-pin-source").textContent = pinSource ? `(${pinSource})` : "";
  if (commit && commit !== "unknown") {
    const wrap = document.getElementById("stat-commit");
    wrap.style.display = "";
    document.getElementById("stat-commit-sha").textContent = commit.slice(0, 7);
    document.getElementById("stat-commit-sha").title = commit;
  }
}

// Card rendering
function createCard(theme) {
  const level = theme.compatibility ? theme.compatibility.level : 0;
  const meta = LEVEL_META[level] || LEVEL_META[0];
  const name = repoShortName(theme.id);
  const creator = theme.creator || (theme.id ? theme.id.split("/")[0] : "unknown");
  const stars = typeof theme.stars === "number" ? theme.stars : 0;
  const desc = theme.description || "";
  const preview = theme.preview || null;
  const badges = Array.isArray(theme.badges) ? theme.badges : [];
  const checks = Array.isArray(theme.checks) ? theme.checks : [];
  const warnings = Array.isArray(theme.warnings) ? theme.warnings : [];
  const hasError = Boolean(theme.error);
  const analyzedAt = theme.compatibility ? theme.compatibility.analyzed_at : null;

  const article = document.createElement("article");
  article.className = "card";
  article.setAttribute("role", "listitem");
  article.dataset.level = String(level);
  article.dataset.creator = creator;
  article.dataset.mode = theme.mode || "dark";
  article.dataset.official = theme.official ? "official" : "community";

  // Preview
  const previewWrap = document.createElement("div");
  previewWrap.className = "card-preview";
  if (preview) {
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = `Preview of ${name} theme`;
    img.src = preview;
    img.onerror = () => {
      // replace with placeholder
      img.remove();
      const ph = document.createElement("div");
      ph.className = "preview-placeholder";
      ph.setAttribute("aria-label", `No preview for ${name}`);
      ph.textContent = initialsFromId(theme.id);
      previewWrap.appendChild(ph);
    };
    previewWrap.appendChild(img);
  } else {
    const ph = document.createElement("div");
    ph.className = "preview-placeholder";
    ph.setAttribute("aria-label", `No preview for ${name}`);
    ph.textContent = initialsFromId(theme.id);
    previewWrap.appendChild(ph);
  }
  article.appendChild(previewWrap);

  const body = document.createElement("div");
  body.className = "card-body";

  // Title
  const title = document.createElement("div");
  title.className = "card-title";
  const nameEl = document.createElement("div");
  nameEl.className = "repo-name";
  nameEl.textContent = name;
  nameEl.title = theme.id || name;
  const creatorEl = document.createElement("div");
  creatorEl.className = "creator";
  creatorEl.textContent = `by ${creator}`;
  title.appendChild(nameEl);
  title.appendChild(creatorEl);
  if (desc) {
    const descEl = document.createElement("div");
    descEl.className = "creator";
    descEl.style.color = "var(--muted)";
    descEl.style.fontSize = "0.82rem";
    descEl.style.marginTop = "0.15rem";
    descEl.textContent = desc;
    title.appendChild(descEl);
  }
  body.appendChild(title);

  // Meta row: level chip + stars
  const metaRow = document.createElement("div");
  metaRow.className = "card-meta";

  if (hasError) {
    const errChip = document.createElement("span");
    errChip.className = "error-chip";
    errChip.textContent = "analysis failed";
    errChip.title = theme.error || "analysis failed";
    metaRow.appendChild(errChip);
  }
  const chip = document.createElement("span");
  chip.className = `level-chip level-${level}`;
  chip.title = `Level ${level}: ${meta.label}`;
  // Emoji + text always visible, never color alone
  chip.textContent = `${meta.emoji} ${meta.label}`;
  metaRow.appendChild(chip);

  const starEl = document.createElement("span");
  starEl.className = "stars";
  starEl.textContent = `★ ${stars}`;
  starEl.setAttribute("aria-label", `${stars} stars`);
  metaRow.appendChild(starEl);

  // Mode indicator inline
  const modeEl = document.createElement("span");
  modeEl.className = "stars";
  modeEl.textContent = theme.mode === "light" ? "☀ light" : "🌙 dark";
  modeEl.title = `Mode: ${theme.mode || "dark"}`;
  metaRow.appendChild(modeEl);

  body.appendChild(metaRow);

  // Badges
  if (badges.length) {
    const badgeRow = document.createElement("div");
    badgeRow.className = "badge-row";
    // If multiple badges, humanize; special wallpapers handling
    badges.forEach((bid) => {
      const span = document.createElement("span");
      span.className = "badge";
      // Try to find wallpapers count in checks/warnings notes
      let label = humanizeBadge(bid);
      if (bid === "wallpapers") {
        // Search checks for wallpapers note count
        const note = checks.map((c) => c.note || "").join(" ") + " " + warnings.join(" ");
        const countMatch = note.match(/(\d+)\s*(wallpapers?|backgrounds)/i);
        if (countMatch) label = `${countMatch[1]} Wallpapers`;
        // Also fallback to bid parsing
        if (label === "Wallpapers" && bid.includes(":")) label = humanizeBadge(bid);
      }
      span.textContent = label;
      badgeRow.appendChild(span);
    });
    body.appendChild(badgeRow);
  }

  // Actions: GitHub link
  const actions = document.createElement("div");
  actions.className = "card-actions";
  const link = document.createElement("a");
  link.className = "github-link";
  link.href = theme.repo_url || `https://github.com/${theme.id}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "GitHub →";
  link.setAttribute("aria-label", `Open ${theme.id} on GitHub`);
  actions.appendChild(link);
  // analyzed date hint
  if (analyzedAt) {
    const small = document.createElement("span");
    small.className = "stars";
    small.style.marginLeft = "auto";
    small.textContent = formatDate(analyzedAt);
    small.title = analyzedAt;
    actions.appendChild(small);
  }
  body.appendChild(actions);

  // Details: Why this rating
  const details = document.createElement("details");
  details.className = "why";
  const summary = document.createElement("summary");
  summary.textContent = "Why this rating";
  details.appendChild(summary);
  const content = document.createElement("div");
  content.className = "why-content";

  if (checks.length) {
    const ul = document.createElement("ul");
    ul.className = "check-list";
    checks.forEach((c) => {
      const li = document.createElement("li");
      const icon = document.createElement("span");
      icon.className = "check-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = c.passed ? "✓" : "✗";
      const text = document.createElement("span");
      const idSpan = document.createElement("strong");
      idSpan.textContent = c.id.replace(/_/g, " ") + " ";
      idSpan.style.fontWeight = "600";
      text.appendChild(idSpan);
      const status = document.createElement("span");
      status.textContent = c.passed ? "passed" : "failed";
      status.style.fontWeight = c.passed ? "400" : "700";
      status.style.color = c.passed ? "var(--muted)" : "#e5484d";
      // aria: include passed/failed text for screen readers
      const sr = document.createElement("span");
      sr.className = "sr-only";
      sr.textContent = c.passed ? " passed" : " failed";
      text.appendChild(status);
      text.appendChild(sr);
      if (c.note) {
        const note = document.createElement("span");
        note.className = "check-note";
        note.textContent = ` — ${c.note}`;
        text.appendChild(note);
      }
      li.appendChild(icon);
      li.appendChild(text);
      ul.appendChild(li);
    });
    content.appendChild(ul);
  } else {
    const p = document.createElement("p");
    p.textContent = "No check details available.";
    p.style.color = "var(--muted)";
    content.appendChild(p);
  }

  if (warnings.length) {
    const w = document.createElement("div");
    w.className = "warnings";
    const strong = document.createElement("strong");
    strong.textContent = "Warnings:";
    w.appendChild(strong);
    const ul = document.createElement("ul");
    warnings.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    });
    w.appendChild(ul);
    content.appendChild(w);
  }

  if (hasError) {
    const e = document.createElement("div");
    e.className = "warnings";
    e.style.borderLeftColor = "#e5484d";
    e.style.background = "rgba(229,72,77,0.12)";
    const strong = document.createElement("strong");
    strong.textContent = "Analysis error:";
    e.appendChild(strong);
    const p = document.createElement("div");
    p.textContent = theme.error;
    p.style.marginTop = "0.25rem";
    p.style.wordBreak = "break-word";
    e.appendChild(p);
    content.appendChild(e);
  }

  details.appendChild(content);
  body.appendChild(details);

  article.appendChild(body);
  return article;
}

// Filtering + sorting
function getFilterState() {
  const levelBoxes = Array.from(document.querySelectorAll("#level-filters input[type=checkbox]"));
  const levels = levelBoxes.filter((b) => b.checked).map((b) => parseInt(b.value, 10));
  const mode = document.getElementById("filter-mode").value; // all/dark/light
  const official = document.getElementById("filter-official").value; // all/official/community
  const creator = document.getElementById("filter-creator").value;
  const q = document.getElementById("filter-search").value.trim().toLowerCase();
  const sort = document.getElementById("filter-sort").value;
  return { levels, mode, official, creator, q, sort };
}

function applyFiltersAndSort(themes, state) {
  let filtered = themes.filter((t) => {
    const lvl = t.compatibility ? t.compatibility.level : 0;
    if (!state.levels.includes(lvl)) return false;
    if (state.mode !== "all" && (t.mode || "dark") !== state.mode) return false;
    if (state.official !== "all") {
      const isOff = Boolean(t.official);
      if (state.official === "official" && !isOff) return false;
      if (state.official === "community" && isOff) return false;
    }
    if (state.creator !== "all" && t.creator !== state.creator) return false;
    if (state.q) {
      const hay = `${repoShortName(t.id)} ${t.creator || ""} ${t.description || ""} ${t.id || ""}`.toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  });

  // Sort
  if (state.sort === "stars") {
    filtered.sort((a, b) => (b.stars || 0) - (a.stars || 0));
  } else if (state.sort === "name") {
    filtered.sort((a, b) => repoShortName(a.id).localeCompare(repoShortName(b.id)));
  } else if (state.sort === "recent") {
    filtered.sort((a, b) => {
      const da = a.compatibility ? new Date(a.compatibility.analyzed_at).getTime() : 0;
      const db = b.compatibility ? new Date(b.compatibility.analyzed_at).getTime() : 0;
      return db - da;
    });
  } else {
    // level desc + stars desc (default)
    filtered.sort((a, b) => {
      const la = a.compatibility ? a.compatibility.level : 0;
      const lb = b.compatibility ? b.compatibility.level : 0;
      if (lb !== la) return lb - la;
      return (b.stars || 0) - (a.stars || 0);
    });
  }
  return filtered;
}

function renderGrid() {
  const state = getFilterState();
  const filtered = applyFiltersAndSort(allThemes, state);
  const grid = document.getElementById("theme-grid");
  grid.replaceChildren();

  // Result count aria-live
  const countEl = document.getElementById("result-count");
  countEl.textContent = `${filtered.length} theme${filtered.length === 1 ? "" : "s"} shown (of ${allThemes.length})`;

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.setAttribute("role", "status");
    const hasData = allThemes.length > 0;
    if (!hasData) {
      empty.textContent = "No themes to display.";
    } else {
      empty.innerHTML = `<p><strong>No results</strong> — try adjusting filters or search.</p><p style="margin-top:0.5rem"><button class="btn-reset" onclick="document.getElementById('btn-reset').click()">Clear filters</button></p>`;
    }
    grid.appendChild(empty);
    return;
  }

  filtered.forEach((t) => {
    grid.appendChild(createCard(t));
  });
}

// Hash serialization
function serializeHash(state) {
  const parts = [];
  // Only serialize non-default to keep hash clean, but include levels if not all 5 checked
  const allLevels = [0, 1, 2, 3, 4];
  const levelsSorted = [...state.levels].sort((a, b) => a - b);
  const isAllLevels = levelsSorted.length === 5 && allLevels.every((v, i) => v === levelsSorted[i]);
  if (!isAllLevels) {
    if (levelsSorted.length) parts.push(`levels=${levelsSorted.join(",")}`);
    else parts.push(`levels=`);
  }
  if (state.mode !== "all") parts.push(`mode=${encodeURIComponent(state.mode)}`);
  if (state.official !== "all") parts.push(`official=${encodeURIComponent(state.official)}`);
  if (state.creator !== "all") parts.push(`creator=${encodeURIComponent(state.creator)}`);
  if (state.q) parts.push(`q=${encodeURIComponent(state.q)}`);
  if (state.sort !== "level") parts.push(`sort=${encodeURIComponent(state.sort)}`);
  return parts.join("&");
}

function parseHash() {
  const hash = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const out = {};
  if (params.has("levels")) {
    const raw = params.get("levels");
    if (raw === "") out.levels = [];
    else out.levels = raw.split(",").map((s) => parseInt(s, 10)).filter((n) => !isNaN(n) && n >= 0 && n <= 4);
  }
  if (params.has("mode")) out.mode = params.get("mode");
  if (params.has("official")) out.official = params.get("official");
  if (params.has("creator")) out.creator = params.get("creator");
  if (params.has("q")) out.q = params.get("q");
  if (params.has("sort")) out.sort = params.get("sort");
  return out;
}

function applyHashToControls() {
  const parsed = parseHash();
  if (!parsed) return;
  if (parsed.levels !== undefined) {
    const boxes = document.querySelectorAll("#level-filters input[type=checkbox]");
    boxes.forEach((b) => {
      b.checked = parsed.levels.includes(parseInt(b.value, 10));
    });
  }
  if (parsed.mode && ["all", "dark", "light"].includes(parsed.mode)) {
    document.getElementById("filter-mode").value = parsed.mode;
  }
  if (parsed.official && ["all", "official", "community"].includes(parsed.official)) {
    document.getElementById("filter-official").value = parsed.official;
  }
  if (parsed.creator) {
    const sel = document.getElementById("filter-creator");
    const exists = Array.from(sel.options).some((o) => o.value === parsed.creator);
    if (exists) sel.value = parsed.creator;
  }
  if (parsed.q !== undefined) {
    document.getElementById("filter-search").value = parsed.q;
  }
  if (parsed.sort && ["level", "stars", "name", "recent"].includes(parsed.sort)) {
    document.getElementById("filter-sort").value = parsed.sort;
  }
}

function updateHashFromState() {
  const state = getFilterState();
  const hash = serializeHash(state);
  const newUrl = hash ? `#${hash}` : location.pathname + location.search;
  // Use replaceState to avoid history spam
  if (hash) {
    if (location.hash.slice(1) !== hash) history.replaceState(null, "", `#${hash}`);
  } else {
    if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  }
}

// Populate creator dropdown
function populateCreatorFilter(themes) {
  const sel = document.getElementById("filter-creator");
  const creators = Array.from(new Set(themes.map((t) => t.creator).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  // keep first option "All creators"
  creators.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    sel.appendChild(opt);
  });
}

// Error state when themes.json missing/invalid
function showLoadError(msg) {
  const countEl = document.getElementById("result-count");
  countEl.textContent = "Failed to load themes.";
  const grid = document.getElementById("theme-grid");
  grid.replaceChildren();
  const div = document.createElement("div");
  div.className = "error-state";
  div.setAttribute("role", "alert");
  div.innerHTML = `<p><strong>Could not load <code>data/themes.json</code></strong></p><p style="margin-top:0.5rem; color: var(--muted)">${escapeHtml(msg)}</p><p style="margin-top:0.75rem">If you are developing locally, run the pipeline to generate <code>site/data/themes.json</code> or check the network tab.</p>`;
  grid.appendChild(div);
  // Header stats fallback
  document.getElementById("stat-total").textContent = "—";
}

// Init
async function init() {
  // Bind control listeners
  const levelBoxes = document.querySelectorAll("#level-filters input[type=checkbox]");
  levelBoxes.forEach((b) => b.addEventListener("change", () => { updateHashFromState(); renderGrid(); }));
  document.getElementById("filter-mode").addEventListener("change", () => { updateHashFromState(); renderGrid(); });
  document.getElementById("filter-official").addEventListener("change", () => { updateHashFromState(); renderGrid(); });
  document.getElementById("filter-creator").addEventListener("change", () => { updateHashFromState(); renderGrid(); });
  document.getElementById("filter-sort").addEventListener("change", () => { updateHashFromState(); renderGrid(); });
  const searchInput = document.getElementById("filter-search");
  let debounce = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { updateHashFromState(); renderGrid(); }, 250);
  });
  document.getElementById("btn-reset").addEventListener("click", () => {
    levelBoxes.forEach((b) => (b.checked = true));
    document.getElementById("filter-mode").value = "all";
    document.getElementById("filter-official").value = "all";
    document.getElementById("filter-creator").value = "all";
    searchInput.value = "";
    document.getElementById("filter-sort").value = "level";
    updateHashFromState();
    renderGrid();
  });

  // Hash changes (back/forward)
  window.addEventListener("hashchange", () => {
    applyHashToControls();
    // only re-render if we have data
    if (allThemes.length) renderGrid();
  });

  // Fetch data
  try {
    const res = await fetch("data/themes.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const db = await res.json();
    // Basic validation
    if (!db || typeof db !== "object" || !Array.isArray(db.themes)) throw new Error("Invalid JSON shape: missing themes array");
    dbMeta = db;
    allThemes = db.themes;
    renderHeader(db);
    populateCreatorFilter(allThemes);
    // Restore hash before initial render
    applyHashToControls();
    renderGrid();
    // Ensure hash reflects current state on first load (if none, clear)
    // Don't force hash if default; user may want clean URL
  } catch (e) {
    showLoadError(e && e.message ? e.message : String(e));
    console.error("Failed to load themes.json", e);
  }
}

document.addEventListener("DOMContentLoaded", init);
