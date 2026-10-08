import argparse
import os
import sys

from botocore.exceptions import ClientError
from dotenv import load_dotenv

from pr_league.roster import connect, scan_teams


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


def _write(table, *updates: dict) -> None:
    try:
        if len(updates) == 1:
            table.update_item(**{k: v for k, v in updates[0].items() if k != "TableName"})
        else:
            table.meta.client.transact_write_items(TransactItems=[{"Update": u} for u in updates])
    except ClientError as error:
        code = error.response["Error"]["Code"]
        if code in ("ConditionalCheckFailedException", "TransactionCanceledException"):
            raise AdminError("the team changed while this command ran; try again") from error
        raise


def teams_list(table, _args) -> None:
    for item in sorted(scan_teams(table), key=lambda i: i["team"]):
        names = ", ".join(m["github"] for m in item.get("members", [])) or "(no members)"
        print(f"{item['team']}: {names}")


def teams_add(table, args) -> None:
    try:
        table.put_item(
            Item={"team": args.team, "members": []},
            ConditionExpression="attribute_not_exists(team)",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AdminError(f"{args.team} already exists") from error
        raise


def teams_remove(table, args) -> None:
    try:
        table.delete_item(Key={"team": args.team}, ConditionExpression="attribute_exists(team)")
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AdminError(f"no team {args.team}") from error
        raise


def members_add(table, args) -> None:
    old = _members(table, args.team)
    found = _find(table, args.github)
    if found:
        raise AdminError(f"{args.github.lower()} is already on {found[0]}")
    member = {"github": args.github}
    if args.slack:
        member["slack"] = args.slack
    if args.jira:
        member["jira"] = args.jira
    _write(table, _set_members_update(table.name, args.team, old, [*old, member]))


def _without(members: list[dict], github: str) -> list[dict]:
    return [m for m in members if m["github"].lower() != github.lower()]


def members_remove(table, args) -> None:
    found = _find(table, args.github)
    if found is None:
        raise AdminError(f"{args.github.lower()} is not on any team")
    team = found[0]
    old = _members(table, team)
    _write(table, _set_members_update(table.name, team, old, _without(old, args.github)))


def members_move(table, args) -> None:
    found = _find(table, args.github)
    if found is None:
        raise AdminError(f"{args.github.lower()} is not on any team")
    source, member = found
    if source == args.team:
        raise AdminError(f"{args.github.lower()} is already on {source}")
    target_old = _members(table, args.team)
    source_old = _members(table, source)
    _write(
        table,
        _set_members_update(table.name, source, source_old, _without(source_old, args.github)),
        _set_members_update(table.name, args.team, target_old, [*target_old, member]),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pr-league-admin", description="Manage the league's teams")
    groups = parser.add_subparsers(dest="group", required=True)

    teams = groups.add_parser("teams").add_subparsers(dest="command", required=True)
    teams.add_parser("list").set_defaults(handler=teams_list)
    for name, handler in (("add", teams_add), ("remove", teams_remove)):
        sub = teams.add_parser(name)
        sub.add_argument("team")
        sub.set_defaults(handler=handler)

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
    move = members.add_parser("move")
    move.add_argument("github")
    move.add_argument("team")
    move.set_defaults(handler=members_move)
    return parser


def main(argv: list[str], table) -> None:
    args = _parser().parse_args(argv)
    args.handler(table, args)


def cli() -> None:
    load_dotenv()
    table_name = os.environ.get("PR_LEAGUE_TABLE")
    if not table_name:
        sys.exit("PR_LEAGUE_TABLE is not set (see .env.example)")
    try:
        main(sys.argv[1:], connect(table_name))
    except AdminError as error:
        sys.exit(str(error))
