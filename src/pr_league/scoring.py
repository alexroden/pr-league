from collections.abc import Iterable, Iterator, Sequence

from pr_league.models import GIVEN_POINTS, Player, ReviewEvent, Standing, TeamStanding


def score(events: Iterable[ReviewEvent], players: Sequence[Player]) -> list[Standing]:
    roster = {p.github.lower(): p for p in players}
    given = dict.fromkeys(roster, 0)
    received = dict.fromkeys(roster, 0)
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

    ordered = sorted(roster, key=lambda key: (-(GIVEN_POINTS * given[key] + received[key]), key))
    return [
        Standing(roster[key], given[key], received[key], position)
        for key, position in zip(
            ordered, _positions([GIVEN_POINTS * given[k] + received[k] for k in ordered])
        )
    ]


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
