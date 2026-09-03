"""
Grader per plan §8 — decision tree exactly first-match wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import rules
from .schema import CheckResult, Compatibility, PaletteInfo, ThemeRecord, utc_now_iso
from .static import StaticFindings
from .verify import VerifyResult
from .pin import PinInfo

__all__ = ["grade_theme", "determine_level"]


def _has_legacy_hard(static: StaticFindings) -> bool:
    return any(f.severity == "hard" for f in static.legacy)


def determine_level(static: StaticFindings, verify: VerifyResult) -> int:
    """
    Decision tree per plan §8 with caps (2026-09-02 revision: stripped files are regenerated from palette — warning, not cap):
    - alacritty-derived ceiling 1
    - legacy_soft warnings only, never demote
    - legacy hard caps at 1 if colors_valid else 0
    - L2 requires colors_valid AND render_clean
    - L3 adds no hard-legacy + modern_conventions (no hard-legacy and native colors.toml palette)
    - L4 adds install_sim_clean (render_clean and no error; stripping is warning-only)
    Returns level 0-4.
    Rationale: every sanitizer-stripped file (*.lua, alacritty.toml, foot.ini, ghostty.conf, kitty.conf, vscode.json)
    has a corresponding template in default/themed/ (neovim.lua.tpl etc.) — Omarchy regenerates them from colors.toml,
    so stripping does not break a valid-palette theme. Appearance loss is warning, not cap.
    """
    colors_valid = static.colors_toml_valid
    alacritty = static.alacritty_usable
    render_clean = verify.render_clean
    legacy_hard = _has_legacy_hard(static)
    # modern_conventions: no hard-legacy and native colors.toml palette (true at L2+); not falsified by stripped files
    modern = (not legacy_hard) and colors_valid
    # install_sim_clean: render_clean and no error — stripping irrelevant (warning-only)
    install_clean = render_clean and verify.error is None

    has_palette = colors_valid or alacritty

    # Tree first-match wins
    # L0 if not (colors_valid or alacritty)
    if not has_palette:
        return 0
    # L0 if legacy_hard and not colors_valid (fundamentally Om3-dependent)
    if legacy_hard and not colors_valid:
        return 0
    # L0 if colors_valid and not render_clean (broken under renderer)
    if colors_valid and not render_clean:
        return 0
    # Also alacritty but render fails should be L0
    if alacritty and not colors_valid and not render_clean:
        return 0
    # L1 if alacritty and render_clean (legacy layer only; ceiling 1)
    if alacritty and not colors_valid and render_clean:
        return 1
    # Legacy hard caps at 1 if colors_valid else 0 (already handled 0 case)
    if legacy_hard and colors_valid:
        return 1

    # Now palette is colors_valid and render_clean (since we excluded alacritty path and L0)
    if not (colors_valid and render_clean):
        # This covers edge where not colors_valid but alacritty case already returned,
        # so remaining should be L0. But we already handled.
        return 0

    # L2 base
    level = 2
    # L3 if L2 and not legacy_hard and modern_conventions
    if not legacy_hard and modern:
        level = 3
        # L4 if L3 and install_sim_clean
        if install_clean:
            level = 4
    # Alacritty ceiling: never above 1 even if everything else passes (defensive)
    if alacritty and not colors_valid and level > 1:
        level = 1

    return level


def _build_checks(static: StaticFindings, verify: VerifyResult) -> list[CheckResult]:
    colors_valid = static.colors_toml_valid
    legacy_hard = _has_legacy_hard(static)
    modern = (not legacy_hard) and colors_valid
    install_clean = verify.render_clean and verify.error is None
    # For modern_conventions note: check if custom shell present via badges
    has_custom_shell = "custom-shell" in (static.badges or set())

    checks: list[CheckResult] = []
    # Order = evaluation order per task
    # 1. palette_available / colors_toml_valid
    if colors_valid:
        checks.append(CheckResult(id="colors_toml_valid", passed=True, note="Native colors.toml ✓"))
    elif static.alacritty_usable:
        checks.append(CheckResult(id="colors_toml_valid", passed=False, note="No native colors.toml — alacritty-derived"))
        # Also add alacritty check for why?
        checks.append(CheckResult(id="alacritty_convertible", passed=True, note="alacritty.toml convertible ✓"))
    else:
        # No valid palette at root+1 — check for deeper nested palettes (collection repo)
        nested = getattr(static, "nested_palette_count", 0)
        if nested and nested > 0:
            checks.append(CheckResult(id="colors_toml_valid", passed=False, note=f"No colors.toml at repo root (found {nested} nested palettes — collection/toolkit repo, not directly installable)"))
        else:
            checks.append(CheckResult(id="colors_toml_valid", passed=False, note="No valid palette"))

    # 2. renderer_clean
    if verify.render_clean:
        checks.append(CheckResult(id="renderer_clean", passed=True, note="Quattro renderer ✓"))
    else:
        note = verify.error or verify.log_excerpt[:200] if verify.log_excerpt else "renderer failed"
        checks.append(CheckResult(id="renderer_clean", passed=False, note=note))

    # 3. no_required_legacy
    if not legacy_hard:
        checks.append(CheckResult(id="no_required_legacy", passed=True, note="No legacy Waybar dependency ✓"))
    else:
        hard_ids = [f.marker_id for f in static.legacy if f.severity == "hard"]
        checks.append(CheckResult(id="no_required_legacy", passed=False, note=f"Legacy hard: {', '.join(hard_ids)}"))

    # 4. modern_conventions — no hard legacy and native palette; shell*.toml presence drives note
    if modern:
        note = "Custom Quickshell styling ✓" if has_custom_shell else "Current Quattro mechanisms ✓"
        checks.append(CheckResult(id="modern_conventions", passed=True, note=note))
    else:
        # Only fails when hard legacy present or non-native palette (stripping is warning-only per 2026-09-02 revision)
        checks.append(CheckResult(id="modern_conventions", passed=False, note="Legacy hard or non-native palette"))

    # 5. install_sim_clean — render_clean and no error; stripping is warning-only (regenerated via templates)
    if install_clean:
        checks.append(CheckResult(id="install_sim_clean", passed=True, note="Install simulation clean ✓"))
    else:
        if not verify.render_clean:
            note = "render not clean"
        elif verify.error:
            note = verify.error[:200]
        else:
            note = "install simulation not clean"
        checks.append(CheckResult(id="install_sim_clean", passed=False, note=note))

    return checks


def grade_theme(
    theme_dir: str | Path | None,
    static: StaticFindings,
    verify: VerifyResult,
    pin: PinInfo,
    candidate_meta: dict | Any | None = None,
) -> ThemeRecord:
    """
    Build ThemeRecord from inputs per spec §14.
    candidate_meta may be dict with keys: id/full_name, repo_url/html_url, creator/owner, description, stars/stargazers_count, topics, default_branch, commit_sha/sha, official, registry, preview
    """
    # Normalize candidate meta
    meta = candidate_meta or {}
    # Support Candidate dataclass
    if not isinstance(meta, dict):
        # Try to extract attributes
        try:
            d = {}
            for k in ["id", "full_name", "repo_url", "html_url", "creator", "owner", "description", "stars", "stargazers_count", "topics", "default_branch", "commit_sha", "sha", "official", "registry", "preview", "mode"]:
                if hasattr(meta, k):
                    d[k] = getattr(meta, k)
            meta = d
        except Exception:
            meta = {}

    # id
    theme_id = meta.get("id") or meta.get("full_name") or (Path(theme_dir).name if theme_dir else "unknown/theme")
    # repo_url
    repo_url = meta.get("repo_url") or meta.get("html_url") or f"https://github.com/{theme_id}"
    # creator
    creator = meta.get("creator") or meta.get("owner") or (theme_id.split("/")[0] if "/" in theme_id else "unknown")
    description = meta.get("description") or ""
    stars = meta.get("stars")
    if stars is None:
        stars = meta.get("stargazers_count", 0)
    try:
        stars = int(stars)
    except Exception:
        stars = 0
    topics = list(meta.get("topics", []))
    default_branch = meta.get("default_branch", "main") or "main"
    commit_sha = meta.get("commit_sha") or meta.get("sha") or meta.get("commitSHA") or ""
    official = bool(meta.get("official", False))
    registry = bool(meta.get("registry", False))
    # mode from palette or meta
    mode = "dark"
    if static.palette and static.palette.mode:
        m = static.palette.mode.lower()
        if m in ("dark", "light"):
            mode = m
    else:
        # Try meta mode
        meta_mode = meta.get("mode")
        if meta_mode in ("dark", "light"):
            mode = meta_mode

    level = determine_level(static, verify)
    label = rules.LEVEL_LABELS.get(level, "incompatible")

    # Badges: from static plus headless-verified for L4
    badges = set(static.badges) if static.badges else set()
    if level == 4:
        badges.add("headless-verified")
    # Sort badges for determinism? But keep insertion order? Sorted
    badges_list = sorted(badges)

    # Palette
    if static.palette:
        palette = PaletteInfo(
            missing_canonical=list(static.palette.missing),
            resolved_via_alias=list(static.palette.used_aliases),
        )
    else:
        palette = PaletteInfo(missing_canonical=list(rules.CANONICAL_COLOR_KEYS), resolved_via_alias=[])

    # Warnings: soft legacy findings only, plus any other warnings
    warnings: list[str] = []
    for f in static.legacy:
        if f.severity == "soft":
            warnings.append(f"{f.marker_id} present but unreferenced — stale junk")
        elif f.severity == "hard":
            # Hard already accounted in checks, but if level capped, also add? Task says legacy_soft warning only, legacy hard caps -> not warning? But we could keep hard as check failure, not warning.
            pass
    # Also add parse_error as warning?
    if static.parse_error:
        warnings.append(f"colors.toml parse error: {static.parse_error}")
    # Stripped files are warning-only: every sanitizer-stripped file has a template in default/themed/
    # (neovim.lua.tpl etc.) — Omarchy regenerates them from colors.toml
    if verify.stripped:
        files = ", ".join(s["file"] for s in verify.stripped[:5])
        if len(verify.stripped) > 5:
            files += f", +{len(verify.stripped)-5} more"
        warnings.append(f"{len(verify.stripped)} file(s) will be regenerated from palette by Omarchy: {files}")
    # Add synthesize info?
    if verify.synthesized_colors:
        warnings.append("colors synthesized from alacritty.toml")

    # Checks ordered
    checks = _build_checks(static, verify)

    # Compatibility
    analyzed_at = utc_now_iso()
    compatibility = Compatibility(
        family="omarchy-4",
        level=level,
        label=label,
        tested_against=pin.tag,
        omarchy_commit=pin.commit_sha,
        analyzed_at=analyzed_at,
        rules_version=rules.RULES_VERSION,
    )

    # Preview URL: if commit_sha known, construct raw githubusercontent else meta preview
    preview = meta.get("preview")
    if not preview and commit_sha:
        # Try to construct raw URL if id looks like owner/repo
        if "/" in theme_id and not theme_id.startswith("omacom/omarchy/"):
            preview = f"https://raw.githubusercontent.com/{theme_id}/{commit_sha}/preview.png"
        elif "/" in theme_id:
            # built-in?
            preview = None
    # For native-full fixture, preview.png exists; we set preview accordingly if file exists in theme_dir
    if theme_dir and not preview:
        td = Path(theme_dir)
        if (td / "preview.png").is_file():
            preview = f"https://raw.githubusercontent.com/{theme_id}/{commit_sha}/preview.png" if commit_sha else None

    # Error field: if verify.error or static parse error?
    error = verify.error
    if not error and static.parse_error and not static.colors_toml_valid and not static.alacritty_usable:
        error = static.parse_error

    return ThemeRecord(
        id=theme_id,
        repo_url=repo_url,
        creator=creator,
        description=description,
        stars=stars,
        topics=topics,
        default_branch=default_branch,
        commit_sha=commit_sha,
        official=official,
        registry=registry,
        preview=preview,
        mode=mode,
        compatibility=compatibility,
        checks=checks,
        badges=badges_list,
        palette=palette,
        warnings=warnings,
        error=error,
    )
