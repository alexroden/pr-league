import boto3
import pytest
from moto import mock_aws

TABLE = "pr-league-teams"


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("PR_LEAGUE_TABLE", TABLE)
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="eu-west-2")
        yield resource.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "team", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "team", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
