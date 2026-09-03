"""
Fetch: shallow clone, commit SHA, cache manifest, content probe.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["FetchResult", "clone_shallow", "commit_sha", "CacheManifest", "needs_reanalysis", "content_probe"]


@dataclass
class FetchResult:
    path: Path | None
    commit_sha: str | None
    error: str | None


def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    Extract owner and repo from URL like https://github.com/owner/repo or owner/repo.
    Strips .git suffix.
    """
    s = repo_url.strip()
    # Remove scheme
    if "://" in s:
        s = s.split("://", 1)[1]
        # Remove github.com/ prefix if present
        if s.startswith("github.com/"):
            s = s[len("github.com/") :]
        elif "/" in s:
            # Handle custom host? just take after first slash?
            # For github URL, host is github.com, already stripped
            pass
    # Now s should be owner/repo maybe with extra path
    # Remove tail after repo: e.g., owner/repo/tree/... -> take first two segments
    parts = s.split("/")
    # Filter empty
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        owner = parts[0]
        repo = parts[1]
        # Strip .git
        if repo.endswith(".git"):
            repo = repo[:-4]
        return (owner, repo)
    elif len(parts) == 1:
        return (parts[0], parts[0])
    else:
        return ("unknown", "unknown")


def clone_shallow(repo_url: str, dest_root: str | Path, branch: str | None = None) -> FetchResult:
    """
    Clone shallow into work/clones/<owner>/<repo> (wipe if exists).
    git clone --depth 1 --single-branch [--branch <branch>] repo_url dest_path
    Returns FetchResult {path, commit_sha, error}. Never follows cloned content beyond cloning.
    """
    dest_root = Path(dest_root)
    owner, repo = _parse_repo_url(repo_url)
    dest_path = dest_root / owner / repo
    # Wipe if exists
    if dest_path.exists():
        shutil.rmtree(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "clone", "--depth", "1", "--single-branch"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo_url, str(dest_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"git clone failed with {result.returncode}"
            return FetchResult(path=None, commit_sha=None, error=err)
    except Exception as e:
        return FetchResult(path=None, commit_sha=None, error=str(e))

    # Get commit SHA
    try:
        sha = commit_sha(dest_path)
        return FetchResult(path=dest_path, commit_sha=sha, error=None)
    except Exception as e:
        return FetchResult(path=dest_path, commit_sha=None, error=f"clone succeeded but rev-parse failed: {e}")


def commit_sha(path: str | Path) -> str:
    """
    git -C <path> rev-parse HEAD
    """
    p = Path(path)
    result = subprocess.run(["git", "-C", str(p), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse failed in {p}: {result.stderr.strip()}")
    return result.stdout.strip()


class CacheManifest:
    """
    Maps full_name -> {commit_sha, rules_version, omarchy_pin, analyzed_at, grade_file}
    Stored at work/cache.json.
    """

    def __init__(self, path: str | Path = "work/cache.json"):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}

    def load(self) -> None:
        if not self.path.is_file():
            self.entries = {}
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # Expect dict of full_name lower -> entry
            # Could also be { "entries": {...}} depending on previous; handle both
            if isinstance(data, dict) and "entries" in data and isinstance(data["entries"], dict):
                self.entries = {k.lower(): v for k, v in data["entries"].items()}
            elif isinstance(data, dict):
                # Assume direct map
                # Detect if keys look like owner/repo
                self.entries = {k.lower(): v for k, v in data.items()}
            else:
                self.entries = {}
        except Exception:
            self.entries = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Save as dict with lower keys to ensure deterministic
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, sort_keys=True)
            f.write("\n")

    def get(self, full_name: str) -> dict | None:
        return self.entries.get(full_name.lower())

    def set(self, full_name: str, commit_sha: str, rules_version: str, omarchy_pin: str, analyzed_at: str, grade_file: str | None = None) -> None:
        self.entries[full_name.lower()] = {
            "commit_sha": commit_sha,
            "rules_version": rules_version,
            "omarchy_pin": omarchy_pin,
            "analyzed_at": analyzed_at,
            "grade_file": grade_file,
        }

    def update(self, full_name: str, **kwargs: Any) -> None:
        lower = full_name.lower()
        entry = self.entries.get(lower, {})
        entry.update(kwargs)
        self.entries[lower] = entry


def needs_reanalysis(candidate: Any, manifest: CacheManifest, rules_version: str, omarchy_pin: str) -> bool:
    """
    Per plan §7: unchanged SHA AND unchanged rules/pin → False (skip). Otherwise True.
    candidate: object with full_name and commit_sha/sha attribute or dict.
    manifest: CacheManifest already loaded.
    """
    # Extract full_name
    if isinstance(candidate, dict):
        full_name = candidate.get("full_name") or candidate.get("fullName") or candidate.get("id") or ""
        cand_sha = candidate.get("commit_sha") or candidate.get("commitSha") or candidate.get("sha") or candidate.get("commitSHA")
    else:
        full_name = getattr(candidate, "full_name", None) or getattr(candidate, "fullName", None) or getattr(candidate, "id", None) or ""
        cand_sha = getattr(candidate, "commit_sha", None) or getattr(candidate, "commitSha", None) or getattr(candidate, "sha", None)
        # Also check repo_url? No
        if cand_sha is None and hasattr(candidate, "sha"):
            cand_sha = candidate.sha

    if not full_name:
        return True

    entry = manifest.get(full_name)
    if entry is None:
        return True

    # Compare SHA, rules_version, omarchy_pin
    entry_sha = entry.get("commit_sha")
    entry_rules = entry.get("rules_version")
    entry_pin = entry.get("omarchy_pin")

    # If candidate sha is None/unknown, we cannot determine unchanged; so need reanalysis
    if cand_sha is None:
        # If manifest has no sha either, then compare rules/pin
        if entry_sha is None:
            # No SHA info: check rules/pin
            if entry_rules == rules_version and entry_pin == omarchy_pin:
                return False
            return True
        return True

    # All three must match to skip
    if cand_sha == entry_sha and entry_rules == rules_version and entry_pin == omarchy_pin:
        return False
    return True


def content_probe(repo_dir: str | Path) -> bool:
    """
    Quick presence check: colors.toml or alacritty.toml anywhere at root or one subdir deep.
    """
    p = Path(repo_dir)
    if not p.is_dir():
        return False
    # Root
    if (p / "colors.toml").is_file() or (p / "alacritty.toml").is_file():
        return True
    # One subdir deep
    for child in p.iterdir():
        if child.is_dir():
            if (child / "colors.toml").is_file() or (child / "alacritty.toml").is_file():
                return True
    return False
