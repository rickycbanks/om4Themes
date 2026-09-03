from pathlib import Path
from om4t.static import StaticFindings, PaletteFindings, LegacyFinding
from om4t.verify import VerifyResult
from om4t.pin import PinInfo
from om4t.grade import determine_level, grade_theme
from om4t import rules


def _palette(valid=True, mode="dark"):
    if valid:
        return PaletteFindings(mode=mode, present=["mode", "background", "foreground"], missing=[], used_aliases=[], invalid_values=[])
    else:
        return None


def _static(has_colors=True, valid=True, alacritty=False, legacy_hard=False, legacy_soft=False, uses_sanitizer=False, mode="dark"):
    palette = _palette(valid=True, mode=mode) if has_colors and valid else (None if not has_colors else PaletteFindings(mode=mode, present=[], missing=rules.CANONICAL_COLOR_KEYS, used_aliases=[], invalid_values=[{"key":"background","value":"#zzz"}] if not valid else []))
    # For valid case, palette not None and invalid empty
    if has_colors and valid:
        palette = PaletteFindings(mode=mode, present=["mode", "background"], missing=[], used_aliases=[], invalid_values=[])
    elif has_colors and not valid:
        palette = PaletteFindings(mode=mode, present=[], missing=[], used_aliases=[], invalid_values=[{"key":"background","value":"#gggg"}])
    else:
        palette = None

    legacy = []
    if legacy_hard:
        legacy.append(LegacyFinding(marker_id="waybar-config", severity="hard", path="waybar/style.css", referenced=True, note="hard"))
    if legacy_soft:
        legacy.append(LegacyFinding(marker_id="waybar-config", severity="soft", path="waybar/style.css", referenced=False, note="soft"))

    return StaticFindings(
        has_colors_toml=has_colors,
        colors_toml_valid=valid if has_colors else False,
        colors_toml_path="colors.toml" if has_colors else None,
        parse_error=None if valid else "parse error",
        palette=palette,
        alacritty_usable=alacritty,
        alacritty_detail="usable" if alacritty else "no",
        legacy=legacy,
        badges=set(),
        uses_sanitizer_stripped_for_appearance=uses_sanitizer,
    )


def _verify(render_clean=True, stripped=None, synthesized=False, error=None):
    return VerifyResult(
        render_clean=render_clean,
        exit_code=0 if render_clean else 1,
        stripped=stripped if stripped is not None else [],
        symlink_skipped=[],
        synthesized_colors=synthesized,
        error=error,
        log_excerpt="log",
    )


def _pin():
    return PinInfo(tag="v4.0.2", commit_sha="abc123"*10, published_at="2026-08-31T00:00:00Z", pin_source="latest")


def test_L0_no_palette():
    static = _static(has_colors=False, valid=False, alacritty=False)
    verify = _verify(render_clean=False)
    assert determine_level(static, verify) == 0


def test_L0_legacy_hard_no_colors():
    static = _static(has_colors=False, valid=False, alacritty=False, legacy_hard=True)
    verify = _verify(render_clean=True)
    assert determine_level(static, verify) == 0


def test_L0_colors_valid_not_render_clean():
    static = _static(has_colors=True, valid=True)
    verify = _verify(render_clean=False)
    assert determine_level(static, verify) == 0


def test_L1_alacritty_ceiling():
    static = _static(has_colors=False, valid=False, alacritty=True)
    verify = _verify(render_clean=True)
    assert determine_level(static, verify) == 1


def test_alacritty_ceiling_never_above():
    # Even with modern and install_clean, alacritty should stay 1
    static = _static(has_colors=False, valid=False, alacritty=True, legacy_hard=False, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[], error=None)
    # This is alacritty derived, so ceiling 1
    assert determine_level(static, verify) == 1


def test_L2_requires_colors_and_render():
    # Stripping is warning-only now; even with referenced terminal configs, a valid palette that renders clean is L4
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=True)
    verify = _verify(render_clean=True, stripped=[{"file": "ghostty.conf", "reason": "x"}])
    lvl = determine_level(static, verify)
    assert lvl == 4  # was 2 before stripped cap, now warning-only


def test_L3_adds_no_hard_legacy_and_modern():
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=False)
    # stripped non-empty but unreferenced (modern True) should NOT block L4 -> now L4 via install_clean without stripped check
    verify = _verify(render_clean=True, stripped=[{"file": "neovim.lua", "reason": "x"}])
    assert determine_level(static, verify) == 4


def test_L4_requires_install_sim_clean():
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[])
    assert determine_level(static, verify) == 4


def test_soft_legacy_never_demotes():
    static = _static(has_colors=True, valid=True, legacy_soft=True, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[])
    lvl = determine_level(static, verify)
    # soft legacy should not demote, so should still be 4 (since modern and install_clean true)
    assert lvl == 4
    # Also check warnings via grade_theme
    pin = _pin()
    rec = grade_theme(None, static, verify, pin, {"id": "a/b", "full_name": "a/b"})
    assert any("stale junk" in w or "waybar" in w.lower() for w in rec.warnings)
    assert rec.compatibility.level == 4


def test_legacy_hard_caps_at_1_if_valid():
    static = _static(has_colors=True, valid=True, legacy_hard=True, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[])
    assert determine_level(static, verify) == 1


def test_L4_not_without_install_clean():
    # L4 now fails only on render/error, not on stripped files
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=False)
    # Case 1: render not clean → L0 (not L4)
    verify = _verify(render_clean=False, stripped=[], error=None)
    assert determine_level(static, verify) == 0
    # Case 2: error present → install_clean false → stays L3 (render clean but error)
    verify2 = _verify(render_clean=True, stripped=[], error="render error")
    assert determine_level(static, verify2) == 3
    # Stripped alone must NOT block L4
    verify3 = _verify(render_clean=True, stripped=[{"file": "a.lua", "reason": "x"}], error=None)
    assert determine_level(static, verify3) == 4


def test_unreferenced_lua_does_not_block_L4():
    """Regression: unreferenced .lua (sanitizer stripped but not appearance-critical) must not block L4."""
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[{"file": "neovim.lua", "reason": "x"}, {"file": "vscode.json", "reason": "x"}])
    assert determine_level(static, verify) == 4
    pin = _pin()
    rec = grade_theme(None, static, verify, pin, {"id": "a/b", "full_name": "a/b"})
    assert rec.compatibility.level == 4
    assert "headless-verified" in rec.badges
    # Stripped files must appear as warning with new wording, never silent
    assert any("will be regenerated from palette by Omarchy" in w and "neovim.lua" in w for w in rec.warnings)
    assert any(c.id == "install_sim_clean" and c.passed for c in rec.checks)


def test_referenced_neovim_does_not_block_L4():
    """Referenced neovim.lua (even with uses_sanitizer True) must NOT cap — warning only."""
    static = _static(has_colors=True, valid=True, legacy_hard=False, uses_sanitizer=True)
    verify = _verify(render_clean=True, stripped=[{"file": "neovim.lua", "reason": "x"}])
    assert determine_level(static, verify) == 4
    pin = _pin()
    rec = grade_theme(None, static, verify, pin, {"id": "a/b", "full_name": "a/b"})
    assert rec.compatibility.level == 4
    assert any("will be regenerated from palette by Omarchy" in w and "neovim.lua" in w for w in rec.warnings)
    assert any(c.id == "modern_conventions" and c.passed for c in rec.checks)
    assert any(c.id == "install_sim_clean" and c.passed for c in rec.checks)


def test_nested_palette_collection_repo_reason(tmp_path):
    """Collection repo with colors deep (themes/a/colors.toml) → L0 with precise reason."""
    # Simulate collection repo: root has no colors.toml, but 2 nested palettes at depth 3+
    repo = tmp_path / "collection"
    repo.mkdir()
    (repo / "themes").mkdir()
    (repo / "themes" / "a").mkdir()
    (repo / "themes" / "b").mkdir()
    (repo / "themes" / "a" / "colors.toml").write_text('mode="dark"\nbackground="#000"\n')
    (repo / "themes" / "b" / "colors.toml").write_text('mode="dark"\nbackground="#111"\n')
    # Need README to avoid legacy hard? Not needed
    from om4t.static import analyze_repo

    static = analyze_repo(repo)
    assert static.has_colors_toml is False
    assert static.nested_palette_count == 2
    verify = _verify(render_clean=False, stripped=[])
    pin = _pin()
    rec = grade_theme(repo, static, verify, pin, {"id": "owner/collection", "full_name": "owner/collection"})
    assert rec.compatibility.level == 0
    # Check note mentions nested palettes
    c = next(x for x in rec.checks if x.id == "colors_toml_valid")
    assert "found 2 nested palettes" in c.note
    assert "collection/toolkit repo" in c.note


def test_grade_populates_schema_fields():
    static = _static(has_colors=True, valid=True, uses_sanitizer=False)
    verify = _verify(render_clean=True, stripped=[])
    pin = _pin()
    rec = grade_theme(Path("analyzer/tests/fixtures/themes/native-full"), static, verify, pin, {"id": "owner/repo", "full_name": "owner/repo", "repo_url": "https://github.com/owner/repo", "creator": "owner", "description": "desc", "stars": 5, "topics": ["omarchy-theme"], "default_branch": "main", "commit_sha": "deadbeef", "official": False, "registry": False})
    assert rec.compatibility.family == "omarchy-4"
    assert rec.compatibility.tested_against == "v4.0.2"
    assert rec.compatibility.omarchy_commit == pin.commit_sha
    assert rec.compatibility.rules_version == rules.RULES_VERSION
    assert rec.compatibility.label == rules.LEVEL_LABELS[rec.compatibility.level]
    assert rec.id == "owner/repo"
    assert len(rec.checks) >= 4
    # checks order should be evaluation order
    ids = [c.id for c in rec.checks]
    assert "colors_toml_valid" in ids
    assert "renderer_clean" in ids
    # L4 should have headless-verified badge
    assert "headless-verified" in rec.badges
    # Also palette and warnings
    assert rec.palette is not None
    assert rec.mode in ("dark", "light")


def test_level_labels_and_emoji_via_rules():
    for lvl in range(5):
        assert lvl in rules.LEVEL_LABELS
        assert lvl in rules.LEVEL_EMOJI
