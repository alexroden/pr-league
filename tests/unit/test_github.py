from datetime import datetime, timezone

import httpx
import pytest

from pr_league.github import HTTP_RETRY_ATTEMPTS, GitHubClient


def reviews_payload():
    return [
        {"submitted_at": "2026-10-02T10:00:00Z", "user": {"login": "alice"}},
    ]


def pr_payload():
    return [{
        "number": 1,
        "repository_url": "https://api.github.com/repos/acme/app",
        "html_url": "https://github.com/acme/app/pull/1",
        "user": {"login": "bob"},
    }]


def flaky_transport(failures, exc=httpx.ReadTimeout("read timed out")):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc
        path = request.url.path
        if "/search/issues" in path:
            return httpx.Response(200, json={"total_count": 1, "items": pr_payload()}, request=request)
        return httpx.Response(200, json=reviews_payload(), request=request)

    return httpx.MockTransport(handler)


def client(exc=None, failures=0):
    transport = flaky_transport(failures, exc) if (exc or failures) else flaky_transport(0)
    token = "t"
    return GitHubClient(token, httpx.Client(transport=transport, base_url="https://api.github.com", headers={"Authorization": f"Bearer {token}"}))


def test_transient_timeout_is_retried_and_fetch_succeeds():
    gh = client(exc=httpx.ReadTimeout("read timed out"), failures=2)
    events = gh.fetch_reviews("acme", datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert [e.reviewer for e in events] == ["alice"]


def test_persistent_timeouts_exhaust_retries_and_raise():
    gh = client(exc=httpx.ReadTimeout("read timed out"), failures=HTTP_RETRY_ATTEMPTS + 1)
    with pytest.raises(httpx.ReadTimeout):
        gh.fetch_reviews("acme", datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_no_retry_on_http_404():
    def handler(request):
        if request.url.path.endswith("/search/issues"):
            return httpx.Response(404, request=request)
        return httpx.Response(200, json=[], request=request)

    gh = GitHubClient(
        "t", httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    )
    with pytest.raises(httpx.HTTPStatusError):
        gh.fetch_reviews("acme", datetime(2026, 10, 1, tzinfo=timezone.utc))
