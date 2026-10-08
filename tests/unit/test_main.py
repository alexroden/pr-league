from datetime import datetime, timezone

from pr_league.config import Config
from pr_league.main import run
from pr_league.models import Player

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


class NoReviews:
    def fetch_reviews(self, org, since):
        return []


class RecordingMessenger:
    def __init__(self):
        self.sent = []

    def send(self, slack_id, text):
        self.sent.append(slack_id)


def config(*players):
    return Config("acme", tuple(players), "gh-token", None)


def test_players_without_a_slack_id_are_scored_but_not_messaged():
    messenger = RecordingMessenger()
    failures = run(config(Player("sam", "U1"), Player("jess", None)), NoReviews(), messenger, NOW)
    assert messenger.sent == ["U1"]
    assert failures == 0


def test_players_without_a_slack_id_are_not_counted_as_failures():
    messenger = RecordingMessenger()
    assert run(config(Player("jess", None)), NoReviews(), messenger, NOW) == 0
    assert messenger.sent == []
