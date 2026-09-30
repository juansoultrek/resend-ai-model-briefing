from __future__ import annotations

from email.utils import parseaddr
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GenerationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY", min_length=4)
    openai_model: str = Field(
        default="gpt-6-astra", alias="OPENAI_MODEL", min_length=1, max_length=100
    )
    briefing_mode: Literal["daily", "weekly"] = Field(default="daily", alias="BRIEFING_MODE")
    sources_file: Path = Field(default=Path("config/sources.yaml"), alias="SOURCES_FILE")

    @field_validator("openai_model")
    @classmethod
    def strip_model_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped or any(character.isspace() for character in stripped):
            raise ValueError("must be a non-empty model identifier without whitespace")
        return stripped

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret != secret.strip() or not secret.startswith("sk-"):
            raise ValueError("OPENAI_API_KEY must be an unpadded key starting with 'sk-'")
        return value


class Settings(GenerationSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    resend_api_key: SecretStr = Field(alias="RESEND_API_KEY", min_length=4)
    resend_from: str = Field(alias="RESEND_FROM", min_length=3)
    resend_segment_id: UUID = Field(alias="RESEND_SEGMENT_ID")

    @field_validator("resend_from")
    @classmethod
    def strip_sender(cls, value: str) -> str:
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

    @field_validator("resend_api_key")
    @classmethod
    def validate_resend_key(cls, value: SecretStr) -> SecretStr:
        return _validate_resend_key(value)


class SubscriberSettings(BaseSettings):
    model_config = GenerationSettings.model_config

    resend_api_key: SecretStr = Field(alias="RESEND_API_KEY", min_length=4)
    resend_segment_id: UUID = Field(alias="RESEND_SEGMENT_ID")

    @field_validator("resend_api_key")
    @classmethod
    def validate_resend_key(cls, value: SecretStr) -> SecretStr:
        return _validate_resend_key(value)


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def load_generation_settings() -> GenerationSettings:
    return GenerationSettings()  # type: ignore[call-arg]


def load_subscriber_settings() -> SubscriberSettings:
    return SubscriberSettings()  # type: ignore[call-arg]


def _validate_resend_key(value: SecretStr) -> SecretStr:
    secret = value.get_secret_value()
    if secret != secret.strip() or not secret.startswith("re_"):
        raise ValueError("RESEND_API_KEY must be an unpadded key starting with 're_'")
    return value
