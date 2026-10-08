import httpx

TEAMS_PATH = "/gateway/api/public/teams/v1/org/{org}/teams"
TEAM_MEMBERS_PATH = "/gateway/api/public/teams/v1/org/{org}/teams/{team}/members"
USER_PATH = "/rest/api/3/user"
DEVELOPERS_GROUP = "developers"


class JiraError(Exception):
    pass


class UnknownTeam(JiraError):
    pass


class AmbiguousTeam(JiraError):
    pass


class JiraClient:
    def __init__(self, http: httpx.Client, org_id: str):
        self._http = http
        self._org = org_id

    def _get(self, path: str, params: dict | None = None):
        response = self._http.get(path, params=params)
        if response.status_code >= 400:
            raise JiraError(f"Atlassian returned {response.status_code} for {path}")
        return response.json()

    def find_team(self, name: str) -> str:
        wanted = name.casefold()
        matches: list[tuple[str, str]] = []
        cursor = None
        while True:
            page = self._get(TEAMS_PATH.format(org=self._org), {"cursor": cursor} if cursor else None)
            matches += [
                (t["displayName"], t["teamId"]) for t in page["entities"] if t["displayName"].casefold() == wanted
            ]
            cursor = page.get("cursor")
            if not cursor:
                break
        if not matches:
            raise UnknownTeam(f"no Atlassian team named {name!r}")
        if len(matches) > 1:
            raise AmbiguousTeam(f"{len(matches)} Atlassian teams are named {matches[0][0]!r}")
        return matches[0][1]

    def team_members(self, team_id: str) -> list[str]:
        accounts: list[str] = []
        cursor = None
        while True:
            page = self._get(
                TEAM_MEMBERS_PATH.format(org=self._org, team=team_id),
                {"cursor": cursor} if cursor else None,
            )
            accounts += [m["accountId"] for m in page["results"]]
            cursor = page["pageInfo"].get("endCursor")
            if not page["pageInfo"].get("hasNextPage"):
                return accounts

    def developers(self, account_ids: list[str]) -> frozenset[str]:
        found = set()
        for account in dict.fromkeys(account_ids):
            user = self._get(USER_PATH, {"accountId": account, "expand": "groups"})
            groups = {g["name"].casefold() for g in user.get("groups", {}).get("items", [])}
            if user.get("active") and DEVELOPERS_GROUP in groups:
                found.add(account)
        return frozenset(found)

    def email(self, account_id: str) -> str | None:
        return self._get(USER_PATH, {"accountId": account_id}).get("emailAddress")
