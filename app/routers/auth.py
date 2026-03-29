import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.services import auth_service, dynamo_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _build_token_response(user: dict) -> TokenResponse:
    """Create an access + refresh token pair for the given user dict."""
    token_data = {"sub": user["userId"]}
    return TokenResponse(
        accessToken=auth_service.create_access_token(token_data),
        refreshToken=auth_service.create_refresh_token(token_data),
        userId=user["userId"],
        email=user["email"],
        name=user["name"],
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    """Create a new user account and return a token pair."""
    # Check for existing email
    existing = dynamo_service.get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    now = datetime.now(timezone.utc).isoformat()
    user_obj = User(
        userId=str(uuid.uuid4()),
        email=body.email,
        passwordHash=auth_service.hash_password(body.password),
        name=body.name,
        createdAt=now,
        updatedAt=now,
    )

    created = dynamo_service.create_user(user_obj.to_dynamo_item())
    logger.info("Registered new user: %s (%s)", created["userId"], created["email"])
    return _build_token_response(created)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(body: LoginRequest):
    """Authenticate with email + password and return a token pair."""
    user = dynamo_service.get_user_by_email(body.email)
    if not user or not auth_service.verify_password(body.password, user["passwordHash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    logger.info("User logged in: %s", user["userId"])
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh_tokens(body: RefreshRequest):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = auth_service.decode_token(body.refreshToken, settings.JWT_REFRESH_SECRET)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token.",
        )

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
        )

    user = dynamo_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    logger.info("Refreshed tokens for user: %s", user_id)
    return _build_token_response(user)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout():
    """Stateless logout — client must discard tokens locally."""
    return {"message": "Logged out successfully. Please clear your tokens on the client."}
