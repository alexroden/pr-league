import argparse
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv

from pr_league.config import Config, load_config
from pr_league.github import GitHubClient
from pr_league.rendering import render_dm
from pr_league.scoring import score
from pr_league.slack import SlackMessenger

log = logging.getLogger("pr_league")


def run(config: Config, github: GitHubClient, messenger: SlackMessenger | None, now: datetime) -> int:
    """Fetch, score and DM. A None messenger prints instead (dry run). Returns the failure count."""
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    events = github.fetch_reviews(config.org, month_start)
    standings = score(events, config.players)

    failures = 0
    for standing in standings:
        text = render_dm(standing, standings, now.date())
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
