# PR League: Jira Team Sync (Design)

Date: 2026-10-08
Status: Implemented, but the Atlassian Teams endpoints are unverified
Extends: `2026-10-08-dynamo-teams-design.md`

## Purpose

Adding a team to the league should pull in its developers from Jira, instead of typing each person in. Jira decides who is eligible for a team. A person can be on several Jira teams, but scores for exactly one league team, because the team league sums points per person.

The league keeps that one-team rule. Jira supplies the choices, and an admin transfer picks which of a person's Jira teams they score for.

## Decisions Made

| Question | Decision |
|----------|----------|
| Source of team membership | Atlassian (Jira) teams |
| Developer filter | Members of the Jira `developers` group who are active. Assumed, matching how `roster.derived.yaml` was built (see Open Questions) |
| Jira person to GitHub login | Jira email, then a GitHub commit search by that email. No approval step: a match is added directly, and `--dry-run` previews it |
| Person on two teams | They stay on the team they were added to first. Later teams skip them and report it |
| Transfer | Only to a team the person is in on Jira. Anyone not on a league team can be moved into a team they are in on Jira |
| Left the Jira team | Moved automatically to the oldest-added league team they are still in on Jira. Removed if there is none |
| Removing people | Confirmed first (`--yes` or a prompt). Moves and additions are not |
| People added by hand | Never touched by a sync. They have no Jira team to check |

## Non-Goals

- No scheduled sync. Running it on the schedule belongs to the scheduling step.
- No Slack ID lookup. People added by a sync have no Slack ID and get no DM until one is set.
- No GitHub teams as a source.
- No change to scoring, rendering, the `Player` model or the bot's run. The bot never calls Jira Teams.

## Data Model

Additions to the `pr-league-teams` item (existing items without them still load):

- `jira_team` (S): the display name of the linked Jira team. Absent for teams that aren't linked.
- `added_at` (S, ISO 8601 UTC): when the team joined the league. Decides "oldest-added".
- `excluded` (list of S): Jira account IDs a sync must not add to this team. Removing a Jira-sourced member by hand adds them here.

Additions to each member map:

- `source`: `"jira"` or `"manual"`. Absent means `manual`. Only `jira` members are ever removed or moved by a sync.
- `out_of_league` (bool): the member is kept in the table and on their team but is not loaded as a player, so they score nothing and appear nowhere. They still count for the one-team-per-login rule, so a sync never adds them again, and the flag survives transfers and sync moves. The name differs from the team's `excluded` list on purpose. Set with `members exclude`, cleared with `members include`.

The loader ignores these fields, so `Player` and `roster.load_players` are unchanged. The one-team-per-login check stays in the loader and is what enforces "first team wins".

## Components

- `jira.py` (new). A client for Atlassian: find a team by exact name, list its members' account IDs, filter to active `developers`-group members, and read a person's email. Takes its base URL and credentials as arguments.
- `matching.py` (new). `github_login(email) -> str | None`: a commit search by author email. It returns a login only if every matching commit has the same login. It returns `None` for no match or an ambiguous one.
- `sync.py` (new). A pure planner. Inputs: the league's teams, each linked team's Jira developers, and a resolver from account ID to GitHub login. Output: a plan of `add`, `move`, `remove`, `skip` (already elsewhere) and `unmatched`, each with the reason. It does no I/O.
- `admin.py`. New and changed commands (below), which build the plan, print it, and apply it.

## Commands

- `teams add <team> [--jira-team <name>] [--empty]`: link the Jira team (named like the league team unless `--jira-team` is given), pull its developers, and add them. `--empty` keeps today's manual behaviour.
- `teams link <team> --jira-team <name>`: link an existing team, such as the two imported Migration teams. Members with a Jira ID who are in that Jira team become `jira`-sourced. The rest stay manual and are reported.
- `teams sync <team>` or `teams sync --all`: recompute. With `--all`, teams are processed oldest-added first, so a person in two new Jira teams lands on the older one.
- `members move <github> <team> [--jira <account-id>]`: the transfer. The target must be linked, and the person must be one of its Jira developers. `--jira` is needed only when the login isn't in the table yet. A successful move sets `source` to `jira` and clears any exclusion.
- `members remove`: a `jira`-sourced member is also added to the team's `excluded` list.
- `members add`: clears an exclusion and records `source: manual`.
- All of the above that write take `--dry-run`. Removals need `--yes` or a prompt.

## Sync Rules

For each linked team being synced, for each Jira developer:

- On no league team and not excluded: add, if a GitHub login is found. Otherwise `unmatched`.
- On another league team: `skip`, reported.
- On this team: nothing.

For each `jira`-sourced member of the team who is no longer one of its Jira developers (left the team, left the group, or deactivated): move them to the oldest-added linked league team that lists them as a Jira developer and hasn't excluded them. If there is none, `remove`.

A move changes both teams in one transaction, as `members move` does today. Writes stay conditional on the member list read, so a concurrent edit gives the existing "changed while this command ran" error.

## Credentials

The Atlassian connection used while designing this isn't available to the CLI. The CLI needs:

- `ATLASSIAN_SITE`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`: Jira user and group reads.
- `ATLASSIAN_ORG_ID`, if the Teams API needs it (unverified, see below).
- `GITHUB_TOKEN`: already present. It must be able to search commits.

Locally these come from `.env`, as the other tokens do. Moving them to Secrets Manager is part of the scheduling step, since only the admin CLI uses them here.

## Error Handling

- Unknown Jira team name, or a name matching more than one team: stop, name the matches.
- Jira or GitHub unreachable or unauthorised: stop before writing anything. A sync with partial Jira data could wrongly remove people.
- An unmatched person is reported, never a failure.
- Rate limits on the commit search: stop with a message rather than treat the person as unmatched.

## Testing

TDD, unit tier. HTTP is faked at the httpx transport, as `test_github.py` does. DynamoDB is faked with `moto`.

- `test_sync.py` (the planner, table-driven): add; skip when on another team; excluded not re-added; unmatched; departure moves to the oldest eligible team; departure with no eligible team removes; manual members untouched; `--all` ordering; a person in two new teams lands on the older.
- `test_jira.py`: team lookup (exact, none, ambiguous), developer filtering, deactivated accounts, pagination.
- `test_matching.py`: one login, none, two different logins, noreply emails.
- `test_admin.py` additions: `teams add` with and without `--empty`; `link`; `move` refused when the person isn't in the target's Jira team; `move` of someone not in the table; `remove` adds to `excluded`; `--dry-run` writes nothing; removals need confirmation.

## Open Questions

Items marked unverified haven't been confirmed against the real services. The plan's first task checks them.

- **Developers group.** Assumed to be Jira's `developers` group, as for `roster.derived.yaml`.
- **Teams API access (unverified).** Reading a team's members over REST probably needs the organisation ID and an API key with Teams access, which is more than a normal Jira token. If you can't get one, the fallback is to read a Jira group for each team.
- **Email visibility (partly verified).** One profile showed its email. Anyone whose email is hidden will be unmatched.
- **Commit-email matching (unverified).** GitHub links a commit to a login only when the author's email is on that account, and many people commit with `noreply` addresses. Expect unmatched people, who can be added with `members add`.
- **Wrong matches.** With no approval step, a wrong match goes straight into the table. `--dry-run` is the safeguard. Limiting matches to logins in the GitHub org is a cheap extra check I'd add if you want it.
- **"Automatically".** I've read this as: a sync moves people without asking. Running it unattended is the scheduling step's job, and an unattended run should apply additions and moves but only report removals.
- **Imported teams.** The two Migration teams have no `added_at`. `teams link` sets it to the time of linking, so link them in the order you want treated as oldest.
