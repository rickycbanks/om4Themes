import tempfile
from pathlib import Path

import pytest

from om4t.schema import (
    CheckResult,
    Compatibility,
    OmarchyInfo,
    PaletteInfo,
    RunSummary,
    ThemeRecord,
    ThemesDB,
    utc_now_iso,
)


def _golden_theme() -> ThemeRecord:
    """Golden record exercising every schema field (rose-pine-custom example shape)."""
    return ThemeRecord(
        id="some-owner/rose-pine-custom",
        repo_url="https://github.com/some-owner/rose-pine-custom",
        creator="some-owner",
        description="Rose Pine custom for Omarchy",
        stars=42,
        topics=["omarchy-theme"],
        default_branch="main",
        commit_sha="abc1234deadbeef1234567890abcdef1234567890",
        official=False,
        registry=True,
        preview="https://raw.githubusercontent.com/some-owner/rose-pine-custom/main/preview.png",
        mode="dark",
        compatibility=Compatibility(
            family="omarchy-4",
            level=3,
            label="quattro-native",
            tested_against="v4.0.2",
            omarchy_commit="deadbeef1234567890abcdef1234567890abcdef12",
            analyzed_at="2026-09-02T06:12:33Z",
            rules_version="2026.09.0",
        ),
        checks=[
            CheckResult(id="colors_toml_valid", passed=True, note=None),
            CheckResult(id="renderer_clean", passed=True, note=None),
            CheckResult(id="no_required_legacy", passed=True, note=None),
            CheckResult(id="modern_conventions", passed=True, note="shell.toml present"),
            CheckResult(id="install_sim_clean", passed=False, note="neovim.lua dropped by sanitizer"),
        ],
        badges=["transparency", "rounded-ui", "wallpapers"],
        palette=PaletteInfo(missing_canonical=[], resolved_via_alias=["cursor"]),
        warnings=["stale waybar/style.css present but unreferenced"],
        error=None,
    )


def _golden_db() -> ThemesDB:
    return ThemesDB(
        schema_version=1,
        generated_at="2026-09-02T06:12:33Z",
        rules_version="2026.09.0",
        omarchy=OmarchyInfo(
            repo="omacom/omarchy",
            pin="v4.0.2",
            pin_source="latest",
            commit="deadbeef1234567890abcdef1234567890abcdef12",
        ),
        run=RunSummary(discovered=267, analyzed=265, errors=2, skipped_unchanged=180, built_at="2026-09-02"),
        themes=[_golden_theme()],
    )


def test_round_trip_equality():
    db = _golden_db()
    data = db.to_dict()
    restored = ThemesDB.from_dict(data)
    assert restored == db
    # validate passes
    restored.validate()


def test_to_json_from_json_round_trip():
    db = _golden_db()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "themes.json"
        db.to_json(p)
        loaded = ThemesDB.from_json(p)
        assert loaded == db
        loaded.validate()


def test_utc_now_iso_has_timezone():
    s = utc_now_iso()
    # must contain timezone info (Z or +00:00)
    assert "Z" in s or "+00:00" in s
    # parsable
    # replace Z with +00:00 for fromisoformat
    iso = s.replace("Z", "+00:00")
    from datetime import datetime

    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None


def test_validate_bad_level_raises():
    db = _golden_db()
    db.themes[0].compatibility.level = 99
    with pytest.raises(ValueError, match="unknown level"):
        db.validate()


def test_validate_bad_level_via_dict():
    data = _golden_db().to_dict()
    data["themes"][0]["compatibility"]["level"] = 5
    obj = ThemesDB.from_dict(data)
    with pytest.raises(ValueError, match="unknown level"):
        obj.validate()


def test_validate_missing_compatibility_field_raises():
    data = _golden_db().to_dict()
    del data["themes"][0]["compatibility"]["tested_against"]
    with pytest.raises(ValueError, match="missing compatibility field"):
        ThemesDB.from_dict(data)


def test_validate_schema_version_mismatch():
    db = _golden_db()
    db.schema_version = 2
    with pytest.raises(ValueError, match="schema_version"):
        db.validate()


def test_validate_missing_compatibility_entirely():
    data = _golden_db().to_dict()
    del data["themes"][0]["compatibility"]
    with pytest.raises(ValueError, match="missing compatibility"):
        ThemesDB.from_dict(data)
