from __future__ import annotations

from email.utils import parseaddr
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY", min_length=1)
    openai_model: str = Field(default="gpt-6-astra", alias="OPENAI_MODEL", min_length=1)
    resend_api_key: SecretStr = Field(alias="RESEND_API_KEY", min_length=4)
    resend_from: str = Field(alias="RESEND_FROM", min_length=3)
    resend_segment_id: UUID = Field(alias="RESEND_SEGMENT_ID")
    briefing_mode: Literal["daily", "weekly"] = Field(default="daily", alias="BRIEFING_MODE")
    sources_file: Path = Field(default=Path("config/sources.yaml"), alias="SOURCES_FILE")

    @field_validator("openai_model", "resend_from")
    @classmethod
    def strip_text_values(cls, value: str) -> str:
        return value.strip()

    @field_validator("resend_from")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("must not contain line breaks")
        _, address = parseaddr(value)
        if not address or "@" not in address:
            raise ValueError("must contain a valid sender address")
        return value

    @model_validator(mode="after")
    def validate_resend_key(self) -> Self:
        if not self.resend_api_key.get_secret_value().startswith("re_"):
            raise ValueError("RESEND_API_KEY must start with 're_'")
        return self


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
