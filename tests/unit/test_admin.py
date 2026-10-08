import boto3
import pytest
from moto import mock_aws

from pr_league.admin import AdminError, main
from pr_league.roster import load_players

TABLE = "pr-league-teams"


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("PR_LEAGUE_TABLE", TABLE)
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="eu-west-2")
        yield resource.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "team", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "team", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


def run(table, *argv):
    main(list(argv), table)


def members(table, team):
    return table.get_item(Key={"team": team})["Item"]["members"]


def test_teams_add_creates_an_empty_team(table):
    run(table, "teams", "add", "Web")
    assert members(table, "Web") == []


def test_teams_add_rejects_an_existing_team(table):
    run(table, "teams", "add", "Web")
    with pytest.raises(AdminError, match="Web already exists"):
        run(table, "teams", "add", "Web")


def test_teams_remove_deletes_the_team(table):
    run(table, "teams", "add", "Web")
    run(table, "teams", "remove", "Web")
    assert "Item" not in table.get_item(Key={"team": "Web"})


def test_teams_remove_rejects_an_unknown_team(table):
    with pytest.raises(AdminError, match="no team Web"):
        run(table, "teams", "remove", "Web")


def test_teams_list_prints_teams_and_members(table, capsys):
    run(table, "teams", "add", "Web")
    run(table, "teams", "add", "Data")
    run(table, "members", "add", "Web", "sam", "--slack", "U1")
    run(table, "teams", "list")
    assert capsys.readouterr().out == "Data: (no members)\nWeb: sam\n"


def test_members_add_stores_identities_and_loads_as_players(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam", "--slack", "U1", "--jira", "712020:abc")
    assert members(table, "Web") == [{"github": "sam", "slack": "U1", "jira": "712020:abc"}]
    assert [(p.github, p.slack, p.team, p.jira) for p in load_players(table)] == [
        ("sam", "U1", "Web", "712020:abc")
    ]


def test_members_add_omits_identities_not_given(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam")
    assert members(table, "Web") == [{"github": "sam"}]


def test_members_add_rejects_an_unknown_team(table):
    with pytest.raises(AdminError, match="no team Web"):
        run(table, "members", "add", "Web", "sam")


def test_members_add_rejects_a_login_already_on_any_team_ignoring_case(table):
    run(table, "teams", "add", "Web")
    run(table, "teams", "add", "Data")
    run(table, "members", "add", "Web", "Sam")
    with pytest.raises(AdminError, match="sam is already on Web"):
        run(table, "members", "add", "Data", "sam")


def test_members_remove_takes_the_player_off_their_team(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam")
    run(table, "members", "add", "Web", "jess")
    run(table, "members", "remove", "SAM")
    assert members(table, "Web") == [{"github": "jess"}]


def test_members_remove_rejects_an_unknown_login(table):
    with pytest.raises(AdminError, match="sam is not on any team"):
        run(table, "members", "remove", "sam")


def test_members_move_keeps_identities_and_leaves_the_old_team(table):
    run(table, "teams", "add", "Web")
    run(table, "teams", "add", "Data")
    run(table, "members", "add", "Web", "sam", "--slack", "U1")
    run(table, "members", "move", "sam", "Data")
    assert members(table, "Web") == []
    assert members(table, "Data") == [{"github": "sam", "slack": "U1"}]


def test_members_move_rejects_an_unknown_target_team_and_changes_nothing(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam")
    with pytest.raises(AdminError, match="no team Data"):
        run(table, "members", "move", "sam", "Data")
    assert members(table, "Web") == [{"github": "sam"}]


def test_members_move_rejects_moving_to_the_same_team(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam")
    with pytest.raises(AdminError, match="sam is already on Web"):
        run(table, "members", "move", "sam", "Web")


def test_a_write_that_loses_a_race_is_reported(table):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "sam")
    original_get = table.get_item

    def stale_then_concurrent_edit(**kwargs):
        item = original_get(**kwargs)
        table.update_item(
            Key={"team": "Web"},
            UpdateExpression="SET members = list_append(members, :m)",
            ExpressionAttributeValues={":m": [{"github": "jess"}]},
        )
        return item

    table.get_item = stale_then_concurrent_edit
    with pytest.raises(AdminError, match="changed while"):
        run(table, "members", "remove", "sam")
