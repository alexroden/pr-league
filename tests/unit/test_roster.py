import pytest

from pr_league.models import Player
from pr_league.roster import load_players



def put(table, team, *members):
    table.put_item(Item={"team": team, "members": list(members)})


def test_members_load_as_players_on_their_team(table):
    put(table, "Web", {"github": "sam", "slack": "U1", "jira": "712020:abc"})
    assert load_players(table) == (Player("sam", "U1", "Web", "712020:abc"),)


def test_slack_and_jira_are_optional(table):
    put(table, "Web", {"github": "sam"})
    assert load_players(table) == (Player("sam", None, "Web", None),)


def test_players_are_ordered_by_team_then_login(table):
    put(table, "Web", {"github": "zoe"}, {"github": "amy"})
    put(table, "Data", {"github": "mo"})
    assert [(p.team, p.github) for p in load_players(table)] == [
        ("Data", "mo"),
        ("Web", "amy"),
        ("Web", "zoe"),
    ]


def test_an_empty_table_is_rejected(table):
    with pytest.raises(ValueError, match="no teams"):
        load_players(table)


def test_a_team_without_members_is_rejected(table):
    put(table, "Web")
    with pytest.raises(ValueError, match="Web"):
        load_players(table)


def test_a_member_without_a_github_login_is_rejected(table):
    put(table, "Web", {"slack": "U1"})
    with pytest.raises(ValueError, match="Web"):
        load_players(table)


def test_a_login_on_two_teams_is_rejected_ignoring_case(table):
    put(table, "Web", {"github": "Sam"})
    put(table, "Data", {"github": "sam"})
    with pytest.raises(ValueError, match="sam"):
        load_players(table)


def test_a_scan_is_followed_across_pages(table):
    for i in range(60):
        put(table, f"T{i:02}", {"github": f"p{i:02}", "slack": "U" + "x" * 20_000})
    assert len(load_players(table)) == 60


def test_sync_fields_on_items_and_members_do_not_affect_the_players_loaded(table):
    table.put_item(
        Item={
            "team": "Web",
            "members": [{"github": "sam", "jira": "a1", "source": "jira"}],
            "jira_team": "Web",
            "added_at": "2026-01-01T00:00:00+00:00",
            "excluded": ["a2"],
        }
    )
    assert load_players(table) == (Player("sam", None, "Web", "a1"),)


def test_a_member_flagged_out_of_the_league_is_not_loaded(table):
    put(table, "Web", {"github": "sam"}, {"github": "mo", "out_of_league": True})
    assert [p.github for p in load_players(table)] == ["sam"]


def test_a_team_whose_members_are_all_flagged_is_valid(table):
    put(table, "Web", {"github": "sam"})
    put(table, "Mgmt", {"github": "mo", "out_of_league": True})
    assert [p.team for p in load_players(table)] == ["Web"]


def test_a_flagged_member_still_counts_for_the_one_team_rule(table):
    put(table, "Web", {"github": "Sam", "out_of_league": True})
    put(table, "Data", {"github": "sam"})
    with pytest.raises(ValueError, match="sam"):
        load_players(table)


def test_a_league_where_everyone_is_flagged_is_rejected(table):
    put(table, "Web", {"github": "mo", "out_of_league": True})
    with pytest.raises(ValueError, match="every member is out of the league"):
        load_players(table)


def test_a_flagged_member_scores_nothing_but_the_other_side_of_their_reviews_still_does(table):
    from datetime import datetime, timezone

    from pr_league.models import ReviewEvent
    from pr_league.scoring import rank_teams, score

    put(table, "Web", {"github": "sam"}, {"github": "mo", "out_of_league": True})
    at = datetime(2026, 10, 3, tzinfo=timezone.utc)
    events = [ReviewEvent("acme/app#1", "mo", "sam", at), ReviewEvent("acme/app#2", "sam", "mo", at)]
    standings = score(events, load_players(table))
    assert [(s.player.github, s.given, s.received, s.points) for s in standings] == [("sam", 1, 1, 3)]
    assert [(t.name, t.points) for t in rank_teams(standings)] == [("Web", 3)]
