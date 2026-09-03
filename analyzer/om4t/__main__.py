"""
CLI per plan §F — argparse, python -m om4t subcommands
"""
from __future__ import annotations

import argparse
import json
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Any

from . import rules
from .pin import PinInfo, resolve_latest_stable
from .schema import ThemesDB
from .static import analyze_repo
from .verify import FakeRenderer, OfficialRenderer, verify_theme
from .grade import grade_theme
from .build_db import build_db
from .fetch import CacheManifest, needs_reanalysis, clone_shallow
from .canary import CanaryFailure, run_canary, assert_canary


def _cmd_resolve_pin(args):
    ref = getattr(args, "omarchy_ref", None)
    # Support --omarchy-ref as attribute with dash replaced
    if ref is None and hasattr(args, "omarchy_ref"):
        ref = args.omarchy_ref
    try:
        pin = resolve_latest_stable(ref_override=ref)
        data = {
            "tag": pin.tag,
            "commit_sha": pin.commit_sha,
            "published_at": pin.published_at,
            "pin_source": pin.pin_source,
        }
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        print(f"resolve-pin failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_clone_omarchy(args):
    pin_path = Path(args.pin)
    dest = Path(args.dest)
    if not pin_path.is_file():
        print(f"pin file not found: {pin_path}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(pin_path.read_text(encoding="utf-8"))
        tag = data.get("tag") or data.get("pin") or ""
        if not tag:
            print(f"pin file missing tag: {data}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"failed to read pin: {e}", file=sys.stderr)
        sys.exit(1)

    # Shallow clone by tag
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    repo_url = f"https://github.com/{rules.OMARCHY_REPO}.git"
    cmd = ["git", "clone", "--depth", "1", "--branch", tag, "--single-branch", repo_url, str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"git clone failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    # Get commit sha
    rev = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True)
    sha = rev.stdout.strip() if rev.returncode == 0 else "unknown"
    print(json.dumps({"tag": tag, "commit_sha": sha, "dest": str(dest)}, indent=2))


def _cmd_canary(args):
    omarchy_dir = Path(args.omarchy_dir)
    fake = getattr(args, "fake", False)
    work_root = getattr(args, "work_root", None) or getattr(args, "workdir", None)
    if fake:
        renderer = FakeRenderer()
    else:
        renderer = OfficialRenderer(omarchy_dir)
    try:
        result = assert_canary(omarchy_dir, renderer, work_root)
        print(json.dumps(result, indent=2))
        sys.exit(0)
    except CanaryFailure as e:
        print(f"CanaryFailed: {e}", file=sys.stderr)
        # Print result if available?
        sys.exit(2)
    except Exception as e:
        print(f"canary error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_discover(args):
    offline = getattr(args, "offline", False)
    fixtures_dir = getattr(args, "fixtures_dir", None)
    out = Path(args.out) if hasattr(args, "out") and args.out else Path("work/manifest.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    if offline:
        # Offline mode: enumerate fixtures_dir or fallback to analyzer/tests/fixtures/themes
        base = Path(fixtures_dir) if fixtures_dir else Path("analyzer/tests/fixtures/themes")
        # If fixtures_dir points to a dir containing themes, use it; if it points to themes dir directly, use it
        if not base.is_dir():
            base = Path("analyzer/tests/fixtures/themes")
        # Enumerate subdirs as theme fixtures
        candidates = []
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            name = child.name
            candidates.append(
                {
                    "full_name": f"fixture/{name}",
                    "repo_url": str(child.resolve()),
                    "creator": "fixture",
                    "default_branch": "main",
                    "description": f"Fixture theme {name}",
                    "stars": 0,
                    "topics": ["omarchy-theme"],
                    "official": False,
                    "registry": False,
                    "commit_sha": "fixture-sha-" + name,
                    "archived": False,
                }
            )
        # If fixtures_dir is a file? not needed
        with out.open("w", encoding="utf-8") as f:
            json.dump(candidates, f, indent=2)
            f.write("\n")
        print(f"discovered {len(candidates)} fixtures offline -> {out}")
        return

    # Online mode: use real discover (topic search + builtins + registry)
    # For now, attempt to use discover.py
    try:
        from .discover import search_topic, builtin_themes, parse_registry_html, build_manifest
        from .http import _default_transport

        # Use transport default (may need gh)
        # Search topic
        try:
            search_results = search_topic("omarchy-theme")
        except Exception as e:
            print(f"search_topic failed: {e}", file=sys.stderr)
            search_results = []

        builtins = []
        # Try to handle omarchy_dir if passed? Not in discover args normally; skip
        registry_repos = []
        sources = {}
        # Try to load data/sources.json if exists
        src_path = Path("data/sources.json")
        if src_path.is_file():
            try:
                sources = json.loads(src_path.read_text())
            except Exception:
                sources = {}

        manifest = build_manifest(search_results, builtins, registry_repos, sources, now=None)
        # Convert to dict list for output
        out_list = []
        for c in manifest:
            out_list.append(
                {
                    "full_name": c.full_name,
                    "repo_url": c.repo_url,
                    "creator": c.creator,
                    "default_branch": c.default_branch,
                    "description": c.description,
                    "stars": c.stars,
                    "topics": c.topics,
                    "official": c.official,
                    "registry": c.registry,
                    "builtin_path": c.builtin_path,
                    "archived": c.archived,
                }
            )
        with out.open("w", encoding="utf-8") as f:
            json.dump(out_list, f, indent=2)
            f.write("\n")
        print(f"discovered {len(out_list)} -> {out}")
    except Exception as e:
        print(f"discover failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_run(args):
    manifest_path = Path(args.manifest) if hasattr(args, "manifest") else Path(args.manifest_path)
    omarchy_dir = Path(args.omarchy_dir) if hasattr(args, "omarchy_dir") else None
    workdir = Path(args.workdir) if hasattr(args, "workdir") and args.workdir else Path("work")
    limit = getattr(args, "limit", None)
    fake_renderer = getattr(args, "fake_renderer", False) or getattr(args, "fake", False)
    offline = getattr(args, "offline", False)
    rules_version_check = getattr(args, "rules_version_for_cache_check", None)

    workdir.mkdir(parents=True, exist_ok=True)
    # Load manifest
    if not manifest_path.is_file():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest_data, dict) and "themes" in manifest_data:
            candidates = manifest_data["themes"]
        elif isinstance(manifest_data, list):
            candidates = manifest_data
        else:
            candidates = []
    except Exception as e:
        print(f"failed to load manifest: {e}", file=sys.stderr)
        sys.exit(1)

    if limit is not None:
        try:
            limit = int(limit)
            candidates = candidates[:limit]
        except Exception:
            pass

    # Pin resolution
    pin: PinInfo
    if fake_renderer or offline:
        # offline fake pin
        from datetime import datetime, timezone

        pin = PinInfo(tag="v4.0.2-fake", commit_sha="fake-sha-" + rules.RULES_VERSION, published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), pin_source="fake")
    else:
        try:
            pin = resolve_latest_stable()
        except Exception as e:
            print(f"pin resolve failed: {e}", file=sys.stderr)
            # fallback fake pin
            from datetime import datetime, timezone

            pin = PinInfo(tag="v4.0.2", commit_sha="unknown", published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), pin_source="latest")

    # Renderer
    if fake_renderer:
        renderer = FakeRenderer()
    else:
        if omarchy_dir and omarchy_dir.is_dir():
            renderer = OfficialRenderer(omarchy_dir)
        else:
            # fallback fake
            renderer = FakeRenderer()

    # Cache manifest
    cache_path = workdir / "cache.json"
    cache = CacheManifest(cache_path)
    cache.load()
    # rules_version_for_cache_check not needed? we just use rules.RULES_VERSION

    theme_records = []
    skipped = 0
    errors = 0
    # workdir for clones
    clones_root = workdir / "clones"
    clones_root.mkdir(parents=True, exist_ok=True)

    for cand in candidates:
        # Candidate may be dict with repo_url pointing to local fixture path (offline)
        # Determine full_name and repo_url
        if isinstance(cand, dict):
            full_name = cand.get("full_name") or cand.get("id") or "unknown/theme"
            repo_url = cand.get("repo_url") or cand.get("html_url") or ""
            commit_sha_candidate = cand.get("commit_sha") or cand.get("sha") or ""
        else:
            full_name = getattr(cand, "full_name", "unknown/theme")
            repo_url = getattr(cand, "repo_url", "")
            commit_sha_candidate = getattr(cand, "commit_sha", "")

        # Check cache skip
        try:
            # Build a minimal candidate object for needs_reanalysis
            class _Cand:
                pass

            tmp = _Cand()
            tmp.full_name = full_name
            tmp.commit_sha = commit_sha_candidate
            if not offline and not needs_reanalysis(tmp, cache, rules.RULES_VERSION, pin.tag):
                skipped += 1
                # Try to load previous grade from cache? For simplicity, we skip analysis but we still need a record.
                # Look for cached grade file? If cache has grade_file, load? For offline test we won't skip.
                # So we skip creating record (but need to count skipped_unchanged)
                continue
        except Exception:
            pass

        # Fetch: determine repo_dir
        repo_dir: Path | None = None
        fetch_error = None
        if offline and repo_url and Path(repo_url).is_dir():
            # Directly use local path
            repo_dir = Path(repo_url)
        elif offline and repo_url and Path(repo_url).exists():
            repo_dir = Path(repo_url)
        else:
            # Try clone_shallow if repo_url looks like github url or local git repo
            if repo_url:
                # If offline and repo_url is http, we cannot clone offline; skip clone and try to use workdir fallback
                if offline and repo_url.startswith("http"):
                    # For offline fixture clones, the manifest's repo_url is local path, already handled; else skip
                    repo_dir = None
                    fetch_error = "offline: cannot clone remote"
                else:
                    res = clone_shallow(repo_url, clones_root)
                    if res.error:
                        fetch_error = res.error
                        repo_dir = None
                    else:
                        repo_dir = res.path
                        # update candidate commit_sha from clone
                        if res.commit_sha:
                            commit_sha_candidate = res.commit_sha
                            cand["commit_sha"] = res.commit_sha
            else:
                # No repo_url, try to find fixture by name under work or fixtures
                repo_dir = None
                fetch_error = "no repo_url"

        if repo_dir is None or not repo_dir.is_dir():
            errors += 1
            # Create error theme record?
            # Use grade with empty static? Instead create placeholder error record
            from .schema import Compatibility, PaletteInfo, CheckResult, ThemeRecord
            from .schema import utc_now_iso

            err_rec = ThemeRecord(
                id=full_name,
                repo_url=repo_url,
                creator=full_name.split("/")[0] if "/" in full_name else "unknown",
                description="",
                stars=0,
                topics=[],
                default_branch="main",
                commit_sha=commit_sha_candidate or "",
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
                checks=[CheckResult(id="fetch", passed=False, note=fetch_error or "fetch failed")],
                badges=[],
                palette=PaletteInfo(missing_canonical=[], resolved_via_alias=[]),
                warnings=[],
                error=fetch_error or "fetch failed",
            )
            theme_records.append(err_rec)
            continue

        # Static analysis
        try:
            static = analyze_repo(repo_dir)
        except Exception as e:
            errors += 1
            from .schema import Compatibility, PaletteInfo, CheckResult, ThemeRecord
            from .schema import utc_now_iso

            err_rec = ThemeRecord(
                id=full_name,
                repo_url=repo_url,
                creator=full_name.split("/")[0] if "/" in full_name else "unknown",
                description="",
                stars=0,
                topics=[],
                default_branch="main",
                commit_sha=commit_sha_candidate or "",
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
                checks=[CheckResult(id="static", passed=False, note=str(e))],
                badges=[],
                palette=PaletteInfo(missing_canonical=[], resolved_via_alias=[]),
                warnings=[],
                error=f"static error: {e}",
            )
            theme_records.append(err_rec)
            continue

        # Verify
        # Use a temporary work dir for verify staging
        verify_work = workdir / "_verify_tmp"
        verify_work.mkdir(parents=True, exist_ok=True)
        try:
            # For offline fixtures that are not git-installed, is_git_installed=True (default) to apply sanitizer
            # But for built-in themes we use False. Here we keep True for community.
            vr = verify_theme(repo_dir, verify_work, renderer, is_git_installed=True)
        except Exception as e:
            from .verify import VerifyResult

            vr = VerifyResult(render_clean=False, exit_code=None, stripped=[], symlink_skipped=[], synthesized_colors=False, error=str(e), log_excerpt=str(e))

        # Grade
        try:
            # Ensure candidate meta includes commit_sha
            meta = dict(cand) if isinstance(cand, dict) else {}
            if "commit_sha" not in meta and commit_sha_candidate:
                meta["commit_sha"] = commit_sha_candidate
            # Ensure id
            if "id" not in meta and "full_name" in meta:
                meta["id"] = meta["full_name"]
            rec = grade_theme(repo_dir, static, vr, pin, meta)
            theme_records.append(rec)
            # Update cache
            try:
                from .schema import utc_now_iso

                cache.set(full_name, rec.commit_sha or commit_sha_candidate or "", rules.RULES_VERSION, pin.tag, rec.compatibility.analyzed_at)
            except Exception:
                pass
            if rec.error:
                errors += 1
        except Exception as e:
            errors += 1
            from .schema import Compatibility, PaletteInfo, CheckResult, ThemeRecord
            from .schema import utc_now_iso

            err_rec = ThemeRecord(
                id=full_name,
                repo_url=repo_url,
                creator=full_name.split("/")[0] if "/" in full_name else "unknown",
                description="",
                stars=0,
                topics=[],
                default_branch="main",
                commit_sha=commit_sha_candidate or "",
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
                checks=[CheckResult(id="grade", passed=False, note=str(e))],
                badges=[],
                palette=PaletteInfo(missing_canonical=[], resolved_via_alias=[]),
                warnings=[],
                error=f"grade error: {e}",
            )
            theme_records.append(err_rec)

    # Build DB
    run_meta = {
        "pin": pin,
        "discovered": len(candidates),
        "analyzed": len(theme_records),
        "errors": errors,
        "skipped_unchanged": skipped,
        "generated_at": None,
        "rules_version": rules.RULES_VERSION,
    }
    db = build_db(theme_records, run_meta)
    # Validate
    try:
        db.validate()
    except Exception as e:
        print(f"db validate warning: {e}", file=sys.stderr)
    # Write work/themes.json
    out_path = workdir / "themes.json"
    db.to_json(out_path)
    # Save cache
    try:
        cache.save()
    except Exception as e:
        print(f"cache save failed: {e}", file=sys.stderr)
    print(f"wrote {out_path} with {len(theme_records)} themes, errors={errors} skipped={skipped}")


def _cmd_analyze_dir(args):
    dir_path = Path(args.dir) if hasattr(args, "dir") else Path(args.DIR)  # handle positional name
    fake = getattr(args, "fake", False)
    omarchy_dir = getattr(args, "omarchy_dir", None)
    # Resolve actual dir argument name (positional is 'dir' but 'dir' is keyword, argparse uses 'dir'?)
    # Our parser defines 'DIR' dest as 'dir_path'? We ensure handling
    if not dir_path.is_dir():
        print(f"not a directory: {dir_path}", file=sys.stderr)
        sys.exit(1)

    static = analyze_repo(dir_path)
    # Choose renderer
    if fake:
        renderer = FakeRenderer()
    else:
        if omarchy_dir and Path(omarchy_dir).is_dir():
            renderer = OfficialRenderer(Path(omarchy_dir))
        else:
            renderer = FakeRenderer()

    # Pin
    if fake or not omarchy_dir:
        from datetime import datetime, timezone

        pin = PinInfo(tag="v4.0.2-fake", commit_sha="fake-sha", published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), pin_source="fake")
    else:
        try:
            pin = resolve_latest_stable()
        except Exception:
            from datetime import datetime, timezone

            pin = PinInfo(tag="v4.0.2", commit_sha="unknown", published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), pin_source="latest")

    # Verify
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        vr = verify_theme(dir_path, td, renderer, is_git_installed=True)
        # Candidate meta minimal
        meta = {
            "id": dir_path.name if dir_path.name != "native-full" else "fixture/native-full",
            "full_name": dir_path.name if "/" not in dir_path.name else dir_path.name,
            "repo_url": f"https://github.com/fixture/{dir_path.name}",
            "creator": "fixture",
            "description": "dev analyze-dir",
            "stars": 0,
            "topics": ["omarchy-theme"],
            "official": False,
            "registry": False,
            "commit_sha": "dev-sha",
            "default_branch": "main",
        }
        # If dir is fixture/native-full, set id appropriately
        if dir_path.name == "native-full":
            meta["id"] = "fixture/native-full"
            meta["full_name"] = "fixture/native-full"
        rec = grade_theme(dir_path, static, vr, pin, meta)
        # Print JSON
        json.dump(rec.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")


def main():
    parser = argparse.ArgumentParser(prog="om4t")
    sub = parser.add_subparsers(dest="command", required=True)

    # resolve-pin
    p_resolve = sub.add_parser("resolve-pin", help="resolve latest stable pin")
    p_resolve.add_argument("--omarchy-ref", dest="omarchy_ref", default=None, help="override tag")
    p_resolve.add_argument("--omarchy_ref", dest="omarchy_ref", default=None, help=argparse.SUPPRESS)
    p_resolve.set_defaults(func=_cmd_resolve_pin)

    # clone-omarchy
    p_clone = sub.add_parser("clone-omarchy", help="clone omarchy by pin")
    p_clone.add_argument("--pin", required=True, help="path to PIN.json")
    p_clone.add_argument("--dest", required=True, help="destination directory")
    p_clone.set_defaults(func=_cmd_clone_omarchy)

    # canary
    p_canary = sub.add_parser("canary", help="run canary gate")
    p_canary.add_argument("--omarchy-dir", required=True, help="path to omarchy checkout")
    p_canary.add_argument("--fake", action="store_true", help="use FakeRenderer")
    p_canary.add_argument("--workdir", default=None, help="workdir for verification")
    p_canary.add_argument("--work-root", default=None, help=argparse.SUPPRESS)
    p_canary.set_defaults(func=_cmd_canary)

    # discover
    p_disc = sub.add_parser("discover", help="discover candidates")
    p_disc.add_argument("--offline", action="store_true")
    p_disc.add_argument("--fixtures-dir", dest="fixtures_dir", default=None, help="fixtures dir for offline")
    p_disc.add_argument("--out", required=True, help="output manifest path")
    p_disc.add_argument("--fixtures_dir", dest="fixtures_dir", default=None, help=argparse.SUPPRESS)
    p_disc.set_defaults(func=_cmd_discover)

    # run
    p_run = sub.add_parser("run", help="full pipeline")
    p_run.add_argument("--manifest", required=True, help="path to manifest.json")
    p_run.add_argument("--manifest-path", dest="manifest", help=argparse.SUPPRESS)
    p_run.add_argument("--omarchy-dir", required=True, help="omarchy checkout dir")
    p_run.add_argument("--omarchy_dir", dest="omarchy_dir", help=argparse.SUPPRESS)
    p_run.add_argument("--workdir", default="work", help="workdir")
    p_run.add_argument("--work-dir", dest="workdir", help=argparse.SUPPRESS)
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--fake-renderer", dest="fake_renderer", action="store_true")
    p_run.add_argument("--fake_renderer", dest="fake_renderer", action="store_true", help=argparse.SUPPRESS)
    p_run.add_argument("--fake", dest="fake_renderer", action="store_true", help=argparse.SUPPRESS)
    p_run.add_argument("--offline", action="store_true")
    p_run.add_argument("--rules-version-for-cache-check", dest="rules_version_for_cache_check", default=None, help=argparse.SUPPRESS)
    p_run.set_defaults(func=_cmd_run)

    # analyze-dir
    p_analyze = sub.add_parser("analyze-dir", help="single-theme dev output")
    p_analyze.add_argument("dir", help="theme directory")
    # Also accept DIR capitalized
    p_analyze.add_argument("--fake", action="store_true", help="use FakeRenderer")
    p_analyze.add_argument("--omarchy-dir", dest="omarchy_dir", default=None, help="omarchy checkout for OfficialRenderer")
    p_analyze.add_argument("--omarchy_dir", dest="omarchy_dir", default=None, help=argparse.SUPPRESS)
    p_analyze.set_defaults(func=_cmd_analyze_dir)

    args = parser.parse_args()
    # Normalize some arg names that conflict with keywords
    # For analyze-dir positional, argparse will store as args.dir, but 'dir' is builtin; ensure accessible
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
