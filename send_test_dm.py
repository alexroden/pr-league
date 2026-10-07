"""Send yourself a stubbed DM. With --mock, prints the DM and the Slack call instead of sending.

All players, teams, and both months' reviews are fixtures — no GitHub is
contacted, so it runs instantly. You play for YOUR_TEAM. If today is within
WINNERS_WINDOW_DAYS of the start of the month, the DM also announces the
previous month's stubbed winners. On Fridays, or with --jira, it ends with
the reader's stubbed "This week in Jira" block.
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta

import yaml
from dotenv import load_dotenv
from pathlib import Path

from pr_league.models import Player, ReviewEvent, TicketEvent
from pr_league.rendering import render_dm, render_jira_week, render_winners, week_start
from pr_league.scoring import rank_teams, score, win_streaks
from pr_league.slack import SlackMessenger

log = logging.getLogger("pr_league")

YOUR_TEAM = "Platform"
WINNERS_WINDOW_DAYS = 7
FRIDAY = 4

FAKE_PLAYERS = (
    Player("sam", "U0000000001", "Platform"),
    Player("jess", "U0000000002", "Web"),
    Player("ravi", "U0000000003", "Web"),
    Player("mira", "U0000000004", "Data"),
    Player("tom", "U0000000005", "Mobile"),
    Player("lena", "U0000000006", "Data"),
)


def fixture_events(now):
    """Reviews among the stubbed players this month — no points land on the reader."""

    def event(pr, reviewer, author, days_ago):
        return ReviewEvent(f"acme/api#{pr}", reviewer, author, now - timedelta(days=days_ago))

    return [
        event(11, "jess", "sam", 6), event(12, "jess", "ravi", 6), event(13, "jess", "mira", 5),
        event(14, "jess", "lena", 5), event(15, "jess", "tom", 4),
        event(16, "sam", "tom", 6), event(17, "sam", "jess", 5), event(18, "sam", "ravi", 4),
        event(19, "sam", "mira", 3),
        event(20, "ravi", "tom", 5), event(21, "ravi", "jess", 4), event(22, "ravi", "sam", 3),
        event(23, "ravi", "lena", 2),
        event(24, "mira", "tom", 4), event(25, "mira", "jess", 3), event(26, "mira", "sam", 2),
        event(27, "mira", "lena", 1),
        event(28, "lena", "jess", 6), event(29, "lena", "sam", 5), event(30, "lena", "ravi", 4),
        event(31, "lena", "mira", 3), event(32, "lena", "ravi", 2),
        event(33, "tom", "jess", 6), event(34, "tom", "mira", 5), event(35, "tom", "lena", 4),
    ]


def last_month_events(now):
    """Reviews among the stubbed players last month — decides the stubbed winners.

    jess edges out sam, and Web takes the team title.
    """

    def event(pr, reviewer, author, days_ago):
        return ReviewEvent(f"acme/api#{pr}", reviewer, author, now - timedelta(days=days_ago))

    return [
        event(1, "jess", "sam", 36), event(2, "jess", "ravi", 35), event(3, "jess", "mira", 34),
        event(4, "jess", "tom", 33), event(5, "jess", "lena", 32),
        event(6, "sam", "jess", 35), event(7, "sam", "ravi", 34), event(8, "sam", "mira", 33),
        event(9, "sam", "tom", 32),
        event(10, "ravi", "tom", 34), event(11, "ravi", "sam", 33), event(12, "ravi", "jess", 32),
        event(13, "mira", "tom", 33), event(14, "mira", "jess", 32),
        event(15, "lena", "sam", 34), event(16, "lena", "ravi", 33), event(17, "lena", "tom", 32),
        event(18, "tom", "jess", 34), event(19, "tom", "sam", 33),
    ]


def fixture_tickets(now, you):
    """Ticket transitions this month. The reader's land this week; Closed is left empty for them."""
    monday = week_start(now)

    def moved(key, actor, status, days_ago):
        return TicketEvent(key, actor, status, now - timedelta(days=days_ago))

    def this_week(key, status, hours_after_monday):
        return TicketEvent(key, you, status, min(now, monday + timedelta(hours=hours_after_monday)))

    return [
        this_week("PLAT-412", "QE check run", 1),
        this_week("PLAT-415", "QE check run", 2),
        this_week("PLAT-398", "Ready for production", 3),
        moved("PLAT-371", "jess", "Closed", 5), moved("PLAT-371", "jess", "Ready for production", 6),
        moved("PLAT-380", "mira", "QE check run", 4), moved("PLAT-383", "tom", "Closed", 3),
        moved("PLAT-390", "lena", "Ready for production", 2),
    ]


def last_month_tickets(now):
    """Ticket transitions last month — sam's Closed tickets don't overturn jess's win."""

    def moved(key, actor, status, days_ago):
        return TicketEvent(key, actor, status, now - timedelta(days=days_ago))

    return [
        moved("PLAT-301", "jess", "Closed", 34), moved("PLAT-305", "sam", "Closed", 33),
        moved("PLAT-310", "ravi", "QE check run", 32),
    ]


# Stubbed winners of the two months before the one being announced, oldest
# first — jess and Web won both, so they announce a 2-month streak.
AUGUST_WINNERS = {"jess"}
SEPTEMBER_WINNERS = {"jess"}
AUGUST_TEAM_WINNERS = {"Web"}
SEPTEMBER_TEAM_WINNERS = {"Web"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--mock", action="store_true", help="print the DM instead of sending it")
    parser.add_argument(
        "--channel",
        help="post to a channel name or ID (e.g. #tmp-platform-hack-team-4) instead of your DM",
    )
    parser.add_argument("--jira", action="store_true", help="show the This week in Jira block on any day")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()

    raw = yaml.safe_load(Path(args.config).read_text()) or {}
    entries = raw.get("players") or []
    if not entries:
        sys.exit(f"{args.config} must set at least one player (see config.example.yaml)")
    you = Player(github=entries[0]["github"], slack=entries[0]["slack"], team=YOUR_TEAM)

    now = datetime.now().astimezone()
    roster = (you,) + FAKE_PLAYERS
    tickets = fixture_tickets(now, you.github)
    standings = score(fixture_events(now), roster, tickets)
    teams = rank_teams(standings)

    winners = ""
    if now.day <= WINNERS_WINDOW_DAYS:
        prev_standings = score(last_month_events(now), roster, last_month_tickets(now))
        prev_teams = rank_teams(prev_standings)
        prev_month_name = (now.replace(day=1) - timedelta(days=1)).strftime("%B")
        streaks = win_streaks([AUGUST_WINNERS, SEPTEMBER_WINNERS])
        team_streaks = win_streaks([AUGUST_TEAM_WINNERS, SEPTEMBER_TEAM_WINNERS])
        winners = render_winners(prev_standings, prev_teams, prev_month_name, streaks, team_streaks)

    jira = ""
    if args.jira or now.weekday() == FRIDAY:
        jira = render_jira_week(tickets, you, week_start(now))

    for standing in standings:
        if standing.player == you:
            text = render_dm(standing, standings, now.date(), teams, winners, jira)
            break
    else:
        sys.exit(f"{you.github} not found in standings")
    destination = args.channel or you.slack
    if args.mock:
        print(f"POST chat.postMessage channel={destination}\n\n{text}")
        return 0

    token = __import__("os").environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set (see .env.example)")
    SlackMessenger(token).send(destination, text)
    log.info("Test DM sent to %s", destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
