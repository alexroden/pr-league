# PR League: Jira Ticket Scoring (Design)

Date: 2026-10-07
Status: Draft, awaiting review
Extends: `2026-10-06-pr-league-design.md`

## Purpose

Jira ticket transitions earn league points alongside PR reviews. A player scores when they move a ticket into one of three workflow statuses. The points join the player's existing monthly total, so there is still one leaderboard and one team league. On Fridays the DM also shows a "This week in Jira" block listing what the reader moved that week.

For now the Jira data is stubbed, as the monthly winners were. The scoring and rendering are real and tested. The Jira client, credentials and fetching are a later piece of work (see Deferred).

## Decisions Made

| Question | Decision |
|----------|----------|
| Role of Jira | Scores points. Not display-only context |
| Points | QE check run: 2. Ready for production: 2. Closed: 3 |
| Who earns | The person who made the transition (the changelog author), not the assignee |
| Pool | Same league total as PR points. One position, one leaderboard. Team scores sum both |
| Deduplication | Each (actor, ticket, status) counts once. Re-entering a status, for example after a reopen, scores nothing more |
| Eligibility | Only rostered players score, as with reviews. Transitions into other statuses score nothing |
| Same ticket, several statuses | All three score. A ticket that reaches Closed having passed through QE check run and Ready for production earns for each transition, if the same person made them |
| Scoring window | The calendar month, like the PR league. Past months, used for winners and streaks, follow the same rule |
| Weeks | Monday to Sunday, clipped at month boundaries |
| Fetch model (later) | Stateless. Each run fetches every week of the month so far and concatenates the events. No stored weekly snapshots |
| Friday block | Shown on Fridays, or on any day with `--jira` in the demo script |
| Data source now | Stubbed in `send_test_dm.py`. The real run passes no ticket events |

## Non-Goals

- No Jira client, credentials, JQL or changelog parsing. Deferred.
- No `jira` identity on roster entries. Deferred.
- No change to `main.py`, `config.py`, `config.example.yaml` or `.env.example`. The real league ignores Jira until the integration exists.
- No stored state. The league stays stateless.
- No scheduler. Running on Fridays is done outside the bot.
- No change to PR scoring rules.
- No generalisation of reviews and tickets into one event type. Reviews and tickets stay separate.

## Model

`models.py` gains:

```python
TICKET_POINTS = {
    "QE check run": 2,
    "Ready for production": 2,
    "Closed": 3,
}

@dataclass(frozen=True)
class TicketEvent:
    key: str            # e.g. "PLAT-412"
    actor: str          # who made the transition; matched to Player.github
    status: str         # the status moved into
    at: datetime
```

`Standing` gains `tickets: int = 0`, the Jira **points** a player earned (not a transition count). `Standing.points` becomes `GIVEN_POINTS * given + RECEIVED_POINTS * received + tickets`.

`actor` is matched case-insensitively against `Player.github`, as reviewers are. The stub treats the roster's GitHub login as the player's identity. A separate Jira identity per player is part of the deferred integration.

## Scoring

`score(events, players, ticket_events=())` keeps its signature and adds an optional third argument.

For each ticket event:

1. Skip it if the status is not in `TICKET_POINTS`.
2. Skip it if the actor is not on the roster.
3. Skip it if (actor, ticket, status) was already counted.
4. Otherwise add `TICKET_POINTS[status]` to the actor's `tickets`.

Positions, ties and the sort order then run over the combined points. `rank_teams` is unchanged, because it already sums `Standing.points`. The sort key in `score` and the points list passed to `_positions` must both use the combined total.

With no ticket events, every number is identical to today's, so existing tests are unaffected.

## Time windows

Scoring and rendering take a flat list of timestamped events and do not know about weeks. The window is the caller's job:

- **Scoring:** the caller passes the events for the calendar month.
- **Friday block:** `render_jira_week` is given the events and the week start, and keeps the reader's events at or after it.
- **Week start:** the Monday 00:00 (local time) on or before the run, clipped to the 1st of the month when the week began in the previous month.

In the later integration, "weekly fetch, monthly total" is a fetch concern only: one request per week of the month so far, results concatenated. Because deduplication runs over the combined list, the total equals a single monthly fetch.

## Display

### Standing line

```
You're *2nd* of 7 this month with *31 points* (6 reviews given, 4 received, 9 from tickets).
```

The `, N from tickets` part is omitted when the reader's `tickets` is 0, so PR-only output is unchanged. `N` is Jira points.

### Top-three table

A `Tickets` column follows `Received`, showing Jira points. It appears only when at least one player in the top three has ticket points, so PR-only tables are unchanged.

### Friday block

`render_jira_week(events, me, week_start)` returns:

```
🎫 *This week in Jira*
• QE check run: 2 (PLAT-412, PLAT-415), 4 pts
• Ready for production: 1 (PLAT-398), 2 pts
• Closed: 0
```

- One line per status in `TICKET_POINTS` order.
- Counts are distinct tickets per status for the reader. Points are `count * TICKET_POINTS[status]`.
- Points are always 2 or more per ticket, so "pts" is always plural. The count has no word attached.
- A status with no tickets shows `0` with no keys or points.
- When nothing moved in any status, the block is "🎫 *This week in Jira*" followed by "No tickets moved this week."
- Ticket keys are plain text for now. Linking them needs the Jira site URL, which arrives with the integration.

`render_dm` gains an optional `jira: str = ""` argument, like `winners`. When non-empty it is appended at the bottom, after the team league.

## Demo script

`send_test_dm.py` supplies:

- Fixture `TicketEvent`s for this month across the fake players and the reader, including at least one event this week and some earlier in the month.
- Fixture `TicketEvent`s for last month, so the stubbed winners can reflect ticket points.
- A `--jira` flag that shows the Friday block on any day. Without it, the block shows on Fridays only.

The fixture should include one status with no tickets for the reader, so the output shows the zero case.

Stubbed streak history (`AUGUST_WINNERS` and the like) is hard-coded and stays as is.

## Testing

Tests are written first and watched failing, per the repo's TDD default.

**Scoring** (`tests/unit/test_scoring.py`):

- Each status awards its points: 2, 2, 3.
- The actor earns, not any other roster member.
- One count per (actor, ticket, status), and a different status on the same ticket counts separately.
- Several tickets accumulate.
- Non-roster actors score nothing.
- Statuses outside `TICKET_POINTS` score nothing.
- Actor matching is case-insensitive.
- Ticket points change positions and ties.
- Team totals include ticket points.
- With no ticket events, results match PR-only scoring.

**Rendering** (`tests/unit/test_rendering.py`):

- The standing line with and without ticket points.
- The table column appears only when someone in the top three has ticket points.
- The Friday block: counts, points, ticket keys, a zero status, the empty week, and the week-start filter including a clipped month start.
- `render_dm` output is unchanged when `jira` is empty, and includes the block when it isn't.

The Jira client does not exist yet, so nothing else is tested.

## README

Add the three ticket rows to the scoring table, with the rule that the person who moved the ticket earns. Note that Jira data is stubbed in the demo script and is not read by real runs yet. Describe the `--jira` flag in the demo section.

## Deferred (the later integration)

- A Jira client in `jira.py` using httpx, with email and API token in `.env`, retries on connection errors, and the site URL for linking ticket keys.
- A Jira identity on each roster entry, so `actor` no longer assumes the GitHub login.
- JQL on status changes, and changelog parsing to find who made each transition and when.
- The per-week fetch loop, paginated, with a check on whether Jira Cloud search needs the enhanced-search endpoint.
- Failure handling. Jira outage behaviour must be decided: skip the Jira part of the DM, or stop the run. Silently dropping Jira points would change standings, which differs from a display-only section.
- Wiring Jira into `main.py`, including the Friday gate on real runs.
- Config for the status names and point values, if renaming a status in Jira should not need a code change.

## Open Questions

1. Whether a ticket that reaches Closed should also keep the earlier QE and Ready for production points. The spec says yes. If the points feel inflated in use, the fix is a scoring rule change here.
2. Whether Jira transitions made by automation or bots should be excluded. Decided during the integration, when the real changelog data is visible.
