from datetime import datetime, timezone

from pr_league.casting import cast_roster, rename_reviews, rename_tickets
from pr_league.models import Player, ReviewEvent, TicketEvent

WHEN = datetime(2026, 10, 2, tzinfo=timezone.utc)

REAL = [Player("ann", "U1", "Real", "j-ann"), Player("bob", None, "Real", "j-bob")]
STANDINS = [Player("x", "U9", "Fake"), Player("y", "U8", "Fake"), Player("z", "U7", "Fake")]


def test_real_players_take_the_first_standin_names():
    cast, rename = cast_roster(REAL, STANDINS)
    assert rename == {"x": "ann", "y": "bob"}
    assert [p.github for p in cast] == ["ann", "bob", "z"]


def test_real_players_keep_their_own_details():
    cast, _ = cast_roster(REAL, STANDINS)
    assert cast[0] == REAL[0]
    assert cast[1] == REAL[1]


def test_leftover_standins_stay_as_they_are():
    cast, _ = cast_roster(REAL, STANDINS)
    assert cast[2] == STANDINS[2]


def test_more_real_players_than_standins_are_all_kept():
    many = [Player(f"p{i}", None) for i in range(5)]
    cast, rename = cast_roster(many, STANDINS)
    assert [p.github for p in cast] == [f"p{i}" for i in range(5)]
    assert rename == {"x": "p0", "y": "p1", "z": "p2"}


def test_review_events_are_renamed_for_reviewer_and_author():
    renamed = rename_reviews([ReviewEvent("acme#1", "x", "y", WHEN)], {"x": "ann", "y": "bob"})
    assert (renamed[0].reviewer, renamed[0].author, renamed[0].pr) == ("ann", "bob", "acme#1")


def test_ticket_events_are_renamed_for_the_actor():
    renamed = rename_tickets([TicketEvent("PLAT-1", "x", "Closed", WHEN)], {"x": "ann"})
    assert (renamed[0].actor, renamed[0].key, renamed[0].status) == ("ann", "PLAT-1", "Closed")


def test_names_without_a_mapping_are_left_alone():
    renamed = rename_reviews([ReviewEvent("acme#1", "q", "x", WHEN)], {"x": "ann"})
    assert (renamed[0].reviewer, renamed[0].author) == ("q", "ann")
