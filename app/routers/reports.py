import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user
from app.models.report import Report
from app.schemas.report import (
    ConfirmRequest,
    ExtractResponse,
    PresignRequest,
    PresignResponse,
    ReportListResponse,
    ReportResponse,
    ReportStatusResponse,
)
from app.services import dynamo_service, s3_service, openai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])

ALLOWED_FILE_TYPES = {"image/jpeg", "image/jpg", "image/png", "application/pdf"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_report_ownership(report: Optional[dict], current_user: dict, report_id: str) -> dict:
    """Raise 404 or 403 if report is missing / owned by another user."""
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    if report["userId"] != current_user["userId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this report.",
        )
    return report


def _report_to_response(report: dict, include_download_url: bool = False) -> ReportResponse:
    """Map a DynamoDB report dict to a ReportResponse schema."""
    download_url: Optional[str] = None
    if include_download_url and report.get("fileKey"):
        try:
            download_url = s3_service.generate_presigned_get_url(report["fileKey"])
        except Exception:
            logger.warning("Could not generate presigned GET URL for report %s", report["reportId"])

    return ReportResponse(
        reportId=report["reportId"],
        userId=report["userId"],
        status=report["status"],
        fileName=report["fileName"],
        fileType=report["fileType"],
        fileKey=report["fileKey"],
        downloadUrl=download_url,
        extractedData=report.get("extractedData"),
        confirmedData=report.get("confirmedData"),
        errorMessage=report.get("errorMessage"),
        uploadedAt=report["uploadedAt"],
        extractedAt=report.get("extractedAt"),
        confirmedAt=report.get("confirmedAt"),
        createdAt=report["createdAt"],
        updatedAt=report["updatedAt"],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ReportListResponse, status_code=status.HTTP_200_OK)
def list_reports(
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
    last_key: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
):
    """Return a paginated list of the authenticated user's reports."""
    items, next_key = dynamo_service.list_user_reports(
        user_id=current_user["userId"],
        limit=limit,
        last_key=last_key,
        status_filter=status_filter,
    )
    report_responses = [_report_to_response(item) for item in items]
    return ReportListResponse(reports=report_responses, lastKey=next_key, count=len(report_responses))


@router.post("/presign", response_model=PresignResponse, status_code=status.HTTP_201_CREATED)
def presign_upload(
    body: PresignRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Generate a presigned S3 PUT URL and create a PENDING_UPLOAD report record."""
    if body.fileType not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{body.fileType}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_FILE_TYPES))}",
        )

    if body.fileSize is not None and body.fileSize > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the 20 MB limit.",
        )

    report_id = str(uuid.uuid4())
    # Derive a safe extension from MIME type
    ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "application/pdf": "pdf",
    }
    ext = ext_map.get(body.fileType, "bin")
    file_key = f"reports/{current_user['userId']}/{report_id}.{ext}"

    upload_url = s3_service.generate_presigned_put_url(
        file_key=file_key,
        file_type=body.fileType,
        expires=300,
    )

    now = datetime.now(timezone.utc).isoformat()
    report_obj = Report(
        reportId=report_id,
        userId=current_user["userId"],
        status="PENDING_UPLOAD",
        fileName=body.fileName,
        fileType=body.fileType,
        fileKey=file_key,
        uploadedAt=now,
        createdAt=now,
        updatedAt=now,
    )
    dynamo_service.create_report(report_obj.to_dynamo_item())
    logger.info("Created PENDING_UPLOAD report %s for user %s", report_id, current_user["userId"])

    return PresignResponse(
        reportId=report_id,
        uploadUrl=upload_url,
        fileKey=file_key,
        expiresIn=300,
    )


@router.post("/{report_id}/extract", response_model=ExtractResponse, status_code=status.HTTP_202_ACCEPTED)
def extract_report(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Download the uploaded file from S3 and run GPT-4o extraction synchronously.

    Status flow: PENDING_UPLOAD / EXTRACTED -> PROCESSING -> EXTRACTED | FAILED
    """
    report = dynamo_service.get_report(report_id)
    _assert_report_ownership(report, current_user, report_id)

    if report["status"] == "CONFIRMED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report has already been confirmed and cannot be re-extracted.",
        )

    now = datetime.now(timezone.utc).isoformat()

    # Mark as PROCESSING
    dynamo_service.update_report(
        report_id,
        {"status": "PROCESSING", "updatedAt": now, "errorMessage": None},
    )
    logger.info("Starting extraction for report %s", report_id)

    try:
        file_bytes = s3_service.get_object_bytes(report["fileKey"])
        extracted_data = openai_service.extract_report_content(file_bytes, report["fileType"])

        finish_time = datetime.now(timezone.utc).isoformat()
        dynamo_service.update_report(
            report_id,
            {
                "status": "EXTRACTED",
                "extractedData": extracted_data,
                "extractedAt": finish_time,
                "updatedAt": finish_time,
                "errorMessage": None,
            },
        )
        logger.info("Extraction succeeded for report %s", report_id)
        return ExtractResponse(
            reportId=report_id,
            status="EXTRACTED",
            message="Extraction completed successfully.",
        )

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Extraction failed for report %s: %s", report_id, error_msg)
        fail_time = datetime.now(timezone.utc).isoformat()
        dynamo_service.update_report(
            report_id,
            {
                "status": "FAILED",
                "errorMessage": error_msg[:1000],  # cap length
                "updatedAt": fail_time,
            },
        )
        return ExtractResponse(
            reportId=report_id,
            status="FAILED",
            message=f"Extraction failed: {error_msg[:200]}",
        )


@router.get("/{report_id}/status", response_model=ReportStatusResponse, status_code=status.HTTP_200_OK)
def get_report_status(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return just the status and errorMessage for a report (lightweight polling endpoint)."""
    report = dynamo_service.get_report(report_id)
    _assert_report_ownership(report, current_user, report_id)
    return ReportStatusResponse(
        reportId=report_id,
        status=report["status"],
        errorMessage=report.get("errorMessage"),
    )


@router.get("/{report_id}", response_model=ReportResponse, status_code=status.HTTP_200_OK)
def get_report(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return the full report including a fresh presigned download URL."""
    report = dynamo_service.get_report(report_id)
    _assert_report_ownership(report, current_user, report_id)
    return _report_to_response(report, include_download_url=True)


@router.patch("/{report_id}/confirm", response_model=ReportResponse, status_code=status.HTTP_200_OK)
def confirm_report(
    report_id: str,
    body: ConfirmRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Save the user-reviewed (confirmed) data and mark the report CONFIRMED."""
    report = dynamo_service.get_report(report_id)
    _assert_report_ownership(report, current_user, report_id)

    if report["status"] not in ("EXTRACTED", "CONFIRMED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm a report in '{report['status']}' status. Report must be EXTRACTED first.",
        )

    now = datetime.now(timezone.utc).isoformat()
    updated = dynamo_service.update_report(
        report_id,
        {
            "status": "CONFIRMED",
            "confirmedData": body.confirmedData,
            "confirmedAt": now,
            "updatedAt": now,
        },
    )
    logger.info("Report %s confirmed by user %s", report_id, current_user["userId"])
    return _report_to_response(updated, include_download_url=True)


@router.delete("/{report_id}", status_code=status.HTTP_200_OK)
def delete_report(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Delete the S3 object and the DynamoDB record for the given report."""
    report = dynamo_service.get_report(report_id)
    _assert_report_ownership(report, current_user, report_id)

    # Delete from S3 first; if it fails, the DB record is still intact
    if report.get("fileKey"):
        try:
            s3_service.delete_object(report["fileKey"])
        except Exception as exc:
            logger.error(
                "Failed to delete S3 object '%s' for report %s: %s",
                report["fileKey"],
                report_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete the file from storage. Report was not deleted.",
            )

    dynamo_service.delete_report(report_id)
    logger.info("Deleted report %s for user %s", report_id, current_user["userId"])
    return {"message": f"Report '{report_id}' has been deleted."}
