import subprocess
import json
import tempfile
from pathlib import Path
import sys

import pytest
from om4t.schema import ThemesDB


def _run_cli(args, cwd=None):
    # Use .venv/bin/python
    cmd = [".venv/bin/python", "-m", "om4t"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result


def test_cli_analyze_dir_fake():
    # Test analyze-dir on native-full fixture with fake renderer -> level >=2
    result = _run_cli(["analyze-dir", "analyzer/tests/fixtures/themes/native-full", "--fake"])
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    data = json.loads(result.stdout)
    assert "compatibility" in data
    level = data["compatibility"]["level"]
    assert level >= 2, f"expected level >=2 got {level} data {data}"
    assert data["compatibility"]["family"] == "omarchy-4"
    assert "badges" in data
    # Should have headless-verified if level 4, but at least some badges
    assert isinstance(data["badges"], list)


def test_cli_run_offline_with_fake_renderer():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        work = td_path / "work"
        work.mkdir()
        manifest = work / "manifest.json"
        # discover offline
        res_disc = _run_cli(["discover", "--offline", "--fixtures-dir", "analyzer/tests/fixtures/themes", "--out", str(manifest)])
        assert res_disc.returncode == 0, f"discover failed: {res_disc.stderr}"
        assert manifest.is_file()
        data = json.loads(manifest.read_text())
        assert len(data) >= 2

        # run with offline and fake renderer, limit 2
        # Need a fake omarchy dir
        fake_omarchy = td_path / "omarchy"
        fake_omarchy.mkdir()
        # Create minimal omarchy structure? Not needed for fake renderer
        res_run = _run_cli(["run", "--manifest", str(manifest), "--omarchy-dir", str(fake_omarchy), "--workdir", str(work), "--limit", "2", "--fake-renderer", "--offline"])
        assert res_run.returncode == 0, f"run failed: {res_run.stderr}\n{res_run.stdout}"
        themes_json = work / "themes.json"
        assert themes_json.is_file(), f"themes.json not created, stdout {res_run.stdout} stderr {res_run.stderr}"
        db = ThemesDB.from_json(themes_json)
        db.validate()
        assert len(db.themes) >= 1
        assert db.omarchy.repo == "omacom/omarchy"
        assert db.schema_version == 1
        # Check run summary
        assert db.run.discovered >= 1
        assert db.run.built_at, "built_at should be populated"


def test_cli_resolve_pin_help():
    result = _run_cli(["resolve-pin", "--help"])
    assert result.returncode == 0
    assert "resolve-pin" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_canary_fake():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        omarchy = td_path / "omarchy"
        themes = omarchy / "themes"
        themes.mkdir(parents=True)
        # Create one good theme
        t = themes / "good"
        t.mkdir()
        (t / "colors.toml").write_text('mode="dark"\nbackground="#000"\nforeground="#fff"\n')
        result = _run_cli(["canary", "--omarchy-dir", str(omarchy), "--fake"])
        assert result.returncode == 0, f"canary failed: {result.stderr}"
        # Should output json
        assert "total" in result.stdout.lower() or "passed" in result.stdout.lower()
