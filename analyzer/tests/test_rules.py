from om4t import rules


def test_canonical_keys_exact():
    expected = [
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
    assert rules.CANONICAL_COLOR_KEYS == expected
    assert len(rules.CANONICAL_COLOR_KEYS) == 26


def test_rules_version_and_repo():
    assert rules.RULES_VERSION == "2026.09.0"
    assert rules.OMARCHY_REPO == "omacom/omarchy"
    assert rules.PIN_MATURITY_DAYS == 3
    assert rules.DISCOVERY_TOPICS == ["omarchy-theme"]
    assert rules.MAX_REPOS_PER_RUN == 400


def test_legacy_aliases_contains_required():
    for k in ["bg", "dark_bg", "darker_bg", "lighter_bg", "fg", "dark_fg", "light_fg", "bright_fg", "purple", "bright_purple", "cursor", "theme_type"]:
        assert k in rules.LEGACY_ALIASES


def test_sanitizer_deny():
    patterns = [p for p, _ in rules.SANITIZER_DENY]
    for pat in ["*.lua", "alacritty.toml", "foot.ini", "ghostty.conf", "kitty.conf", "vscode.json"]:
        assert pat in patterns
    # each entry has non-empty reason
    for pat, reason in rules.SANITIZER_DENY:
        assert isinstance(pat, str) and pat
        assert isinstance(reason, str) and reason


def test_legacy_markers_hard_structure():
    assert len(rules.LEGACY_MARKERS_HARD) >= 6
    ids = {e["id"] for e in rules.LEGACY_MARKERS_HARD}
    for expected_id in ["waybar-config", "mako-config", "walker-config", "swayosd-config", "hyprlock-config", "hyprland-conf", "old-current-path", "old-share-layout"]:
        assert expected_id in ids
    for entry in rules.LEGACY_MARKERS_HARD:
        assert "id" in entry and isinstance(entry["id"], str)
        assert "globs" in entry and isinstance(entry["globs"], list)
        assert "regexes" in entry and isinstance(entry["regexes"], list)
        assert "description" in entry and isinstance(entry["description"], str) and entry["description"]
        assert entry.get("required_if_referenced") is True


def test_legacy_markers_soft_exists():
    assert isinstance(rules.LEGACY_MARKERS_SOFT, list)
    assert len(rules.LEGACY_MARKERS_SOFT) == len(rules.LEGACY_MARKERS_HARD)


def test_badge_probes_structure():
    badge_ids = {e["badge_id"] for e in rules.BADGE_PROBES}
    for bid in ["transparency", "rounded-ui", "custom-borders", "gradient-borders", "light-mode", "custom-shell", "unlock-theme", "icons", "wallpapers", "preview"]:
        assert bid in badge_ids
    for entry in rules.BADGE_PROBES:
        assert "badge_id" in entry and isinstance(entry["badge_id"], str) and entry["badge_id"]
        assert "globs" in entry and isinstance(entry["globs"], list)
        assert "regexes" in entry and isinstance(entry["regexes"], list)
        # at least one of globs/regexes non-empty
        assert entry["globs"] or entry["regexes"]


def test_level_labels_and_emoji():
    assert rules.LEVEL_LABELS == {
        0: "incompatible",
        1: "legacy-compatible",
        2: "quattro-compatible",
        3: "quattro-native",
        4: "quattro-verified",
    }
    assert rules.LEVEL_EMOJI == {
        0: "❌",
        1: "🟠",
        2: "🟡",
        3: "🟢",
        4: "💚",
    }
    # emoji present for every level
    for lvl in range(5):
        assert lvl in rules.LEVEL_LABELS
        assert lvl in rules.LEVEL_EMOJI
        assert rules.LEVEL_LABELS[lvl]
        assert rules.LEVEL_EMOJI[lvl]
