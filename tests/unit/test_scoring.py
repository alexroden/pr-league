from datetime import datetime, timezone

from pr_league.models import Player, ReviewEvent, Standing
from pr_league.scoring import rank_teams, score, win_streaks

ALICE = Player("alice", "U1")
BOB = Player("bob", "U2")
CAROL = Player("carol", "U3")
WHEN = datetime(2026, 10, 2, tzinfo=timezone.utc)


def review(pr_number, reviewer, author):
    return ReviewEvent(f"acme/app#{pr_number}", reviewer, author, WHEN)


def by_login(standings):
    return {s.player.github: s for s in standings}


def test_review_scores_reviewer_and_author():
    s = by_login(score([review(1, "alice", "bob")], [ALICE, BOB]))
    assert (s["alice"].given, s["alice"].received) == (1, 0)
    assert (s["bob"].given, s["bob"].received) == (0, 1)


def test_given_reviews_are_worth_two_points_and_received_one():
    s = by_login(score([review(1, "alice", "bob")], [ALICE, BOB]))
    assert s["alice"].points == 2
    assert s["bob"].points == 1


def test_reviewing_outranks_being_reviewed():
    events = [review(1, "alice", "bob"), review(2, "alice", "bob"), review(3, "alice", "bob")]
    standings = score(events, [ALICE, BOB])
    assert standings[0].player.github == "alice"
    assert standings[0].points == 6
    assert standings[1].points == 3


def test_self_review_scores_nothing():
    s = by_login(score([review(1, "alice", "alice")], [ALICE, BOB]))
    assert s["alice"].points == 0


def test_non_rostered_reviewer_still_rewards_the_author():
    s = by_login(score([review(1, "dependabot", "bob")], [ALICE, BOB]))
    assert s["bob"].received == 1
    assert s["alice"].points == 0


def test_non_rostered_author_still_rewards_the_reviewer():
    s = by_login(score([review(1, "alice", "stranger")], [ALICE, BOB]))
    assert s["alice"].given == 1


def test_several_reviews_by_one_reviewer_on_one_pr_count_once():
    events = [review(1, "alice", "bob"), review(1, "alice", "bob"), review(1, "alice", "bob")]
    s = by_login(score(events, [ALICE, BOB]))
    assert s["alice"].given == 1
    assert s["bob"].received == 1


def test_reviewer_pair_matching_ignores_login_case():
    s = by_login(score([review(1, "alice", "bob"), review(1, "Alice", "bob")], [ALICE, BOB]))
    assert s["alice"].given == 1


def test_one_reviewer_on_two_prs_counts_twice():
    events = [review(1, "alice", "bob"), review(2, "alice", "bob")]
    s = by_login(score(events, [ALICE, BOB]))
    assert s["alice"].given == 2
    assert s["bob"].received == 2


def test_two_reviewers_on_one_pr_each_count():
    events = [review(1, "alice", "carol"), review(1, "bob", "carol")]
    s = by_login(score(events, [ALICE, BOB, CAROL]))
    assert s["alice"].given == 1
    assert s["bob"].given == 1
    assert s["carol"].received == 2


def test_logins_match_case_insensitively():
    s = by_login(score([review(1, "Alice", "BOB")], [ALICE, BOB]))
    assert s["alice"].given == 1
    assert s["bob"].received == 1


def test_player_with_no_activity_has_zero_points():
    s = by_login(score([review(1, "alice", "bob")], [ALICE, BOB, CAROL]))
    assert s["carol"].points == 0


def test_standings_are_ordered_by_points():
    events = [review(1, "alice", "bob"), review(2, "alice", "bob"), review(3, "alice", "carol")]
    standings = score(events, [CAROL, BOB, ALICE])
    assert [s.player.github for s in standings] == ["alice", "bob", "carol"]
    assert [s.position for s in standings] == [1, 2, 3]


def test_ties_share_a_position_and_the_next_position_is_skipped():
    # alice: 1 review given = 2 points; bob: 2 received = 2 points.
    events = [review(1, "alice", "bob"), review(2, "stranger", "bob")]
    standings = score(events, [ALICE, BOB, CAROL])
    assert [s.player.github for s in standings] == ["alice", "bob", "carol"]
    assert [s.position for s in standings] == [1, 1, 3]


def test_no_events_means_everyone_is_joint_first_on_zero():
    standings = score([], [ALICE, BOB, CAROL])
    assert [s.position for s in standings] == [1, 1, 1]
    assert [s.points for s in standings] == [0, 0, 0]


def standing(login, given, received, position, team):
    return Standing(Player(login, "U" + login, team), given, received, position)


def test_team_points_are_the_sum_of_member_points():
    standings = [standing("alice", 3, 2, 1, "core"), standing("bob", 1, 1, 2, "core"), standing("carol", 2, 0, 3, "web")]
    teams = rank_teams(standings)
    assert [(t.name, t.points) for t in teams] == [("core", 11), ("web", 4)]


def test_teams_are_ordered_by_points():
    standings = [standing("alice", 1, 0, 2, "core"), standing("bob", 4, 0, 1, "web")]
    assert [t.name for t in rank_teams(standings)] == ["web", "core"]
    assert [t.position for t in rank_teams(standings)] == [1, 2]


def test_tied_teams_share_a_position_and_the_next_is_skipped():
    standings = [standing("alice", 2, 0, 1, "web"), standing("bob", 2, 0, 1, "core"), standing("carol", 1, 0, 3, "data")]
    teams = rank_teams(standings)
    assert [t.name for t in teams] == ["core", "web", "data"]
    assert [t.position for t in teams] == [1, 1, 3]


def test_players_without_a_team_are_left_out_of_the_team_league():
    standings = [standing("alice", 5, 0, 1, None), standing("bob", 1, 0, 2, "core")]
    assert [(t.name, t.points) for t in rank_teams(standings)] == [("core", 2)]


def test_win_streaks_counts_consecutive_months_most_recent_last():
    history = [{"sam"}, {"sam"}, {"sam", "jess"}, {"sam"}]
    assert win_streaks(history) == {"sam": 4}


def test_win_streaks_breaks_when_a_name_misses_a_month():
    history = [{"sam"}, {"jess"}, {"sam"}]
    assert win_streaks(history) == {"sam": 1}


def test_win_streaks_counts_each_tied_winner():
    history = [{"sam", "bob"}, {"sam", "bob"}]
    assert win_streaks(history) == {"sam": 2, "bob": 2}


def test_win_streaks_with_no_history_reports_single_win():
    assert win_streaks([{"sam"}]) == {"sam": 1}
