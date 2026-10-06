import logging
from datetime import datetime, timezone

import httpx

from pr_league.models import ReviewEvent

log = logging.getLogger(__name__)

API = "https://api.github.com"
SEARCH_LIMIT = 1000


class GitHubClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._http = client or httpx.Client(
            base_url=API,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def fetch_reviews(self, org: str, since: datetime) -> list[ReviewEvent]:
        events: list[ReviewEvent] = []
        for pr in self._search_prs(org, since):
            for review in self._get_paged(f"{pr['repository_url']}/pulls/{pr['number']}/reviews"):
                submitted = review.get("submitted_at")
                reviewer = review.get("user")
                if not submitted or not reviewer:
                    continue
                submitted_at = datetime.fromisoformat(submitted)
                if submitted_at < since:
                    continue
                events.append(
                    ReviewEvent(pr["html_url"], reviewer["login"], pr["user"]["login"], submitted_at)
                )
        return events

    def _search_prs(self, org: str, since: datetime):
        day = since.astimezone(timezone.utc).date().isoformat()
        params = {"q": f"org:{org} is:pr updated:>={day}", "per_page": 100}
        response = self._http.get("/search/issues", params=params)
        response.raise_for_status()
        total = response.json()["total_count"]
        if total > SEARCH_LIMIT:
            log.warning(
                "Search matched %d PRs but GitHub only returns the first %d; scores will be low",
                total, SEARCH_LIMIT,
            )
        while True:
            yield from response.json()["items"]
            url = response.links.get("next", {}).get("url")
            if not url:
                return
            response = self._http.get(url)
            response.raise_for_status()

    def _get_paged(self, url: str):
        params = {"per_page": 100}
        while url:
            response = self._http.get(url, params=params)
            response.raise_for_status()
            yield from response.json()
            url = response.links.get("next", {}).get("url")
            params = None
