import boto3

from pr_league.models import Player


def connect(table_name: str):
    return boto3.resource("dynamodb").Table(table_name)


def scan_teams(table) -> list[dict]:
    response = table.scan()
    items = response["Items"]
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    return items


def load_players(table) -> tuple[Player, ...]:
    teams = scan_teams(table)
    if not teams:
        raise ValueError(f"{table.name} has no teams")
    owner: dict[str, str] = {}
    players = []
    for item in teams:
        team, members = item["team"], item.get("members") or []
        if not members:
            raise ValueError(f"team {team!r} has no members")
        for member in members:
            github = member.get("github")
            if not github:
                raise ValueError(f"team {team!r} has a member without a github login")
            key = github.lower()
            if key in owner:
                raise ValueError(f"{key} is on both {owner[key]!r} and {team!r}")
            owner[key] = team
            players.append(Player(github, member.get("slack"), team, member.get("jira")))
    return tuple(sorted(players, key=lambda p: (p.team, p.github.lower())))
