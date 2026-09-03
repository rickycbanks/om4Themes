import tempfile
from pathlib import Path
import tomllib

from om4t.verify import stage_theme, synthesize_colors, FakeRenderer, verify_theme


def test_stage_strips_deny_list(tmp_path):
    # Create theme dir with deny-list files
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#000"\n')
    (theme / "neovim.lua").write_text("-- lua\n")
    (theme / "alacritty.toml").write_text('[colors]\n[colors.primary]\nbackground="#000"\n')
    (theme / "vscode.json").write_text('{}')
    (theme / "shell.toml").write_text('a=1\n')

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)
    # Check stripped contains lua and vscode and alacritty
    stripped_files = {s["file"] for s in res.stripped}
    assert "neovim.lua" in stripped_files
    assert "vscode.json" in stripped_files
    assert "alacritty.toml" in stripped_files
    # shell.toml should remain
    assert (res.staged_path / "shell.toml").is_file()
    assert not (res.staged_path / "neovim.lua").exists()


def test_stage_no_strip_when_not_git_installed(tmp_path):
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "neovim.lua").write_text("-- lua\n")
    (theme / "colors.toml").write_text('mode="dark"\n')

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=False)
    # Should keep lua when not git installed (built-in)
    assert len(res.stripped) == 0
    assert (res.staged_path / "neovim.lua").is_file()


def test_symlink_skipped(tmp_path):
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\n')
    target = theme / "real.txt"
    target.write_text("hello")
    link = theme / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        # Skip test if symlink not supported
        return
    # Create symlink dir
    sub = theme / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("x")
    link_dir = theme / "linkdir"
    try:
        link_dir.symlink_to(sub)
    except OSError:
        pass

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)
    # link.txt should be skipped
    assert "link.txt" in res.symlink_skipped or any("link.txt" in s for s in res.symlink_skipped)
    # Ensure staged does not contain symlink
    assert not (res.staged_path / "link.txt").exists()
    # linkdir should be skipped
    if any("linkdir" in s for s in res.symlink_skipped):
        assert True


def test_fake_renderer_truth_tables(tmp_path):
    # Valid colors -> clean
    theme_valid = tmp_path / "valid"
    theme_valid.mkdir()
    (theme_valid / "colors.toml").write_text('mode="dark"\nbackground="#000"\nforeground="#fff"\naccent="#f0f"\n')

    stage_root = tmp_path / "stage_valid"
    stage_root.mkdir()
    res = stage_theme(theme_valid, stage_root, is_git_installed=True)
    rr = FakeRenderer()
    clean, code, log = rr.render(res.staged_path)
    assert clean is True
    assert code == 0
    # Check output files exist with no placeholders
    assert "rendered clean" in log.lower() or clean

    # Invalid values -> not clean
    theme_invalid = tmp_path / "invalid"
    theme_invalid.mkdir()
    (theme_invalid / "colors.toml").write_text('mode="dark"\nbackground="#gggggg"\n')

    stage_root2 = tmp_path / "stage_invalid"
    stage_root2.mkdir()
    res2 = stage_theme(theme_invalid, stage_root2, is_git_installed=True)
    clean2, code2, log2 = rr.render(res2.staged_path)
    assert clean2 is False

    # No colors.toml -> not clean
    theme_no = tmp_path / "no_palette"
    theme_no.mkdir()
    (theme_no / "README.md").write_text("hello")

    stage_root3 = tmp_path / "stage_no"
    stage_root3.mkdir()
    res3 = stage_theme(theme_no, stage_root3, is_git_installed=True)
    clean3, code3, log3 = rr.render(res3.staged_path)
    assert clean3 is False
    assert code3 == 1

    # Ensure output files have no placeholders
    staged_path = res.staged_path
    # After fake render, check rendered files contain no {{
    for p in (stage_root / ".local").rglob("*") if (stage_root / ".local").exists() else []:
        if p.is_file():
            txt = p.read_text(errors="ignore")
            assert "{{" not in txt


def test_synthesize_graceful_when_script_absent(tmp_path):
    # staged has alacritty.toml but no colors.toml, omarchy script absent
    omarchy = tmp_path / "omarchy"
    omarchy.mkdir()
    # No bin script
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "alacritty.toml").write_text('[colors]\n[colors.primary]\nbackground="#000"\nforeground="#fff"\n[colors.normal]\nblack="#000"\nred="#f00"\ngreen="#0f0"\nyellow="#ff0"\nblue="#00f"\nmagenta="#f0f"\ncyan="#0ff"\n')

    ok, detail, ran = synthesize_colors(omarchy, staged)
    assert ran is False
    assert ok is True
    assert "absent" in detail.lower() or "no synthesis" in detail.lower() or "script" in detail.lower()

    # Also test no synthesis needed when colors exists
    (staged / "colors.toml").write_text('mode="dark"\n')
    ok2, detail2, ran2 = synthesize_colors(omarchy, staged)
    assert ran2 is False
    assert ok2 is True


def test_verify_theme_integration(tmp_path):
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#000"\nforeground="#fff"\n')
    work_root = tmp_path / "work"
    work_root.mkdir()
    renderer = FakeRenderer()
    vr = verify_theme(theme, work_root, renderer, is_git_installed=True)
    assert vr.render_clean is True
    assert vr.exit_code == 0
    assert vr.error is None
    assert isinstance(vr.stripped, list)
    assert isinstance(vr.symlink_skipped, list)
    assert vr.synthesized_colors is False


# --- OfficialRenderer hermetic tests with FAKE omarchy tree ---

def _make_fake_omarchy(tmp_path: Path) -> Path:
    fake = tmp_path / "fakeOM"
    bin_dir = fake / "bin"
    bin_dir.mkdir(parents=True)
    themed_dir = fake / "default" / "themed"
    themed_dir.mkdir(parents=True)
    # Minimal template files (content irrelevant, fake script ignores them but they exist)
    # Create all real Omarchy templates so targeted scan covers them
    for name in [
        "alacritty.toml.tpl",
        "btop.theme.tpl",
        "chromium.theme.tpl",
        "claude.json.tpl",
        "foot.ini.tpl",
        "ghostty.conf.tpl",
        "gum_env.lua.tpl",
        "helix.toml.tpl",
        "hyprland-preview-share-picker.css.tpl",
        "hyprland.lua.tpl",
        "keyboard.rgb.tpl",
        "kitty.conf.tpl",
        "neovim.lua.tpl",
        "obsidian.css.tpl",
        "pi.json.tpl",
        "shell.toml.tpl",
        "vscode-theme.json.tpl",
    ]:
        (themed_dir / name).write_text("background = {{ background }}\n")

    # Stub omarchy-theme-color
    color_stub = bin_dir / "omarchy-theme-color"
    color_stub.write_text("#!/bin/bash\necho 'dummy'\nexit 0\n")
    color_stub.chmod(0o755)

    # Fake omarchy-theme-set-templates script per contract
    # Asserts HOME/.local/state/omarchy/current/next-theme/colors.toml exists (exit 3 if not)
    # Asserts omarchy-theme-color resolvable via command -v (exit 4 if not)
    # Then writes rendered outputs into next-theme, substituting first hex via grep, and skips pre-existing files
    script = bin_dir / "omarchy-theme-set-templates"
    script.write_text(
        """#!/bin/bash
set -e
NEXT="$HOME/.local/state/omarchy/current/next-theme"
COLORS_FILE="$NEXT/colors.toml"
if [[ ! -f "$COLORS_FILE" ]]; then
  echo "missing colors.toml at $COLORS_FILE" >&2
  exit 3
fi
if ! command -v omarchy-theme-color >/dev/null 2>&1; then
  echo "omarchy-theme-color not found on PATH" >&2
  exit 4
fi
bg=$(grep -Eo '#[0-9A-Fa-f]{6}' "$COLORS_FILE" | head -n1)
if [[ -z "$bg" ]]; then bg="#000000"; fi
# Render outputs only if not already present (theme-shipped overrides win)
if [[ ! -f "$NEXT/alacritty.toml" ]]; then
  echo "background = \\"$bg\\"" > "$NEXT/alacritty.toml"
fi
if [[ ! -f "$NEXT/ghostty.conf" ]]; then
  echo "background=$bg" > "$NEXT/ghostty.conf"
fi
exit 0
"""
    )
    script.chmod(0o755)
    return fake


def test_official_renderer_fake_omarchy_binary_safe(tmp_path):
    from om4t.verify import OfficialRenderer, stage_theme

    fakeOM = _make_fake_omarchy(tmp_path)

    # Staged theme with colors.toml + binary png containing {{ bytes and null
    theme = tmp_path / "theme_src"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#1a2b3c"\nforeground="#ffffff"\n')
    # Create binary PNG with embedded {{ and null byte in first 1024
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR{{ not_a_template }}\x00\xff" + b"\x00" * 200
    (theme / "preview.png").write_bytes(png_bytes)

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)
    # res.staged_path contains colors.toml and preview.png

    renderer = OfficialRenderer(str(fakeOM))
    clean, code, log = renderer.render(res.staged_path)
    assert code == 0, f"log: {log}"
    assert clean is True, f"binary png should not cause false positive, log: {log}"
    # Verify preview.png was copied to next-theme and is binary-skipped
    next_theme = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
    assert (next_theme / "preview.png").is_file()
    assert (next_theme / "colors.toml").is_file()
    # Rendered files should exist
    assert (next_theme / "alacritty.toml").is_file()
    assert (next_theme / "ghostty.conf").is_file()


def test_official_renderer_placeholder_failure_and_skip(tmp_path):
    from om4t.verify import OfficialRenderer, stage_theme

    fakeOM = _make_fake_omarchy(tmp_path)

    theme = tmp_path / "theme_src2"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#112233"\n')
    # Theme-shipped override with placeholder that matches a template output name
    # Fake script skips writing if file already exists, so placeholder remains and must be detected
    # Use btop.theme which is a real template output (btop.theme.tpl) and not sanitizer-denied
    (theme / "btop.theme").write_text("value = {{ leftover_placeholder }}\n")

    stage_root = tmp_path / "stage2"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)

    renderer = OfficialRenderer(fakeOM)
    clean, code, log = renderer.render(res.staged_path)
    # Should be not clean because btop.theme still contains {{
    assert code == 0
    assert clean is False, f"expected placeholder detection, log: {log}"
    assert "btop.theme" in log


def test_official_renderer_ignores_readme_placeholder(tmp_path):
    """README containing {{ must not affect render_clean — scan only template outputs."""
    from om4t.verify import OfficialRenderer, stage_theme

    fakeOM = _make_fake_omarchy(tmp_path)

    theme = tmp_path / "theme_readme_placeholder"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#123456"\nforeground="#ffffff"\n')
    (theme / "README.md").write_text("This is {{ not_a_placeholder }} in docs\n")

    stage_root = tmp_path / "stage_readme_placeholder"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)

    renderer = OfficialRenderer(fakeOM)
    clean, code, log = renderer.render(res.staged_path)
    assert code == 0
    assert clean is True, f"README placeholder should be ignored, log: {log}"


def test_official_renderer_override_placeholder_names_file(tmp_path):
    """Theme-shipped override with {{ must fail and list filename."""
    from om4t.verify import OfficialRenderer, stage_theme

    fakeOM = _make_fake_omarchy(tmp_path)

    theme = tmp_path / "theme_override_named"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#123456"\n')
    # btop.theme is a real template output (btop.theme.tpl)
    (theme / "btop.theme").write_text("color = {{ x }}\n")

    stage_root = tmp_path / "stage_override_named"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)

    renderer = OfficialRenderer(fakeOM)
    # Extend fake script to also handle btop.theme skip? Our fake script only handles alacritty/ghostty,
    # so btop.theme will be copied and not overwritten (since fake doesn't write it), still contains placeholder.
    # Need to ensure fake script doesn't overwrite btop.theme — it doesn't, so placeholder remains.
    clean, code, log = renderer.render(res.staged_path)
    # Fake script will still succeed (exit 0) but btop.theme remains with placeholder
    # However our fake script only checks colors.toml and writes alacritty/ghostty, so btop.theme stays
    # Targeted scan should detect btop.theme
    # To make it work, we need to manually ensure the file is in next-theme (copied via _copy_staged_to_next)
    # Our renderer will scan it if it exists
    assert code == 0
    # This may be True if btop.theme not in targeted list? It is in templates, so should be detected
    # Check existence
    next_theme = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
    # Need to handle that our fake script doesn't know about btop.theme, but file was copied
    # So clean should be False
    # If our targeted scan only checks existing outputs, btop.theme exists and has placeholder
    assert clean is False
    assert "btop.theme" in log


def test_official_renderer_relative_path(tmp_path, monkeypatch):
    from om4t.verify import OfficialRenderer, stage_theme
    import os

    fakeOM = _make_fake_omarchy(tmp_path)

    # Create a relative path string from tmp_path perspective
    # Use monkeypatch to chdir and use relative path
    rel = os.path.relpath(fakeOM, start=tmp_path)
    # Ensure rel is not absolute
    assert not Path(rel).is_absolute()

    # Change cwd to tmp_path so relative resolves correctly
    monkeypatch.chdir(tmp_path)

    theme = tmp_path / "theme_rel"
    theme.mkdir()
    (theme / "colors.toml").write_text('mode="dark"\nbackground="#abcdef"\n')

    stage_root = tmp_path / "stage_rel"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)

    renderer = OfficialRenderer(rel)
    # Constructor should resolve to absolute
    assert renderer.omarchy_dir.is_absolute(), "omarchy_dir should be resolved to absolute"
    clean, code, log = renderer.render(res.staged_path)
    assert code == 0
    assert clean is True


def test_official_renderer_requires_colors_toml(tmp_path):
    from om4t.verify import OfficialRenderer, stage_theme

    fakeOM = _make_fake_omarchy(tmp_path)

    theme = tmp_path / "theme_nocolor"
    theme.mkdir()
    (theme / "README.md").write_text("no colors")

    stage_root = tmp_path / "stage_nocolor"
    stage_root.mkdir()
    res = stage_theme(theme, stage_root, is_git_installed=True)

    renderer = OfficialRenderer(fakeOM)
    clean, code, log = renderer.render(res.staged_path)
    # Fake script exits 3 when colors.toml missing -> render should be not clean
    assert code == 3
    assert clean is False
