import boto3
import pytest
from moto import mock_aws

from pr_league.models import Player
from pr_league.roster import load_players

TABLE = "pr-league-teams"


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="eu-west-2")
        yield resource.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "team", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "team", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


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
