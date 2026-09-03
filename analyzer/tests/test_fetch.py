import tempfile
import subprocess
from pathlib import Path
from om4t.fetch import CacheManifest, needs_reanalysis, content_probe
from om4t import rules


def test_cache_manifest_needs_reanalysis_truth_table(tmp_path):
    manifest_path = tmp_path / "cache.json"
    cm = CacheManifest(manifest_path)
    cm.entries = {
        "owner/repo": {"commit_sha": "abc123", "rules_version": "2026.09.0", "omarchy_pin": "v4.0.2", "analyzed_at": "2026-09-02T00:00:00Z"}
    }

    class Cand:
        def __init__(self, full_name, sha):
            self.full_name = full_name
            self.commit_sha = sha

    # unchanged SHA and same rules/pin => False (skip)
    cand = Cand("owner/repo", "abc123")
    assert needs_reanalysis(cand, cm, "2026.09.0", "v4.0.2") is False

    # SHA changed => True
    cand2 = Cand("owner/repo", "different")
    assert needs_reanalysis(cand2, cm, "2026.09.0", "v4.0.2") is True

    # rules_version changed => True even if SHA same
    cand3 = Cand("owner/repo", "abc123")
    assert needs_reanalysis(cand3, cm, "2026.10.0", "v4.0.2") is True

    # omarchy_pin changed => True
    assert needs_reanalysis(cand3, cm, "2026.09.0", "v4.0.3") is True

    # missing entry => True
    cand4 = Cand("new/owner", "abc123")
    assert needs_reanalysis(cand4, cm, "2026.09.0", "v4.0.2") is True

    # candidate without sha => True (cannot determine)
    class NoSha:
        full_name = "owner/repo"
    assert needs_reanalysis(NoSha(), cm, "2026.09.0", "v4.0.2") is True

    # dict candidate
    dict_cand = {"full_name": "owner/repo", "commit_sha": "abc123"}
    assert needs_reanalysis(dict_cand, cm, "2026.09.0", "v4.0.2") is False
    dict_cand2 = {"full_name": "owner/repo", "commit_sha": "xyz"}
    assert needs_reanalysis(dict_cand2, cm, "2026.09.0", "v4.0.2") is True

    # case-insensitive full_name
    cand_case = Cand("Owner/Repo", "abc123")
    assert needs_reanalysis(cand_case, cm, "2026.09.0", "v4.0.2") is False


def test_cache_manifest_load_save(tmp_path):
    p = tmp_path / "cache.json"
    cm = CacheManifest(p)
    cm.load()
    assert cm.entries == {}
    cm.set("owner/repo", "abc", "2026.09.0", "v4.0.2", "2026-09-02T00:00:00Z", grade_file="x.json")
    cm.save()
    assert p.is_file()
    cm2 = CacheManifest(p)
    cm2.load()
    assert "owner/repo" in cm2.entries or "owner/repo".lower() in cm2.entries
    entry = cm2.get("owner/repo")
    assert entry["commit_sha"] == "abc"
    assert entry["rules_version"] == "2026.09.0"


def test_content_probe_on_fixtures():
    base = Path("analyzer/tests/fixtures/themes")
    # broken-toml has colors.toml at root -> True
    assert content_probe(base / "broken-toml") is True
    # no-palette has no colors or alacritty -> False
    assert content_probe(base / "no-palette") is False
    # alacritty-only has alacritty.toml -> True
    assert content_probe(base / "alacritty-only") is True
    # native-minimal has colors.toml -> True
    assert content_probe(base / "native-minimal") is True
    # native-full has colors.toml -> True
    assert content_probe(base / "native-full") is True
    # waybar-required -> True (has colors.toml)
    assert content_probe(base / "waybar-required") is True
    # subdir probing: create temp repo with subdir colors.toml
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sub = td_path / "subtheme"
        sub.mkdir()
        (sub / "colors.toml").write_text('mode="dark"')
        assert content_probe(td_path) is True
        # also test missing
        with tempfile.TemporaryDirectory() as td2:
            assert content_probe(Path(td2)) is False


def test_clone_shallow_and_commit_sha(tmp_path):
    # Create a local git repo to clone
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(["git", "init", str(src)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "Test"], check=True)
    (src / "colors.toml").write_text('mode="dark"')
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "commit", "-m", "init"], check=True, capture_output=True)
    # Get src sha
    result = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    src_sha = result.stdout.strip()

    from om4t.fetch import clone_shallow, commit_sha
    dest_root = tmp_path / "clones"
    repo_url = str(src)  # local path as repo_url
    fetch = clone_shallow(repo_url, dest_root)
    assert fetch.error is None
    assert fetch.path is not None
    assert fetch.path.is_dir()
    assert fetch.commit_sha == src_sha
    # commit_sha helper
    assert commit_sha(fetch.path) == src_sha
    # second clone should wipe and re-clone
    fetch2 = clone_shallow(repo_url, dest_root)
    assert fetch2.error is None
    assert fetch2.commit_sha == src_sha
