from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    github: str
    jira: str | None
    source: str


@dataclass(frozen=True)
class Team:
    name: str
    members: tuple[Member, ...]
    jira_team: str | None
    added_at: str
    excluded: frozenset[str]


@dataclass(frozen=True)
class Add:
    team: str
    github: str
    jira: str


@dataclass(frozen=True)
class Move:
    github: str
    source: str
    target: str


@dataclass(frozen=True)
class Remove:
    github: str
    team: str


@dataclass(frozen=True)
class Skip:
    jira: str
    team: str
    on: str


@dataclass(frozen=True)
class Unmatched:
    jira: str
    team: str


@dataclass(frozen=True)
class Plan:
    adds: tuple[Add, ...] = ()
    moves: tuple[Move, ...] = ()
    removes: tuple[Remove, ...] = ()
    skips: tuple[Skip, ...] = ()
    unmatched: tuple[Unmatched, ...] = ()


def plan_sync(
    teams: Iterable[Team],
    developers: Mapping[str, frozenset[str]],
    resolve_login: Callable[[str], str | None],
    scope: set[str],
) -> Plan:
    ordered = sorted(teams, key=lambda t: (t.added_at, t.name))
    owner: dict[str, str] = {}
    by_jira: dict[str, str] = {}
    for team in ordered:
        for member in team.members:
            owner[member.github.lower()] = team.name
            if member.jira:
                by_jira[member.jira] = team.name

    adds, moves, removes, skips, unmatched = [], [], [], [], []
    for team in ordered:
        if team.name not in scope or team.jira_team is None:
            continue
        current = developers[team.name]

        for member in team.members:
            if member.source != "jira" or member.jira in current:
                continue
            target = next(
                (
                    other
                    for other in ordered
                    if other.name != team.name
                    and other.jira_team is not None
                    and member.jira in developers[other.name]
                    and member.jira not in other.excluded
                ),
                None,
            )
            if target is None:
                removes.append(Remove(member.github, team.name))
                del owner[member.github.lower()]
            else:
                moves.append(Move(member.github, team.name, target.name))
                owner[member.github.lower()] = target.name
                by_jira[member.jira] = target.name

        for account in sorted(current):
            if account in team.excluded:
                continue
            located = by_jira.get(account)
            if located is None:
                login = resolve_login(account)
                if login is None:
                    unmatched.append(Unmatched(account, team.name))
                    continue
                located = owner.get(login.lower())
                if located is None:
                    adds.append(Add(team.name, login, account))
                    owner[login.lower()] = team.name
                    by_jira[account] = team.name
                    continue
            if located != team.name:
                skips.append(Skip(account, team.name, located))

    return Plan(tuple(adds), tuple(moves), tuple(removes), tuple(skips), tuple(unmatched))
