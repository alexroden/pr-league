from datetime import datetime, timezone

from pr_league.models import Player, ReviewEvent
from pr_league.scoring import score

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
    events = [review(1, "alice", "bob"), review(2, "alice", "bob")]
    standings = score(events, [ALICE, BOB, CAROL])
    assert [s.player.github for s in standings] == ["alice", "bob", "carol"]
    assert [s.position for s in standings] == [1, 1, 3]


def test_no_events_means_everyone_is_joint_first_on_zero():
    standings = score([], [ALICE, BOB, CAROL])
    assert [s.position for s in standings] == [1, 1, 1]
    assert [s.points for s in standings] == [0, 0, 0]
