"""
DynamoDB table setup script.

Run once before starting the API:
    python dynamo_setup.py

Creates:
  - MedicalAppUsers  with EmailIndex GSI (PK: email)
  - MedicalAppReports with UserReportsIndex GSI (PK: userId, SK: createdAt)

Tables are created with PAY_PER_REQUEST billing so no capacity planning is needed.
The script is idempotent — it skips tables that already exist.
"""

import sys
import time

import boto3
from botocore.exceptions import ClientError

# Allow running from the project root without installing the package
sys.path.insert(0, ".")

from app.config import settings  # noqa: E402


def _get_dynamodb_client():
    return boto3.client(
        "dynamodb",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def _table_exists(client, table_name: str) -> bool:
    try:
        client.describe_table(TableName=table_name)
        return True
    except client.exceptions.ResourceNotFoundException:
        return False


def _wait_for_active(client, table_name: str, timeout: int = 60):
    """Poll until the table status is ACTIVE or timeout."""
    print(f"  Waiting for '{table_name}' to become ACTIVE...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.describe_table(TableName=table_name)
        table_status = resp["Table"]["TableStatus"]
        if table_status == "ACTIVE":
            print(" ACTIVE")
            return
        print(".", end="", flush=True)
        time.sleep(2)
    print(" TIMEOUT")
    raise TimeoutError(f"Table '{table_name}' did not become ACTIVE within {timeout}s.")


def create_users_table(client):
    table_name = settings.DYNAMODB_USERS_TABLE
    if _table_exists(client, table_name):
        print(f"  Table '{table_name}' already exists — skipping.")
        return

    print(f"  Creating table '{table_name}'...")
    client.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "userId", "KeyType": "HASH"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "EmailIndex",
                "KeySchema": [
                    {"AttributeName": "email", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )
    _wait_for_active(client, table_name)
    print(f"  '{table_name}' created successfully.")


def create_reports_table(client):
    table_name = settings.DYNAMODB_REPORTS_TABLE
    if _table_exists(client, table_name):
        print(f"  Table '{table_name}' already exists — skipping.")
        return

    print(f"  Creating table '{table_name}'...")
    client.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "reportId", "AttributeType": "S"},
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "createdAt", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "reportId", "KeyType": "HASH"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "UserReportsIndex",
                "KeySchema": [
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "createdAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )
    _wait_for_active(client, table_name)
    print(f"  '{table_name}' created successfully.")


def main():
    print("=== DynamoDB Table Setup ===")
    print(f"Region : {settings.AWS_REGION}")
    print(f"Users  : {settings.DYNAMODB_USERS_TABLE}")
    print(f"Reports: {settings.DYNAMODB_REPORTS_TABLE}")
    print()

    client = _get_dynamodb_client()

    try:
        create_users_table(client)
        create_reports_table(client)
    except ClientError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
