import pytest

from pr_league.config import load_config
from pr_league.models import Player

PLAYERS = (Player("sam", "U1", "Web"),)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GITHUB_ORG", "acme")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("PR_LEAGUE_TABLE", "pr-league-teams")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)


def fake_loader(seen):
    def load(table_name):
        seen.append(table_name)
        return PLAYERS

    return load


def test_config_comes_from_the_environment_and_the_named_table(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb")
    seen = []
    config = load_config(fake_loader(seen))
    assert (config.org, config.players, config.github_token, config.slack_token) == (
        "acme",
        PLAYERS,
        "gh-token",
        "xoxb",
    )
    assert seen == ["pr-league-teams"]


def test_slack_token_is_optional():
    assert load_config(fake_loader([])).slack_token is None


@pytest.mark.parametrize("name", ["GITHUB_ORG", "GITHUB_TOKEN", "PR_LEAGUE_TABLE"])
def test_each_required_variable_is_named_when_missing(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(ValueError, match=name):
        load_config(fake_loader([]))
