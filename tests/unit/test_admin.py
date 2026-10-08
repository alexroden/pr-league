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


def roster_file(tmp_path, body):
    path = tmp_path / "roster.yaml"
    path.write_text(body)
    return str(path)


ROSTER = """\
org: acme
players:
  - github: sam
    slack: U1
    jira: 712020:abc
    team: Web
  - github: jess
    slack: null
    team: Web
  - github: mo
    team: Data
"""


def test_import_creates_teams_and_members_without_empty_identities(table, tmp_path):
    run(table, "import", roster_file(tmp_path, ROSTER))
    assert members(table, "Web") == [
        {"github": "sam", "slack": "U1", "jira": "712020:abc"},
        {"github": "jess"},
    ]
    assert members(table, "Data") == [{"github": "mo"}]
    assert len(load_players(table)) == 3


def test_import_adds_to_an_existing_team_and_keeps_its_members(table, tmp_path):
    run(table, "teams", "add", "Web")
    run(table, "members", "add", "Web", "amy", "--slack", "U9")
    run(table, "import", roster_file(tmp_path, ROSTER))
    assert [m["github"] for m in members(table, "Web")] == ["amy", "sam", "jess"]


def test_import_twice_changes_nothing_the_second_time(table, tmp_path, capsys):
    path = roster_file(tmp_path, ROSTER)
    run(table, "import", path)
    before = (members(table, "Web"), members(table, "Data"))
    capsys.readouterr()
    run(table, "import", path)
    assert (members(table, "Web"), members(table, "Data")) == before
    assert "Imported 0 members" in capsys.readouterr().out


def test_import_reports_what_it_did(table, tmp_path, capsys):
    run(table, "teams", "add", "Web")
    run(table, "import", roster_file(tmp_path, ROSTER))
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Imported 3 members into 2 teams (1 created); 0 already present."
    )


def test_import_rejects_a_login_that_is_on_another_team_and_writes_nothing(table, tmp_path):
    run(table, "teams", "add", "Ops")
    run(table, "members", "add", "Ops", "Sam")
    with pytest.raises(AdminError, match="sam is already on Ops, not Web"):
        run(table, "import", roster_file(tmp_path, ROSTER))
    assert members(table, "Ops") == [{"github": "Sam"}]
    assert "Item" not in table.get_item(Key={"team": "Data"})


def test_import_rejects_a_player_without_a_team_and_writes_nothing(table, tmp_path):
    body = ROSTER + "  - github: kim\n    slack: U7\n"
    with pytest.raises(AdminError, match="kim has no team"):
        run(table, "import", roster_file(tmp_path, body))
    assert table.scan()["Items"] == []


def test_import_rejects_a_login_listed_twice_ignoring_case(table, tmp_path):
    body = ROSTER + "  - github: SAM\n    team: Data\n"
    with pytest.raises(AdminError, match="sam appears twice"):
        run(table, "import", roster_file(tmp_path, body))
    assert table.scan()["Items"] == []


def test_import_rejects_a_player_without_a_github_login(table, tmp_path):
    with pytest.raises(AdminError, match="no github login"):
        run(table, "import", roster_file(tmp_path, "players:\n  - slack: U1\n    team: Web\n"))


@pytest.mark.parametrize("body", ["org: acme\n", "", "- just\n- a list\n"])
def test_import_rejects_a_file_with_no_players(table, tmp_path, body):
    with pytest.raises(AdminError, match="no players"):
        run(table, "import", roster_file(tmp_path, body))


def test_import_rejects_a_missing_file(table, tmp_path):
    with pytest.raises(AdminError, match="nope.yaml"):
        run(table, "import", str(tmp_path / "nope.yaml"))


def test_import_dry_run_prints_the_plan_and_writes_nothing(table, tmp_path, capsys):
    run(table, "import", "--dry-run", roster_file(tmp_path, ROSTER))
    out = capsys.readouterr().out
    assert "Web (new): sam, jess" in out
    assert out.splitlines()[-1].startswith("Would import 3 members into 2 teams (2 created)")
    assert table.scan()["Items"] == []
