import boto3
from functools import lru_cache
from app.config import settings


@lru_cache(maxsize=1)
def get_dynamodb():
    """Return a cached boto3 DynamoDB resource."""
    return boto3.resource(
        "dynamodb",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


@lru_cache(maxsize=1)
def get_s3():
    """Return a cached boto3 S3 client."""
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def get_table(name: str):
    """Return a DynamoDB Table resource by name."""
    dynamodb = get_dynamodb()
    return dynamodb.Table(name)
