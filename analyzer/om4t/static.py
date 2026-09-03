"""
Static analyzer: palette, alacritty, legacy, badges, sanitizer heuristic.
"""
from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import rules

__all__ = [
    "StaticError",
    "PaletteFindings",
    "LegacyFinding",
    "StaticFindings",
    "find_palette",
    "parse_colors_toml",
    "validate_palette",
    "alacritty_palette_usable",
    "detect_legacy",
    "detect_badges",
    "analyze_repo",
]


class StaticError(RuntimeError):
    pass


@dataclass
class PaletteFindings:
    mode: str | None
    present: list[str]
    missing: list[str]
    used_aliases: list[str]
    invalid_values: list[dict]


@dataclass
class LegacyFinding:
    marker_id: str
    severity: str  # "hard" | "soft"
    path: str | None
    referenced: bool
    note: str | None


@dataclass
class StaticFindings:
    has_colors_toml: bool
    colors_toml_valid: bool
    colors_toml_path: str | None
    parse_error: str | None
    palette: PaletteFindings | None
    alacritty_usable: bool
    alacritty_detail: str | None
    legacy: list[LegacyFinding]
    badges: set[str]
    uses_sanitizer_stripped_for_appearance: bool


_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGBA_RE = re.compile(r"^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)\s*$", re.IGNORECASE)
# For detecting rgba inside toml values (maybe without full match, but we validate full)
# Also need to detect old path regexes
_OLD_PATH_REGEXES = [re.compile(p) for p in [r"~\/\.config\/omarchy\/current", r"~\/\.local\/share\/omarchy"]]


def find_palette(repo_dir: str | Path) -> Path | None:
    """
    Path to colors.toml (root first, then one subdir) or None.
    """
    p = Path(repo_dir)
    if not p.is_dir():
        return None
    root_candidate = p / "colors.toml"
    if root_candidate.is_file():
        return root_candidate
    # one subdir deep, deterministic sorted
    subdirs = sorted([d for d in p.iterdir() if d.is_dir()], key=lambda x: x.name)
    for sub in subdirs:
        cand = sub / "colors.toml"
        if cand.is_file():
            return cand
    return None


def parse_colors_toml(path: str | Path) -> dict:
    """
    Parse colors.toml via tomllib; raise StaticError with reason on failure.
    """
    p = Path(path)
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
        if not isinstance(data, dict):
            raise StaticError(f"colors.toml did not parse to dict: {p}")
        return data
    except StaticError:
        raise
    except Exception as e:
        raise StaticError(f"failed to parse {p}: {e}") from e


def validate_palette(data: dict) -> PaletteFindings:
    """
    Validate palette data.
    mode via mode or theme_type fallback.
    present/missing canonical, used_aliases, invalid_values (hex/rgba).
    """
    # mode resolution
    mode = data.get("mode")
    if mode is None and "theme_type" in data:
        mode = data.get("theme_type")
    # Normalize mode to string if present
    if mode is not None:
        mode = str(mode)

    # Build present/missing
    present: list[str] = []
    used_aliases: list[str] = []
    # Check aliases first
    for alias, canonical in rules.LEGACY_ALIASES.items():
        if alias in data:
            if canonical not in present:
                present.append(canonical)
            if alias not in used_aliases:
                used_aliases.append(alias)
    # Check canonical directly
    for key in rules.CANONICAL_COLOR_KEYS:
        if key in data:
            if key not in present:
                present.append(key)
        # Also handle case where alias already counted; ensure present reflects direct presence
    # Now determine missing: canonical keys not in present
    missing = [k for k in rules.CANONICAL_COLOR_KEYS if k not in present]

    # Invalid values: regex-check hex forms and rgba
    invalid_values: list[dict] = []
    for k, v in data.items():
        if not isinstance(v, str):
            continue
        # Only check values that look like colors: those where key is a canonical color or alias or contains color-like?
        # Spec says regex-check hex forms #rgb/#rrggbb/#rrggbbaa and rgba(...). So any string starting with # or rgba should be validated.
        stripped = v.strip()
        if stripped.startswith("#"):
            if not _HEX_RE.match(stripped):
                invalid_values.append({"key": k, "value": v})
        elif stripped.lower().startswith("rgba("):
            if not _RGBA_RE.match(stripped):
                invalid_values.append({"key": k, "value": v})
        # Also maybe check if canonical color key has non-hex string that is not valid? But we only flag hex-like invalid.
        # For mode, we could flag invalid mode values? But spec says invalid_values is hex check, so we keep.

    # Sort for determinism
    present.sort()
    missing.sort()
    used_aliases.sort()

    return PaletteFindings(mode=mode, present=present, missing=missing, used_aliases=used_aliases, invalid_values=invalid_values)


def _find_alacritty_path(repo_dir: Path) -> Path | None:
    p = Path(repo_dir)
    cand = p / "alacritty.toml"
    if cand.is_file():
        return cand
    for sub in sorted([d for d in p.iterdir() if d.is_dir()], key=lambda x: x.name):
        cand2 = sub / "alacritty.toml"
        if cand2.is_file():
            return cand2
    return None


def alacritty_palette_usable(repo_dir: str | Path) -> tuple[bool, str]:
    """
    Alacritty palette usable: alacritty.toml parses via tomllib and has ≥6 colors.normal entries plus background or foreground.
    Returns (bool, detail).
    """
    repo = Path(repo_dir)
    path = _find_alacritty_path(repo)
    if path is None:
        return (False, "no alacritty.toml found")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        return (False, f"parse error: {e}")

    # Navigate to colors.normal
    colors = data.get("colors", {})
    if not isinstance(colors, dict):
        return (False, "no [colors] table")
    normal = colors.get("normal", {})
    if not isinstance(normal, dict):
        # Also check legacy flat colors.normal via nested? tomllib already nests.
        return (False, "no [colors.normal]")
    count = len([k for k in normal.keys() if isinstance(normal[k], str)])
    # Also check colors.primary background/foreground
    primary = colors.get("primary", {})
    has_bg = False
    has_fg = False
    if isinstance(primary, dict):
        has_bg = "background" in primary and isinstance(primary["background"], str)
        has_fg = "foreground" in primary and isinstance(primary["foreground"], str)
    # Also fallback to top-level background/foreground inside colors?
    if not has_bg:
        has_bg = "background" in colors and isinstance(colors["background"], str)
    if not has_fg:
        has_fg = "foreground" in colors and isinstance(colors["foreground"], str)

    if count >= 6 and (has_bg or has_fg):
        return (True, f"found {count} normal colors, bg={has_bg} fg={has_fg}")
    else:
        return (False, f"found {count} normal colors, bg={has_bg} fg={has_fg} (need >=6 and bg or fg)")


def _collect_all_files(repo_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in repo_dir.rglob("*"):
        if p.is_file():
            files.append(p)
    return files


def _glob_matches(rel_path: Path, pattern: str) -> bool:
    # Use pathlib match for ** support, fallback to fnmatch
    try:
        # pathlib's match expects pattern relative to some parent; it works but needs posix
        # Ensure pattern not starting with /
        pat = pattern.lstrip("/")
        # Path.match does fnmatch with ** support (since Python 3.10)
        if rel_path.match(pat):
            return True
        # Also try fnmatch for wildcard combos not covered
        import fnmatch as fnm

        rel_str = rel_path.as_posix()
        # fnmatch with ** -> treat ** as *
        fn_pat = pat.replace("**", "*")
        if fnm.fnmatch(rel_str, fn_pat):
            return True
        # Also check basename only for patterns like "mako*" that should match any file named mako*
        if fnm.fnmatch(rel_path.name, pat):
            return True
        # For patterns like "waybar/**", also check if rel_str starts with "waybar/"
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if rel_str == prefix or rel_str.startswith(prefix + "/"):
                return True
        return False
    except Exception:
        import fnmatch as fnm

        return fnm.fnmatch(rel_path.as_posix(), pattern)


def _is_text_file(path: Path) -> bool:
    # Text-ish detection: try to read as utf-8, if fails treat as binary? For our grep, we skip binary.
    try:
        path.read_text(encoding="utf-8")
        return True
    except Exception:
        return False


def _get_text_file_candidates(repo_dir: Path) -> list[Path]:
    # text-ish files: README*, *.md, *.sh, install*, *.txt anywhere (recursive for simplicity)
    candidates: list[Path] = []
    for p in repo_dir.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        # Check patterns
        if (
            name.startswith("README")
            or fnmatch.fnmatch(name, "*.md")
            or fnmatch.fnmatch(name, "*.sh")
            or fnmatch.fnmatch(name, "install*")
            or fnmatch.fnmatch(name, "*.txt")
        ):
            candidates.append(p)
        # Also check for install* directory? But spec says files.
        # Also handle README* without extension, already covered.
    return candidates


def detect_legacy(repo_dir: str | Path) -> list[LegacyFinding]:
    """
    Detect legacy markers.
    """
    repo = Path(repo_dir)
    if not repo.is_dir():
        return []
    all_files = _collect_all_files(repo)
    rel_files = [(f, f.relative_to(repo)) for f in all_files]

    # Collect text file contents for reference check (exclude docs/examples etc for hard-require heuristic)
    text_candidates = _get_text_file_candidates(repo)
    combined_text = ""
    text_contents: dict[Path, str] = {}
    for tf in text_candidates:
        try:
            rel_tf = tf.relative_to(repo)
            # Exclude docs/examples etc from reference check for hard markers
            if rel_tf.parts and rel_tf.parts[0].lower() in {"examples", "docs", "screenshots", "previews"}:
                continue
            txt = tf.read_text(encoding="utf-8", errors="ignore")
            text_contents[tf] = txt
            combined_text += "\n" + txt
        except Exception:
            continue
    combined_lower = combined_text.lower()

    # Subtrees to exclude from legacy marker file presence (docs/examples not part of installed theme)
    _EXCLUDED_PREFIXES = {"examples", "docs", "screenshots", "previews"}

    def _is_excluded(rel: Path) -> bool:
        # Exclude if first part is in excluded set (e.g., docs/foo, examples/bar)
        parts = rel.parts
        if not parts:
            return False
        return parts[0].lower() in _EXCLUDED_PREFIXES

    findings: list[LegacyFinding] = []

    # For each marker with globs, check presence
    for entry in rules.LEGACY_MARKERS_HARD:
        marker_id = entry["id"]
        globs = entry.get("globs", [])
        regexes = entry.get("regexes", [])
        # Handle glob-based markers
        if globs:
            matched_files: list[Path] = []
            for f, rel in rel_files:
                if _is_excluded(rel):
                    continue
                for pat in globs:
                    if _glob_matches(rel, pat):
                        matched_files.append(f)
                        break
            if matched_files:
                # Determine referenced: does combined text contain marker keyword?
                # Derive keyword: first part of id before dash, or glob base
                keyword = marker_id.split("-")[0].lower()
                # Also check globs base tokens
                referenced = False
                # Check keyword in combined text
                if keyword in combined_lower:
                    referenced = True
                else:
                    # Check any glob token (strip wildcards and dirs)
                    for pat in globs:
                        token = re.sub(r"[*\/]+", " ", pat).strip().split()
                        for t in token:
                            t = t.strip().lower()
                            if t and t in combined_lower:
                                referenced = True
                                break
                        if referenced:
                            break
                # Also old-path regexes in text? But that's for separate markers
                severity = "hard" if referenced else "soft"
                # Emit one finding per marker (with first matched path)
                rel_path_str = str(matched_files[0].relative_to(repo))
                # Build note
                note = entry.get("description", "")
                findings.append(
                    LegacyFinding(
                        marker_id=marker_id,
                        severity=severity,
                        path=rel_path_str,
                        referenced=referenced,
                        note=note,
                    )
                )
        # Handle regex-only markers (old paths)
        if regexes:
            # Search text files for regex hits -> hard
            for regex_str in regexes:
                try:
                    pat = re.compile(regex_str)
                except re.error:
                    continue
                for tf, txt in text_contents.items():
                    if pat.search(txt):
                        findings.append(
                            LegacyFinding(
                                marker_id=marker_id,
                                severity="hard",
                                path=str(tf.relative_to(repo)),
                                referenced=True,
                                note=entry.get("description", ""),
                            )
                        )
                        # break after first hit per marker? But if multiple files, we could emit one per file? Keep one per hit file maybe.
                        # For now, emit one per marker per file hit, but dedupe marker_id? We'll break to avoid duplicates per marker
                        # Actually if multiple text files contain old path, we should maybe emit one per file, but spec expects per marker.
                        # We'll break after first to avoid duplicate findings for same marker.
                        break
                # Also, if regex-only marker has no glob, the above loop handles
                # Ensure we don't double-count markers that also have globs and regexes? Those globs already handled, regex hits add additional hard finding.

    # Dedupe by marker_id keeping hardest severity? If we emitted soft then hard for same marker, keep hard.
    deduped: dict[str, LegacyFinding] = {}
    for f in findings:
        if f.marker_id not in deduped:
            deduped[f.marker_id] = f
        else:
            # Prefer hard over soft
            existing = deduped[f.marker_id]
            if existing.severity == "soft" and f.severity == "hard":
                deduped[f.marker_id] = f

    return list(deduped.values())


def detect_badges(repo_dir: str | Path, palette: PaletteFindings | None = None) -> set[str]:
    """
    Badge detection per rules.BADGE_PROBES.
    """
    repo = Path(repo_dir)
    badges: set[str] = set()

    # Helper to find files matching globs
    def find_glob_files(patterns: list[str]) -> list[Path]:
        matched: list[Path] = []
        all_files = _collect_all_files(repo)
        for f in all_files:
            rel = f.relative_to(repo)
            for pat in patterns:
                if _glob_matches(rel, pat):
                    matched.append(f)
                    break
        return matched

    # Pre-collect shell toml files for regex probes that have empty globs (transparency)
    shell_files = find_glob_files(["shell*.toml", "shell.toml"])
    # Also collect all .toml files content for transparency if needed? But spec says read shell*.toml file contents for alpha/corner...
    # We'll limit to shell*.toml for transparency too (since empty globs implies search shell*.toml)
    # For each badge probe
    for probe in rules.BADGE_PROBES:
        badge_id = probe["badge_id"]
        globs = probe.get("globs", [])
        regexes = probe.get("regexes", [])

        if badge_id == "light-mode":
            # Special: check palette mode or colors.toml regex
            mode_is_light = False
            if palette and palette.mode and palette.mode.lower() == "light":
                mode_is_light = True
            else:
                # Check colors.toml file content for mode = "light"
                palette_path = find_palette(repo)
                if palette_path and palette_path.is_file():
                    try:
                        txt = palette_path.read_text(encoding="utf-8", errors="ignore")
                        if re.search(r'mode\s*=\s*"light"', txt):
                            mode_is_light = True
                    except Exception:
                        pass
            if mode_is_light:
                badges.add(badge_id)
            continue

        if badge_id == "wallpapers":
            # Check backgrounds/ non-empty with image files
            bg_dir = repo / "backgrounds"
            if bg_dir.is_dir():
                # Check one subdir deep also? spec says backgrounds/ count
                files = list(bg_dir.iterdir())
                # Count image files (png/jpg/jpeg/webp/gif)
                image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
                count = 0
                for f in bg_dir.rglob("*"):
                    if f.is_file() and f.suffix.lower() in image_exts:
                        count += 1
                if count > 0:
                    badges.add(badge_id)
            continue

        # For other badges, check globs and regexes
        if not globs and not regexes:
            continue

        matched_files: list[Path] = []
        if globs:
            matched_files = find_glob_files(globs)
            if not matched_files and not regexes:
                # existence-only probe failed
                continue
            if not matched_files and regexes:
                # Need files to search regex in, but none exist -> no badge
                continue
        else:
            # No globs but regexes present -> search in shell*.toml
            matched_files = shell_files

        if not regexes:
            # Existence probe only
            if matched_files:
                badges.add(badge_id)
            continue

        # Regex probe: need to read matched files and check regexes
        found = False
        for f in matched_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for rx in regexes:
                try:
                    if re.search(rx, content):
                        found = True
                        break
                except re.error:
                    continue
            if found:
                break
        if found:
            badges.add(badge_id)
        # Special handling for transparency probe which has globs empty but we searched shell_files
        # Already handled.

    return badges


def analyze_repo(repo_dir: str | Path) -> StaticFindings:
    """
    Full repo analysis bundling palette, alacritty, legacy, badges, sanitizer heuristic.
    """
    repo = Path(repo_dir)
    palette_path = find_palette(repo)
    has_colors = palette_path is not None
    colors_toml_valid = False
    parse_error: str | None = None
    palette: PaletteFindings | None = None

    if has_colors:
        try:
            data = parse_colors_toml(palette_path)  # type: ignore[arg-type]
            palette = validate_palette(data)
            # Valid if no invalid values and no parse error; missing canonical allowed but maybe warn.
            if not palette.invalid_values:
                # Also check that mode is dark/light? But minimal requires at least background etc.
                # Consider valid if palette present not empty? We'll define valid if present non-empty or mode resolved.
                # For our fixtures, native-minimal should be valid.
                colors_toml_valid = True
                # If invalid_values exists, valid is False
                # Already checked
                # Additional check: if data empty, not valid
                if not palette.present:
                    # If palette has no canonical keys at all, maybe not valid - but spec says broken-toml parse error -> valid False, no-palette has no colors.toml -> valid False
                    # For minimal, present includes mode etc.
                    pass
            else:
                colors_toml_valid = False
        except StaticError as e:
            parse_error = str(e)
            colors_toml_valid = False
            palette = None
    else:
        colors_toml_valid = False

    alacritty_usable, alacritty_detail = alacritty_palette_usable(repo)
    legacy = detect_legacy(repo)
    badges = detect_badges(repo, palette)

    # Sanitizer heuristic: lua/vscode.json/terminal-config present AND referenced in README/scripts → True
    uses_sanitizer = False
    # Check presence of deny list patterns
    all_files = _collect_all_files(repo) if repo.is_dir() else []
    deny_present: list[Path] = []
    for pat, _ in rules.SANITIZER_DENY:
        for f in all_files:
            rel = f.relative_to(repo)
            if _glob_matches(rel, pat):
                deny_present.append(f)
                break  # one per pattern
            # Also exact name match for alacritty.toml etc.
            if pat == f.name or pat == rel.name:
                if f not in deny_present:
                    deny_present.append(f)
    if deny_present:
        # Check referenced in README/scripts text files
        text_candidates = _get_text_file_candidates(repo)
        combined = ""
        for tf in text_candidates:
            try:
                combined += "\n" + tf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        combined_lower = combined.lower()
        referenced_names: list[str] = []
        for f in deny_present:
            name = f.name.lower()
            # Check if name mentioned in combined text
            if name in combined_lower or f.stem.lower() in combined_lower:
                referenced_names.append(name)
            # Also check generic tokens like "lua" for *.lua
            if f.suffix.lower() == ".lua" and "lua" in combined_lower:
                if "lua" not in referenced_names:
                    referenced_names.append("lua")
        # For terminal configs, check e.g., alacritty
        # Heuristic: if any deny present AND any reference to that file exists → True
        # For *, if there are deny files and combined mentions them, set True
        # But also if README says "requires neovim.lua", that would be referenced.
        if referenced_names:
            uses_sanitizer = True
        else:
            # Also check if combined text mentions any deny pattern token generically (e.g., "vscode.json" string)
            # Already covered via name check; if none, then not referenced.
            uses_sanitizer = False

    return StaticFindings(
        has_colors_toml=has_colors,
        colors_toml_valid=colors_toml_valid,
        colors_toml_path=str(palette_path) if palette_path else None,
        parse_error=parse_error,
        palette=palette,
        alacritty_usable=alacritty_usable,
        alacritty_detail=alacritty_detail,
        legacy=legacy,
        badges=badges,
        uses_sanitizer_stripped_for_appearance=uses_sanitizer,
    )
