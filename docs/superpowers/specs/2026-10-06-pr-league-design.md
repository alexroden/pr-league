# PR League: Design

Date: 2026-10-06
Status: Draft, awaiting review

## Purpose

A personal learning project: a Slack bot that gamifies pull request reviews for a small team. Players earn points for reviewing PRs and for having their own PRs reviewed. A league table resets at the start of every month. Once a week, each player receives a Slack DM showing their points and their position relative to the rest of the team.

## Decisions Made

| Question | Decision |
|----------|----------|
| Purpose | Learning / side project, not company tooling |
| PR source | GitHub, whole org |
| Trigger | Scheduled weekly batch job |
| Players | A few named people, listed in a config file |
| Scoring | 1 point per review given, 1 point per review received |
| League | Monthly, lazy reset, weekly standing in DM |
| Stack | Python 3.12, uv, SQLite, `httpx`, run by launchd on the user's Mac |

## Non-Goals

- No web server, Events API, slash commands, or interactivity. The bot never listens; it only posts.
- No web UI.
- No multi-workspace support, OAuth install flow, or app distribution.
- No always-on process. No cloud deployment (may move to GitHub Actions later).
- No weighted scoring, streaks, or bonuses.

## Architecture

One Python project, `pr-league`, made of small single-purpose modules.

```
pr-league/
├── pyproject.toml          # uv-managed, Python 3.12
├── config.yaml             # org + roster (GitHub login, Slack member ID)
├── .env                    # tokens, gitignored
├── league.db               # SQLite state, gitignored
├── src/pr_league/
│   ├── config.py           # load and validate config.yaml
│   ├── github.py           # fetch review events for the org in a window
│   ├── scoring.py          # pure: review events + roster -> points delta per player
│   ├── league.py           # SQLite: points, monthly rollover, standings, last_run_at
│   ├── rendering.py        # pure: standings -> DM text
│   ├── slack.py            # post a DM
│   └── main.py             # orchestration of one weekly run
└── tests/
    ├── unit/               # mirrors src layout
    ├── component/
    └── contract/           # live GitHub tests, opt-in
```

Module responsibilities:

- `github.py` only talks to GitHub.
- `scoring.py` and `rendering.py` are pure functions with no I/O.
- `league.py` only touches SQLite.
- `slack.py` only posts DMs.
- `main.py` composes the others. Collaborators (`GitHubClient`, `LeagueStore`, `SlackMessenger`) are passed in as arguments, so each can be replaced by a fake in tests.

## Data Flow: One Weekly Run

1. **Trigger.** launchd runs `uv run pr-league` weekly (e.g. Mondays 09:00). A single invocation runs fetch, score, store, notify, then exits.
2. **Fetch window.** The window starts at `last_run_at` from the store (first run: the previous 7 days) and ends at the run's start time.
3. **Fetch.** `github.py` returns review events for the org in the window: reviewer login, PR author login, review ID, submitted-at timestamp. Pagination is handled inside this module. The exact GitHub API strategy (org PR search vs. per-repo listing) is an implementation-plan decision, verified by the contract tests.
4. **Score.** `scoring.py` converts events to a points delta per rostered player:
   - A review submitted by a rostered player: +1 to the reviewer ("given").
   - The PR author of that review, if rostered: +1 ("received").
   - Self-review never scores for either side.
   - Non-rostered reviewers or authors score nothing, but the other side of the review still can.
   - Each review ID counts once.
5. **Store.** In a single SQLite transaction, `league.py` adds the deltas to the current month's totals and updates `last_run_at`. Because both happen together, a crash cannot double-count or drop events.
6. **Standings.** Computed from the current month's rows. Ties share a position.
7. **DM.** `rendering.py` builds each player's message and `slack.py` posts it.
8. **Failure handling.**
   - If the GitHub fetch fails, the run aborts before storing anything. The next run's window simply covers the gap.
   - DM failures are isolated per player: logged, and the run continues. Points are already stored, so a failed DM never loses scoring.

### State schema

```
players (github_login PRIMARY KEY, slack_id)
points  (player, month, given, received)    -- month like "2026-10"
meta    (key PRIMARY KEY, value)            -- last_run_at
```

The monthly reset is lazy: there is no reset job. A run in a new month writes to the new month's rows, and standings always read the current month. Earlier months remain as history.

### DM content

Example:

> **PR League: October, week 1**
> You're **2nd** of 5 this month with **14 points** (7 reviews given, 7 received).
> Next up: Sam, 1 point ahead of you.
> Table: 1. Sam (15) · 2. You (14) · 3. Alex (11) …

Rendering is a pure function of (player, standings, month, week number). Ordinals (1st, 2nd, 3rd, 4th, 11th, 12th, 13th) and tie wording must be correct.

## Slack Setup

1. Create an app at api.slack.com/apps, **From scratch**, in the target workspace.
2. Under **OAuth & Permissions → Bot Token Scopes**, add `chat:write`. No other scopes are needed.
3. **Install to Workspace** and copy the Bot User OAuth Token (`xoxb-…`) into `.env` as `SLACK_BOT_TOKEN`.
4. Each player's Slack member ID (`U…`: profile → ⋯ → Copy member ID) goes in `config.yaml`.
5. **DM delivery.** The bot posts with `chat.postMessage`, passing the member ID as `channel`. The message appears in the app's Messages tab for that user. Whether a player must open that tab first is to be confirmed in the first live test. If it is required, setup adds one step: each player opens the bot once.
6. A GitHub PAT with read access to the org's repos goes in `.env` as `GITHUB_TOKEN`.

```yaml
org: your-github-org
players:
  - github: alexghdev
    slack: U0123ABCDEF
```

Secrets stay in a gitignored `.env`. Moving them to a proper secrets store is a later option.

## CLI

- `uv run pr-league`: normal run.
- `--dry-run`: runs fetch and scoring, prints the DMs to stdout, posts nothing and does not write state.
- `--player <github-login>`: restricts a run to one player, for debugging.

## Testing Strategy

Bottom-up, mostly unit tier since this is a batch job with no web layer. pytest with `pytest-mock`, `pytest-cov`, `respx` for HTTP mocking.

**Unit tier** (every PR, blocks merge):

- `scoring`: in-window review scores; out-of-window does not; reviewer and author both score; non-rostered users score nothing; self-review guard; duplicate review ID counted once; inactive player has delta 0.
- `config`: valid file loads; duplicate GitHub logins or Slack IDs rejected; missing org rejected; clear error messages.
- `league`: points accumulate across runs; month rollover starts fresh rows; standings order; ties share a position; `last_run_at` round-trips. Uses a temp SQLite file.
- `rendering`: position, gap to next player, ordinals, medals, ties.
- `github` and `slack`: `respx` at the HTTP boundary; pagination, window filtering, error responses.

**Component tier:** `main.py` wired with fake GitHub and Slack collaborators and a temp SQLite store. Asserts the correct deltas are stored, `last_run_at` advances, every player receives exactly one DM, and one failing DM does not stop the others.

**Contract tier (opt-in):** a small number of live tests against the real GitHub API, skipped by default and enabled with a flag plus a real PAT. They verify pagination and window filtering at the one real boundary between our code and a system we do not own.

**Practices:** tests are written before the code; every bug fix ships with a regression test; time is injected rather than read from the clock; no `sleep`. Line coverage must be at least 85% on the unit tier (`--cov-fail-under=85`).

## Open Questions

1. Whether a player must open the bot's Messages tab before the first DM (resolved by the first live test; see Slack Setup).
2. Which GitHub API strategy gives the most reliable org-wide review listing (resolved in the implementation plan, confirmed by contract tests).

## Next Step

After spec approval, write the implementation plan (writing-plans skill).
