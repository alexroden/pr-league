import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from pr_league.models import Player


@dataclass(frozen=True)
class Config:
    org: str
    players: tuple[Player, ...]
    github_token: str
    slack_token: str | None


def load_config(path: str | Path = "config.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    org = raw.get("org")
    entries = raw.get("players") or []
    if not org or not entries:
        raise ValueError(f"{path} must set 'org' and at least one entry under 'players'")
    players = tuple(
        Player(github=e["github"], slack=e.get("slack"), team=e.get("team"), jira=e.get("jira"))
        for e in entries
    )
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN is not set (see .env.example)")
    return Config(org, players, github_token, os.environ.get("SLACK_BOT_TOKEN"))
