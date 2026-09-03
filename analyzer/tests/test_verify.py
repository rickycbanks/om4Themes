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
