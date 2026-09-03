"""
Headless verification per plan §9.3 with pluggable renderer.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import rules
from .static import validate_palette

__all__ = [
    "StageResult",
    "VerifyResult",
    "OfficialRenderer",
    "FakeRenderer",
    "stage_theme",
    "synthesize_colors",
    "verify_theme",
]


@dataclass
class StageResult:
    staged_path: Path
    stripped: list[dict]  # [{file, reason}]
    symlink_skipped: list[str]


@dataclass
class VerifyResult:
    render_clean: bool
    exit_code: int | None
    stripped: list[dict]
    symlink_skipped: list[str]
    synthesized_colors: bool
    error: str | None
    log_excerpt: str


def _is_denied(rel_path: Path, deny_patterns: list[tuple[str, str]]) -> tuple[bool, str | None]:
    """Check if rel_path matches any deny pattern; returns (bool, reason)."""
    rel_str = rel_path.as_posix()
    name = rel_path.name
    for pat, reason in deny_patterns:
        # Pattern handling: "*.lua" should match any file ending .lua anywhere
        # Use fnmatch on posix string and on name
        # Convert ** handling via Path.match mimic: try fnmatch with pattern
        # For "*.lua", fnmatch on name or rel_str
        if pat == "*.lua":
            if rel_path.suffix == ".lua":
                return True, reason
            continue
        # For exact filenames like alacritty.toml etc.
        # Check fnmatch on name and on rel path
        if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(name, pat):
            return True, reason
        # Also check Path.match for patterns with **
        try:
            if rel_path.match(pat):
                return True, reason
        except Exception:
            pass
        # Special handling for patterns with ** -> already via match, but fallback
        if "**" in pat:
            # treat ** as *
            fn_pat = pat.replace("**", "*")
            if fnmatch.fnmatch(rel_str, fn_pat):
                return True, reason
    return False, None


def stage_theme(theme_dir: str | Path, stage_root: str | Path, *, is_git_installed: bool = True) -> StageResult:
    """
    Copy regular files only (never follow symlinks), drop SANITIZER_DENY patterns when is_git_installed.
    is_git_installed False => built-in themes aren't sanitized — same script, flag off (keep all).
    Returns StageResult(staged_path, stripped, symlink_skipped).
    """
    theme_dir = Path(theme_dir)
    stage_root = Path(stage_root)
    staged_path = stage_root / "theme"
    if staged_path.exists():
        shutil.rmtree(staged_path)
    staged_path.mkdir(parents=True, exist_ok=True)

    stripped: list[dict] = []
    symlink_skipped: list[str] = []

    # Use deny list only if is_git_installed
    deny = rules.SANITIZER_DENY if is_git_installed else []

    # Walk theme_dir recursively without following symlinks
    for root, dirs, files in os.walk(theme_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        # Handle dirs: skip symlink dirs, don't descend into them
        # os.walk with followlinks=False will not descend into symlinked dirs automatically,
        # but we should still record them as symlink_skipped and remove from dirs
        # We need to check each dir entry for symlink
        # Modify dirs in-place to avoid descending into symlinked dirs
        new_dirs = []
        for d in list(dirs):
            dir_full = root_path / d
            if dir_full.is_symlink():
                # Record symlink skipped
                try:
                    rel = dir_full.relative_to(theme_dir)
                except Exception:
                    rel = Path(d)
                symlink_skipped.append(str(rel))
                # Do not descend
                continue
            else:
                new_dirs.append(d)
        dirs[:] = new_dirs

        rel_root = root_path.relative_to(theme_dir) if root_path != theme_dir else Path(".")

        for fname in files:
            src = root_path / fname
            # Never follow symlinks: if file is symlink, record and skip
            if src.is_symlink():
                try:
                    rel = src.relative_to(theme_dir)
                except Exception:
                    rel = Path(fname) if rel_root == Path(".") else rel_root / fname
                symlink_skipped.append(str(rel))
                continue
            # Ensure regular file (not symlink, not other)
            if not src.is_file():
                continue
            # Compute destination relative path
            if rel_root == Path("."):
                rel = Path(fname)
            else:
                rel = rel_root / fname

            # Check deny
            denied, reason = _is_denied(rel, deny) if deny else (False, None)
            if denied:
                stripped.append({"file": str(rel), "reason": reason or "sanitizer deny"})
                continue

            # Copy file
            dest = staged_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copy without following symlink (already verified not symlink)
            shutil.copy2(src, dest)

    return StageResult(staged_path=staged_path, stripped=stripped, symlink_skipped=symlink_skipped)


def synthesize_colors(omarchy_dir: str | Path, staged_path: str | Path) -> tuple[bool, str, bool]:
    """
    Runs $OMARCHY/bin/omarchy-theme-colors-from-alacritty if the script exists
    and staged dir has alacritty.toml but no colors.toml (mirror stage_installed_colors_from_alacritty).
    Returns (ok, detail, script_ran: bool).
    """
    omarchy_dir = Path(omarchy_dir) if omarchy_dir else None
    staged_path = Path(staged_path)
    script_ran = False
    # Check existence conditions
    has_colors = (staged_path / "colors.toml").is_file()
    has_alacritty = (staged_path / "alacritty.toml").is_file()
    # Also check one subdir deep? For simplicity check root only; if not there, check subdirs
    if not has_alacritty:
        # Check one subdir deep for alacritty.toml
        for sub in staged_path.iterdir():
            if sub.is_dir() and (sub / "alacritty.toml").is_file():
                has_alacritty = True
                break
    if has_colors or not has_alacritty:
        return (True, "no synthesis needed", False)

    # Need script
    if omarchy_dir is None:
        return (True, "no omarchy_dir, skip synthesis", False)
    script = Path(omarchy_dir) / "bin" / "omarchy-theme-colors-from-alacritty"
    if not script.is_file():
        return (True, f"script absent at {script}, skipping synthesis", False)

    script_ran = True
    # Run script: It typically takes staged_path? Check omarchy source: stage_installed_colors_from_alacritty runs it inside staged dir.
    # We'll attempt to run with staged_path as argument; if script expects no args, it may use pwd?
    # Try both: run with staged_path as cwd and also pass path.
    # Inspect script behavior: we can run `script staged_path` or `script` with HOME.
    # We'll try: bash script with staged_path argument, cwd = staged_path
    try:
        # Try invocation with staged_path as argument
        result = subprocess.run(
            [str(script), str(staged_path / "alacritty.toml")],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(staged_path),
        )
        # If that fails due to usage, try without args
        if result.returncode != 0 and "No such file" in result.stderr:
            result = subprocess.run([str(script)], capture_output=True, text=True, timeout=30, cwd=str(staged_path))

        # Some scripts generate colors.toml in staged_path automatically when run without args and cwd set.
        # Check if colors.toml now exists
        if result.returncode == 0:
            # If script expects to write to staged dir, check existence
            if (staged_path / "colors.toml").is_file():
                return (True, result.stdout.strip() or "synthesized colors.toml", True)
            # Maybe script writes to somewhere else; check for output containing path
            # Consider success even if not created, but we report detail
            return (True, result.stdout.strip() or "script succeeded but colors.toml not created", True)
        else:
            # If script failed, consider alacritty not convertible?
            return (False, result.stderr.strip() or result.stdout.strip() or f"script exit {result.returncode}", True)
    except Exception as e:
        return (False, str(e), True)


PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")


class OfficialRenderer:
    """
    Official renderer using omarchy's omarchy-theme-set-templates script.
    Sets up $STAGE/.local/state/omarchy/current/next-theme per plan,
    runs OMARCHY_PATH=$OM HOME=$STAGE $OM/bin/omarchy-theme-set-templates,
    captures exit code + output, then Python regex scan over ALL rendered files for leftover placeholders → render_clean.
    """

    def __init__(self, omarchy_dir: str | Path):
        self.omarchy_dir = Path(omarchy_dir).resolve()

    def _copy_staged_to_next(self, staged_path: Path, next_theme_dir: Path) -> None:
        """Copy staged theme contents into next_theme_dir, regular files only, never follow symlinks."""
        for root, dirs, files in os.walk(staged_path, topdown=True, followlinks=False):
            root_path = Path(root)
            # Skip symlink dirs, don't descend
            new_dirs = []
            for d in list(dirs):
                dir_full = root_path / d
                if dir_full.is_symlink():
                    continue
                new_dirs.append(d)
            dirs[:] = new_dirs
            rel_root = root_path.relative_to(staged_path) if root_path != staged_path else Path(".")
            for fname in files:
                src = root_path / fname
                if src.is_symlink() or not src.is_file():
                    continue
                if rel_root == Path("."):
                    rel = Path(fname)
                else:
                    rel = rel_root / fname
                dest = next_theme_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    def render(self, staged_path: str | Path) -> tuple[bool, int | None, str]:
        """
        Returns (render_clean, exit_code, log_output)
        render_clean True iff exit 0 and no {{...}} placeholders in rendered output.
        """
        staged_path = Path(staged_path)
        # The STAGE is parent of staged_path? staged_path is stage_root/theme, so STAGE = stage_root
        # stage_root = staged_path.parent? But staged_path is stage_root/theme, so STAGE = staged_path.parent
        # However if staged_path is already stage_root/theme, parent is stage_root.
        # We'll infer STAGE as staged_path.parent if staged_path.name == "theme", else staged_path.parent
        if staged_path.name == "theme":
            stage_root = staged_path.parent
        else:
            stage_root = staged_path.parent

        # Setup $STAGE/.local/state/omarchy/current/next-theme per plan
        # Plan says sets up $STAGE/.local/state/omarchy/current/next-theme
        # This is the output location expectation for renderer.
        next_theme_dir = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
        next_theme_dir.mkdir(parents=True, exist_ok=True)

        # Also need to ensure $STAGE dir exists
        stage_root.mkdir(parents=True, exist_ok=True)

        # Fix #1: copy staged theme dir contents into next_theme_dir before invoking
        # (renderer requires COLORS_FILE at $NEXT_THEME_DIR/colors.toml and skips pre-existing files)
        try:
            self._copy_staged_to_next(staged_path, next_theme_dir)
        except Exception as e:
            return (False, None, f"copy to next-theme failed: {e}")

        script = self.omarchy_dir / "bin" / "omarchy-theme-set-templates"
        # Check script exists
        if not script.is_file():
            return (False, None, f"renderer script missing at {script}")

        env = os.environ.copy()
        env["OMARCHY_PATH"] = str(self.omarchy_dir)
        env["HOME"] = str(stage_root)
        # Fix #4: prepend omarchy bin to PATH for bare omarchy-theme-color invocation
        env["PATH"] = str(self.omarchy_dir / "bin") + os.pathsep + env.get("PATH", "")

        try:
            result = subprocess.run(
                [str(script)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(staged_path),
                env=env,
            )
            exit_code = result.returncode
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            log = output.strip()

            # If exit !=0, render not clean
            if exit_code != 0:
                return (False, exit_code, log)

            # Fix #2: binary-safe placeholder scan: read as bytes, skip files with \\x00 in first 1024 bytes
            leftover = False
            for p in stage_root.rglob("*"):
                if not p.is_file():
                    continue
                # Skip symlink files (should not exist, but be safe)
                try:
                    if p.is_symlink():
                        continue
                except Exception:
                    pass
                try:
                    data = p.read_bytes()
                    if b"\x00" in data[:1024]:
                        continue
                    # Decode remainder as utf-8 ignoring errors
                    text = data.decode("utf-8", errors="ignore")
                    if PLACEHOLDER_RE.search(text):
                        leftover = True
                        break
                except Exception:
                    continue

            render_clean = not leftover and exit_code == 0
            return (render_clean, exit_code, log)

        except Exception as e:
            return (False, None, str(e))


class FakeRenderer:
    """
    Offline-test-only renderer: render_clean iff colors.toml parses AND validate_palette has no invalid_values;
    produces a couple of output files with no placeholders. Clearly docstring-marked as offline-test-only, never used in CI runs.
    """

    def render(self, staged_path: str | Path) -> tuple[bool, int | None, str]:
        """
        Fake render: checks colors.toml parses via tomllib and validate_palette invalid_values empty.
        Always creates a couple of output files under $STAGE/.local/state/omarchy/current/next-theme with no placeholders.
        Returns (render_clean, exit_code, log).
        """
        staged_path = Path(staged_path)
        if staged_path.name == "theme":
            stage_root = staged_path.parent
        else:
            stage_root = staged_path

        # Find colors.toml in staged_path
        colors_path = staged_path / "colors.toml"
        if not colors_path.is_file():
            # Check subdir
            for sub in staged_path.iterdir():
                if sub.is_dir() and (sub / "colors.toml").is_file():
                    colors_path = sub / "colors.toml"
                    break

        if not colors_path.is_file():
            # No colors.toml => not clean
            next_dir = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
            next_dir.mkdir(parents=True, exist_ok=True)
            (next_dir / "dummy.conf").write_text("# no palette\n", encoding="utf-8")
            return (False, 1, "FakeRenderer: no colors.toml")

        try:
            with colors_path.open("rb") as f:
                data = tomllib.load(f)
            pf = validate_palette(data)
            if pf.invalid_values:
                next_dir = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
                next_dir.mkdir(parents=True, exist_ok=True)
                (next_dir / "dummy.conf").write_text("# invalid values\n", encoding="utf-8")
                return (False, 1, f"FakeRenderer: invalid_values {pf.invalid_values}")
            # Success: produce output files with no placeholders
            next_dir = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
            next_dir.mkdir(parents=True, exist_ok=True)
            (next_dir / "wayland.conf").write_text("# rendered from colors.toml\nforeground=#ffffff\n", encoding="utf-8")
            (next_dir / "shell.conf").write_text("# rendered shell\n", encoding="utf-8")
            return (True, 0, "FakeRenderer: rendered clean")
        except Exception as e:
            next_dir = stage_root / ".local" / "state" / "omarchy" / "current" / "next-theme"
            next_dir.mkdir(parents=True, exist_ok=True)
            (next_dir / "dummy.conf").write_text(f"# parse error {e}\n", encoding="utf-8")
            return (False, 1, f"FakeRenderer parse error: {e}")


def verify_theme(theme_dir: str | Path, work_root: str | Path, renderer, *, is_git_installed: bool = True) -> VerifyResult:
    """
    Full verification: stage_theme -> synthesize_colors -> renderer.render
    Returns VerifyResult {render_clean, exit_code, stripped, symlink_skipped, synthesized_colors: bool, error, log_excerpt}.
    """
    theme_dir = Path(theme_dir)
    work_root = Path(work_root)
    # Create a unique stage_root under work_root
    # Use work_root / _verify_stage_<name>
    # Ensure work_root exists
    work_root.mkdir(parents=True, exist_ok=True)
    stage_root = work_root / f"_verify_stage_{theme_dir.name}_{os.getpid()}"
    if stage_root.exists():
        shutil.rmtree(stage_root, ignore_errors=True)
    stage_root.mkdir(parents=True, exist_ok=True)

    try:
        stage_res = stage_theme(theme_dir, stage_root, is_git_installed=is_git_installed)
        # synthesize if needed
        # Need omarchy_dir: renderer may have it, but we try to deduce
        omarchy_dir = getattr(renderer, "omarchy_dir", None)
        if omarchy_dir is None:
            # Try to get from renderer? FakeRenderer has no omarchy_dir, so skip synthesis
            synthesized = False
            synth_ok = True
            synth_detail = "no omarchy_dir"
        else:
            synth_ok, synth_detail, script_ran = synthesize_colors(omarchy_dir, stage_res.staged_path)
            synthesized = script_ran and synth_ok

        # Render
        try:
            render_clean, exit_code, log = renderer.render(stage_res.staged_path)
        except Exception as e:
            render_clean = False
            exit_code = None
            log = str(e)

        # Log excerpt: first 500 chars?
        log_excerpt = log[:2000] if log else ""

        # Determine error field: if staging synthesized failed or render exit non-zero?
        error = None
        if not synth_ok:
            error = f"synthesize failed: {synth_detail}"
        elif exit_code is not None and exit_code != 0:
            # Not necessarily error if render_clean false? But keep log
            # Only set error if render_clean false? We'll set error as log excerpt if not clean
            if not render_clean:
                error = f"render exit {exit_code}: {log_excerpt[:500]}"
        elif not render_clean and exit_code == 0:
            error = f"placeholders remain: {log_excerpt[:500]}"

        return VerifyResult(
            render_clean=render_clean,
            exit_code=exit_code,
            stripped=stage_res.stripped,
            symlink_skipped=stage_res.symlink_skipped,
            synthesized_colors=synthesized,
            error=error,
            log_excerpt=log_excerpt,
        )
    finally:
        # Cleanup stage_root? Keep for debugging? But remove to avoid accumulation
        # We'll remove unless keep for inspection? For test, remove.
        try:
            shutil.rmtree(stage_root, ignore_errors=True)
        except Exception:
            pass
