from collections.abc import Sequence
from datetime import date

from pr_league.models import Standing


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def render_dm(me: Standing, standings: Sequence[Standing], today: date) -> str:
    week = (today.day - 1) // 7 + 1
    lines = [f"*PR League: {today.strftime('%B')}, week {week}*"]

    tied = sum(1 for s in standings if s.position == me.position) > 1
    place = ("joint " if tied else "") + ordinal(me.position)
    lines.append(
        f"You're *{place}* of {len(standings)} this month with "
        f"*{_count(me.points, 'point')}* ({_count(me.given, 'review')} given, {me.received} received)."
    )

    ahead = [s for s in standings if s.position < me.position]
    if ahead:
        nearest = max(s.position for s in ahead)
        next_up = [s for s in standings if s.position == nearest]
        names = " and ".join(s.player.github for s in next_up)
        gap = next_up[0].points - me.points
        lines.append(f"Next up: {names}, {_count(gap, 'point')} ahead of you.")

    rows = " · ".join(
        f"{s.position}. {'You' if s.player == me.player else s.player.github} ({s.points})"
        for s in standings
    )
    lines.append(f"Table: {rows}")
    return "\n".join(lines)
