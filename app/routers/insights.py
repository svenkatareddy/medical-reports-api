import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services import openai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["Insights"])


class InsightsRequest(BaseModel):
    reportSummary: str


class Observation(BaseModel):
    title: str
    detail: str
    severity: str


class InsightsResponse(BaseModel):
    summary: str
    observations: List[Observation]
    recommendations: List[str]
    disclaimer: str


@router.post("", response_model=InsightsResponse, status_code=status.HTTP_200_OK)
def get_insights(
    body: InsightsRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Generate AI health insights from a summary of the user's medical reports."""
    if not body.reportSummary.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="reportSummary cannot be empty.",
        )

    try:
        result = openai_service.generate_insights(body.reportSummary)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Insights generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate insights. Please try again.",
        )

    return InsightsResponse(**result)
