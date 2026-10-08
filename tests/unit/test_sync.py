import pytest

from pr_league.sync import Add, Member, Move, Plan, Remove, Skip, Team, Unmatched, plan_sync


def member(github, account=None, source="jira"):
    return Member(github, account, source)


def team(name, *members, jira_team=True, added_at="2026-01-01", excluded=()):
    return Team(name, tuple(members), name if jira_team else None, added_at, frozenset(excluded))


def developers(**by_team):
    return {name: frozenset(ids) for name, ids in by_team.items()}


def plan(teams, devs, scope, logins=None):
    resolve = (logins or {}).get
    return plan_sync(teams, devs, resolve, scope)


def test_a_developer_on_no_team_is_added_with_their_github_login():
    result = plan([team("Web")], developers(Web=["a1"]), {"Web"}, {"a1": "alice"})
    assert result == Plan(adds=(Add("Web", "alice", "a1"),))


def test_a_developer_with_no_github_login_is_reported_unmatched_not_added():
    result = plan([team("Web")], developers(Web=["a1"]), {"Web"})
    assert result == Plan(unmatched=(Unmatched("a1", "Web"),))


def test_a_developer_already_on_another_team_stays_there_and_is_reported():
    teams = [team("Web", member("alice", "a1")), team("Data", added_at="2026-02-01")]
    result = plan(teams, developers(Web=["a1"], Data=["a1"]), {"Data"})
    assert result == Plan(skips=(Skip("a1", "Data", "Web"),))


def test_a_developer_already_on_this_team_needs_nothing():
    teams = [team("Web", member("alice", "a1"))]
    assert plan(teams, developers(Web=["a1"]), {"Web"}) == Plan()


def test_a_developer_on_an_unlinked_team_is_skipped_too():
    teams = [team("Ops", member("alice", "a1"), jira_team=False), team("Web")]
    result = plan(teams, developers(Web=["a1"]), {"Web"})
    assert result == Plan(skips=(Skip("a1", "Web", "Ops"),))


def test_an_excluded_developer_is_not_added_back():
    teams = [team("Web", excluded=["a1"])]
    assert plan(teams, developers(Web=["a1"]), {"Web"}, {"a1": "alice"}) == Plan()


def test_a_hand_added_member_found_by_login_is_not_added_twice():
    teams = [team("Web", member("Alice", None, "manual"))]
    result = plan(teams, developers(Web=["a1"]), {"Web"}, {"a1": "alice"})
    assert result == Plan()


def test_a_hand_added_member_on_another_team_is_skipped_by_login():
    teams = [team("Web", member("Alice", None, "manual")), team("Data", added_at="2026-02-01")]
    result = plan(teams, developers(Web=[], Data=["a1"]), {"Data"}, {"a1": "alice"})
    assert result == Plan(skips=(Skip("a1", "Data", "Web"),))


def test_the_github_search_is_not_made_for_someone_already_located_by_jira_id():
    def never(_account):
        raise AssertionError("searched GitHub for a known member")

    teams = [team("Web", member("alice", "a1")), team("Data", added_at="2026-02-01")]
    plan_sync(teams, developers(Web=["a1"], Data=["a1"]), never, {"Data"})


def test_someone_who_left_the_jira_team_moves_to_the_oldest_team_they_are_still_in():
    teams = [
        team("Web", member("alice", "a1"), added_at="2026-01-01"),
        team("Platform", added_at="2026-03-01"),
        team("Data", added_at="2026-02-01"),
    ]
    devs = developers(Web=[], Platform=["a1"], Data=["a1"])
    assert plan(teams, devs, {"Web"}) == Plan(moves=(Move("alice", "Web", "Data"),))


def test_someone_who_left_every_jira_team_is_removed():
    teams = [team("Web", member("alice", "a1")), team("Data", added_at="2026-02-01")]
    result = plan(teams, developers(Web=[], Data=[]), {"Web"})
    assert result == Plan(removes=(Remove("alice", "Web"),))


def test_a_departure_does_not_move_to_a_team_that_excluded_them():
    teams = [
        team("Web", member("alice", "a1")),
        team("Data", added_at="2026-02-01", excluded=["a1"]),
        team("Platform", added_at="2026-03-01"),
    ]
    devs = developers(Web=[], Data=["a1"], Platform=["a1"])
    assert plan(teams, devs, {"Web"}) == Plan(moves=(Move("alice", "Web", "Platform"),))


def test_a_departure_never_moves_to_an_unlinked_team():
    teams = [team("Web", member("alice", "a1")), team("Ops", jira_team=False)]
    result = plan(teams, developers(Web=[]), {"Web"})
    assert result == Plan(removes=(Remove("alice", "Web"),))


def test_members_added_by_hand_are_never_moved_or_removed():
    teams = [team("Web", member("alice", "a1", "manual"), member("bob", None, "manual"))]
    assert plan(teams, developers(Web=[]), {"Web"}) == Plan()


def test_only_the_teams_in_scope_are_synced_but_all_linked_teams_are_move_targets():
    teams = [
        team("Web", member("alice", "a1")),
        team("Data", member("bob", "b1"), added_at="2026-02-01"),
        team("Platform", added_at="2026-03-01"),
    ]
    devs = developers(Web=[], Data=[], Platform=["a1", "b1"])
    assert plan(teams, devs, {"Web"}) == Plan(moves=(Move("alice", "Web", "Platform"),))


def test_a_person_in_two_new_jira_teams_lands_on_the_older_team_whatever_the_input_order():
    teams = [team("Data", added_at="2026-02-01"), team("Web", added_at="2026-01-01")]
    result = plan(teams, developers(Web=["a1"], Data=["a1"]), {"Web", "Data"}, {"a1": "alice"})
    assert result.adds == (Add("Web", "alice", "a1"),)
    assert result.skips == (Skip("a1", "Data", "Web"),)


def test_someone_moved_into_a_team_is_not_added_or_skipped_again_in_the_same_run():
    teams = [team("Web", member("alice", "a1")), team("Data", added_at="2026-02-01")]
    result = plan(teams, developers(Web=[], Data=["a1"]), {"Web", "Data"})
    assert result == Plan(moves=(Move("alice", "Web", "Data"),))


@pytest.mark.parametrize("scope", [set(), {"Missing"}])
def test_nothing_is_planned_when_no_team_in_scope_exists(scope):
    assert plan([team("Web", member("alice", "a1"))], developers(Web=[]), scope) == Plan()


def test_a_linked_team_with_no_developer_list_is_an_error_not_an_empty_team():
    with pytest.raises(KeyError):
        plan([team("Web", member("alice", "a1"))], {}, {"Web"})
