"""
Canary gate per plan §9.2
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .verify import verify_theme

__all__ = ["CanaryFailure", "run_canary", "assert_canary"]


class CanaryFailure(RuntimeError):
    pass


def run_canary(omarchy_dir: str | Path, renderer, work_root: str | Path | None = None) -> dict:
    """
    Verifies every subdir of $OMARCHY/themes/ renders clean.
    Returns {total, passed, failures: [{theme, reason}]}.
    """
    omarchy_dir = Path(omarchy_dir)
    themes_dir = omarchy_dir / "themes"
    if not themes_dir.is_dir():
        raise CanaryFailure(f"canary: themes dir missing at {themes_dir}")

    theme_names = sorted([p.name for p in themes_dir.iterdir() if p.is_dir() and not p.name.startswith(".")])
    total = len(theme_names)
    if total == 0:
        raise CanaryFailure("canary: no built-in themes found")

    # work_root for verification
    if work_root is None:
        work_root = Path(tempfile.mkdtemp())
        temp_work = True
    else:
        work_root = Path(work_root)
        work_root.mkdir(parents=True, exist_ok=True)
        temp_work = False

    failures: list[dict] = []
    passed = 0

    for name in theme_names:
        theme_dir = themes_dir / name
        # For built-ins, is_git_installed=False (not sanitized)
        result = verify_theme(theme_dir, work_root, renderer, is_git_installed=False)
        if result.render_clean and (result.exit_code == 0):
            passed += 1
        else:
            reason = result.error or result.log_excerpt or f"exit_code={result.exit_code} render_clean={result.render_clean}"
            failures.append({"theme": name, "reason": reason})

    # Clean up temp work if we created it
    if temp_work:
        import shutil

        try:
            shutil.rmtree(work_root, ignore_errors=True)
        except Exception:
            pass

    return {"total": total, "passed": passed, "failures": failures}


def assert_canary(omarchy_dir: str | Path, renderer, work_root: str | Path | None = None) -> dict:
    """
    Run canary and raise CanaryFailure if any built-in fails.
    Returns same dict as run_canary on success.
    """
    result = run_canary(omarchy_dir, renderer, work_root)
    if result["failures"]:
        details = "; ".join(f"{f['theme']}: {f['reason']}" for f in result["failures"][:3])
        raise CanaryFailure(f"Canary failed: {len(result['failures'])}/{result['total']} themes failed — {details}")
    return result
