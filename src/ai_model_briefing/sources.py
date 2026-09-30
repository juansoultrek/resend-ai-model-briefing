from __future__ import annotations

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

MAX_SOURCES_FILE_BYTES = 65_536


class SourceConfigurationError(ValueError):
    """Raised when the source catalog cannot be safely loaded."""


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    company: str = Field(min_length=1, max_length=100)
    type: Literal["rss", "sitemap", "html"]
    url: HttpUrl
    include_paths: tuple[str, ...] = ()
    enabled: bool = True
    max_items: int = Field(default=10, ge=1, le=25)

    @model_validator(mode="after")
    def validate_url_and_paths(self) -> Self:
        parsed = urlsplit(str(self.url))
        if parsed.scheme != "https":
            raise ValueError("source URLs must use HTTPS")
        if parsed.username or parsed.password:
            raise ValueError("source URLs must not contain credentials")
        for path in self.include_paths:
            if not path.startswith("/") or ".." in path:
                raise ValueError("include paths must be absolute and must not contain '..'")
        return self


class SourceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    sources: tuple[Source, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique")
        if not any(source.enabled for source in self.sources):
            raise ValueError("at least one source must be enabled")
        return self


def load_source_catalog(path: Path) -> SourceCatalog:
    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise SourceConfigurationError(f"cannot read source catalog: {path}") from error

    if file_size > MAX_SOURCES_FILE_BYTES:
        raise SourceConfigurationError(
            f"source catalog exceeds {MAX_SOURCES_FILE_BYTES} bytes: {path}"
        )

    try:
        raw_catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
        return SourceCatalog.model_validate(raw_catalog)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise SourceConfigurationError(f"invalid source catalog: {path}: {error}") from error
