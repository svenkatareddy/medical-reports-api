from pydantic import BaseModel
from typing import Optional, List, Any


class PresignRequest(BaseModel):
    fileName: str
    fileType: str
    fileSize: Optional[int] = None

    @classmethod
    def validate_file_type(cls, v: str) -> str:
        allowed = {"image/jpeg", "image/jpg", "image/png", "application/pdf"}
        if v not in allowed:
            raise ValueError(f"File type '{v}' is not allowed. Allowed types: {', '.join(allowed)}")
        return v


class PresignResponse(BaseModel):
    reportId: str
    uploadUrl: str
    fileKey: str
    expiresIn: int


class ExtractResponse(BaseModel):
    reportId: str
    status: str
    message: str


class ConfirmRequest(BaseModel):
    confirmedData: dict


class ReportResponse(BaseModel):
    reportId: str
    userId: str
    status: str
    fileName: str
    fileType: str
    fileKey: str
    downloadUrl: Optional[str] = None
    extractedData: Optional[dict] = None
    confirmedData: Optional[dict] = None
    errorMessage: Optional[str] = None
    uploadedAt: str
    extractedAt: Optional[str] = None
    confirmedAt: Optional[str] = None
    createdAt: str
    updatedAt: str


class ReportStatusResponse(BaseModel):
    reportId: str
    status: str
    errorMessage: Optional[str] = None


class ReportListResponse(BaseModel):
    reports: List[ReportResponse]
    lastKey: Optional[str] = None
    count: int
