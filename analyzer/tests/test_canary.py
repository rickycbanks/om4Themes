import tempfile
from pathlib import Path
import pytest

from om4t.canary import run_canary, assert_canary, CanaryFailure
from om4t.verify import FakeRenderer


def _make_theme(dir_path: Path, name: str, valid=True):
    theme = dir_path / name
    theme.mkdir(parents=True)
    if valid:
        (theme / "colors.toml").write_text('mode="dark"\nbackground="#000"\nforeground="#fff"\n')
    else:
        (theme / "colors.toml").write_text('mode="dark"\nbackground="#gggggg"\n')  # invalid


def test_canary_fake_all_pass():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        omarchy = td_path / "omarchy"
        themes = omarchy / "themes"
        themes.mkdir(parents=True)
        _make_theme(themes, "catppuccin", valid=True)
        _make_theme(themes, "tokyo", valid=True)

        renderer = FakeRenderer()
        work = td_path / "work"
        work.mkdir()
        result = run_canary(omarchy, renderer, work)
        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["failures"] == []

        # assert_canary should not raise
        assert_canary(omarchy, renderer, work)


def test_canary_failure_raises():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        omarchy = td_path / "omarchy"
        themes = omarchy / "themes"
        themes.mkdir(parents=True)
        _make_theme(themes, "good", valid=True)
        _make_theme(themes, "bad", valid=False)

        renderer = FakeRenderer()
        work = td_path / "work"
        work.mkdir()
        result = run_canary(omarchy, renderer, work)
        assert result["total"] == 2
        assert result["passed"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["theme"] == "bad"

        with pytest.raises(CanaryFailure) as exc:
            assert_canary(omarchy, renderer, work)
        assert "Canary failed" in str(exc.value)
        assert "bad" in str(exc.value)


def test_canary_missing_themes_dir():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        omarchy = td_path / "omarchy"
        omarchy.mkdir()
        renderer = FakeRenderer()
        with pytest.raises(CanaryFailure):
            run_canary(omarchy, renderer)
