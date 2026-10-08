import httpx
import pytest

from pr_league.jira import AmbiguousTeam, JiraClient, JiraError, UnknownTeam

TEAM_ID = "6e31efe1-6a5d-4fea-8566-6149bd08a62e"


def make(routes, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        reply = routes(request)
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply, request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://acme.atlassian.net")
    return JiraClient(http, org_id="org-1")


def teams_page(*names_and_ids, cursor=None):
    return {
        "entities": [{"teamId": i, "displayName": n} for n, i in names_and_ids],
        "cursor": cursor,
    }


def members_page(*ids, cursor=None):
    return {"results": [{"accountId": a} for a in ids], "pageInfo": {"endCursor": cursor, "hasNextPage": bool(cursor)}}


def test_find_team_returns_the_id_of_the_exact_name_ignoring_case():
    jira = make(lambda r: teams_page(("Migration Product Team", TEAM_ID), ("Migration Product", "other")))
    assert jira.find_team("migration product team") == TEAM_ID


def test_find_team_rejects_an_unknown_name_and_lists_nothing_close_as_a_match():
    jira = make(lambda r: teams_page(("Migration Product Team", TEAM_ID)))
    with pytest.raises(UnknownTeam, match="Migration"):
        jira.find_team("Migration")


def test_find_team_rejects_two_teams_with_the_same_name():
    jira = make(lambda r: teams_page(("Web", "t1"), ("web", "t2")))
    with pytest.raises(AmbiguousTeam, match="Web"):
        jira.find_team("Web")


def test_find_team_follows_the_cursor_across_pages():
    pages = {None: teams_page(("A", "t1"), cursor="c1"), "c1": teams_page(("Web", "t2"))}
    jira = make(lambda r: pages[r.url.params.get("cursor")])
    assert jira.find_team("Web") == "t2"


def test_team_members_follows_pagination():
    pages = {None: members_page("a1", "a2", cursor="c1"), "c1": members_page("a3")}
    jira = make(lambda r: pages[r.url.params.get("cursor")])
    assert jira.team_members(TEAM_ID) == ["a1", "a2", "a3"]


def test_developers_keeps_only_active_members_of_the_developers_group():
    users = {
        "a1": {"accountId": "a1", "active": True, "groups": {"items": [{"name": "developers"}]}},
        "a2": {"accountId": "a2", "active": True, "groups": {"items": [{"name": "designers"}]}},
        "a3": {"accountId": "a3", "active": False, "groups": {"items": [{"name": "developers"}]}},
    }
    jira = make(lambda r: users[r.url.params["accountId"]])
    assert jira.developers(["a1", "a2", "a3"]) == frozenset({"a1"})


def test_developers_reads_each_person_once_and_asks_for_their_groups():
    seen = []
    users = {"a1": {"accountId": "a1", "active": True, "groups": {"items": [{"name": "developers"}]}}}
    jira = make(lambda r: users[r.url.params["accountId"]], seen)
    jira.developers(["a1", "a1"])
    assert len(seen) == 1
    assert seen[0].url.params["expand"] == "groups"


def test_email_returns_the_address_when_visible_and_none_when_hidden():
    users = {"a1": {"accountId": "a1", "emailAddress": "a@acme.com"}, "a2": {"accountId": "a2"}}
    jira = make(lambda r: users[r.url.params["accountId"]])
    assert (jira.email("a1"), jira.email("a2")) == ("a@acme.com", None)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_an_http_error_is_reported_with_its_status_and_not_treated_as_empty(status):
    jira = make(lambda r: httpx.Response(status, json={}, request=r))
    with pytest.raises(JiraError, match=str(status)):
        jira.find_team("Web")


def test_requests_use_the_org_in_the_teams_path():
    seen = []
    jira = make(lambda r: teams_page(("Web", "t1")), seen)
    jira.find_team("Web")
    assert "org-1" in seen[0].url.path
