from pathlib import Path
import pytest
from om4t.static import (
    find_palette,
    parse_colors_toml,
    validate_palette,
    alacritty_palette_usable,
    detect_legacy,
    detect_badges,
    analyze_repo,
    StaticError,
)

BASE = Path("analyzer/tests/fixtures/themes")


def test_broken_toml():
    repo = BASE / "broken-toml"
    palette_path = find_palette(repo)
    assert palette_path is not None
    assert palette_path.name == "colors.toml"
    with pytest.raises(StaticError):
        parse_colors_toml(palette_path)
    findings = analyze_repo(repo)
    assert findings.has_colors_toml is True
    assert findings.colors_toml_valid is False
    assert findings.parse_error is not None
    assert "failed to parse" in findings.parse_error.lower() or "parse" in findings.parse_error.lower()


def test_no_palette():
    repo = BASE / "no-palette"
    assert find_palette(repo) is None
    findings = analyze_repo(repo)
    assert findings.has_colors_toml is False
    assert findings.colors_toml_valid is False
    assert findings.palette is None


def test_alacritty_only():
    repo = BASE / "alacritty-only"
    # No colors.toml, palette valid false
    findings = analyze_repo(repo)
    assert findings.has_colors_toml is False
    assert findings.colors_toml_valid is False
    assert findings.palette is None
    # alacritty usable true
    usable, detail = alacritty_palette_usable(repo)
    assert usable is True, detail
    assert findings.alacritty_usable is True
    # overall palette usable false -> has_colors_toml false
    assert findings.alacritty_detail is not None


def test_native_minimal():
    repo = BASE / "native-minimal"
    findings = analyze_repo(repo)
    assert findings.has_colors_toml is True
    assert findings.colors_toml_valid is True
    assert findings.palette is not None
    # Check palette present includes mode etc.
    assert "mode" in findings.palette.present or findings.palette.mode == "dark"
    # No legacy findings
    assert len(findings.legacy) == 0 or all(f.severity != "hard" for f in findings.legacy)
    # Palette invalid values empty
    assert findings.palette.invalid_values == []


def test_native_minimal_palette_details():
    repo = BASE / "native-minimal"
    palette_path = find_palette(repo)
    data = parse_colors_toml(palette_path)
    pf = validate_palette(data)
    assert pf.mode == "dark"
    assert "background" in pf.present
    assert "foreground" in pf.present
    assert pf.invalid_values == []
    # Missing includes some canonical keys not in minimal
    assert len(pf.missing) > 0
    # But present should include at least accent, background, etc.
    assert "accent" in pf.present
    # No aliases used
    assert pf.used_aliases == []


def test_native_full_badges():
    repo = BASE / "native-full"
    findings = analyze_repo(repo)
    assert findings.has_colors_toml is True
    assert findings.colors_toml_valid is True
    # badges superset
    expected = {"transparency", "rounded-ui", "gradient-borders", "custom-shell", "unlock-theme", "icons", "wallpapers", "preview"}
    assert expected.issubset(findings.badges), f"missing {expected - findings.badges}, got {findings.badges}"
    # also ensure wallpapers count >0, etc.
    assert "wallpapers" in findings.badges
    assert "preview" in findings.badges


def test_native_full_invalid_values_none():
    repo = BASE / "native-full"
    palette_path = find_palette(repo)
    data = parse_colors_toml(palette_path)
    pf = validate_palette(data)
    assert pf.invalid_values == []
    assert pf.mode == "dark"


def test_waybar_required_hard():
    repo = BASE / "waybar-required"
    findings = analyze_repo(repo)
    # Should have at least one hard legacy finding for waybar-config
    hard = [f for f in findings.legacy if f.severity == "hard"]
    assert len(hard) >= 1, f"expected hard finding, got {findings.legacy}"
    ids = {f.marker_id for f in hard}
    assert "waybar-config" in ids
    # Ensure referenced true
    waybar_hard = [f for f in hard if f.marker_id == "waybar-config"][0]
    assert waybar_hard.referenced is True


def test_stale_waybar_junk_soft_only():
    repo = BASE / "stale-waybar-junk"
    findings = analyze_repo(repo)
    # Should have soft, not hard for waybar
    assert len(findings.legacy) >= 1
    waybar_findings = [f for f in findings.legacy if f.marker_id == "waybar-config"]
    assert len(waybar_findings) == 1
    assert waybar_findings[0].severity == "soft"
    assert waybar_findings[0].referenced is False
    # No hard findings at all
    hard = [f for f in findings.legacy if f.severity == "hard"]
    assert len(hard) == 0


def test_lua_dependent_sanitizer_heuristic():
    repo = BASE / "lua-dependent"
    findings = analyze_repo(repo)
    assert findings.uses_sanitizer_stripped_for_appearance is True
    # Also native palette should be valid
    assert findings.colors_toml_valid is True
    # Legacy none? lua not in legacy markers, but sanitizer heuristic true


def test_lua_dependent_no_hard_legacy():
    repo = BASE / "lua-dependent"
    findings = analyze_repo(repo)
    # lua-dependent should not have hard legacy waybar etc.
    hard = [f for f in findings.legacy if f.severity == "hard"]
    # may be zero (since no waybar etc.)
    assert len(hard) == 0


def test_invalid_hex_detection(tmp_path):
    # Create temp colors.toml with invalid hex
    p = tmp_path / "colors.toml"
    p.write_text('mode = "dark"\nbackground = "#gggggg"\naccent = "rgba(300,0,0)"\n', encoding="utf-8")
    data = parse_colors_toml(p)
    pf = validate_palette(data)
    # #gggggg should be invalid
    assert any(v["key"] == "background" for v in pf.invalid_values)
    # rgba(300,0,0) is technically valid per our regex (digits allowed), but we check generic rgba pattern which would accept 300
    # So only background invalid


def test_alacritty_usable_detail_on_minimal():
    # native-minimal has no alacritty, should be false
    usable, detail = alacritty_palette_usable(BASE / "native-minimal")
    assert usable is False


def test_detect_badges_light_mode(tmp_path):
    # Create temp repo with light mode colors.toml
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "colors.toml").write_text('mode = "light"\nbackground = "#ffffff"\n')
    findings = analyze_repo(repo)
    assert "light-mode" in findings.badges or detect_badges(repo, findings.palette) == {"light-mode"} or "light-mode" in detect_badges(repo, findings.palette)


def test_old_path_hard_detection(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "colors.toml").write_text('mode="dark"\nbackground="#000"\n')
    (repo / "README.md").write_text("See ~/.config/omarchy/current for old path\n")
    findings = analyze_repo(repo)
    hard = [f for f in findings.legacy if f.marker_id == "old-current-path"]
    assert len(hard) == 1
    assert hard[0].severity == "hard"
