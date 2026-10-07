from datetime import date

from pr_league.models import Player, Standing, TeamStanding
from pr_league.rendering import _render_table, _render_team_table, ordinal, render_dm, render_winners

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


def test_header_has_trophy_month_and_week_of_month():
    standings = table(("sam", 1, 0, 1))
    assert "🏆 *PR League: October, week 1*" in render_dm(standings[0], standings, date(2026, 10, 1))
    assert "week 1*" in render_dm(standings[0], standings, date(2026, 10, 7))
    assert "week 2*" in render_dm(standings[0], standings, date(2026, 10, 8))
    assert "week 5*" in render_dm(standings[0], standings, date(2026, 10, 29))


def test_position_points_and_breakdown():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2), ("alex", 5, 6, 3))
    text = render_dm(standings[1], standings, OCT)
    assert "You're *2nd* of 3 this month with *21 points* (7 reviews given, 7 received)." in text


def test_singular_wording():
    reviewer = table(("sam", 1, 0, 1))
    text = render_dm(reviewer[0], reviewer, OCT)
    assert "*2 points*" in text
    assert "(1 review given, 0 received)" in text
    author = table(("you", 0, 1, 1))
    text = render_dm(author[0], author, OCT)
    assert "*1 point*" in text
    assert "(0 reviews given, 1 received)" in text


def test_next_up_names_the_player_ahead_and_the_gap():
    standings = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    assert "⬆️ Next up: sam, 1 point ahead of you." in render_dm(standings[1], standings, OCT)


def test_next_up_uses_plural_gap():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    assert "⬆️ Next up: sam, 2 points ahead of you." in render_dm(standings[1], standings, OCT)


def test_next_up_names_every_player_tied_ahead():
    standings = table(("bob", 5, 5, 1), ("sam", 5, 5, 1), ("you", 1, 0, 3))
    assert "⬆️ Next up: bob and sam, 13 points ahead of you." in render_dm(standings[2], standings, OCT)


def test_leader_has_no_next_up_line():
    standings = table(("you", 8, 7, 1), ("sam", 7, 7, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "Next up" not in text
    assert "*1st*" in text


def test_table_is_a_fenced_code_block():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    text = render_dm(standings[1], standings, OCT)
    assert "```" in text


def test_table_medals_top_three_and_hides_the_rest():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2), ("alex", 5, 6, 3), ("ravi", 3, 2, 4), ("mira", 4, 0, 5))
    text = render_dm(standings[1], standings, OCT)
    assert " #  Player  Pts   Given  Received" in text
    assert "🥇  sam      23       8         7" in text
    assert "🥈  You      21       7         7  ◀" in text
    assert "🥉  alex     16       5         6" in text
    assert "ravi" not in text
    assert "mira" not in text


def test_table_marks_only_the_readers_row():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    text = render_dm(standings[1], standings, OCT)
    assert "◀" not in text.split("🥇", 1)[1].split("\n", 1)[0]
    assert text.count("◀") == 1


def test_table_widens_for_long_names():
    standings = table(("constantin", 8, 7, 1), ("you", 7, 7, 2))
    text = render_dm(standings[1], standings, OCT)
    assert " #  Player      Pts   Given  Received" in text
    assert "🥇  constantin   23       8         7" in text
    assert "🥈  You          21       7         7  ◀" in text


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
    assert "You" in text
    for login in ("sam", "alex"):
        assert login in text


def teams(*rows):
    """rows are (name, points, position) tuples."""
    return [TeamStanding(name, pts, pos) for name, pts, pos in rows]


def mine(team):
    return Standing(Player("you", "Uyou", team), 7, 7, 2)


def test_team_league_shows_only_the_top_three_teams():
    league = teams(("core", 30, 1), ("web", 22, 2), ("data", 15, 3), ("infra", 9, 4))
    text = render_dm(mine("web"), [mine("web")], OCT, league)
    assert "*Team league*" in text
    assert "🥇  core   30" in text
    assert "🥈  web    22  ◀" in text
    assert "🥉  data   15" in text
    assert "infra" not in text


def test_team_league_marks_nothing_when_your_team_is_outside_the_top_three():
    league = teams(("core", 30, 1), ("web", 22, 2), ("data", 15, 3), ("infra", 9, 4))
    text = render_dm(mine("infra"), [mine("infra")], OCT, league)
    team_table = text.split("*Team league*", 1)[1]
    assert "◀" not in team_table


def test_team_league_includes_teams_tied_for_third():
    league = teams(("core", 30, 1), ("web", 22, 2), ("data", 15, 3), ("infra", 15, 3), ("qa", 2, 5))
    text = render_dm(mine("web"), [mine("web")], OCT, league)
    assert "🥉  data    15" in text
    assert "🥉  infra   15" in text
    assert "qa" not in text


def test_no_team_league_section_without_teams():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    assert "Team league" not in render_dm(standings[1], standings, OCT)


def test_winners_section_announces_player_and_team_winners():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    text = render_winners(prev, teams(("Web", 27, 1)), "September")
    assert text == "🎉 *September winners*\n\n🏆 sam (22 points)\n🏆 Team: Web (27 points)"


def test_winners_section_names_tied_player_and_team_winners():
    prev = table(("sam", 5, 5, 1), ("bob", 5, 5, 1), ("you", 1, 0, 3))
    league = teams(("Web", 20, 1), ("Data", 20, 1))
    text = render_winners(prev, league, "September")
    assert "🏆 sam (15 points)" in text
    assert "🏆 bob (15 points)" in text
    assert "🏆 Team: Web (20 points)" in text
    assert "🏆 Team: Data (20 points)" in text


def test_winners_section_without_teams_has_no_team_part():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    assert render_winners(prev, (), "September") == "🎉 *September winners*\n\n🏆 sam (22 points)"


def test_winners_section_uses_singular_point_wording():
    prev = table(("sam", 0, 1, 1), ("you", 0, 0, 2))
    assert render_winners(prev, (), "September") == "🎉 *September winners*\n\n🏆 sam (1 point)"


def test_winners_section_sits_after_the_header_and_defaults_to_absent():
    standings = table(("sam", 8, 7, 1), ("you", 7, 7, 2))
    winners = render_winners(standings, teams(("Web", 27, 1)), "September")
    text = render_dm(standings[1], standings, OCT, winners=winners)
    assert text.splitlines()[2:6] == winners.splitlines()
    assert "September winners" not in render_dm(standings[1], standings, OCT)


def test_winners_line_is_separated_from_header_and_body():
    winners = render_winners(table(("sam", 8, 6, 1), ("you", 7, 7, 2)), (), "September")
    standings = table(("you", 7, 7, 1))
    lines = render_dm(standings[0], standings, OCT, winners=winners).splitlines()
    assert lines[2] == "🎉 *September winners*"
    assert lines[3] == ""
    assert lines[4].startswith("🏆 sam")
    assert lines[5] == ""
    assert lines[6].startswith("⚽")
    assert lines[8].startswith("👟")
    assert lines[10] == ""
    assert lines[11].startswith("You're")


def test_winners_streak_of_one_month_has_no_streak_note():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    text = render_winners(prev, (), "September", streaks={"sam": 1})
    assert "in a row" not in text


def test_winners_streak_of_two_months_is_announced():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    text = render_winners(prev, (), "September", streaks={"sam": 3})
    assert "🏆 sam (22 points) — 3 months in a row" in text


def test_team_winners_streak_is_announced():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    text = render_winners(prev, teams(("Web", 27, 1)), "September", team_streaks={"Web": 2})
    assert "🏆 Team: Web (27 points) — 2 months in a row" in text


def test_blank_line_after_the_header():
    standings = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    assert lines[0].startswith("🏆")
    assert lines[1] == ""





def test_team_league_title_has_blank_lines_around_it():
    league = teams(("core", 30, 1), ("web", 22, 2))
    lines = render_dm(mine("web"), [mine("web")], OCT, league).splitlines()
    i = lines.index("*Team league*")
    assert lines[i - 1] == ""
    assert lines[i + 1] == ""


def test_blank_line_before_the_player_table():
    standings = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    i = next(i for i, line in enumerate(lines) if line.startswith("```"))
    assert lines[i - 1] == ""


def test_player_table_keeps_players_tied_for_third():
    standings = table(("jess", 5, 5, 1), ("lena", 5, 4, 2), ("mira", 4, 4, 3), ("ravi", 4, 4, 3), ("sam", 4, 4, 3), ("tom", 3, 4, 6))
    text = render_dm(standings[5], standings, OCT)  # read as tom: everyone above shows
    for login in ("You", "jess", "lena", "mira", "ravi", "sam"):
        assert login in text
    assert "🥉" in text
    assert " 6  tom" not in text  # tom's own row is hidden even though he reads it


def test_player_table_leaves_out_the_reader_when_outside_the_top_three():
    standings = table(("sam", 8, 6, 1), ("jess", 5, 5, 2), ("lena", 5, 4, 3), ("you", 0, 0, 4))
    text = render_dm(standings[3], standings, OCT)
    player_table = text.split("```")[1]
    assert "You" not in player_table
    assert "You're *4th* of 4" in text


def test_top_scorer_section_skipped_when_nobody_leads_the_fixture():
    standings = [mine("web")]
    text = render_dm(standings[0], standings, OCT, teams(("core", 30, 1), ("web", 22, 2)))
    assert "Top scorer" not in text


def test_top_scorer_section_names_the_current_leader():
    standings = table(("jess", 5, 5, 1), ("you", 5, 4, 2))
    text = render_dm(standings[1], standings, OCT)
    assert "⚽ *Top scorer of the month: jess (15 points)*" in text


def test_top_scorer_sits_below_the_winners_as_its_own_section():
    standings = table(("jess", 5, 5, 1), ("you", 5, 4, 2))
    winners = render_winners(table(("sam", 8, 6, 1), ("you", 7, 7, 2)), (), "September")
    lines = render_dm(standings[1], standings, OCT, winners=winners).splitlines()
    assert lines[2:5] == winners.splitlines()
    assert lines[5] == ""
    assert lines[6] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[8].startswith("👟")
    assert lines[10] == ""
    assert lines[11].startswith("You're")


def test_wider_gap_between_the_top_sections_and_the_body():
    standings = table(("jess", 5, 5, 1), ("you", 4, 4, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    assert lines[2] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[3] == ""
    assert lines[4] == "👟 *Top assists of the month: jess (5 reviews given)*"
    assert lines[5] == ""
    assert lines[6] == ""
    assert "You're" in lines[7]


def test_top_scorer_section_names_tied_leaders():
    standings = table(("jess", 5, 5, 1), ("sam", 5, 5, 1), ("you", 0, 0, 3))
    text = render_dm(standings[2], standings, OCT)
    assert "⚽ *Top scorer of the month: jess and sam (15 points)*" in text


def test_top_scorer_section_mentions_the_reader_when_they_lead():
    standings = table(("you", 5, 5, 1), ("sam", 0, 0, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "⚽ *Top scorer of the month: You (15 points)*" in text


def test_top_assists_sits_below_the_top_scorer_as_its_own_section():
    standings = table(("jess", 5, 5, 1), ("lena", 4, 4, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    assert lines[2] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[3] == ""
    assert lines[4] == "👟 *Top assists of the month: jess (5 reviews given)*"
    assert lines[5] == ""


def test_top_assists_names_tied_reviewers():
    standings = table(("jess", 5, 5, 1), ("sam", 5, 3, 1), ("you", 0, 0, 3))
    text = render_dm(standings[2], standings, OCT)
    assert "👟 *Top assists of the month: jess and sam (5 reviews given)*" in text


def test_top_assists_mentions_the_reader_when_they_lead():
    standings = table(("you", 5, 0, 1), ("sam", 0, 5, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "👟 *Top assists of the month: You (5 reviews given)*" in text


def test_winners_title_is_separated_from_the_winner_lines():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    lines = render_winners(prev, teams(("Web", 27, 1)), "September").splitlines()
    assert lines[0] == "🎉 *September winners*"
    assert lines[1] == ""
    assert lines[2].startswith("🏆 sam")
    assert lines[3].startswith("🏆 Team: Web")


def test_team_table_pts_header_lines_up_with_the_values():
    league = teams(("Web", 27, 1))
    table = _render_team_table(mine("web"), league)
    header, row = table.splitlines()[1:3]
    assert header.endswith("Pts")
    assert row.rstrip().endswith(" 27")  # value right-aligned under the 3-wide Pts header


def test_player_table_pts_header_lines_up_with_the_values():
    standings = table(("jess", 5, 5, 1), ("lena", 5, 4, 2))
    rows = _render_table(standings[0], standings).splitlines()
    header, row = rows[1], rows[2]

    def display_columns(text):
        # medals render two columns wide but are one character
        return len(text) + sum(1 for medal in ("🥇", "🥈", "🥉") if medal in text)

    pts_edge = display_columns(header[: header.index("Pts") + 3])
    value_edge = display_columns(row[: row.index("15") + 2])
    assert pts_edge == value_edge


def test_blank_line_before_the_player_table():
    standings = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    i = next(i for i, line in enumerate(lines) if line.startswith("```"))
    assert lines[i - 1] == ""


def test_player_table_keeps_players_tied_for_third():
    standings = table(("jess", 5, 5, 1), ("lena", 5, 4, 2), ("mira", 4, 4, 3), ("ravi", 4, 4, 3), ("sam", 4, 4, 3), ("tom", 3, 4, 6))
    text = render_dm(standings[5], standings, OCT)  # read as tom: everyone above shows
    for login in ("You", "jess", "lena", "mira", "ravi", "sam"):
        assert login in text
    assert "🥉" in text
    assert " 6  tom" not in text  # tom's own row is hidden even though he reads it


def test_player_table_leaves_out_the_reader_when_outside_the_top_three():
    standings = table(("sam", 8, 6, 1), ("jess", 5, 5, 2), ("lena", 5, 4, 3), ("you", 0, 0, 4))
    text = render_dm(standings[3], standings, OCT)
    player_table = text.split("```")[1]
    assert "You" not in player_table
    assert "You're *4th* of 4" in text


def test_top_scorer_section_skipped_when_nobody_leads_the_fixture():
    standings = [mine("web")]
    text = render_dm(standings[0], standings, OCT, teams(("core", 30, 1), ("web", 22, 2)))
    assert "Top scorer" not in text


def test_top_scorer_section_names_the_current_leader():
    standings = table(("jess", 5, 5, 1), ("you", 5, 4, 2))
    text = render_dm(standings[1], standings, OCT)
    assert "⚽ *Top scorer of the month: jess (15 points)*" in text


def test_top_scorer_sits_below_the_winners_as_its_own_section():
    standings = table(("jess", 5, 5, 1), ("you", 5, 4, 2))
    winners = render_winners(table(("sam", 8, 6, 1), ("you", 7, 7, 2)), (), "September")
    lines = render_dm(standings[1], standings, OCT, winners=winners).splitlines()
    assert lines[2:5] == winners.splitlines()
    assert lines[5] == ""
    assert lines[6] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[8].startswith("👟")
    assert lines[10] == ""
    assert lines[11].startswith("You're")


def test_wider_gap_between_the_top_sections_and_the_body():
    standings = table(("jess", 5, 5, 1), ("you", 4, 4, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    assert lines[2] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[3] == ""
    assert lines[4] == "👟 *Top assists of the month: jess (5 reviews given)*"
    assert lines[5] == ""
    assert lines[6] == ""
    assert "You're" in lines[7]


def test_top_scorer_section_names_tied_leaders():
    standings = table(("jess", 5, 5, 1), ("sam", 5, 5, 1), ("you", 0, 0, 3))
    text = render_dm(standings[2], standings, OCT)
    assert "⚽ *Top scorer of the month: jess and sam (15 points)*" in text


def test_top_scorer_section_mentions_the_reader_when_they_lead():
    standings = table(("you", 5, 5, 1), ("sam", 0, 0, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "⚽ *Top scorer of the month: You (15 points)*" in text


def test_top_assists_sits_below_the_top_scorer_as_its_own_section():
    standings = table(("jess", 5, 5, 1), ("lena", 4, 4, 2))
    lines = render_dm(standings[1], standings, OCT).splitlines()
    assert lines[2] == "⚽ *Top scorer of the month: jess (15 points)*"
    assert lines[3] == ""
    assert lines[4] == "👟 *Top assists of the month: jess (5 reviews given)*"
    assert lines[5] == ""


def test_top_assists_names_tied_reviewers():
    standings = table(("jess", 5, 5, 1), ("sam", 5, 3, 1), ("you", 0, 0, 3))
    text = render_dm(standings[2], standings, OCT)
    assert "👟 *Top assists of the month: jess and sam (5 reviews given)*" in text


def test_top_assists_mentions_the_reader_when_they_lead():
    standings = table(("you", 5, 0, 1), ("sam", 0, 5, 2))
    text = render_dm(standings[0], standings, OCT)
    assert "👟 *Top assists of the month: You (5 reviews given)*" in text


def test_winners_title_is_separated_from_the_winner_lines():
    prev = table(("sam", 8, 6, 1), ("you", 7, 7, 2))
    lines = render_winners(prev, teams(("Web", 27, 1)), "September").splitlines()
    assert lines[0] == "🎉 *September winners*"
    assert lines[1] == ""
    assert lines[2].startswith("🏆 sam")
    assert lines[3].startswith("🏆 Team: Web")


def test_team_table_pts_header_lines_up_with_the_values():
    league = teams(("Web", 27, 1))
    table = _render_team_table(mine("web"), league)
    header, row = table.splitlines()[1:3]
    assert header.endswith("Pts")
    assert row.rstrip().endswith(" 27")  # value right-aligned under the 3-wide Pts header


def test_player_table_pts_header_lines_up_with_the_values():
    standings = table(("jess", 5, 5, 1), ("lena", 5, 4, 2))
    rows = _render_table(standings[0], standings).splitlines()
    header, row = rows[1], rows[2]
    display_width = len(row) - row.count("🥇") - row.count("🥈") - row.count("🥉")  # medals render double-width
    header_width = len(header) - header.count(" ") + 0
    # account for emoji taking two display columns but one character
    emoji = any(medal in row for medal in ("🥇", "🥈", "🥉"))
    offset = 1 if emoji else 0
    assert header.index("Pts") + 3 == display_width - (len(row) - row.index("15") - 2) + 0 or True
    # simpler: verify the header's Pts column right edge equals the row's, in display columns
    def display_len(text, medals):
        return len(text) + sum(1 for m in medals if m in text)
    medals = ("🥇", "🥈", "🥉")
    assert display_len(header[:header.index("Pts") + 3], ()) == display_len(row[:row.index("15") + 2], medals)
