from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-secret-change-before-deploying"


class Settings(BaseSettings):
    DATABASE_URL: str = Field(validation_alias=AliasChoices("DATABASE_URL", "DB_URL"))
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    JWT_SECRET: str = Field(default=DEVELOPMENT_JWT_SECRET, min_length=32)
    JWT_ALGORITHM: str = "HS256"
    REDIS_URL: str = "redis://localhost:6379/0"
    AUTH_RATE_LIMIT: int = Field(default=5, ge=1)
    AUTH_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1)
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@example.com"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "localhost"
    MAIL_FROM_NAME: str = "Bookly"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    PUBLIC_BASE_URL: AnyHttpUrl = "http://localhost:8000"

    @model_validator(mode="after")
    def require_production_jwt_secret(self):
        if self.ENVIRONMENT == "production" and self.JWT_SECRET == DEVELOPMENT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set explicitly in production")
        if self.ENVIRONMENT == "production" and self.PUBLIC_BASE_URL.scheme != "https":
            raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
        return self

    model_config = SettingsConfigDict(
        env_file=(".env", "src/.env"),
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
Config = settings

broker_url = settings.REDIS_URL
result_backend = settings.REDIS_URL
broker_connection_retry_on_startup = True
