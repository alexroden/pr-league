import pytest

from pr_league.admin import AdminError, main
from pr_league.jira import UnknownTeam
from pr_league.matching import SearchFailed
from pr_league.roster import load_players



def run(table, *argv):
    main(list(argv), table)


def members(table, team):
    return table.get_item(Key={"team": team})["Item"]["members"]


def test_teams_add_creates_an_empty_team(table):
    run(table, "teams", "add", "--empty", "Web")
    assert members(table, "Web") == []


def test_teams_add_rejects_an_existing_team(table):
    run(table, "teams", "add", "--empty", "Web")
    with pytest.raises(AdminError, match="Web already exists"):
        run(table, "teams", "add", "--empty", "Web")


def test_teams_remove_deletes_the_team(table):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "teams", "remove", "Web")
    assert "Item" not in table.get_item(Key={"team": "Web"})


def test_teams_remove_rejects_an_unknown_team(table):
    with pytest.raises(AdminError, match="no team Web"):
        run(table, "teams", "remove", "Web")


def test_teams_list_prints_teams_and_members(table, capsys):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "teams", "add", "--empty", "Data")
    run(table, "members", "add", "Web", "sam", "--slack", "U1")
    run(table, "teams", "list")
    assert capsys.readouterr().out == "Data: (no members)\nWeb: sam\n"


def test_members_add_stores_identities_and_loads_as_players(table):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "members", "add", "Web", "sam", "--slack", "U1", "--jira", "712020:abc")
    assert members(table, "Web") == [{"github": "sam", "source": "manual", "slack": "U1", "jira": "712020:abc"}]
    assert [(p.github, p.slack, p.team, p.jira) for p in load_players(table)] == [
        ("sam", "U1", "Web", "712020:abc")
    ]


def test_members_add_omits_identities_not_given(table):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "members", "add", "Web", "sam")
    assert members(table, "Web") == [{"github": "sam", "source": "manual"}]


def test_members_add_rejects_an_unknown_team(table):
    with pytest.raises(AdminError, match="no team Web"):
        run(table, "members", "add", "Web", "sam")


def test_members_add_rejects_a_login_already_on_any_team_ignoring_case(table):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "teams", "add", "--empty", "Data")
    run(table, "members", "add", "Web", "Sam")
    with pytest.raises(AdminError, match="sam is already on Web"):
        run(table, "members", "add", "Data", "sam")


def test_members_remove_takes_the_player_off_their_team(table):
    run(table, "teams", "add", "--empty", "Web")
    run(table, "members", "add", "Web", "sam")
    run(table, "members", "add", "Web", "jess")
    run(table, "members", "remove", "SAM")
    assert members(table, "Web") == [{"github": "jess", "source": "manual"}]


def test_members_remove_rejects_an_unknown_login(table):
    with pytest.raises(AdminError, match="sam is not on any team"):
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
    run(table, "teams", "add", "--empty", "Web")
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
    run(table, "teams", "add", "--empty", "Web")
    run(table, "import", roster_file(tmp_path, ROSTER))
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Imported 3 members into 2 teams (1 created); 0 already present."
    )


def test_import_rejects_a_login_that_is_on_another_team_and_writes_nothing(table, tmp_path):
    run(table, "teams", "add", "--empty", "Ops")
    run(table, "members", "add", "Ops", "Sam")
    with pytest.raises(AdminError, match="sam is already on Ops, not Web"):
        run(table, "import", roster_file(tmp_path, ROSTER))
    assert members(table, "Ops") == [{"github": "Sam", "source": "manual"}]
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


class FakeJira:
    def __init__(self, teams, emails=None):
        self.teams = teams
        self.emails = emails or {}

    def find_team(self, name):
        for team_name in self.teams:
            if team_name.casefold() == name.casefold():
                return team_name
        raise UnknownTeam(f"no Atlassian team named {name!r}")

    def team_members(self, team_id):
        return list(self.teams[team_id])

    def developers(self, account_ids):
        return frozenset(account_ids)

    def email(self, account_id):
        return self.emails.get(account_id)


class FakeSearch:
    def __init__(self, logins):
        self.logins = logins

    def login_for(self, email):
        return self.logins.get(email)


def jira_run(table, jira, search, *argv):
    main(list(argv), table, jira=jira, search=search, confirm=lambda _prompt: True)


def jira_team(*pairs):
    return FakeJira(
        {name: ids for name, ids in pairs},
        {a: f"{a}@acme.com" for _, ids in pairs for a in ids},
    )


def stored(table, team):
    return table.get_item(Key={"team": team})["Item"]


def test_teams_add_pulls_the_jira_developers_and_matches_their_github_logins(table):
    jira = jira_team(("Web", ["a1", "a2"]))
    jira_run(table, jira, FakeSearch({"a1@acme.com": "alice", "a2@acme.com": "bob"}), "teams", "add", "Web")
    item = stored(table, "Web")
    assert item["members"] == [
        {"github": "alice", "jira": "a1", "source": "jira"},
        {"github": "bob", "jira": "a2", "source": "jira"},
    ]
    assert item["jira_team"] == "Web"
    assert item["added_at"]


def test_teams_add_uses_jira_team_when_the_names_differ(table):
    jira = jira_team(("Migration Product Team", ["a1"]))
    search = FakeSearch({"a1@acme.com": "alice"})
    jira_run(table, jira, search, "teams", "add", "Product", "--jira-team", "Migration Product Team")
    assert stored(table, "Product")["jira_team"] == "Migration Product Team"


def test_teams_add_leaves_out_people_already_on_an_earlier_team_and_reports_them(table, capsys):
    jira = jira_team(("Web", ["a1"]), ("Data", ["a1", "a2"]))
    search = FakeSearch({"a1@acme.com": "alice", "a2@acme.com": "bob"})
    jira_run(table, jira, search, "teams", "add", "Web")
    jira_run(table, jira, search, "teams", "add", "Data")
    assert [m["github"] for m in stored(table, "Data")["members"]] == ["bob"]
    assert "a1 stays on Web" in capsys.readouterr().out


def test_teams_add_reports_people_it_could_not_match_and_still_creates_the_team(table, capsys):
    jira = jira_team(("Web", ["a1", "a2"]))
    jira_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "add", "Web")
    assert [m["github"] for m in stored(table, "Web")["members"]] == ["alice"]
    assert "a2 could not be matched" in capsys.readouterr().out


def test_a_person_with_a_hidden_email_is_unmatched(table, capsys):
    jira = FakeJira({"Web": ["a1"]})
    jira_run(table, jira, FakeSearch({}), "teams", "add", "Web")
    assert stored(table, "Web")["members"] == []
    assert "a1 could not be matched" in capsys.readouterr().out


def test_teams_add_dry_run_prints_the_plan_and_writes_nothing(table, capsys):
    jira = jira_team(("Web", ["a1"]))
    jira_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "add", "Web", "--dry-run")
    assert "alice" in capsys.readouterr().out
    assert table.scan()["Items"] == []


def test_teams_add_rejects_an_unknown_jira_team_and_creates_nothing(table):
    with pytest.raises(AdminError, match="no Atlassian team"):
        jira_run(table, FakeJira({}), FakeSearch({}), "teams", "add", "Web")
    assert table.scan()["Items"] == []


def test_teams_add_rejects_an_existing_team_before_asking_jira(table):
    run(table, "teams", "add", "--empty", "Web")
    with pytest.raises(AdminError, match="Web already exists"):
        jira_run(table, FakeJira({}), FakeSearch({}), "teams", "add", "Web")


def test_teams_add_empty_never_needs_jira(table):
    run(table, "teams", "add", "--empty", "Web")
    assert "jira_team" not in stored(table, "Web")


def test_building_the_clients_names_each_missing_credential(monkeypatch):
    from pr_league.admin import build_clients

    for name in ("ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN", "ATLASSIAN_ORG_ID", "ATLASSIAN_SITE_ID", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(AdminError, match="ATLASSIAN_SITE"):
        build_clients()
    monkeypatch.setenv("ATLASSIAN_SITE", "acme.atlassian.net")
    with pytest.raises(AdminError, match="ATLASSIAN_EMAIL"):
        build_clients()
    for name in ("ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN", "ATLASSIAN_ORG_ID"):
        monkeypatch.setenv(name, "x")
    with pytest.raises(AdminError, match="ATLASSIAN_SITE_ID"):
        build_clients()


def test_building_the_clients_succeeds_when_every_credential_is_set(monkeypatch):
    from pr_league.admin import build_clients
    from pr_league.jira import JiraClient
    from pr_league.matching import CommitSearch

    for name in ("ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN", "ATLASSIAN_ORG_ID", "ATLASSIAN_SITE_ID", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "x")
    jira, search = build_clients()
    assert isinstance(jira, JiraClient) and isinstance(search, CommitSearch)


def seed(table, team, *members, jira_team=None, added_at="2026-01-01T00:00:00+00:00", excluded=()):
    item = {"team": team, "members": list(members), "added_at": added_at}
    if jira_team:
        item["jira_team"] = jira_team
    if excluded:
        item["excluded"] = list(excluded)
    table.put_item(Item=item)


def jm(github, account, source="jira"):
    return {"github": github, "jira": account, "source": source}


def sync_run(table, jira, search, *argv, confirm=lambda _prompt: True):
    main(list(argv), table, jira=jira, search=search, confirm=confirm)


def test_teams_link_marks_listed_members_as_jira_sourced_and_sets_the_link(table, capsys):
    seed(table, "Web", {"github": "alice", "jira": "a1"}, {"github": "bob", "jira": "a2"}, {"github": "cy"})
    jira = jira_team(("Web", ["a1"]))
    sync_run(table, jira, FakeSearch({}), "teams", "link", "Web", "--jira-team", "Web")
    item = stored(table, "Web")
    assert item["jira_team"] == "Web"
    assert [(m["github"], m.get("source")) for m in item["members"]] == [
        ("alice", "jira"), ("bob", None), ("cy", None),
    ]
    assert "bob" in capsys.readouterr().out


def test_teams_link_rejects_an_unknown_team_and_an_unknown_jira_team(table):
    with pytest.raises(AdminError, match="no team Web"):
        sync_run(table, jira_team(("Web", [])), FakeSearch({}), "teams", "link", "Web", "--jira-team", "Web")
    seed(table, "Web")
    with pytest.raises(AdminError, match="no Atlassian team"):
        sync_run(table, FakeJira({}), FakeSearch({}), "teams", "link", "Web", "--jira-team", "Web")


def test_sync_adds_new_developers_to_the_team(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    jira = jira_team(("Web", ["a1", "a2"]))
    sync_run(table, jira, FakeSearch({"a2@acme.com": "bob"}), "teams", "sync", "Web")
    assert [m["github"] for m in stored(table, "Web")["members"]] == ["alice", "bob"]


def test_sync_moves_someone_who_left_the_jira_team_to_another_team_they_are_in(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    jira = jira_team(("Web", []), ("Data", ["a1"]))
    sync_run(table, jira, FakeSearch({}), "teams", "sync", "Web")
    assert stored(table, "Web")["members"] == []
    assert stored(table, "Data")["members"] == [jm("alice", "a1")]


def test_sync_removes_someone_who_left_every_team_after_confirming(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    asked = []
    sync_run(
        table, jira_team(("Web", [])), FakeSearch({}), "teams", "sync", "Web",
        confirm=lambda prompt: asked.append(prompt) or True,
    )
    assert stored(table, "Web")["members"] == []
    assert len(asked) == 1 and "alice" in asked[0]


def test_sync_keeps_a_member_when_the_removal_is_declined_but_still_applies_the_rest(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    jira = jira_team(("Web", ["a2"]))
    sync_run(table, jira, FakeSearch({"a2@acme.com": "bob"}), "teams", "sync", "Web", confirm=lambda _p: False)
    assert [m["github"] for m in stored(table, "Web")["members"]] == ["alice", "bob"]


def test_sync_yes_skips_the_prompt(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")

    def refuse(_prompt):
        raise AssertionError("asked despite --yes")

    sync_run(table, jira_team(("Web", [])), FakeSearch({}), "teams", "sync", "Web", "--yes", confirm=refuse)
    assert stored(table, "Web")["members"] == []


def test_sync_dry_run_writes_nothing_and_never_asks(table, capsys):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    jira = jira_team(("Web", ["a2"]))

    def refuse(_prompt):
        raise AssertionError("asked during a dry run")

    sync_run(table, jira, FakeSearch({"a2@acme.com": "bob"}), "teams", "sync", "Web", "--dry-run", confirm=refuse)
    assert stored(table, "Web")["members"] == [jm("alice", "a1")]
    out = capsys.readouterr().out
    assert "would add bob" in out and "would remove alice" in out


def test_sync_never_touches_members_added_by_hand(table):
    seed(table, "Web", {"github": "cy"}, jira_team="Web")
    sync_run(table, jira_team(("Web", [])), FakeSearch({}), "teams", "sync", "Web")
    assert stored(table, "Web")["members"] == [{"github": "cy"}]


def test_sync_all_goes_through_every_linked_team_oldest_first(table):
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    seed(table, "Web", jira_team="Web", added_at="2026-01-01T00:00:00+00:00")
    seed(table, "Ops")
    jira = jira_team(("Web", ["a1"]), ("Data", ["a1"]))
    sync_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "sync", "--all")
    assert [m["github"] for m in stored(table, "Web")["members"]] == ["alice"]
    assert stored(table, "Data")["members"] == []
    assert stored(table, "Ops")["members"] == []


def test_sync_rejects_a_team_that_is_not_linked(table):
    seed(table, "Ops")
    with pytest.raises(AdminError, match="Ops is not linked"):
        sync_run(table, FakeJira({}), FakeSearch({}), "teams", "sync", "Ops")


def test_sync_needs_a_team_or_all(table):
    with pytest.raises(AdminError, match="name a team or pass --all"):
        sync_run(table, FakeJira({}), FakeSearch({}), "teams", "sync")


def test_sync_stops_without_writing_when_the_commit_search_fails(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")

    class Failing:
        def login_for(self, _email):
            raise SearchFailed("GitHub commit search returned 429")

    with pytest.raises(AdminError, match="429"):
        sync_run(table, jira_team(("Web", ["a2"])), Failing(), "teams", "sync", "Web")
    assert stored(table, "Web")["members"] == [jm("alice", "a1")]


def move_run(table, jira, *argv):
    main(list(argv), table, jira=jira, search=FakeSearch({}), confirm=lambda _prompt: True)


def test_members_move_transfers_someone_who_is_a_developer_in_the_target_jira_team(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    move_run(table, jira_team(("Web", ["a1"]), ("Data", ["a1"])), "members", "move", "alice", "Data")
    assert stored(table, "Web")["members"] == []
    assert stored(table, "Data")["members"] == [jm("alice", "a1")]


def test_members_move_refuses_someone_who_is_not_in_the_target_jira_team(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    with pytest.raises(AdminError, match="alice is not a developer in Data"):
        move_run(table, jira_team(("Web", ["a1"]), ("Data", ["a2"])), "members", "move", "alice", "Data")
    assert stored(table, "Web")["members"] == [jm("alice", "a1")]


def test_members_move_refuses_a_target_that_is_not_linked(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    seed(table, "Ops")
    with pytest.raises(AdminError, match="Ops is not linked"):
        move_run(table, FakeJira({}), "members", "move", "alice", "Ops")


def test_members_move_refuses_a_member_added_by_hand_because_it_has_no_jira_id(table):
    seed(table, "Web", {"github": "alice"}, jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    with pytest.raises(AdminError, match="alice has no Jira ID"):
        move_run(table, jira_team(("Data", ["a1"])), "members", "move", "alice", "Data")


def test_members_move_clears_an_exclusion_for_the_target_team(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00", excluded=["a1"])
    move_run(table, jira_team(("Data", ["a1"])), "members", "move", "alice", "Data")
    assert stored(table, "Data").get("excluded", []) == []


def test_members_move_adds_someone_not_yet_on_a_team_when_given_their_jira_id(table):
    seed(table, "Data", jira_team="Data")
    move_run(table, jira_team(("Data", ["a1"])), "members", "move", "alice", "Data", "--jira", "a1")
    assert stored(table, "Data")["members"] == [jm("alice", "a1")]


def test_members_move_needs_a_jira_id_for_someone_not_yet_on_a_team(table):
    seed(table, "Data", jira_team="Data")
    with pytest.raises(AdminError, match="alice is not on any team; pass --jira"):
        move_run(table, jira_team(("Data", ["a1"])), "members", "move", "alice", "Data")


def test_members_move_rejects_moving_to_the_same_team(table):
    seed(table, "Web", jm("alice", "a1"), jira_team="Web")
    with pytest.raises(AdminError, match="alice is already on Web"):
        move_run(table, jira_team(("Web", ["a1"])), "members", "move", "alice", "Web")


def test_removing_a_jira_sourced_member_excludes_them_from_the_next_sync(table):
    seed(table, "Web", jm("alice", "a1"), jm("bob", "a2"), jira_team="Web")
    run(table, "members", "remove", "alice")
    assert stored(table, "Web")["excluded"] == ["a1"]
    jira = jira_team(("Web", ["a1", "a2"]))
    sync_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "sync", "Web")
    assert [m["github"] for m in stored(table, "Web")["members"]] == ["bob"]


def test_removing_a_member_added_by_hand_excludes_nobody(table):
    seed(table, "Web", {"github": "alice"}, jira_team="Web")
    run(table, "members", "remove", "alice")
    assert "excluded" not in stored(table, "Web")


def test_adding_someone_by_hand_lifts_their_exclusion_and_records_the_source(table):
    seed(table, "Web", jira_team="Web", excluded=["a1", "a2"])
    run(table, "members", "add", "Web", "alice", "--jira", "a1")
    item = stored(table, "Web")
    assert item["excluded"] == ["a2"]
    assert item["members"] == [{"github": "alice", "jira": "a1", "source": "manual"}]


def test_members_exclude_flags_the_member_and_keeps_their_other_fields(table):
    seed(table, "Web", {**jm("alice", "a1"), "slack": "U1"}, jm("bob", "a2"), jira_team="Web")
    run(table, "members", "exclude", "ALICE")
    assert stored(table, "Web")["members"] == [
        {**jm("alice", "a1"), "slack": "U1", "out_of_league": True},
        jm("bob", "a2"),
    ]
    assert [p.github for p in load_players(table)] == ["bob"]


def test_members_include_clears_the_flag(table):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jm("bob", "a2"))
    run(table, "members", "include", "alice")
    assert stored(table, "Web")["members"] == [jm("alice", "a1"), jm("bob", "a2")]


def test_excluding_twice_and_including_a_member_who_is_not_flagged_change_nothing(table):
    seed(table, "Web", jm("alice", "a1"), jm("bob", "a2"))
    run(table, "members", "include", "alice")
    run(table, "members", "exclude", "alice")
    run(table, "members", "exclude", "alice")
    assert stored(table, "Web")["members"][0] == {**jm("alice", "a1"), "out_of_league": True}


@pytest.mark.parametrize("command", ["exclude", "include"])
def test_exclude_and_include_reject_an_unknown_login(table, command):
    with pytest.raises(AdminError, match="alice is not on any team"):
        run(table, "members", command, "alice")


def test_teams_list_marks_excluded_members(table, capsys):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jm("bob", "a2"))
    run(table, "teams", "list")
    assert capsys.readouterr().out == "Web: alice (excluded), bob\n"


def test_the_flag_survives_a_transfer_with_members_move(table):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    move_run(table, jira_team(("Data", ["a1"])), "members", "move", "alice", "Data")
    assert stored(table, "Data")["members"] == [{**jm("alice", "a1"), "out_of_league": True}]


def test_the_flag_survives_a_sync_that_moves_someone_who_left_their_jira_team(table):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    sync_run(table, jira_team(("Web", []), ("Data", ["a1"])), FakeSearch({}), "teams", "sync", "Web")
    assert stored(table, "Data")["members"] == [{**jm("alice", "a1"), "out_of_league": True}]


def test_a_flagged_member_is_not_added_a_second_time_by_a_sync_of_their_own_team(table):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jira_team="Web")
    sync_run(table, jira_team(("Web", ["a1"])), FakeSearch({"a1@acme.com": "alice"}), "teams", "sync", "Web")
    assert stored(table, "Web")["members"] == [{**jm("alice", "a1"), "out_of_league": True}]


def test_a_flagged_member_is_not_pulled_onto_a_second_team_by_its_sync(table):
    seed(table, "Web", {**jm("alice", "a1"), "out_of_league": True}, jira_team="Web")
    seed(table, "Data", jira_team="Data", added_at="2026-02-01T00:00:00+00:00")
    jira = jira_team(("Web", ["a1"]), ("Data", ["a1"]))
    sync_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "sync", "Data")
    assert stored(table, "Data")["members"] == []


def test_someone_newly_added_by_a_sync_starts_in_the_league(table):
    seed(table, "Web", jira_team="Web")
    sync_run(table, jira_team(("Web", ["a1"])), FakeSearch({"a1@acme.com": "alice"}), "teams", "sync", "Web")
    assert "out_of_league" not in stored(table, "Web")["members"][0]


def test_a_dry_run_words_actions_as_would_but_reports_are_not_prefixed(table, capsys):
    jira = jira_team(("Web", ["a1", "a2"]))
    jira_run(table, jira, FakeSearch({"a1@acme.com": "alice"}), "teams", "add", "Web", "--dry-run")
    lines = capsys.readouterr().out.splitlines()
    assert "would add alice to Web" in lines
    assert "a2 could not be matched to a GitHub login for Web" in lines
