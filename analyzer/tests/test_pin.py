from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from om4t.pin import PinInfo, resolve_latest_stable


FIXED_NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def _make_release(tag, days_ago, draft=False, prerelease=False, published_at=None, now=None):
    base = now if now is not None else FIXED_NOW
    if published_at is None:
        dt = base - timedelta(days=days_ago)
        published_at = dt.isoformat().replace("+00:00", "Z")
    return {
        "tag_name": tag,
        "published_at": published_at,
        "draft": draft,
        "prerelease": prerelease,
        "target_commitish": "fake-sha-" + tag,
        "commit_sha": "sha-" + tag,
    }


def test_young_latest_fallback():
    now = FIXED_NOW
    # Newest is 1 day old (too young, maturity 3), next is 5 days old (qualifies)
    releases = [
        _make_release("v4.0.3", days_ago=1, now=now),
        _make_release("v4.0.2", days_ago=5, now=now),
        _make_release("v4.0.1", days_ago=10, now=now),
    ]

    def transport(path):
        assert "releases" in path
        return (200, {}, releases)

    pin = resolve_latest_stable(transport=transport, now=now, maturity_days=3)
    assert pin.tag == "v4.0.2"
    assert pin.pin_source == "latest"
    # Should have commit_sha derived
    assert pin.commit_sha is not None
    assert pin.published_at is not None


def test_prerelease_skip():
    now = FIXED_NOW
    releases = [
        _make_release("v4.1.0-rc1", days_ago=5, prerelease=True, now=now),
        _make_release("v4.0.2", days_ago=5, now=now),
        _make_release("v4.0.3-draft", days_ago=6, draft=True, now=now),
    ]

    def transport(path):
        return (200, {}, releases)

    pin = resolve_latest_stable(transport=transport, now=now, maturity_days=3)
    assert pin.tag == "v4.0.2"
    assert pin.pin_source == "latest"


def test_override_uses_direct():
    now = FIXED_NOW

    def transport(path):
        # Should not be called for releases list when override? But our impl may still call for published_at lookup
        # Return a list containing the override tag
        return (200, {}, [_make_release("v9.9.9", days_ago=20, now=now)])

    with patch("om4t.pin._get_commit_sha_for_tag", return_value="override-sha-xyz") as mock_sha:
        pin = resolve_latest_stable(transport=transport, now=now, maturity_days=3, ref_override="v9.9.9")
        assert pin.tag == "v9.9.9"
        assert pin.pin_source == "override"
        assert pin.commit_sha == "override-sha-xyz"
        # published_at should be from release or now
        assert pin.published_at is not None


def test_override_without_transport():
    # Test override without transport (offline) — should still return override pin with fake sha fallback
    with patch("om4t.pin._get_commit_sha_for_tag", return_value="sha-for-v1") as mock:
        pin = resolve_latest_stable(now=FIXED_NOW, ref_override="v1.2.3")
        assert pin.tag == "v1.2.3"
        assert pin.pin_source == "override"
        assert pin.commit_sha == "sha-for-v1"


def test_filter_draft_prerelease_maturity():
    now = FIXED_NOW
    # All too young except oldest
    releases = [
        _make_release("v4.0.4", days_ago=1, now=now),
        _make_release("v4.0.3", days_ago=2, now=now),
        _make_release("v4.0.2", days_ago=4, now=now),
    ]

    def transport(path):
        return (200, {}, releases)

    pin = resolve_latest_stable(transport=transport, now=now, maturity_days=3)
    assert pin.tag == "v4.0.2"
