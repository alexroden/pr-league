import httpx

NOREPLY_SUFFIX = "@users.noreply.github.com"


class SearchFailed(Exception):
    pass


class CommitSearch:
    def __init__(self, http: httpx.Client):
        self._http = http

    def login_for(self, email: str) -> str | None:
        if email.lower().endswith(NOREPLY_SUFFIX):
            return None
        response = self._http.get(
            "/search/commits",
            params={"q": f"author-email:{email}", "per_page": 30},
            headers={"Accept": "application/vnd.github+json"},
        )
        if response.status_code >= 400:
            raise SearchFailed(f"GitHub commit search returned {response.status_code}")
        by_case: dict[str, str] = {}
        for commit in response.json()["items"]:
            login = (commit.get("author") or {}).get("login")
            if login:
                by_case.setdefault(login.lower(), login)
        return next(iter(by_case.values())) if len(by_case) == 1 else None
