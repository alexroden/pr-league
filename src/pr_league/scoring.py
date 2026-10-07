from collections.abc import Iterable, Iterator, Sequence

from pr_league.models import (
    GIVEN_POINTS,
    RECEIVED_POINTS,
    TICKET_POINTS,
    Player,
    ReviewEvent,
    Standing,
    TeamStanding,
    TicketEvent,
)


def score(
    events: Iterable[ReviewEvent],
    players: Sequence[Player],
    ticket_events: Iterable[TicketEvent] = (),
) -> list[Standing]:
    roster = {p.github.lower(): p for p in players}
    given = dict.fromkeys(roster, 0)
    received = dict.fromkeys(roster, 0)
    tickets = _ticket_points(ticket_events, roster)
    seen: set[tuple[str, str]] = set()

    for event in events:
        reviewer, author = event.reviewer.lower(), event.author.lower()
        if (reviewer, event.pr) in seen:
            continue
        seen.add((reviewer, event.pr))
        if reviewer == author:
            continue
        if reviewer in roster:
            given[reviewer] += 1
        if author in roster:
            received[author] += 1

    def total(key: str) -> int:
        return GIVEN_POINTS * given[key] + RECEIVED_POINTS * received[key] + tickets[key]

    ordered = sorted(roster, key=lambda key: (-total(key), key))
    return [
        Standing(roster[key], given[key], received[key], position, tickets[key])
        for key, position in zip(ordered, _positions([total(k) for k in ordered]))
    ]


def _ticket_points(ticket_events: Iterable[TicketEvent], roster: dict[str, Player]) -> dict[str, int]:
    points = dict.fromkeys(roster, 0)
    seen: set[tuple[str, str, str]] = set()
    for event in ticket_events:
        actor = event.actor.lower()
        if actor not in roster or event.status not in TICKET_POINTS:
            continue
        if (actor, event.key, event.status) in seen:
            continue
        seen.add((actor, event.key, event.status))
        points[actor] += TICKET_POINTS[event.status]
    return points


def rank_teams(standings: Iterable[Standing]) -> list[TeamStanding]:
    totals: dict[str, int] = {}
    for s in standings:
        if s.player.team is not None:
            totals[s.player.team] = totals.get(s.player.team, 0) + s.points
    ordered = sorted(totals, key=lambda name: (-totals[name], name))
    return [
        TeamStanding(name, totals[name], position)
        for name, position in zip(ordered, _positions([totals[n] for n in ordered]))
    ]


def _positions(points: Sequence[int]) -> Iterator[int]:
    """Positions for points sorted high to low: ties share a place, the next place is skipped."""
    position, previous = 0, None
    for index, value in enumerate(points, start=1):
        if value != previous:
            position, previous = index, value
        yield position


def win_streaks(history: Sequence[Iterable[str]]) -> dict[str, int]:
    """Consecutive wins ending with the most recent month (last in the sequence).

    A name missing any month ends its streak at the most recent month it won.
    """
    streaks = {name: 0 for names in history for name in names}
    for names in history:
        for name in names:
            streaks[name] += 1
        for name in list(streaks):
            if name not in names:
                streaks[name] = 0
    return {name: count for name, count in streaks.items() if count > 0}
