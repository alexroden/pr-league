from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta

from pr_league.models import TICKET_POINTS, Player, Standing, TeamStanding, TicketEvent


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def render_winners(
    standings: Sequence[Standing],
    teams: Sequence[TeamStanding],
    month: str,
    streaks: dict[str, int] | None = None,
    team_streaks: dict[str, int] | None = None,
) -> str:
    streaks = streaks or {}
    team_streaks = team_streaks or {}

    lines = [f"🎉 *{month} winners*", ""]
    for s in standings:
        if s.position == 1:
            lines.append(f"🏆 {s.player.github} ({_count(s.points, 'point')}){_streak(s.player.github, streaks)}")
    for t in teams:
        if t.position == 1:
            lines.append(f"🏆 Team: {t.name} ({_count(t.points, 'point')}){_streak(t.name, team_streaks)}")
    return "\n".join(lines)


def _streak(name: str, streaks: dict[str, int]) -> str:
    count = streaks.get(name, 1)
    return "" if count == 1 else f" — {count} months in a row"


def render_dm(
    me: Standing,
    standings: Sequence[Standing],
    today: date,
    teams: Sequence[TeamStanding] = (),
    winners: str = "",
    jira: str = "",
) -> str:
    week = (today.day - 1) // 7 + 1
    lines = [f"🏆 *PR League: {today.strftime('%B')}, week {week}*"]
    if winners:
        lines.append("")
        lines.append(winners)

    leaders = [s for s in standings if s.position == 1]
    if leaders:
        leader_names = " and ".join(
            "You" if s.player == me.player else s.player.github for s in leaders
        )
        lines.append("")
        lines.append(
            f"⚽ *Top scorer of the month: {leader_names} "
            f"({_count(leaders[0].points, 'point')})*"
        )
    top_given = max((s.given for s in standings), default=0)
    assist_leaders = [s for s in standings if s.given == top_given]
    if assist_leaders:
        assist_names = " and ".join(
            "You" if s.player == me.player else s.player.github for s in assist_leaders
        )
        lines.append("")
        lines.append(
            f"👟 *Top assists of the month: {assist_names} "
            f"({_count(top_given, 'review')} given)*"
        )

    lines.append("")
    lines.append("")

    tied = sum(1 for s in standings if s.position == me.position) > 1
    place = ("joint " if tied else "") + ordinal(me.position)
    lines.append(
        f"You're *{place}* of {len(standings)} this month with "
        f"*{_count(me.points, 'point')}* ({_count(me.given, 'review')} given, {me.received} received"
        + (f", {me.tickets} from tickets" if me.tickets else "")
        + ")."
    )

    ahead = [s for s in standings if s.position < me.position]
    if ahead:
        nearest = max(s.position for s in ahead)
        next_up = [s for s in standings if s.position == nearest]
        names = " and ".join(s.player.github for s in next_up)
        gap = next_up[0].points - me.points
        lines.append(f"⬆️ Next up: {names}, {_count(gap, 'point')} ahead of you.")

    lines.append("")
    lines.append(_render_table(me, standings))

    podium = [t for t in teams if t.position <= TEAM_PODIUM]
    if podium:
        lines.append("")
        lines.append("*Team league*")
        lines.append("")
        lines.append(_render_team_table(me, podium))
    if jira:
        lines.append("")
        lines.append(jira)
    return "\n".join(lines)


MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
TEAM_PODIUM = 3


def _render_table(me: Standing, standings: Sequence[Standing]) -> str:
    standings = [s for s in standings if s.position <= TEAM_PODIUM]
    names = ["You" if s.player == me.player else s.player.github for s in standings]
    width = max(len("Player"), max(len(name) for name in names))
    points = max(s.points for s in standings)
    digits = max(len("Pts"), len(str(points)))

    given_digits = max(len("Given"), max(len(str(s.given)) for s in standings))
    received_digits = max(len("Received"), max(len(str(s.received)) for s in standings))
    show_tickets = any(s.tickets for s in standings)
    ticket_digits = max(len("Tickets"), max(len(str(s.tickets)) for s in standings))
    rows = [
        f" #  {'Player':<{width}}  {'Pts':>{digits}}   "
        f"{'Given':>{given_digits}}  {'Received':>{received_digits}}"
        + (f"  {'Tickets':>{ticket_digits}}" if show_tickets else "")
    ]
    for s, name in zip(standings, names):
        place = MEDALS.get(s.position, f"{s.position:>2}")
        marker = "  ◀" if s.player == me.player else ""
        tickets = f"  {s.tickets:>{ticket_digits}}" if show_tickets else ""
        rows.append(
            f"{place}  {name:<{width}}  {s.points:>{digits}}   "
            f"{s.given:>{given_digits}}  {s.received:>{received_digits}}{tickets}{marker}"
        )
    return "```\n" + "\n".join(rows) + "\n```"


def _render_team_table(me: Standing, teams: Sequence[TeamStanding]) -> str:
    width = max(len("Team"), max(len(t.name) for t in teams))
    digits = max(len("Pts"), *(len(str(t.points)) for t in teams))
    rows = [f" #  {'Team':<{width}}  {'Pts':>{digits}}"]
    for t in teams:
        marker = "  ◀" if t.name == me.player.team else ""
        rows.append(f"{MEDALS[t.position]}  {t.name:<{width}}  {t.points:>{digits}}{marker}")
    return "```\n" + "\n".join(rows) + "\n```"


def week_start(now: datetime) -> datetime:
    """Monday 00:00 local on or before now, clipped to the 1st of the month."""
    monday = (now - timedelta(days=now.weekday())).date()
    first = now.date().replace(day=1)
    return datetime.combine(max(monday, first), datetime.min.time()).astimezone()


def render_jira_week(events: Iterable[TicketEvent], me: Player, since: datetime) -> str:
    keys: dict[str, list[str]] = {status: [] for status in TICKET_POINTS}
    for e in events:
        if e.actor.lower() == me.github.lower() and e.at >= since and e.status in keys:
            if e.key not in keys[e.status]:
                keys[e.status].append(e.key)

    lines = ["🎫 *This week in Jira*"]
    if not any(keys.values()):
        lines.append("No tickets moved this week.")
        return "\n".join(lines)
    for status, moved in keys.items():
        if moved:
            lines.append(f"• {status}: {len(moved)} ({', '.join(moved)}), {len(moved) * TICKET_POINTS[status]} pts")
        else:
            lines.append(f"• {status}: 0")
    return "\n".join(lines)
