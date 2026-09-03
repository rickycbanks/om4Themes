"""
Versioned rule tables for om4Themes — v2026.09.0.

These tables are declarative and diffable; bumping RULES_VERSION signals a rubric change.
Runtime palette resolution is delegated to the official oracle `omarchy-theme-color`.
"""

RULES_VERSION = "2026.09.0"
OMARCHY_REPO = "omacom/omarchy"
PIN_MATURITY_DAYS = 3
DISCOVERY_TOPICS = ["omarchy-theme"]
MAX_REPOS_PER_RUN = 400

# Canonical semantic palette keys (26) — includes orange/brown added in Quattro.
CANONICAL_COLOR_KEYS = [
    "mode",
    "accent",
    "selection",
    "muted",
    "background",
    "dark_background",
    "darker_background",
    "lighter_background",
    "foreground",
    "dark_foreground",
    "light_foreground",
    "bright_foreground",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "orange",
    "brown",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
]

# Legacy aliases — reference only. The runtime oracle is `bin/omarchy-theme-color`.
# Maps legacy/alias key -> canonical key.
LEGACY_ALIASES = {
    "bg": "background",
    "dark_bg": "dark_background",
    "darker_bg": "darker_background",
    "lighter_bg": "lighter_background",
    "fg": "foreground",
    "dark_fg": "dark_foreground",
    "light_fg": "light_foreground",
    "bright_fg": "bright_foreground",
    "purple": "magenta",
    "bright_purple": "bright_magenta",
    "cursor": "bright_foreground",
    "theme_type": "mode",
    # Note: color0–color15 ANSI bridging also exists in omarchy-theme-color
    # (legacy terminal palette indices mapped to semantic keys at render time).
}

# Sanitizer deny list — files dropped by omarchy-theme-set's stage_installed_theme
# for git-installed themes (not trusted for appearance).
SANITIZER_DENY: list[tuple[str, str]] = [
    ("*.lua", "Hyprland Lua configs are regenerated from colors.toml"),
    ("alacritty.toml", "legacy terminal palette — converted or dropped"),
    ("foot.ini", "terminal config — regenerated from colors.toml"),
    ("ghostty.conf", "terminal config — regenerated from colors.toml"),
    ("kitty.conf", "terminal config — regenerated from colors.toml"),
    ("vscode.json", "editor config dropped for git-installed themes"),
]

# Legacy markers — hard (fail) only when referenced by README/install scripts,
# otherwise soft (warning). Classification logic lives in static.py; rules.py
# just declares the tables. Each entry carries required_if_referenced flag.
LEGACY_MARKERS_HARD: list[dict] = [
    {
        "id": "waybar-config",
        "globs": ["waybar/**", "*waybar*style.css", "waybar.css", ".config/waybar/**"],
        "regexes": [],
        "description": "Waybar config — replaced by Quickshell in Quattro",
        "required_if_referenced": True,
    },
    {
        "id": "mako-config",
        "globs": ["mako/**", "mako*"],
        "regexes": [],
        "description": "Mako notification daemon config — replaced in Quattro",
        "required_if_referenced": True,
    },
    {
        "id": "walker-config",
        "globs": ["walker/**", "walker*"],
        "regexes": [],
        "description": "Walker launcher config — replaced in Quattro",
        "required_if_referenced": True,
    },
    {
        "id": "swayosd-config",
        "globs": ["swayosd/**", "swayosd*"],
        "regexes": [],
        "description": "SwayOSD config — replaced in Quattro",
        "required_if_referenced": True,
    },
    {
        "id": "hyprlock-config",
        "globs": ["hyprlock/**", "hyprlock*", "hyprlock.conf"],
        "regexes": [],
        "description": "hyprlock config — replaced in Quattro",
        "required_if_referenced": True,
    },
    {
        "id": "hyprland-conf",
        "globs": ["hyprland.conf", "**/hyprland.conf"],
        "regexes": [],
        "description": "Hyprland .conf — Quattro uses Lua (hypr/*.lua)",
        "required_if_referenced": True,
    },
    {
        "id": "old-current-path",
        "globs": [],
        "regexes": [r"~\/\.config\/omarchy\/current"],
        "description": "Old state path ~/.config/omarchy/current — moved to ~/.local/state/omarchy/current",
        "required_if_referenced": True,
    },
    {
        "id": "old-share-layout",
        "globs": [],
        "regexes": [r"~\/\.local\/share\/omarchy"],
        "description": "Pre-Quattro ~/.local/share/omarchy layout assumption",
        "required_if_referenced": True,
    },
]

# Legacy markers soft — warning-only when unreferenced (may reference same table).
# Kept as a separate export for clarity; values mirror HARD with note that
# presence alone is stale junk, not a hard failure.
LEGACY_MARKERS_SOFT: list[dict] = [
    {**entry, "note": "warning-only when unreferenced — stale junk does not auto-fail"}
    for entry in LEGACY_MARKERS_HARD
]

# Badge probes — orthogonal to level. Each entry declares how to detect the feature.
BADGE_PROBES: list[dict] = [
    {
        "badge_id": "transparency",
        "globs": [],
        "regexes": [r"[\w-]*fill[\w-]*alpha", r"[\w-]*border[\w-]*alpha", r"rgba\("],
        "description": "Transparency via fill/border alpha or rgba()",
    },
    {
        "badge_id": "rounded-ui",
        "globs": ["shell*.toml"],
        "regexes": [r"corner", r"corner-radius", r"radius"],
        "description": "Rounded UI — corner-radius tokens in shell*.toml",
    },
    {
        "badge_id": "custom-borders",
        "globs": ["shell*.toml"],
        "regexes": [r"border.*width", r"border.*alpha", r"border_width", r"border_alpha"],
        "description": "Custom borders — border width/alpha tokens",
    },
    {
        "badge_id": "gradient-borders",
        "globs": ["shell*.toml"],
        "regexes": [r"border.*gradient", r"gradient.*border"],
        "description": "Gradient borders — border gradient definitions",
    },
    {
        "badge_id": "light-mode",
        "globs": ["colors.toml"],
        "regexes": [r"mode\s*=\s*\"light\""],
        "description": 'Light mode — mode = "light" in colors.toml',
    },
    {
        "badge_id": "custom-shell",
        "globs": ["shell.toml"],
        "regexes": [],
        "description": "Custom shell — shell.toml override present",
    },
    {
        "badge_id": "unlock-theme",
        "globs": ["unlock.png", "preview-unlock.png", "**/unlock.png"],
        "regexes": [],
        "description": "Unlock theme — unlock.png / preview-unlock.png present",
    },
    {
        "badge_id": "icons",
        "globs": ["icons.theme", "**/icons.theme"],
        "regexes": [],
        "description": "Icons — icons.theme present",
    },
    {
        "badge_id": "wallpapers",
        "globs": ["backgrounds/*", "backgrounds/**"],
        "regexes": [],
        "description": "Wallpapers — backgrounds/ non-empty",
    },
    {
        "badge_id": "preview",
        "globs": ["preview.png", "**/preview.png"],
        "regexes": [],
        "description": "Preview — preview.png present",
    },
]

LEVEL_LABELS: dict[int, str] = {
    0: "incompatible",
    1: "legacy-compatible",
    2: "quattro-compatible",
    3: "quattro-native",
    4: "quattro-verified",
}

LEVEL_EMOJI: dict[int, str] = {
    0: "❌",
    1: "🟠",
    2: "🟡",
    3: "🟢",
    4: "💚",
}
