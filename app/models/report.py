from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class Report(BaseModel):
    reportId: str
    userId: str
    status: str  # PENDING_UPLOAD | PROCESSING | EXTRACTED | CONFIRMED | FAILED
    fileName: str
    fileType: str
    fileKey: str
    extractedData: Optional[dict] = None
    confirmedData: Optional[dict] = None
    errorMessage: Optional[str] = None
    uploadedAt: str
    extractedAt: Optional[str] = None
    confirmedAt: Optional[str] = None
    createdAt: str
    updatedAt: str

    def to_dynamo_item(self) -> dict:
        """Serialize the Report to a DynamoDB-compatible dict.

        None values are omitted so they don't overwrite existing attributes
        with NULL in DynamoDB.
        """
        item: dict = {
            "reportId": self.reportId,
            "userId": self.userId,
            "status": self.status,
            "fileName": self.fileName,
            "fileType": self.fileType,
            "fileKey": self.fileKey,
            "uploadedAt": self.uploadedAt,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }
        if self.extractedData is not None:
            item["extractedData"] = self.extractedData
        if self.confirmedData is not None:
            item["confirmedData"] = self.confirmedData
        if self.errorMessage is not None:
            item["errorMessage"] = self.errorMessage
        if self.extractedAt is not None:
            item["extractedAt"] = self.extractedAt
        if self.confirmedAt is not None:
            item["confirmedAt"] = self.confirmedAt
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "Report":
        """Deserialize a DynamoDB item into a Report model.

        Converts Decimal values returned by boto3 to float.
        """

        def _convert(value):
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {k: _convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_convert(v) for v in value]
            return value

        converted = {k: _convert(v) for k, v in item.items()}
        return cls(**converted)
