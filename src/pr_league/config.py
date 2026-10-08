import os
from collections.abc import Callable
from dataclasses import dataclass

from pr_league import roster
from pr_league.models import Player


@dataclass(frozen=True)
class Config:
    org: str
    players: tuple[Player, ...]
    github_token: str
    slack_token: str | None


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is not set (see .env.example)")
    return value


def load_table_players(table_name: str) -> tuple[Player, ...]:
    return roster.load_players(roster.connect(table_name))


def load_config(
    load_players: Callable[[str], tuple[Player, ...]] = load_table_players,
) -> Config:
    org = required("GITHUB_ORG")
    github_token = required("GITHUB_TOKEN")
    players = load_players(required("PR_LEAGUE_TABLE"))
    return Config(org, players, github_token, os.environ.get("SLACK_BOT_TOKEN"))
