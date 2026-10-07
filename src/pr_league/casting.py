from collections.abc import Iterable, Sequence
from dataclasses import replace

from pr_league.models import Player, ReviewEvent, TicketEvent


def cast_roster(
    real: Sequence[Player], standins: Sequence[Player]
) -> tuple[list[Player], dict[str, str]]:
    """Real players take the stand-ins' names first; leftover stand-ins stay in the league."""
    rename = {standin.github: player.github for standin, player in zip(standins, real)}
    return [*real, *standins[len(real):]], rename


def rename_reviews(events: Iterable[ReviewEvent], rename: dict[str, str]) -> list[ReviewEvent]:
    return [
        replace(e, reviewer=rename.get(e.reviewer, e.reviewer), author=rename.get(e.author, e.author))
        for e in events
    ]


def rename_tickets(events: Iterable[TicketEvent], rename: dict[str, str]) -> list[TicketEvent]:
    return [replace(e, actor=rename.get(e.actor, e.actor)) for e in events]
