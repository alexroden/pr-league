# PR League: DynamoDB-managed Teams (Design)

Date: 2026-10-08
Status: Implemented
Extends: `2026-10-06-pr-league-design.md`

## Purpose

The league's teams and members move out of `config.yaml` into a DynamoDB table, edited through a small admin CLI. This is step 1 of running the whole bot on a schedule in AWS (ECS Fargate scheduled task, EventBridge, Secrets Manager, Terraform). A scheduled container has no local file to read, so the roster needs a home that both the bot and the people managing it can reach.

The container, schedule, secrets and Jira integration are later steps and out of scope here.

## Decisions Made

| Question | Decision |
|----------|----------|
| Table shape | One item per team, members embedded |
| Editing | Admin CLI in this repo (`pr-league-admin`) |
| YAML roster | Removed entirely. DynamoDB is the only source |
| Infrastructure | Terraform in `infra/` in this repo, based on `arbor-education/terraform.modules` |
| `org` | Moves from the YAML to the `GITHUB_ORG` environment variable |
| Datastore ADR | Required, because DynamoDB is not in Arbor's datastore defaults |

## Non-Goals

- No container image, ECS task, EventBridge schedule or Secrets Manager wiring.
- No change to scoring, rendering, casting or the `Player` model.
- No Slack-driven roster editing.
- No YAML import command (open question below).
- No stored league state. The bot stays stateless.

## Data Model

Table `pr-league-teams` (name from `PR_LEAGUE_TABLE`), eu-west-2, on-demand billing, point-in-time recovery on, server-side encryption on.

- Partition key `team` (S).
- `members`: list of maps `{github: S, slack: S?, jira: S?}`.

Invariants, enforced by both the loader and the admin CLI:

- There is at least one team, and every team has at least one member.
- A GitHub login appears under one team only, compared case-insensitively. `score()` keys players by lowercase login (`scoring.py:20`), so a duplicate would merge silently.
- Every member has a `github`. `slack` and `jira` are optional. A missing `slack` still means the DM is skipped (`main.py:73`).

Behaviour changes:

- No teamless players. Every member belongs to a team, so the "skip the team league" case in `scoring.py:65` no longer arises from real data.
- A table scan has no stable order, so the loader sorts by team, then login.

## Components

- `roster.py` (new). `load_players(table) -> tuple[Player, ...]` takes a boto3 Table resource, scans, validates and maps members to `Player`. `connect(table_name)` builds the resource.
- `config.py`. Drops YAML. `load_config()` reads `GITHUB_ORG`, `GITHUB_TOKEN`, `SLACK_BOT_TOKEN` and `PR_LEAGUE_TABLE` from the environment. The `Config` shape is unchanged, so `main.run` is untouched.
- `admin.py` (new), script `pr-league-admin`:
  - `teams list`, `teams add <team>`, `teams remove <team>`
  - `members add <team> <github> [--slack U…] [--jira …]`
  - `members remove <github>`
  - `members move <github> <team>`

  Writes are conditional. `members move` is one transaction across two items. `members add` rejects a login that exists in any team.
- `main.py`. The `--config` flag is removed.
- `send_test_dm.py`. `--config` and "the first player is you" are replaced by a required `--me <github-login>`, because scan order is not stable.

## Error Handling

- Loader problems raise `ValueError` naming the team or login at fault, as `config._read` does today.
- Missing environment variables fail at startup with the variable's name.
- Admin commands exit non-zero with a one-line message on a duplicate, a missing team or member, or a lost conditional write.

## Infrastructure

`infra/` holds the table and two IAM policies: read-only for the bot, read/write for admins. The ECS task role is a later step. `arbor-education/terraform.modules` has no DynamoDB module, so the table is a plain `aws_dynamodb_table` with point-in-time recovery, deletion protection and encryption with the AWS-owned key. The S3 backend is a partial config (bucket, key and role passed at `terraform init`), because the target account isn't decided.

## Testing

TDD. Unit tier under `tests/unit/`, with `moto` faking DynamoDB at the AWS boundary. Coverage gate 85%.

- `test_roster.py`: loads teams into players; stable order; rejects an empty table, an empty team, a duplicate login across teams (case-insensitive) and a member without `github`; absent `slack` and `jira` load as `None`.
- `test_admin.py`: each subcommand's effect; duplicate and not-found errors; `members move` leaves no half-moved state.
- `test_config.py`: rewritten for environment loading, including each missing variable.
- `test_main.py`: unchanged unless the `cli()` signature forces it.

## Dependencies

Add `boto3`. Remove `pyyaml`. Add dev dependencies `moto[dynamodb]` and `pytest-cov`.

## Files Removed Or Rewritten

`config.example.yaml` is deleted. `.env.example` gains `GITHUB_ORG`, `PR_LEAGUE_TABLE` and `AWS_REGION`. The README setup and roster sections are rewritten. `config.yaml` and `roster.derived.yaml` stay in `.gitignore`, because local copies with real member IDs still exist and should be moved into the table, then deleted.

## Risks And Open Questions

- Local runs and `send_test_dm.py` now need AWS credentials, or a moto-backed table. That follows from dropping YAML.
- The current local `config.yaml` has real members. A one-off `pr-league-admin import config.yaml` would save re-typing them but would keep a YAML dependency. Left out unless you want it.
- Where Arbor ADRs live is unconfirmed. ADR 0001 is in this repo's `docs/adr/` for now.
- Terraform is unvalidated: `terraform` isn't installed on the machine it was written on, so `terraform validate` and `plan` haven't run.
