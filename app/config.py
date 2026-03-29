from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    PORT: int = 8000

    # JWT
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str

    # S3
    S3_BUCKET_NAME: str

    # DynamoDB
    DYNAMODB_USERS_TABLE: str = "MedicalAppUsers"
    DYNAMODB_REPORTS_TABLE: str = "MedicalAppReports"

    # OpenAI
    OPENAI_API_KEY: str

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:8081,exp://localhost:8081"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str) -> str:
        return v

    def get_allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
