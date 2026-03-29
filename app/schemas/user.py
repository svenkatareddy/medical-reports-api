from pydantic import BaseModel, EmailStr
from typing import Optional


class UserResponse(BaseModel):
    userId: str
    email: str
    name: str
    createdAt: str
    updatedAt: str


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

    model_config = {"extra": "forbid"}
