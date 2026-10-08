#!/bin/sh
set -e

python - <<'PY'
import os

import boto3
from botocore.exceptions import ClientError

name = os.environ["PR_LEAGUE_TABLE"]
db = boto3.client("dynamodb")
try:
    db.describe_table(TableName=name)
except ClientError as error:
    if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise
    db.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": "team", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "team", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"created local table {name}")
PY

exec "$@"
