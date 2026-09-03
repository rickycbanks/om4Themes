"""
GitHub API access with backoff.

Transport abstraction: injectable for tests.
Default transport shells `gh api` if available, else urllib.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Callable

__all__ = ["gh_api", "RateLimitExhausted", "ApiError"]


class RateLimitExhausted(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass


# Transport signature: (path: str) -> tuple[int, dict, Any]
# where dict is headers (lower-cased keys optional), Any is parsed JSON data.
Transport = Callable[[str], tuple[int, dict, Any]]


def _urllib_transport(path: str) -> tuple[int, dict, Any]:
    url = f"https://api.github.com/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "om4t"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            headers = {k.lower(): v for k, v in resp.headers.items()} if resp.headers else {}
            # also preserve original case for Retry-After lookup
            for k, v in list(resp.headers.items()):
                headers[k] = v
                headers[k.lower()] = v
            body = resp.read()
            data: Any = {}
            if body:
                try:
                    data = json.loads(body.decode())
                except Exception:
                    data = body.decode(errors="ignore")
            return (status, headers, data)
    except urllib.error.HTTPError as e:
        headers = {}
        try:
            if e.headers:
                for k, v in e.headers.items():
                    headers[k] = v
                    headers[k.lower()] = v
        except Exception:
            pass
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        data: Any = {}
        if body:
            try:
                data = json.loads(body.decode())
            except Exception:
                data = body.decode(errors="ignore")
        return (e.code, headers, data)
    except urllib.error.URLError as e:
        raise ApiError(f"network error for {path}: {e}") from e


def _gh_transport(path: str) -> tuple[int, dict, Any]:
    # Try gh cli; if fails, fallback to urllib
    if shutil.which("gh") is None:
        return _urllib_transport(path)
    # Use gh api; include headers if possible via --include flag
    # We try with --include to capture headers, but fallback to plain if not.
    try:
        # Attempt to get headers: gh api --include returns header + body
        result = subprocess.run(
            ["gh", "api", path, "--include"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Split headers and body: headers end at blank line, body is JSON
            # gh --include outputs HTTP headers then blank line then body.
            stdout = result.stdout
            # Find first '{' or '[' to locate JSON start
            json_start = None
            for i, ch in enumerate(stdout):
                if ch == "{" or ch == "[":
                    # check if previous char is newline and we have headers before
                    json_start = i
                    break
            if json_start is not None:
                header_part = stdout[:json_start]
                body_part = stdout[json_start:]
                headers: dict = {}
                for line in header_part.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip()] = v.strip()
                        headers[k.strip().lower()] = v.strip()
                try:
                    data = json.loads(body_part) if body_part.strip() else {}
                except Exception:
                    data = {}
                return (200, headers, data)
            else:
                # No JSON start found, treat whole stdout as JSON
                try:
                    data = json.loads(stdout) if stdout.strip() else {}
                except Exception:
                    data = {}
                return (200, {}, data)
        else:
            stderr = result.stderr or ""
            # Detect rate limit in stderr
            if "403" in stderr or "429" in stderr or "rate limit" in stderr.lower():
                # Try to parse Retry-After from stderr headers if present
                headers = {}
                # gh error may contain headers in stderr
                for line in stderr.splitlines():
                    if "retry-after" in line.lower():
                        # e.g. retry-after: 5
                        if ":" in line:
                            _, v = line.split(":", 1)
                            headers["retry-after"] = v.strip()
                            headers["Retry-After"] = v.strip()
                return (429, headers, {})
            # Generic error
            return (500, {}, {"error": stderr})
    except FileNotFoundError:
        return _urllib_transport(path)
    except Exception:
        # fallback to urllib for any unexpected
        return _urllib_transport(path)


def _default_transport(path: str) -> tuple[int, dict, Any]:
    # Prefer gh if available, else urllib
    if shutil.which("gh"):
        # try gh, but if it fails (e.g., not authenticated), fallback to urllib
        status, headers, data = _gh_transport(path)
        # If gh returned 500 without meaningful data, fallback to urllib
        # But we treat 200 and 429/403 as valid gh responses
        if status == 500 and not data:
            return _urllib_transport(path)
        return (status, headers, data)
    return _urllib_transport(path)


def _add_pagination(path: str, page: int, per_page: int = 100) -> str:
    # Inject per_page and page query params
    # Search API pagination cap: max 1000 results / 10 pages (per_page=100)
    import re

    sep = "&" if "?" in path else "?"
    # avoid duplicating per_page if already present
    if "per_page=" not in path:
        path = f"{path}{sep}per_page={per_page}"
        sep = "&"
    # Check for page param as distinct query param (&page= or ?page=), not inside per_page
    if re.search(r"[?&]page=", path) is None:
        path = f"{path}{sep}page={page}"
    else:
        # replace existing page param precisely (avoid matching per_page)
        path = re.sub(r"([?&]page=)\d+", rf"\g<1>{page}", path)
    return path


def gh_api(path: str, *, paginate: bool = False, transport: Transport | None = None) -> Any:
    """
    Call GitHub API.

    path: e.g. "search/repositories?q=topic:omarchy-theme+is:public"
    paginate: if True, iterate pages (per_page=100) until less than per_page returned.
    transport: injectable callable(path)->(status, headers, data) for testing.
    """
    if transport is None:
        transport = _default_transport

    def _call_with_retry(p: str) -> Any:
        attempt = 0
        max_retries = 3
        while True:
            result = transport(p)
            # Normalize transport return: allow tuple or direct data or object with status
            if isinstance(result, tuple) and len(result) == 3:
                status, headers, data = result
            elif isinstance(result, tuple) and len(result) == 2:
                # (status, data) without headers
                status, data = result
                headers = {}
            elif isinstance(result, dict) and "status" in result:
                status = result["status"]
                headers = result.get("headers", {})
                data = result.get("data", result)
            else:
                # Assume transport returned parsed JSON directly with 200
                return result

            # Normalize headers keys to allow case-insensitive lookup
            lower_headers = {k.lower(): v for k, v in headers.items()} if headers else {}

            if status in (403, 429):
                if attempt >= max_retries:
                    raise RateLimitExhausted(f"rate limit exhausted after {max_retries} retries for {p} (last status {status})")
                retry_after = headers.get("Retry-After") or headers.get("retry-after") or lower_headers.get("retry-after")
                if retry_after is not None:
                    try:
                        delay = int(str(retry_after).strip())
                    except Exception:
                        delay = (2**attempt)
                else:
                    delay = (2**attempt)  # 1,2,4
                # sleep; in tests this may be mocked
                time.sleep(delay)
                attempt += 1
                continue
            elif status >= 400:
                raise ApiError(f"GitHub API error {status} for {p}: {data}")
            else:
                return data

    if not paginate:
        return _call_with_retry(path)

    # Paginate: aggregate items
    # Distinguish search (dict with items) vs list endpoints
    aggregated_items: list[Any] = []
    page = 1
    first_data: Any = None
    total_count = None
    while True:
        paginated_path = _add_pagination(path, page)
        data = _call_with_retry(paginated_path)
        if first_data is None:
            first_data = data
            if isinstance(data, dict):
                total_count = data.get("total_count")
        if isinstance(data, dict) and "items" in data:
            items = data["items"] or []
            aggregated_items.extend(items)
            if len(items) < 100:
                break
            # safety: if total_count known and we have all, break
            if total_count is not None and len(aggregated_items) >= total_count:
                break
        elif isinstance(data, list):
            aggregated_items.extend(data)
            if len(data) < 100:
                break
        else:
            # Unexpected single object when paginate=True; return as is
            return data
        page += 1
        if page > 10:  # cap pages to avoid infinite loop (400 repos = 4 pages)
            break
        # For search, if we collected MAX_REPOS_PER_RUN, break early
        # Don't import rules to avoid cycle? but we can check len
        if len(aggregated_items) >= 400:
            aggregated_items = aggregated_items[:400]
            break
    # Return shape: if original was search dict, return dict with aggregated items? But callers expect list of repos.
    # To keep generic, if first_data was dict with items, return aggregated list for convenience,
    # but also allow caller to handle list. We return list of items when search, else list.
    if isinstance(first_data, dict) and "items" in first_data:
        return aggregated_items
    return aggregated_items
