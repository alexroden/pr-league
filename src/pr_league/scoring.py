from collections.abc import Iterable, Sequence

from pr_league.models import Player, ReviewEvent, Standing


def score(events: Iterable[ReviewEvent], players: Sequence[Player]) -> list[Standing]:
    roster = {p.github.lower(): p for p in players}
    given = dict.fromkeys(roster, 0)
    received = dict.fromkeys(roster, 0)
    seen: set[int] = set()

    for event in events:
        if event.review_id in seen:
            continue
        seen.add(event.review_id)
        reviewer, author = event.reviewer.lower(), event.author.lower()
        if reviewer == author:
            continue
        if reviewer in roster:
            given[reviewer] += 1
        if author in roster:
            received[author] += 1

    ordered = sorted(roster, key=lambda key: (-(given[key] + received[key]), key))
    standings: list[Standing] = []
    previous_points = None
    position = 0
    for index, key in enumerate(ordered, start=1):
        points = given[key] + received[key]
        if points != previous_points:
            position, previous_points = index, points
        standings.append(Standing(roster[key], given[key], received[key], position))
    return standings
