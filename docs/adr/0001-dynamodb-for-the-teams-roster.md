# ADR 0001: DynamoDB for the teams roster

Date: 2026-10-08
Status: Proposed

## Context

PR League's roster (teams, and each member's GitHub, Slack and Jira identities) lived in a gitignored `config.yaml`. The bot is moving to a scheduled ECS Fargate task, and a container has no local file to read. The roster has to live somewhere that both the bot and the people managing the league can reach.

The roster is small (tens of players), read once per run with a full scan, and edited by hand a few times a month. Nothing queries it relationally, and there is no other league state to store, because scores are recomputed from GitHub on every run.

Arbor's datastore defaults are Aurora PostgreSQL (relational), ElastiCache Redis (cache), S3 (objects) and S3 Vectors. DynamoDB isn't among them, and `arbor-education/terraform.modules` has no DynamoDB module. Choosing it is a deviation that needs this ADR.

## Decision

Store the roster in one DynamoDB table, `pr-league-teams`, in eu-west-2. Each item is a team (partition key `team`) with its members embedded as a list. The bot reads it with a scan and validates it on every run. People edit it with `pr-league-admin`, which uses conditional writes and transactions.

## Alternatives considered

- **Aurora PostgreSQL.** The default for relational data, but a cluster, VPC networking, Liquibase migrations and a standing monthly cost are out of proportion to a few dozen rows read once a week.
- **S3 object (YAML or JSON).** On the paved road and the cheapest option. It has no per-field conditional writes, so two concurrent admin edits would need ETag-based optimistic locking written by hand, and every edit rewrites the whole roster.
- **Keep it in the repo.** Reviewable in PRs, but member IDs would be committed, and every roster change would need a release.

## Consequences

- On-demand billing at this size costs close to nothing, and there is nothing to patch or scale.
- Point-in-time recovery and deletion protection are on. Encryption uses the AWS-owned key. Moving to a customer-managed key via `terraform-aws-kms` is a follow-up once key admins are agreed.
- The table is a plain `aws_dynamodb_table` resource in `infra/`, not a shared module. If more services adopt DynamoDB, a module in `terraform.modules` would be the next step.
- Local runs need AWS credentials. Tests use `moto`, so CI needs none.
- The ADR location is this repo's `docs/adr/` until a central Arbor ADR home is confirmed. Move or link it if ADRs belong elsewhere.
