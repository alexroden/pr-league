# PR League: Design (Proof of Concept)

Date: 2026-10-06
Status: Draft, awaiting review

## Purpose

A proof of concept for a Slack bot that gamifies pull request reviews for a small team. Players earn points for reviewing PRs and for having their own PRs reviewed. The league table covers the current calendar month, so it resets at the start of every month. Each run DMs every player their points and their position relative to the rest of the team.

The goal is to prove the idea works end to end. Details will be adjusted locally as it gets used.

## Decisions Made

| Question | Decision |
|----------|----------|
| Purpose | Proof of concept, personal learning project |
| PR source | GitHub, whole org |
| Trigger | Run by hand from the terminal (intended weekly) |
| Players | A few named people, listed in a config file |
| Scoring | 1 point per PR reviewed, 1 point per reviewer on your PR. Each (reviewer, PR) pair counts once |
| League | Current calendar month, computed fresh from GitHub on every run |
| State | None. No database. |
| Stack | Python 3.12, uv, `httpx` |

## Non-Goals (for the PoC)

- No database or stored state.
- No scheduler. Runs are manual.
- No web server, Events API, slash commands, or interactivity. The bot only posts.
- No CI, coverage gate, or live contract tests.
- No weighted scoring, streaks, or bonuses.

## Architecture

```
pr-league/
├── pyproject.toml
├── config.yaml             # org + roster (GitHub login, Slack member ID)
├── .env                    # tokens, gitignored
├── src/pr_league/
│   ├── config.py           # load config.yaml and tokens
│   ├── github.py           # fetch review events for the org in a date range
│   ├── scoring.py          # pure: events + roster -> points and ranked standings
│   ├── rendering.py        # pure: standings -> DM text
│   ├── slack.py            # post a DM
│   └── main.py             # one run: fetch, score, render, send
└── tests/
    └── unit/               # scoring and rendering
```

`scoring.py` and `rendering.py` are pure functions with no I/O. `main.py` passes the GitHub and Slack clients in, so they can be swapped for fakes if needed.

## Data Flow: One Run

1. **Run.** `uv run pr-league` (or `--dry-run`).
2. **Window.** From 00:00 on the 1st of the current month (machine local time) to now. Because every run recomputes the whole month from GitHub, the monthly reset needs no code, and there is no state to corrupt or double-count.
3. **Fetch.** `github.py` returns review events in the window: PR URL, reviewer login, PR author login, submitted-at. Pagination is handled inside this module. The API strategy (org-wide search vs. per-repo listing) is decided in the implementation plan.
4. **Score.** For each review:
   - A rostered reviewer gets +1 ("given").
   - A rostered PR author gets +1 ("received").
   - Self-reviews score nothing.
   - Non-rostered people score nothing, but the other side of the review still can.
   - Each (reviewer, PR) pair counts once, however many reviews the reviewer submits on that PR. GitHub records every reply in a review thread as a new review, so counting raw reviews inflated scores.
5. **Rank.** Players are sorted by total points. Ties share a position.
6. **DM.** Each player gets one message. If a DM fails, it's logged and the run continues to the next player. If the GitHub fetch fails, the run stops before sending anything.

Trade-off: re-fetching the whole month on every run costs more GitHub API calls than an incremental approach. That's fine for a small org at weekly frequency. If it isn't, the fix is to add stored state (see Later).

### DM content

> **PR League: October, week 1**
> You're **2nd** of 5 this month with **14 points** (7 reviews given, 7 received).
> Next up: Sam, 1 point ahead of you.
> Table: 1. Sam (15) · 2. You (14) · 3. Alex (11) …

"Week N" is the week of the month the run happens in.

## Slack Setup

1. Create an app at api.slack.com/apps, **From scratch**, in the target workspace.
2. Under **OAuth & Permissions → Bot Token Scopes**, add `chat:write`.
3. **Install to Workspace** and copy the Bot User OAuth Token (`xoxb-…`) into `.env` as `SLACK_BOT_TOKEN`.
4. Put each player's Slack member ID (`U…`: profile → ⋯ → Copy member ID) in `config.yaml`.
5. The bot posts with `chat.postMessage`, passing the member ID as `channel`. The message lands in the app's Messages tab. Whether a player must open that tab first is checked in the first live run.
6. Put a GitHub PAT with read access to the org's repos in `.env` as `GITHUB_TOKEN`.

```yaml
org: your-github-org
players:
  - github: alexghdev
    slack: U0123ABCDEF
```

## CLI

- `uv run pr-league`: fetch, score, and send DMs.
- `--dry-run`: print the DMs to stdout instead of sending.

## Testing

- Unit tests (pytest) for `scoring.py` and `rendering.py`, written before the code: review scoring rules, self-review, non-rostered users, duplicates, tie ranking, ordinals (1st, 2nd, 3rd, 11th, 12th, 13th), and gap-to-next wording.
- GitHub and Slack modules are checked by hand with `--dry-run` and a real run against the team.

## Open Questions

1. Whether a player must open the bot's Messages tab before the first DM. Answered by the first live run.
2. Which GitHub API strategy is most reliable for org-wide reviews. Decided in the implementation plan.

## Later (if the PoC graduates)

- Stored state (SQLite) and incremental fetching.
- A weekly launchd or GitHub Actions schedule.
- HTTP-mocked tests for the GitHub and Slack modules, plus a coverage gate.
