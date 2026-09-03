from pathlib import Path
import tempfile
from om4t.discover import search_topic, builtin_themes, parse_registry_html, build_manifest
from om4t import rules

# Helpers

def make_search_item(full_name, stars=10, archived=False, fork=False, description="desc", owner=None):
    owner = owner or full_name.split("/")[0]
    name = full_name.split("/")[1] if "/" in full_name else full_name
    return {
        "owner": owner,
        "name": name,
        "full_name": full_name,
        "archived": archived,
        "fork": fork,
        "default_branch": "main",
        "description": description,
        "stargazers_count": stars,
        "topics": ["omarchy-theme"],
        "html_url": f"https://github.com/{full_name}",
    }


def test_dedupe_and_archived_dropped():
    search_results = [
        make_search_item("ownerA/repo1", stars=100),
        make_search_item("ownera/repo1", stars=5),  # dedupe case-insensitive, should keep first
        make_search_item("ownerB/archived-repo", stars=50, archived=True),
        make_search_item("ownerC/active", stars=20),
    ]
    builtins = []
    registry_repos = []
    sources = {"blocklist": [], "allowlist": []}
    manifest = build_manifest(search_results, builtins, registry_repos, sources, now=None)
    full_names = [c.full_name.lower() for c in manifest]
    assert "ownera/repo1" not in full_names or "ownera/repo1" == "ownera/repo1"  # check dedupe logic
    # Archived should be dropped
    assert "ownerb/archived-repo" not in full_names
    # Active should remain
    assert "ownerc/active" in full_names
    # Dedupe: only one of ownerA/repo1
    assert full_names.count("ownera/repo1") == 1


def test_blocklist_applied():
    search_results = [
        make_search_item("spam/bad", stars=100),
        make_search_item("good/keep", stars=10),
    ]
    sources = {"blocklist": ["spam/bad"], "allowlist": []}
    manifest = build_manifest(search_results, [], [], sources, now=None)
    names = [c.full_name.lower() for c in manifest]
    assert "spam/bad" not in names
    assert "good/keep" in names


def test_allowlist_overrides_blocklist():
    search_results = [
        make_search_item("spam/bad", stars=10, archived=True),
    ]
    sources = {"blocklist": ["spam/bad"], "allowlist": ["spam/bad"]}
    manifest = build_manifest(search_results, [], [], sources, now=None)
    names = [c.full_name.lower() for c in manifest]
    assert "spam/bad" in names


def test_cap_applied():
    many = [make_search_item(f"owner{i}/repo{i}", stars=i) for i in range(500)]
    manifest = build_manifest(many, [], [], {"blocklist": [], "allowlist": []}, now=None)
    assert len(manifest) <= rules.MAX_REPOS_PER_RUN
    assert len(manifest) == rules.MAX_REPOS_PER_RUN


def test_builtins_marked_official():
    search_results = []
    builtins = ["catppuccin", "tokyo-night"]
    manifest = build_manifest(search_results, builtins, [], {"blocklist": [], "allowlist": []}, now=None)
    # Should have 2 entries, both official
    assert len(manifest) == 2
    for c in manifest:
        assert c.official is True
        assert c.builtin_path is not None
        assert c.builtin_path.startswith("themes/")
        assert "omacom/omarchy" in c.full_name.lower()
        assert "https://github.com/omacom/omarchy" in c.repo_url


def test_registry_parse_ignores_non_repo_urls():
    html = Path("analyzer/tests/fixtures/registry_sample.html").read_text()
    # Also test raw string
    repos = parse_registry_html(html)
    lower = [r.lower() for r in repos]
    assert "owner1/theme-one" in lower
    assert "owner2/theme-two" in lower
    assert "owner3/theme-three" in lower
    # Non-repo URLs should be ignored
    assert "topics/omarchy-theme" not in lower
    assert "explore" not in lower
    # dedupe: owner1/theme-one appears twice but should be once
    assert lower.count("owner1/theme-one") == 1
    assert len(repos) == 3


def test_search_topic_uses_transport():
    items = [
        {"owner": {"login": "alice"}, "name": "theme-a", "full_name": "alice/theme-a", "archived": False, "fork": False, "default_branch": "main", "description": "a", "stargazers_count": 5, "topics": [], "html_url": "https://github.com/alice/theme-a"},
        {"owner": {"login": "bob"}, "name": "theme-b", "full_name": "bob/theme-b", "archived": False, "fork": False, "default_branch": "main", "description": "b", "stargazers_count": 10, "topics": [], "html_url": "https://github.com/bob/theme-b"},
    ]

    def transport(path):
        # search_topic will paginate: we need to handle per_page/page params
        # Return dict with items for first page, empty for subsequent
        if "page=1" in path or "page=" not in path:
            return (200, {}, {"items": items, "total_count": 2})
        else:
            return (200, {}, {"items": [], "total_count": 2})

    result = search_topic("omarchy-theme", transport=transport)
    assert len(result) == 2
    assert result[0]["full_name"] == "alice/theme-a"
    assert result[1]["owner"] == "bob"


def test_builtin_themes_function(tmp_path):
    # missing dir returns []
    assert builtin_themes(None) == []
    assert builtin_themes("/nonexistent/path") == []
    # create temp omarchy dir with themes
    om = tmp_path / "omarchy"
    themes = om / "themes"
    themes.mkdir(parents=True)
    (themes / "theme-a").mkdir()
    (themes / "theme-b").mkdir()
    (themes / ".hidden").mkdir()
    result = builtin_themes(str(om))
    assert result == ["theme-a", "theme-b"]


def test_build_manifest_deterministic_sort():
    search_results = [
        make_search_item("a/low", stars=5),
        make_search_item("b/high", stars=100),
        make_search_item("c/mid", stars=50),
        make_search_item("a2/high2", stars=100),  # tie on stars -> full_name sort
    ]
    manifest = build_manifest(search_results, [], [], {"blocklist": [], "allowlist": []}, now=None)
    # Expect stars desc, then full_name
    # b/high and a2/high2 both 100, sorted by full_name: a2/high2 before b/high ?
    # full_name.lower comparison: "a2/high2" < "b/high" => a2 first
    assert manifest[0].full_name == "a2/high2"
    assert manifest[1].full_name == "b/high"
    assert manifest[2].full_name == "c/mid"
    assert manifest[3].full_name == "a/low"


def test_registry_repos_mark_registry():
    search_results = [make_search_item("owner1/theme-one", stars=10)]
    registry_repos = ["owner1/theme-one", "owner2/new-repo"]
    manifest = build_manifest(search_results, [], registry_repos, {"blocklist": [], "allowlist": []}, now=None)
    by_name = {c.full_name.lower(): c for c in manifest}
    assert by_name["owner1/theme-one"].registry is True
    assert by_name["owner2/new-repo"].registry is True
    assert by_name["owner2/new-repo"].stars == 0
