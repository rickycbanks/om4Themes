"""
Discovery: topic search, builtins, registry html parsing, manifest merge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import rules
from .http import gh_api

__all__ = [
    "Candidate",
    "search_topic",
    "builtin_themes",
    "parse_registry_html",
    "build_manifest",
]


@dataclass
class Candidate:
    full_name: str
    repo_url: str
    creator: str
    default_branch: str
    description: str
    stars: int
    topics: list[str]
    official: bool
    registry: bool
    builtin_path: str | None
    is_fork: bool
    archived: bool


def _normalize_repo_item(item: dict) -> dict:
    owner = item.get("owner", {})
    if isinstance(owner, dict):
        owner_login = owner.get("login", "")
    else:
        owner_login = str(owner)
    name = item.get("name", "")
    full_name = item.get("full_name") or f"{owner_login}/{name}" if owner_login and name else item.get("full_name", "")
    return {
        "owner": owner_login,
        "name": name,
        "full_name": full_name,
        "archived": bool(item.get("archived", False)),
        "fork": bool(item.get("fork", False)),
        "default_branch": item.get("default_branch", "main") or "main",
        "description": item.get("description") or "",
        "stargazers_count": int(item.get("stargazers_count", 0) or 0),
        "topics": list(item.get("topics", []) or []),
        "html_url": item.get("html_url") or f"https://github.com/{full_name}",
    }


def search_topic(topic: str, transport=None) -> list[dict]:
    """
    Search repositories by topic via GitHub API.
    Returns normalized dicts: owner, name, full_name, archived, fork, default_branch, description, stargazers_count, topics, html_url.
    """
    query = f"search/repositories?q=topic:{topic}+is:public"
    # gh_api paginate returns list of items
    data = gh_api(query, paginate=True, transport=transport)
    # data is list of items when paginated, or dict if not
    items: list[dict]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data:
        items = data["items"]
    else:
        items = []
    normalized = [_normalize_repo_item(it) for it in items]
    return normalized


def builtin_themes(omarchy_dir: str | Path | None) -> list[str]:
    """
    Subdirectory names of <omarchy_dir>/themes/ ; return [] if None/missing.
    """
    if omarchy_dir is None:
        return []
    p = Path(omarchy_dir) / "themes"
    if not p.is_dir():
        return []
    names: list[str] = []
    for child in p.iterdir():
        if child.is_dir():
            # ignore hidden dirs
            if child.name.startswith("."):
                continue
            names.append(child.name)
    names.sort()
    return names


# Regex to extract github.com owner/repo
# Matches https://github.com/owner/repo or http://github.com/owner/repo
# Captures owner and repo; allows trailing / or ? or # or " or '
_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)(?:(?:/[^A-Za-z0-9_.\-][^\s\"'<>]*)?)?",
    re.IGNORECASE,
)
# Alternative simpler: extract owner/repo then validate
_GITHUB_SIMPLE_RE = re.compile(r"github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)", re.IGNORECASE)

# Owners to ignore (github system paths)
_IGNORED_OWNERS = {
    "topics",
    "orgs",
    "collections",
    "features",
    "sponsors",
    "settings",
    "marketplace",
    "explore",
    "notifications",
    "codespaces",
    "login",
    "logout",
    "sessions",
    "search",
    "trending",
    "about",
    "pricing",
    "enterprise",
}

# Repo suffixes to strip: .git, trailing slash segment
_IGNORED_REPOS = {"topics"}


def parse_registry_html(html_text: str) -> list[str]:
    """
    Extract github.com/<owner>/<repo> URLs via regex (dedupe, ignore /topics, /tree etc.).
    Returns list of "owner/repo" strings deduped case-insensitively, preserving first seen case.
    """
    seen_lower: dict[str, str] = {}
    # Find all github.com owner/repo occurrences
    for m in _GITHUB_SIMPLE_RE.finditer(html_text):
        owner, repo = m.group(1), m.group(2)
        # Strip trailing .git if present (repo captured may include .git? Our regex captures up to . but need to handle)
        # Actually regex captures owner/repo where repo may be e.g., "repo.git" if URL ends with .git
        # Remove .git suffix
        if repo.lower().endswith(".git"):
            repo = repo[:-4]
        # Remove trailing punctuation that may have been captured (already limited char set, so minimal)
        # Validate owner/repo not in ignored lists
        if owner.lower() in _IGNORED_OWNERS:
            continue
        if repo.lower() in _IGNORED_REPOS:
            continue
        # Validate owner/repo look like valid github names (no consecutive dots? simple)
        # Also ignore if repo contains '.' only? but allow.
        # Ensure not capturing overly generic: e.g., github.com/owner/repo/tree -> we captured owner/repo correctly, which is good.
        # But if the URL is github.com/owner/repo/tree/main, we still want owner/repo -> valid, so keep.
        # If URL is github.com/topics/foo, owner=topics -> ignored above.
        full = f"{owner}/{repo}"
        lower = full.lower()
        if lower not in seen_lower:
            seen_lower[lower] = full
        # else dedupe

        # Note: for URLs like github.com/owner/repo/tree/main, the regex will match once for owner/repo, ignoring /tree suffix.
        # That's intended: dedupe to base repo.

    # Also handle github.com owner/repo with potential trailing path like /blob etc. already covered.

    # Return sorted for determinism? Preserve order of first appearance but sort for test determinism?
    # Keep insertion order, but sort case-insensitive for deterministic? Spec says dedupe; order not specified.
    # Return list in discovered order (dict preserves insertion order).
    return list(seen_lower.values())


def build_manifest(
    search_results: list[dict],
    builtins: list[str],
    registry_repos: list[str],
    sources: dict[str, Any] | None,
    now: Any,
) -> list[Candidate]:
    """
    Merge/dedupe by lowercase full_name; drop archived; drop forks whose parent is already included
    (best-effort via fork flag — parent detection out of scope, comment it);
    apply sources blocklist/allowlist; mark official true for builtins; cap at MAX_REPOS_PER_RUN;
    deterministic sort (stars desc, then full_name).
    """
    if sources is None:
        sources = {}
    blocklist = [s.lower() for s in sources.get("blocklist", [])]
    allowlist = [s.lower() for s in sources.get("allowlist", [])]
    allow_set = set(allowlist)
    block_set = set(blocklist)
    # seeds may be in sources; treat as extra registry-like entries
    seeds = sources.get("seeds", [])

    # Map lower full_name -> Candidate
    candidates: dict[str, Candidate] = {}

    # Helper to make candidate from search result
    for item in search_results:
        full_name = item.get("full_name", "")
        if not full_name:
            continue
        lower = full_name.lower()
        # Dedupe: keep first occurrence (highest stars? but search order is API relevance; we keep first)
        if lower in candidates:
            continue
        # archived handling deferred to filter phase, but we still create candidate now
        # Create Candidate
        cand = Candidate(
            full_name=full_name,
            repo_url=item.get("html_url") or f"https://github.com/{full_name}",
            creator=item.get("owner", ""),
            default_branch=item.get("default_branch", "main"),
            description=item.get("description", "") or "",
            stars=int(item.get("stargazers_count", 0) or 0),
            topics=list(item.get("topics", []) or []),
            official=False,
            registry=False,
            builtin_path=None,
            is_fork=bool(item.get("fork", False)),
            archived=bool(item.get("archived", False)),
        )
        candidates[lower] = cand

    # Builtins: emit as separate entries with official=true
    for name in builtins:
        # Use distinct full_name per builtin to avoid dedupe collapsing all into one
        # Keep full_name as omacom/omarchy/<name> is intuitive; task says simpler emit with builtin_path.
        # We'll use omacom/omarchy/<name> to keep uniqueness, but also set builtin_path.
        full_name = f"omacom/omarchy/{name}"
        lower = full_name.lower()
        if lower in candidates:
            # If builtin name collides with a search result that is exactly omacom/omarchy (unlikely), tweak
            # Keep builtin separate by ensuring unique key
            pass
        else:
            cand = Candidate(
                full_name=full_name,
                repo_url=f"https://github.com/omacom/omarchy/tree/quattro/themes/{name}",
                creator="omacom",
                default_branch="quattro",
                description=f"Built-in Omarchy theme: {name}",
                stars=0,
                topics=["omarchy-theme"],
                official=True,
                registry=False,
                builtin_path=f"themes/{name}",
                is_fork=False,
                archived=False,
            )
            candidates[lower] = cand
        # If already exists (should not for builtins distinct), mark official
        if lower in candidates:
            candidates[lower].official = True
            candidates[lower].builtin_path = f"themes/{name}"
            # Ensure repo_url points to tree
            if not candidates[lower].repo_url:
                candidates[lower].repo_url = f"https://github.com/omacom/omarchy/tree/quattro/themes/{name}"

    # Registry repos: list of "owner/repo" strings
    for repo_full in registry_repos:
        if not repo_full or "/" not in repo_full:
            continue
        full_name = repo_full.strip()
        # Remove potential URL prefix if passed as URL
        if "github.com" in full_name:
            m = _GITHUB_SIMPLE_RE.search(full_name)
            if m:
                full_name = f"{m.group(1)}/{m.group(2)}"
        lower = full_name.lower()
        if lower in candidates:
            candidates[lower].registry = True
        else:
            # synthesize minimal candidate for registry-only
            owner = full_name.split("/")[0]
            cand = Candidate(
                full_name=full_name,
                repo_url=f"https://github.com/{full_name}",
                creator=owner,
                default_branch="main",
                description="",
                stars=0,
                topics=[],
                official=False,
                registry=True,
                builtin_path=None,
                is_fork=False,
                archived=False,
            )
            candidates[lower] = cand

    # Seeds similarly (if seeds are repo URLs or full_names)
    for seed in seeds:
        if not seed:
            continue
        full_name = seed.strip()
        if "github.com" in full_name:
            m = _GITHUB_SIMPLE_RE.search(full_name)
            if m:
                owner, repo = m.group(1), m.group(2)
                if repo.lower().endswith(".git"):
                    repo = repo[:-4]
                full_name = f"{owner}/{repo}"
        # skip if not owner/repo format
        if "/" not in full_name:
            continue
        # Handle owner case: if seed contains scheme but not matched earlier
        lower = full_name.lower()
        if lower not in candidates:
            owner = full_name.split("/")[0]
            cand = Candidate(
                full_name=full_name,
                repo_url=f"https://github.com/{full_name}",
                creator=owner,
                default_branch="main",
                description="",
                stars=0,
                topics=[],
                official=False,
                registry=False,
                builtin_path=None,
                is_fork=False,
                archived=False,
            )
            candidates[lower] = cand

    # Apply filtering: drop archived unless allowlisted
    # Also apply blocklist; allowlist overrides blocklist and archived
    filtered: dict[str, Candidate] = {}
    for lower, cand in candidates.items():
        is_blocked = lower in block_set
        is_allowed = lower in allow_set
        # Blocklist: drop if blocked and not allowlisted
        if is_blocked and not is_allowed:
            continue
        # Archived: drop if archived and not allowlisted
        if cand.archived and not is_allowed:
            continue
        # Fork handling: best-effort via fork flag — parent detection out of scope.
        # We cannot know parent repo from fork flag alone (GitHub API would need parent field).
        # Spec says drop forks whose parent is already included, but without parent info we can't safely drop.
        # So we keep forks unless blocklisted. Commenting that parent detection is out of scope.
        # If we had parent info, we'd check: if cand.is_fork and parent_lower in candidates -> drop unless allowlisted.
        # For now, keep all forks (unless blocked/archived rules above).
        filtered[lower] = cand

    # If allowlist contains entries not yet in filtered (e.g., allowlisted archived repo that was dropped, or allowlist repo not in search),
    # ensure they are added (synthesize if needed). This handles allowlist force-include.
    for allow_full in allowlist:
        if allow_full not in filtered:
            # If it was in original candidates but dropped due to archived/block, re-add
            if allow_full in candidates:
                filtered[allow_full] = candidates[allow_full]
            else:
                # synthesize missing allowlisted repo
                owner = allow_full.split("/")[0] if "/" in allow_full else allow_full
                cand = Candidate(
                    full_name=allow_full,
                    repo_url=f"https://github.com/{allow_full}",
                    creator=owner,
                    default_branch="main",
                    description="",
                    stars=0,
                    topics=[],
                    official=False,
                    registry=False,
                    builtin_path=None,
                    is_fork=False,
                    archived=False,
                )
                filtered[allow_full] = cand

    # Deterministic sort: stars desc, then full_name asc (case-insensitive)
    sorted_cands = sorted(filtered.values(), key=lambda c: (-c.stars, c.full_name.lower()))

    # Cap at MAX_REPOS_PER_RUN
    cap = rules.MAX_REPOS_PER_RUN
    if len(sorted_cands) > cap:
        sorted_cands = sorted_cands[:cap]

    return sorted_cands
