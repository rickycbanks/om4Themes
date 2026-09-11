"""
Assembly + ThemesDB per plan §14
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import rules
from .schema import OmarchyInfo, RunSummary, ThemeRecord, ThemesDB, utc_now_iso
from .pin import PinInfo

__all__ = ["build_db"]


def build_db(theme_records: list[ThemeRecord | dict], run_meta: dict | Any) -> ThemesDB:
    """
    Assemble ThemesDB from theme_records and run_meta.
    Per-theme try/except → error field, never abort.
    run_meta: dict with keys discovered, analyzed, errors, skipped_unchanged, omarchy PinInfo or dict, generated_at etc.
    theme_records: list of ThemeRecord or dicts (will be coerced)
    """
    # Extract pin info
    pin: PinInfo | None = run_meta.get("pin") if isinstance(run_meta, dict) else getattr(run_meta, "pin", None)
    if isinstance(pin, dict):
        pin = PinInfo(
            tag=pin.get("tag") or pin.get("pin") or "",
            commit_sha=pin.get("commit_sha") or pin.get("commit") or "",
            published_at=pin.get("published_at") or "",
            pin_source=pin.get("pin_source") or "latest",
        )
    if pin is None:
        # Fallback try to get from run_meta directly
        tag = run_meta.get("omarchy_pin") or run_meta.get("pin_tag") or "unknown"
        commit = run_meta.get("omarchy_commit") or run_meta.get("pin_commit") or "unknown"
        pin_source = run_meta.get("pin_source") or "latest"
        pin = PinInfo(tag=tag, commit_sha=commit, published_at=run_meta.get("published_at", ""), pin_source=pin_source)

    # Build OmarchyInfo
    omarchy = OmarchyInfo(
        repo=rules.OMARCHY_REPO,
        pin=pin.tag,
        pin_source=pin.pin_source,
        commit=pin.commit_sha,
    )

    # generated_at — computed early so built_at can be derived for RunSummary
    generated_at = run_meta.get("generated_at") if isinstance(run_meta, dict) else getattr(run_meta, "generated_at", None)
    if not generated_at:
        generated_at = utc_now_iso()
    built_at = generated_at[:10]  # YYYY-MM-DD

    # RunSummary
    if isinstance(run_meta, dict):
        discovered = int(run_meta.get("discovered", len(theme_records)))
        analyzed = int(run_meta.get("analyzed", len(theme_records)))
        errors = int(run_meta.get("errors", 0))
        skipped = int(run_meta.get("skipped_unchanged", 0))
    else:
        discovered = int(getattr(run_meta, "discovered", len(theme_records)))
        analyzed = int(getattr(run_meta, "analyzed", len(theme_records)))
        errors = int(getattr(run_meta, "errors", 0))
        skipped = int(getattr(run_meta, "skipped_unchanged", 0))

    run = RunSummary(
        discovered=discovered,
        analyzed=analyzed,
        errors=errors,
        skipped_unchanged=skipped,
        built_at=built_at,
    )

    # Coerce theme_records to ThemeRecord, per-theme try/except
    themes: list[ThemeRecord] = []
    error_count = 0
    for rec in theme_records:
        try:
            if isinstance(rec, ThemeRecord):
                themes.append(rec)
            elif isinstance(rec, dict):
                # Try to convert via from_dict
                themes.append(ThemeRecord.from_dict(rec))
            else:
                # Unknown type, try to treat as object with to_dict
                if hasattr(rec, "to_dict"):
                    themes.append(ThemeRecord.from_dict(rec.to_dict()))
                else:
                    raise ValueError(f"unknown record type {type(rec)}")
        except Exception as e:
            error_count += 1
            # Create error record placeholder? Per task: per-theme try/except → error field, never abort.
            # If we cannot parse the record, we create a minimal error ThemeRecord if possible
            # Try to extract id from rec
            try:
                rec_id = rec.get("id") if isinstance(rec, dict) else getattr(rec, "id", "unknown/error")
            except Exception:
                rec_id = "unknown/error"
            # Create placeholder ThemeRecord with error
            from .schema import Compatibility, PaletteInfo, CheckResult

            try:
                placeholder = ThemeRecord(
                    id=str(rec_id),
                    repo_url=str(rec.get("repo_url", "")) if isinstance(rec, dict) else "",
                    creator="unknown",
                    description="",
                    stars=0,
                    topics=[],
                    default_branch="main",
                    commit_sha="",
                    official=False,
                    registry=False,
                    preview=None,
                    mode="dark",
                    compatibility=Compatibility(
                        family="omarchy-4",
                        level=0,
                        label=rules.LEVEL_LABELS[0],
                        tested_against=pin.tag,
                        omarchy_commit=pin.commit_sha,
                        analyzed_at=utc_now_iso(),
                        rules_version=rules.RULES_VERSION,
                    ),
                    checks=[CheckResult(id="build_error", passed=False, note=str(e))],
                    badges=[],
                    palette=PaletteInfo(missing_canonical=[], resolved_via_alias=[]),
                    warnings=[],
                    error=str(e),
                )
                themes.append(placeholder)
            except Exception:
                # If even placeholder fails, skip
                continue

    # If errors were counted from exceptions, update run.errors to reflect actual errors vs meta
    # Keep meta errors as is, but also ensure we reflect per-record errors?
    # We'll keep run.errors as provided, but if we added error placeholders, increment?
    # The task says build_db should set RunSummary with discovered, analyzed, errors, skipped_unchanged from run_meta, per-theme errors isolated into JSON error field, never abort.
    # So we don't need to auto-increment run.errors; keep as meta.

    rules_version = run_meta.get("rules_version") if isinstance(run_meta, dict) else getattr(run_meta, "rules_version", None)
    if not rules_version:
        rules_version = rules.RULES_VERSION

    db = ThemesDB(
        schema_version=1,
        generated_at=generated_at,
        rules_version=rules_version,
        omarchy=omarchy,
        run=run,
        themes=themes,
    )
    return db
