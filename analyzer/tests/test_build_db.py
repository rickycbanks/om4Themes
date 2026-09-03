import tempfile
from pathlib import Path
from om4t.build_db import build_db
from om4t.schema import ThemeRecord, Compatibility, PaletteInfo, CheckResult, ThemesDB
from om4t.pin import PinInfo
from om4t import rules


def _make_pin():
    return PinInfo(tag="v4.0.2", commit_sha="abc123"*10, published_at="2026-08-31T00:00:00Z", pin_source="latest")


def _make_record(id="a/b", level=2):
    return ThemeRecord(
        id=id,
        repo_url=f"https://github.com/{id}",
        creator=id.split("/")[0],
        description="desc",
        stars=1,
        topics=["omarchy-theme"],
        default_branch="main",
        commit_sha="deadbeef"*5,
        official=False,
        registry=False,
        preview=None,
        mode="dark",
        compatibility=Compatibility(
            family="omarchy-4",
            level=level,
            label=rules.LEVEL_LABELS[level],
            tested_against="v4.0.2",
            omarchy_commit="abc123"*10,
            analyzed_at="2026-09-02T06:12:33Z",
            rules_version=rules.RULES_VERSION,
        ),
        checks=[CheckResult(id="colors_toml_valid", passed=True, note=None)],
        badges=[],
        palette=PaletteInfo(missing_canonical=[], resolved_via_alias=[]),
        warnings=[],
        error=None,
    )


def test_build_db_basic():
    pin = _make_pin()
    records = [_make_record("a/b", 2), _make_record("c/d", 3)]
    run_meta = {"pin": pin, "discovered": 2, "analyzed": 2, "errors": 0, "skipped_unchanged": 0}
    db = build_db(records, run_meta)
    assert db.schema_version == 1
    assert db.omarchy.pin == "v4.0.2"
    assert db.omarchy.pin_source == "latest"
    assert db.run.discovered == 2
    assert len(db.themes) == 2
    db.validate()


def test_build_db_per_theme_error_isolation():
    pin = _make_pin()
    good = _make_record("good/theme", 2)
    # Bad record: dict that will fail validation but build_db should isolate
    bad_dict = {"id": "bad/theme", "repo_url": "https://github.com/bad/theme"}  # missing compatibility -> will cause error but we handle via try
    # Another bad: completely invalid type
    records = [good, bad_dict, "not-a-record"]
    run_meta = {"pin": pin, "discovered": 3, "analyzed": 1, "errors": 1, "skipped_unchanged": 0}
    db = build_db(records, run_meta)
    # Should have created placeholders for bad records, not abort
    assert len(db.themes) >= 1
    # Validate should pass (placeholders have level 0)
    db.validate()
    # At least one has error
    assert any(t.error is not None for t in db.themes)


def test_build_db_dict_coercion():
    pin = _make_pin()
    rec = _make_record("x/y", 1)
    dict_rec = rec.to_dict()
    run_meta = {"pin": pin, "discovered": 1, "analyzed": 1, "errors": 0, "skipped_unchanged": 0}
    db = build_db([dict_rec], run_meta)
    assert db.themes[0].id == "x/y"
    db.validate()
