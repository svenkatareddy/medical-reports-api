from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class User(BaseModel):
    userId: str
    email: str
    passwordHash: str
    name: str
    createdAt: str
    updatedAt: str

    def to_dynamo_item(self) -> dict:
        """Serialize the User to a DynamoDB-compatible dict."""
        return {
            "userId": self.userId,
            "email": self.email,
            "passwordHash": self.passwordHash,
            "name": self.name,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "User":
        """Deserialize a DynamoDB item into a User model.

        DynamoDB may return Decimal for numeric fields; convert them to the
        appropriate Python type before constructing the model.
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
