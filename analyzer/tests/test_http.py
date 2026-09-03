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
