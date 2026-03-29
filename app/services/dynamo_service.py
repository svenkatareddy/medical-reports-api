import json
import logging
from decimal import Decimal
from typing import Optional, Tuple, List

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from app.config import settings
from app.database import get_table

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decimal_to_native(obj):
    """Recursively convert Decimal values to int or float for JSON safety."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    return obj


def _handle_client_error(exc: ClientError, context: str):
    """Log and re-raise ClientError with context."""
    logger.error("DynamoDB ClientError in %s: %s", context, exc)
    raise exc


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def get_user_by_email(email: str) -> Optional[dict]:
    """Query the EmailIndex GSI to find a user by email address."""
    try:
        table = get_table(settings.DYNAMODB_USERS_TABLE)
        response = table.query(
            IndexName="EmailIndex",
            KeyConditionExpression=Key("email").eq(email),
            Limit=1,
        )
        items = response.get("Items", [])
        return _decimal_to_native(items[0]) if items else None
    except ClientError as exc:
        _handle_client_error(exc, "get_user_by_email")


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Fetch a user item by primary key (userId)."""
    try:
        table = get_table(settings.DYNAMODB_USERS_TABLE)
        response = table.get_item(Key={"userId": user_id})
        item = response.get("Item")
        return _decimal_to_native(item) if item else None
    except ClientError as exc:
        _handle_client_error(exc, "get_user_by_id")


def create_user(user_data: dict) -> dict:
    """Write a new user item to DynamoDB and return the created item."""
    try:
        table = get_table(settings.DYNAMODB_USERS_TABLE)
        table.put_item(
            Item=user_data,
            ConditionExpression=Attr("userId").not_exists(),
        )
        return user_data
    except ClientError as exc:
        _handle_client_error(exc, "create_user")


def update_user(user_id: str, updates: dict) -> dict:
    """Apply a partial update to a user item and return the updated attributes."""
    if not updates:
        raise ValueError("No updates provided.")

    try:
        table = get_table(settings.DYNAMODB_USERS_TABLE)
        expression_parts = []
        attr_names = {}
        attr_values = {}

        for idx, (key, value) in enumerate(updates.items()):
            placeholder = f"#f{idx}"
            value_placeholder = f":v{idx}"
            expression_parts.append(f"{placeholder} = {value_placeholder}")
            attr_names[placeholder] = key
            attr_values[value_placeholder] = value

        update_expression = "SET " + ", ".join(expression_parts)

        response = table.update_item(
            Key={"userId": user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
            ConditionExpression=Attr("userId").exists(),
            ReturnValues="ALL_NEW",
        )
        return _decimal_to_native(response["Attributes"])
    except ClientError as exc:
        _handle_client_error(exc, "update_user")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def create_report(report_data: dict) -> dict:
    """Write a new report item to DynamoDB and return it."""
    try:
        table = get_table(settings.DYNAMODB_REPORTS_TABLE)
        table.put_item(
            Item=report_data,
            ConditionExpression=Attr("reportId").not_exists(),
        )
        return report_data
    except ClientError as exc:
        _handle_client_error(exc, "create_report")


def get_report(report_id: str) -> Optional[dict]:
    """Fetch a report item by primary key (reportId)."""
    try:
        table = get_table(settings.DYNAMODB_REPORTS_TABLE)
        response = table.get_item(Key={"reportId": report_id})
        item = response.get("Item")
        return _decimal_to_native(item) if item else None
    except ClientError as exc:
        _handle_client_error(exc, "get_report")


def update_report(report_id: str, updates: dict) -> dict:
    """Apply a partial update to a report item and return the updated attributes."""
    if not updates:
        raise ValueError("No updates provided.")

    try:
        table = get_table(settings.DYNAMODB_REPORTS_TABLE)
        expression_parts = []
        attr_names = {}
        attr_values = {}

        for idx, (key, value) in enumerate(updates.items()):
            placeholder = f"#f{idx}"
            value_placeholder = f":v{idx}"
            expression_parts.append(f"{placeholder} = {value_placeholder}")
            attr_names[placeholder] = key
            attr_values[value_placeholder] = value

        update_expression = "SET " + ", ".join(expression_parts)

        response = table.update_item(
            Key={"reportId": report_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
            ConditionExpression=Attr("reportId").exists(),
            ReturnValues="ALL_NEW",
        )
        return _decimal_to_native(response["Attributes"])
    except ClientError as exc:
        _handle_client_error(exc, "update_report")


def list_user_reports(
    user_id: str,
    limit: int = 20,
    last_key: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> Tuple[List[dict], Optional[str]]:
    """List reports for a user via UserReportsIndex GSI with optional pagination.

    Returns a tuple of (items, next_last_key).  next_last_key is a JSON string
    that can be passed back as *last_key* on the next call; None means no more pages.
    """
    try:
        table = get_table(settings.DYNAMODB_REPORTS_TABLE)

        query_kwargs: dict = {
            "IndexName": "UserReportsIndex",
            "KeyConditionExpression": Key("userId").eq(user_id),
            "Limit": limit,
            "ScanIndexForward": False,  # newest first
        }

        if status_filter:
            query_kwargs["FilterExpression"] = Attr("status").eq(status_filter)

        if last_key:
            try:
                query_kwargs["ExclusiveStartKey"] = json.loads(last_key)
            except (json.JSONDecodeError, ValueError):
                pass  # ignore malformed pagination key

        response = table.query(**query_kwargs)
        items = [_decimal_to_native(item) for item in response.get("Items", [])]

        next_last_key: Optional[str] = None
        if "LastEvaluatedKey" in response:
            next_last_key = json.dumps(response["LastEvaluatedKey"])

        return items, next_last_key
    except ClientError as exc:
        _handle_client_error(exc, "list_user_reports")


def delete_report(report_id: str) -> None:
    """Delete a report item from DynamoDB."""
    try:
        table = get_table(settings.DYNAMODB_REPORTS_TABLE)
        table.delete_item(Key={"reportId": report_id})
    except ClientError as exc:
        _handle_client_error(exc, "delete_report")
