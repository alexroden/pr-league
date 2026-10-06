from datetime import date

from pr_league.models import Player, Standing
from pr_league.rendering import ordinal, render_dm

OCT = date(2026, 10, 3)


def table(*rows):
    """rows are (login, given, received, position) tuples."""
    return [Standing(Player(login, "U" + login), g, r, pos) for login, g, r, pos in rows]


def test_ordinal_suffixes():
    expected = {
        1: "1st", 2: "2nd", 3: "3rd", 4: "4th",
        11: "11th", 12: "12th", 13: "13th",
        21: "21st", 22: "22nd", 23: "23rd", 101: "101st", 111: "111th",
    }
    for n, text in expected.items():
        assert ordinal(n) == text


def test_header_has_month_and_week_of_month():
    standings = table(("sam", 1, 0, 1))
    assert "*PR League: October, week 1*" in render_dm(standings[0], standings, date(2026, 10, 1))
    assert "week 1*" in render_dm(standings[0], standings, date(2026, 10, 7))
    assert "week 2*" in render_dm(standings[0], standings, date(2026, 10, 8))
    assert "week 5*" in render_dm(standings[0], standings, date(2026, 10, 29))


def test_position_points_and_breakdown():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2), ("alex", 5, 6, 3))
    text = render_dm(standings[1], standings, OCT)
    assert "You're *2nd* of 3 this month with *14 points* (7 reviews given, 7 received)." in text


def test_singular_wording():
    standings = table(("sam", 1, 0, 1), ("you", 0, 0, 2))
    assert "*1 point*" in render_dm(standings[0], standings, OCT)
    assert "(1 review given, 0 received)" in render_dm(standings[0], standings, OCT)


def test_next_up_names_the_player_ahead_and_the_gap():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    assert "Next up: sam, 1 point ahead of you." in render_dm(standings[1], standings, OCT)


def test_next_up_uses_plural_gap():
    standings = table(("sam", 8, 8, 1), ("you", 7, 7, 2))
    assert "Next up: sam, 2 points ahead of you." in render_dm(standings[1], standings, OCT)


def test_next_up_names_every_player_tied_ahead():
    standings = table(("bob", 5, 5, 1), ("sam", 5, 5, 1), ("you", 1, 0, 3))
    assert "Next up: bob and sam, 9 points ahead of you." in render_dm(standings[2], standings, OCT)


def test_leader_has_no_next_up_line():
    standings = table(("you", 8, 7, 1), ("sam", 7, 7, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "Next up" not in text
    assert "*1st*" in text


def test_joint_leaders_say_joint_and_have_no_next_up_line():
    standings = table(("you", 5, 5, 1), ("sam", 5, 5, 1), ("alex", 1, 0, 3))
    text = render_dm(standings[0], standings, OCT)
    assert "*joint 1st*" in text
    assert "Next up" not in text


def test_everyone_on_zero_does_not_crash():
    standings = table(("you", 0, 0, 1), ("sam", 0, 0, 1))
    text = render_dm(standings[0], standings, OCT)
    assert "*joint 1st* of 2" in text
    assert "*0 points*" in text
    assert "Next up" not in text


def test_table_marks_the_reader_as_you():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2), ("alex", 5, 6, 3))
    text = render_dm(standings[1], standings, OCT)
    assert "Table: 1. sam (15) · 2. You (14) · 3. alex (11)" in text
