import httpx
import pytest

from pr_league.matching import CommitSearch, SearchFailed


def make(items=None, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"items": items or []}, request=request)

    return CommitSearch(httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com"))


def commit(login):
    return {"author": {"login": login} if login else None}


def test_a_login_is_returned_when_every_matching_commit_has_the_same_author():
    assert make([commit("alice"), commit("alice")]).login_for("a@acme.com") == "alice"


def test_none_is_returned_when_there_are_no_commits():
    assert make([]).login_for("a@acme.com") is None


def test_none_is_returned_when_commits_belong_to_different_logins():
    assert make([commit("alice"), commit("bob")]).login_for("a@acme.com") is None


def test_commits_not_linked_to_an_account_are_ignored():
    assert make([commit(None), commit("alice")]).login_for("a@acme.com") == "alice"


def test_none_is_returned_when_no_commit_is_linked_to_an_account():
    assert make([commit(None)]).login_for("a@acme.com") is None


def test_logins_that_differ_only_by_case_are_the_same_person():
    assert make([commit("Alice"), commit("alice")]).login_for("a@acme.com") == "Alice"


def test_noreply_addresses_are_not_searched():
    seen = []
    result = make([commit("alice")], seen=seen).login_for("123+alice@users.noreply.github.com")
    assert (result, seen) == (None, [])


def test_the_search_is_by_author_email():
    seen = []
    make([], seen=seen).login_for("a@acme.com")
    assert seen[0].url.params["q"] == "author-email:a@acme.com"


@pytest.mark.parametrize("status", [401, 403, 422, 429, 500])
def test_a_failed_search_is_an_error_not_an_unmatched_person(status):
    with pytest.raises(SearchFailed, match=str(status)):
        make(status=status).login_for("a@acme.com")
