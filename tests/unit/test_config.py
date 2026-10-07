import pytest

from pr_league.config import load_config


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)


def load(tmp_path, body):
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(path)


def test_player_jira_id_is_loaded(tmp_path):
    config = load(tmp_path, "org: acme\nplayers:\n  - github: sam\n    slack: U1\n    jira: 712020:abc\n")
    assert config.players[0].jira == "712020:abc"


def test_jira_id_is_optional(tmp_path):
    config = load(tmp_path, "org: acme\nplayers:\n  - github: sam\n    slack: U1\n")
    assert config.players[0].jira is None


def test_null_slack_id_loads_as_none(tmp_path):
    config = load(tmp_path, "org: acme\nplayers:\n  - github: sam\n    slack: null\n")
    assert config.players[0].slack is None


def test_missing_slack_key_loads_as_none(tmp_path):
    config = load(tmp_path, "org: acme\nplayers:\n  - github: sam\n")
    assert config.players[0].slack is None


def test_team_and_slack_still_load(tmp_path):
    config = load(tmp_path, "org: acme\nplayers:\n  - github: sam\n    slack: U1\n    team: Web\n")
    player = config.players[0]
    assert (player.github, player.slack, player.team) == ("sam", "U1", "Web")


def test_org_and_players_are_required(tmp_path):
    with pytest.raises(ValueError):
        load(tmp_path, "org: acme\n")
