"""
Application configuration using Pydantic Settings
"""
import os
from pathlib import Path
from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

# Find .env file at project root
# __file__ is apps/api/app/core/config.py
# We need to go up 4 levels: core -> app -> api -> apps -> root
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

# Fallback: also check current directory and parent
if not ENV_FILE.exists():
    # Try current working directory
    ENV_FILE = Path.cwd() / ".env"
    if not ENV_FILE.exists():
        # Try going up from cwd
        ENV_FILE = Path.cwd().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra fields from .env that aren't in the model
    )

    # App
    APP_NAME: str = "Early Signals API"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    API_SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Meilisearch
    MEILI_URL: str = Field(default="http://localhost:7700")
    MEILI_MASTER_KEY: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    # CORS - can be comma-separated string or list
    CORS_ORIGINS: Union[str, List[str]] = Field(
        default="http://localhost:4200,http://localhost:3000"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from env var (comma-separated)"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # Email
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM_EMAIL: str = Field(default="noreply@earlysignals.io")
    SMTP_FROM_NAME: str = Field(default="Early Signals")

    # Development email (MailHog)
    SMTP_HOST_DEV: str = Field(default="localhost")
    SMTP_PORT_DEV: int = Field(default=1025)

    # Stripe
    STRIPE_SECRET_KEY: str = Field(default="")
    STRIPE_PUBLISHABLE_KEY: str = Field(default="")
    STRIPE_WEBHOOK_SECRET: str = Field(default="")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    FRONTEND_URL: str = Field(
        default="http://localhost:4200",
        description="Frontend base URL for OAuth redirect after login",
    )


settings = Settings()
