import time
import pytest
from unittest.mock import patch
from om4t.http import gh_api, RateLimitExhausted


def test_retry_after_then_success():
    calls = []

    def transport(path):
        calls.append(path)
        if len(calls) == 1:
            return (429, {"Retry-After": "0", "retry-after": "0"}, {})
        else:
            return (200, {}, {"items": [{"full_name": "a/b"}]})

    with patch("om4t.http.time.sleep") as mock_sleep:
        # also need to patch http.time.sleep used inside gh_api (it imports time)
        # Our gh_api uses time.sleep directly, so patching time.sleep via unittest.mock.patch on time.sleep may work if we patch om4t.http.time.sleep
        data = gh_api("search/repositories?q=topic:omarchy-theme", transport=transport)
        assert data == {"items": [{"full_name": "a/b"}]}
        assert len(calls) == 2
        # sleep should have been called once
        assert mock_sleep.called


def test_retry_with_paginate():
    # Test paginated search that hits 429 then succeeds
    call_count = {"n": 0}

    def transport(path):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (429, {"Retry-After": "0"}, {})
        # second call returns empty page to stop pagination
        return (200, {}, {"items": [], "total_count": 0})

    with patch("om4t.http.time.sleep"):
        data = gh_api("search/repositories?q=topic:omarchy-theme", paginate=True, transport=transport)
        # paginate returns list
        assert isinstance(data, list)
        assert data == []


def test_persistent_429_raises_after_3_retries():
    def transport(path):
        return (429, {"Retry-After": "0"}, {})

    with patch("om4t.http.time.sleep"):
        with pytest.raises(RateLimitExhausted):
            gh_api("search/repositories?q=topic:omarchy-theme", transport=transport)
        # Ensure it retried max 3 times => transport called 4 times (initial + 3 retries)
    # Count
    cnt = {"c": 0}

    def counting_transport(path):
        cnt["c"] += 1
        return (429, {}, {})

    with patch("om4t.http.time.sleep"):
        try:
            gh_api("x", transport=counting_transport)
        except RateLimitExhausted:
            pass
        assert cnt["c"] == 4  # 1 initial + 3 retries


def test_403_also_retries():
    cnt = {"c": 0}

    def transport(path):
        cnt["c"] += 1
        if cnt["c"] < 3:
            return (403, {}, {})
        return (200, {}, {"ok": True})

    with patch("om4t.http.time.sleep"):
        data = gh_api("repos/omacom/omarchy/releases/latest", transport=transport)
        assert data == {"ok": True}
        assert cnt["c"] == 3


def test_exponential_backoff_without_retry_after():
    delays = []

    def fake_sleep(d):
        delays.append(d)

    def transport(path):
        return (429, {}, {})

    with patch("om4t.http.time.sleep", side_effect=fake_sleep):
        with pytest.raises(RateLimitExhausted):
            gh_api("test/path", transport=transport)
        # Expect 3 sleeps with exponential 1,2,4
        assert delays == [1, 2, 4]


def test_gh_api_success_direct():
    def transport(path):
        return (200, {}, {"hello": "world"})

    data = gh_api("some/path", transport=transport)
    assert data == {"hello": "world"}


def test_add_pagination_per_page_and_page():
    from om4t.http import _add_pagination

    # No existing params
    assert _add_pagination("search/repositories?q=topic:omarchy-theme", 1) == "search/repositories?q=topic:omarchy-theme&per_page=100&page=1"
    assert _add_pagination("search/repositories?q=topic:omarchy-theme", 2) == "search/repositories?q=topic:omarchy-theme&per_page=100&page=2"
    # Existing per_page must not be corrupted when updating page
    assert _add_pagination("search/repositories?q=topic:x&per_page=100&page=1", 2) == "search/repositories?q=topic:x&per_page=100&page=2"
    assert _add_pagination("search/repositories?q=topic:x&per_page=100&page=9", 10) == "search/repositories?q=topic:x&per_page=100&page=10"
    # Ensure per_page substring not confused with page
    assert "per_page=100" in _add_pagination("search/repositories?q=topic:x", 1)
    # Already has per_page, should preserve it
    assert _add_pagination("search/repositories?q=topic:x&per_page=50&page=1", 2) == "search/repositories?q=topic:x&per_page=50&page=2"


def test_gh_api_paginate_aggregates_multi_page_with_per_page_100():
    from om4t.http import gh_api

    requested_urls = []

    def transport(path):
        requested_urls.append(path)
        # Simulate GitHub search pagination: page 1 = 100 items, page 2 = 50 items, page 3 would be 0 but we stop after <100
        import re

        m = re.search(r"[?&]page=(\d+)", path)
        page = int(m.group(1)) if m else 1
        # Verify per_page=100 in every request (regression for per_page=1 leak)
        assert "per_page=100" in path, f"expected per_page=100 in {path}"
        assert re.search(r"[?&]page=", path), f"expected page param in {path}"
        if page == 1:
            items = [{"full_name": f"owner/repo{i}", "id": i} for i in range(100)]
            return (200, {}, {"total_count": 150, "items": items})
        elif page == 2:
            items = [{"full_name": f"owner/repo{i+100}", "id": i + 100} for i in range(50)]
            return (200, {}, {"total_count": 150, "items": items})
        else:
            return (200, {}, {"total_count": 150, "items": []})

    data = gh_api("search/repositories?q=topic:omarchy-theme+is:public", paginate=True, transport=transport)
    assert isinstance(data, list)
    assert len(data) == 150
    assert data[0]["full_name"] == "owner/repo0"
    assert data[149]["full_name"] == "owner/repo149"
    # Ensure we stopped after short page (no extra call for page 3)
    assert len(requested_urls) == 2
    assert all("per_page=100" in u for u in requested_urls)


def test_gh_api_paginate_single_page_short():
    from om4t.http import gh_api

    def transport(path):
        assert "per_page=100" in path
        items = [{"full_name": f"owner/repo{i}"} for i in range(5)]
        return (200, {}, {"total_count": 5, "items": items})

    data = gh_api("search/repositories?q=topic:omarchy-theme+is:public", paginate=True, transport=transport)
    assert len(data) == 5
