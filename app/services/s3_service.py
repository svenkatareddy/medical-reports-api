import logging
from botocore.exceptions import ClientError

from app.config import settings
from app.database import get_s3

logger = logging.getLogger(__name__)


def generate_presigned_put_url(file_key: str, file_type: str, expires: int = 300) -> str:
    """Generate a pre-signed S3 PUT URL for direct client uploads.

    Args:
        file_key: The S3 object key where the file will be stored.
        file_type: The MIME type of the file (used as ContentType constraint).
        expires: URL validity in seconds (default 300 = 5 minutes).

    Returns:
        A pre-signed URL string.
    """
    s3 = get_s3()
    try:
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": file_key,
                "ContentType": file_type,
            },
            ExpiresIn=expires,
        )
        return url
    except ClientError as exc:
        logger.error("Failed to generate presigned PUT URL for key '%s': %s", file_key, exc)
        raise


def generate_presigned_get_url(file_key: str, expires: int = 900) -> str:
    """Generate a pre-signed S3 GET URL for temporary file access.

    Args:
        file_key: The S3 object key to provide access to.
        expires: URL validity in seconds (default 900 = 15 minutes).

    Returns:
        A pre-signed URL string.
    """
    s3 = get_s3()
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": file_key,
            },
            ExpiresIn=expires,
        )
        return url
    except ClientError as exc:
        logger.error("Failed to generate presigned GET URL for key '%s': %s", file_key, exc)
        raise


def get_object_bytes(file_key: str) -> bytes:
    """Download an S3 object and return its raw bytes.

    Args:
        file_key: The S3 object key to download.

    Returns:
        The file contents as bytes.
    """
    s3 = get_s3()
    try:
        response = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=file_key)
        return response["Body"].read()
    except ClientError as exc:
        logger.error("Failed to fetch S3 object '%s': %s", file_key, exc)
        raise


def delete_object(file_key: str) -> None:
    """Delete an object from S3.

    Args:
        file_key: The S3 object key to delete.
    """
    s3 = get_s3()
    try:
        s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_key)
    except ClientError as exc:
        logger.error("Failed to delete S3 object '%s': %s", file_key, exc)
        raise
