import argparse
import logging
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

from pr_league.config import Config, load_config
from pr_league.github import GitHubClient
from pr_league.rendering import render_dm, render_winners
from pr_league.scoring import rank_teams, score, win_streaks
from pr_league.slack import SlackMessenger

log = logging.getLogger("pr_league")

ANNOUNCE_WINDOW_DAYS = 7
STREAK_LOOKBACK_MONTHS = 6


def _month_start(shift: datetime) -> datetime:
    return shift.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _winning_months(standings, teams, github: str, team: str | None) -> int:
    """How many consecutive months ending with the announced one this player and team won, 1 if none prior."""
    raise NotImplementedError


def _streaks(prev_standings, prev_teams, github, team, github_client, config, prev_last) -> tuple[dict[str, int], dict[str, int]]:
    raise NotImplementedError


def run(config: Config, github: GitHubClient, messenger: SlackMessenger | None, now: datetime) -> int:
    """Fetch, score and DM. A None messenger prints instead (dry run). Returns the failure count."""
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    events = github.fetch_reviews(config.org, month_start)
    standings = score(events, config.players)
    teams = rank_teams(standings)

    winners = ""
    if now.day <= ANNOUNCE_WINDOW_DAYS:
        prev_last = month_start - timedelta(days=1)
        prev_start = prev_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_events = github.fetch_reviews(config.org, prev_start)
        prev_standings = score(prev_events, config.players)
        prev_teams = rank_teams(prev_standings)

        player_history: list[set[str]] = []
        team_history: list[set[str]] = []
        window_start = prev_start
        for _ in range(STREAK_LOOKBACK_MONTHS):
            events_for_month = (
                prev_events if window_start == prev_start else github.fetch_reviews(config.org, window_start)
            )
            month_standings = (
                prev_standings if window_start == prev_start else score(events_for_month, config.players)
            )
            month_teams = rank_teams(month_standings)
            player_history.append({s.player.github for s in month_standings if s.position == 1})
            team_history.append({t.name for t in month_teams if t.position == 1})
            window_last = window_start - timedelta(days=1)
            window_start = window_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        streaks = win_streaks(player_history)
        team_streaks = win_streaks(team_history)
        winners = render_winners(
            prev_standings, prev_teams, prev_last.strftime("%B"), streaks, team_streaks
        )

    failures = 0
    for standing in standings:
        text = render_dm(standing, standings, now.date(), teams, winners)
        if messenger is None:
            print(f"--- would DM {standing.player.github} ({standing.player.slack}) ---\n{text}\n")
            continue
        try:
            messenger.send(standing.player.slack, text)
            log.info("DM sent to %s", standing.player.github)
        except Exception:
            failures += 1
            log.exception("DM to %s failed", standing.player.github)
    return failures


def cli() -> None:
    parser = argparse.ArgumentParser(prog="pr-league")
    parser.add_argument("--dry-run", action="store_true", help="print the DMs instead of sending them")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    config = load_config(args.config)

    messenger = None
    if not args.dry_run:
        if not config.slack_token:
            sys.exit("SLACK_BOT_TOKEN is not set (see .env.example), or use --dry-run")
        messenger = SlackMessenger(config.slack_token)

    now = datetime.now().astimezone()
    failures = run(config, GitHubClient(config.github_token), messenger, now)
    if failures:
        sys.exit(f"{failures} DM(s) failed")
