import argparse
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx

import yaml
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from pr_league.jira import JiraClient, JiraError
from pr_league.matching import CommitSearch, SearchFailed
from pr_league.roster import connect, scan_teams
from pr_league.sync import Member, Plan, Team, plan_sync


class AdminError(Exception):
    pass


def _members(table, team: str) -> list[dict]:
    item = table.get_item(Key={"team": team}, ConsistentRead=True).get("Item")
    if item is None:
        raise AdminError(f"no team {team}")
    return item.get("members", [])


def _find(table, github: str) -> tuple[str, dict] | None:
    for item in scan_teams(table):
        for member in item.get("members", []):
            if member["github"].lower() == github.lower():
                return item["team"], member
    return None


def _set_members_update(table_name: str, team: str, old: list[dict], new: list[dict]) -> dict:
    return {
        "TableName": table_name,
        "Key": {"team": team},
        "UpdateExpression": "SET members = :new",
        "ConditionExpression": "members = :old",
        "ExpressionAttributeValues": {":new": new, ":old": old},
    }


@contextmanager
def _lost_race():
    try:
        yield
    except ClientError as error:
        code = error.response["Error"]["Code"]
        if code in ("ConditionalCheckFailedException", "TransactionCanceledException"):
            raise AdminError("the team changed while this command ran; try again") from error
        raise


def _write(table, *updates: dict) -> None:
    with _lost_race():
        if len(updates) == 1:
            table.update_item(**{k: v for k, v in updates[0].items() if k != "TableName"})
        else:
            table.meta.client.transact_write_items(TransactItems=[{"Update": u} for u in updates])


def teams_list(table, _args) -> None:
    for item in sorted(scan_teams(table), key=lambda i: i["team"]):
        names = ", ".join(
            m["github"] + (" (excluded)" if m.get("out_of_league") else "") for m in item.get("members", [])
        ) or "(no members)"
        print(f"{item['team']}: {names}")


def _sync_teams(items: list[dict]) -> list[Team]:
    return [
        Team(
            item["team"],
            tuple(Member(m["github"], m.get("jira"), m.get("source", "manual")) for m in item.get("members", [])),
            item.get("jira_team"),
            item.get("added_at", ""),
            frozenset(item.get("excluded", [])),
        )
        for item in items
    ]


def _developers(jira, teams: list[Team], names: set[str]) -> dict[str, frozenset[str]]:
    return {
        team.name: jira.developers(jira.team_members(jira.find_team(team.jira_team)))
        for team in teams
        if team.name in names and team.jira_team
    }


def _resolver(jira, search):
    def resolve(account: str) -> str | None:
        email = jira.email(account)
        return search.login_for(email) if email else None

    return resolve


def _print_plan(plan: Plan, dry_run: bool = False) -> None:
    would = "would " if dry_run else ""
    for add in plan.adds:
        print(f"{would}add {add.github} to {add.team}")
    for move in plan.moves:
        print(f"{would}move {move.github} from {move.source} to {move.target}")
    for remove in plan.removes:
        print(f"{would}remove {remove.github} from {remove.team}")
    for skip in plan.skips:
        print(f"{skip.jira} stays on {skip.on}, not {skip.team}")
    for miss in plan.unmatched:
        print(f"{miss.jira} could not be matched to a GitHub login for {miss.team}")


def teams_add(table, args, jira=None, search=None, confirm=None) -> None:
    if scan_team_exists(table, args.team):
        raise AdminError(f"{args.team} already exists")
    if args.empty:
        _create_team(table, args.team, [], None)
        return
    jira_name = args.jira_team or args.team
    teams = _sync_teams(scan_teams(table))
    new = Team(args.team, (), jira_name, datetime.now(timezone.utc).isoformat(), frozenset())
    teams = [*teams, new]
    try:
        plan = plan_sync(
            teams, _developers(jira, teams, {args.team}), _resolver(jira, search), {args.team}
        )
    except (JiraError, SearchFailed) as error:
        raise AdminError(str(error)) from error
    _print_plan(plan, args.dry_run)
    if args.dry_run:
        return
    members = [{"github": a.github, "jira": a.jira, "source": "jira"} for a in plan.adds]
    _create_team(table, args.team, members, jira_name, new.added_at)


def teams_link(table, args, jira=None, search=None, confirm=None) -> None:
    item = table.get_item(Key={"team": args.team}, ConsistentRead=True).get("Item")
    if item is None:
        raise AdminError(f"no team {args.team}")
    try:
        listed = jira.developers(jira.team_members(jira.find_team(args.jira_team)))
    except JiraError as error:
        raise AdminError(str(error)) from error
    old = item.get("members", [])
    new, unlisted = [], []
    for member in old:
        if member.get("jira") in listed:
            new.append({**member, "source": "jira"})
        else:
            new.append(member)
            unlisted.append(member["github"])
    update = _set_members_update(table.name, args.team, old, new)
    update["UpdateExpression"] = "SET members = :new, jira_team = :jt, added_at = if_not_exists(added_at, :now)"
    update["ExpressionAttributeValues"].update(
        {":jt": args.jira_team, ":now": datetime.now(timezone.utc).isoformat()}
    )
    _write(table, update)
    for github in unlisted:
        print(f"{github} is not a developer in {args.jira_team}; left as added by hand")


def _apply(table, items: list[dict], plan: Plan) -> None:
    by_team = {item["team"]: item for item in items}
    members = {name: list(item.get("members", [])) for name, item in by_team.items()}
    old = {name: list(item.get("members", [])) for name, item in by_team.items()}
    for remove in plan.removes:
        members[remove.team] = _without(members[remove.team], remove.github)
    for move in plan.moves:
        member = next(m for m in members[move.source] if m["github"].lower() == move.github.lower())
        members[move.source] = _without(members[move.source], move.github)
        members[move.target].append({**member, "source": "jira"})
    for add in plan.adds:
        members[add.team].append({"github": add.github, "jira": add.jira, "source": "jira"})
    changed = [name for name in members if members[name] != old[name]]
    if not changed:
        return
    _write(table, *(_set_members_update(table.name, name, old[name], members[name]) for name in changed))


def teams_sync(table, args, jira=None, search=None, confirm=None) -> None:
    if not args.team and not args.all:
        raise AdminError("name a team or pass --all")
    items = scan_teams(table)
    teams = _sync_teams(items)
    if args.all:
        scope = {t.name for t in teams if t.jira_team}
    else:
        chosen = next((t for t in teams if t.name == args.team), None)
        if chosen is None:
            raise AdminError(f"no team {args.team}")
        if not chosen.jira_team:
            raise AdminError(f"{args.team} is not linked to a Jira team (see teams link)")
        scope = {args.team}
    try:
        plan = plan_sync(teams, _developers(jira, teams, {t.name for t in teams if t.jira_team}), _resolver(jira, search), scope)
    except (JiraError, SearchFailed) as error:
        raise AdminError(str(error)) from error
    _print_plan(plan, args.dry_run)
    if args.dry_run:
        return
    if plan.removes and not args.yes:
        names = ", ".join(f"{r.github} ({r.team})" for r in plan.removes)
        if not confirm(f"Remove {names} from the league?"):
            plan = Plan(plan.adds, plan.moves, (), plan.skips, plan.unmatched)
    _apply(table, items, plan)


def scan_team_exists(table, team: str) -> bool:
    return "Item" in table.get_item(Key={"team": team}, ConsistentRead=True)


def _create_team(table, team: str, members: list[dict], jira_team: str | None, added_at: str | None = None) -> None:
    item = {"team": team, "members": members, "added_at": added_at or datetime.now(timezone.utc).isoformat()}
    if jira_team:
        item["jira_team"] = jira_team
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(team)")
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AdminError(f"{team} already exists") from error
        raise


def teams_remove(table, args) -> None:
    try:
        table.delete_item(Key={"team": args.team}, ConditionExpression="attribute_exists(team)")
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AdminError(f"no team {args.team}") from error
        raise


def members_add(table, args) -> None:
    item = table.get_item(Key={"team": args.team}, ConsistentRead=True).get("Item")
    if item is None:
        raise AdminError(f"no team {args.team}")
    old = item.get("members", [])
    found = _find(table, args.github)
    if found:
        raise AdminError(f"{args.github.lower()} is already on {found[0]}")
    member = {"github": args.github, "source": "manual"}
    if args.slack:
        member["slack"] = args.slack
    if args.jira:
        member["jira"] = args.jira
    update = _set_members_update(table.name, args.team, old, [*old, member])
    excluded = [e for e in item.get("excluded", []) if e != args.jira]
    if args.jira and excluded != item.get("excluded", []):
        update["UpdateExpression"] += ", excluded = :excl"
        update["ExpressionAttributeValues"][":excl"] = excluded
    _write(table, update)


def _without(members: list[dict], github: str) -> list[dict]:
    return [m for m in members if m["github"].lower() != github.lower()]


def members_remove(table, args) -> None:
    found = _find(table, args.github)
    if found is None:
        raise AdminError(f"{args.github.lower()} is not on any team")
    team, member = found
    item = table.get_item(Key={"team": team}, ConsistentRead=True)["Item"]
    old = item.get("members", [])
    update = _set_members_update(table.name, team, old, _without(old, args.github))
    if member.get("source") == "jira" and member.get("jira"):
        update["UpdateExpression"] += ", excluded = :excl"
        update["ExpressionAttributeValues"][":excl"] = [*item.get("excluded", []), member["jira"]]
    _write(table, update)


def _set_flag(table, args, flagged: bool) -> None:
    found = _find(table, args.github)
    if found is None:
        raise AdminError(f"{args.github.lower()} is not on any team")
    team = found[0]
    old = _members(table, team)
    new = []
    for member in old:
        if member["github"].lower() == args.github.lower():
            member = {k: v for k, v in member.items() if k != "out_of_league"}
            if flagged:
                member["out_of_league"] = True
        new.append(member)
    if new != old:
        _write(table, _set_members_update(table.name, team, old, new))


def members_exclude(table, args) -> None:
    _set_flag(table, args, True)


def members_include(table, args) -> None:
    _set_flag(table, args, False)


def members_move(table, args, jira=None, search=None, confirm=None) -> None:
    github = args.github.lower()
    target = table.get_item(Key={"team": args.team}, ConsistentRead=True).get("Item")
    if target is None:
        raise AdminError(f"no team {args.team}")
    if not target.get("jira_team"):
        raise AdminError(f"{args.team} is not linked to a Jira team (see teams link)")
    found = _find(table, args.github)
    if found is None:
        if not args.jira:
            raise AdminError(f"{github} is not on any team; pass --jira with their Atlassian account ID")
        member, source = {"github": args.github, "jira": args.jira}, None
    else:
        source, member = found
        if source == args.team:
            raise AdminError(f"{github} is already on {source}")
        if not member.get("jira"):
            raise AdminError(f"{github} has no Jira ID, so they cannot be checked against {args.team}")
    try:
        eligible = jira.developers(jira.team_members(jira.find_team(target["jira_team"])))
    except JiraError as error:
        raise AdminError(str(error)) from error
    if member["jira"] not in eligible:
        raise AdminError(f"{github} is not a developer in {args.team}")

    moved = {**member, "source": "jira"}
    target_old = target.get("members", [])
    target_update = _set_members_update(table.name, args.team, target_old, [*target_old, moved])
    excluded = [e for e in target.get("excluded", []) if e != member["jira"]]
    if excluded != target.get("excluded", []):
        target_update["UpdateExpression"] += ", excluded = :excl"
        target_update["ExpressionAttributeValues"][":excl"] = excluded
    if source is None:
        _write(table, target_update)
        return
    source_old = _members(table, source)
    _write(table, _set_members_update(table.name, source, source_old, _without(source_old, args.github)), target_update)


def _read_roster(path: str) -> list[tuple[str, dict]]:
    try:
        raw = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as error:
        raise AdminError(f"{path}: {error}") from error
    entries = raw.get("players") if isinstance(raw, dict) else None
    if not entries:
        raise AdminError(f"{path} has no players")
    seen: set[str] = set()
    players = []
    for entry in entries:
        github = entry.get("github") if isinstance(entry, dict) else None
        if not github:
            raise AdminError(f"{path} has a player with no github login")
        key = str(github).lower()
        if not entry.get("team"):
            raise AdminError(f"{key} has no team in {path}")
        if key in seen:
            raise AdminError(f"{key} appears twice in {path}")
        seen.add(key)
        member = {"github": str(github)}
        for field in ("slack", "jira"):
            if entry.get(field):
                member[field] = str(entry[field])
        players.append((str(entry["team"]), member))
    return players


def import_roster(table, args) -> None:
    players = _read_roster(args.file)
    teams = {item["team"]: item.get("members", []) for item in scan_teams(table)}
    owner = {m["github"].lower(): team for team, members in teams.items() for m in members}

    additions: dict[str, list[dict]] = {}
    present = 0
    for team, member in players:
        key = member["github"].lower()
        if key in owner and owner[key] != team:
            raise AdminError(f"{key} is already on {owner[key]}, not {team}")
        if key in owner:
            present += 1
        else:
            additions.setdefault(team, []).append(member)

    in_file = {team for team, _ in players}
    created = in_file - teams.keys()
    added = sum(len(members) for members in additions.values())
    summary = f"{added} members into {len(in_file)} teams ({len(created)} created); {present} already present."

    if args.dry_run:
        for team, members in additions.items():
            print(f"{team}{' (new)' if team in created else ''}: {', '.join(m['github'] for m in members)}")
        print(f"Would import {summary}")
        return

    items = []
    for team, members in additions.items():
        if team in teams:
            update = _set_members_update(table.name, team, teams[team], [*teams[team], *members])
            items.append({"Update": update})
        else:
            put = {
                "TableName": table.name,
                "Item": {"team": team, "members": members},
                "ConditionExpression": "attribute_not_exists(team)",
            }
            items.append({"Put": put})
    if items:
        with _lost_race():
            table.meta.client.transact_write_items(TransactItems=items)
    print(f"Imported {summary}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pr-league-admin", description="Manage the league's teams")
    groups = parser.add_subparsers(dest="group", required=True)

    teams = groups.add_parser("teams").add_subparsers(dest="command", required=True)
    teams.add_parser("list").set_defaults(handler=teams_list)
    add_team = teams.add_parser("add", help="add a team, pulling its developers from Jira")
    add_team.add_argument("team")
    add_team.add_argument("--jira-team", help="the Atlassian team's name, if it differs from the team's")
    add_team.add_argument("--empty", action="store_true", help="create an empty team without asking Jira")
    add_team.add_argument("--dry-run", action="store_true", help="show who would be added and write nothing")
    add_team.set_defaults(handler=teams_add)
    link = teams.add_parser("link", help="link an existing team to an Atlassian team")
    link.add_argument("team")
    link.add_argument("--jira-team", required=True, help="the Atlassian team's name")
    link.set_defaults(handler=teams_link)
    sync = teams.add_parser("sync", help="bring a team in line with its Atlassian team")
    sync.add_argument("team", nargs="?")
    sync.add_argument("--all", action="store_true", help="sync every linked team")
    sync.add_argument("--dry-run", action="store_true", help="show the changes and write nothing")
    sync.add_argument("--yes", action="store_true", help="remove people without asking")
    sync.set_defaults(handler=teams_sync)
    remove_team = teams.add_parser("remove")
    remove_team.add_argument("team")
    remove_team.set_defaults(handler=teams_remove)

    members = groups.add_parser("members").add_subparsers(dest="command", required=True)
    add = members.add_parser("add")
    add.add_argument("team")
    add.add_argument("github")
    add.add_argument("--slack", help="Slack member ID (U…)")
    add.add_argument("--jira", help="Jira account ID")
    add.set_defaults(handler=members_add)
    remove = members.add_parser("remove")
    remove.add_argument("github")
    remove.set_defaults(handler=members_remove)
    for name, handler, help_text in (
        ("exclude", members_exclude, "keep a member's stats out of the league"),
        ("include", members_include, "put an excluded member back in the league"),
    ):
        flag = members.add_parser(name, help=help_text)
        flag.add_argument("github")
        flag.set_defaults(handler=handler)
    move = members.add_parser("move")
    move.add_argument("github")
    move.add_argument("team")
    move.add_argument("--jira", help="Atlassian account ID, for someone not yet on a team")
    move.set_defaults(handler=members_move)

    load = groups.add_parser("import", help="add the players in a roster YAML file")
    load.add_argument("file")
    load.add_argument("--dry-run", action="store_true", help="show what would be added and write nothing")
    load.set_defaults(handler=import_roster)
    return parser


def main(argv: list[str], table, jira=None, search=None, confirm=None) -> None:
    args = _parser().parse_args(argv)
    handler = args.handler
    if handler in JIRA_COMMANDS:
        handler(table, args, jira=jira, search=search, confirm=confirm)
    else:
        handler(table, args)


JIRA_COMMANDS = {teams_add, teams_link, teams_sync, members_move}


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AdminError(f"{name} is not set (see .env.example)")
    return value


def build_clients() -> tuple[JiraClient, CommitSearch]:
    site, email = _env("ATLASSIAN_SITE"), _env("ATLASSIAN_EMAIL")
    jira = JiraClient(
        httpx.Client(base_url=f"https://{site}", auth=(email, _env("ATLASSIAN_API_TOKEN")), timeout=30),
        _env("ATLASSIAN_ORG_ID"),
        _env("ATLASSIAN_SITE_ID"),
    )
    search = CommitSearch(
        httpx.Client(
            base_url="https://api.github.com",
            headers={"Authorization": f"Bearer {_env('GITHUB_TOKEN')}"},
            timeout=30,
        )
    )
    return jira, search


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


def cli() -> None:
    load_dotenv()
    table_name = os.environ.get("PR_LEAGUE_TABLE")
    if not table_name:
        sys.exit("PR_LEAGUE_TABLE is not set (see .env.example)")
    try:
        args = _parser().parse_args(sys.argv[1:])
        clients = {}
        if args.handler in JIRA_COMMANDS and not getattr(args, "empty", False):
            clients["jira"], clients["search"] = build_clients()
        main(sys.argv[1:], connect(table_name), confirm=_confirm, **clients)
    except AdminError as error:
        sys.exit(str(error))
