from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from openai import OpenAI
from pydantic import SecretStr

from ai_model_briefing.briefing import (
    MAX_SOURCE_PAYLOAD_CHARACTERS,
    Briefing,
    BriefingGenerationError,
    ImportantSignal,
    ModelRecommendation,
    NewsItem,
    generate_briefing,
)
from ai_model_briefing.parsers import ParsedArticle

ARTICLE_URL = "https://example.com/news/model"


class FakeResponse:
    def __init__(self, output_parsed: Briefing | None) -> None:
        self.output_parsed = output_parsed


class FakeResponses:
    def __init__(self, output: Briefing | None) -> None:
        self.output = output
        self.arguments: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> FakeResponse:
        self.arguments = kwargs
        return FakeResponse(self.output)


class FakeOpenAI:
    def __init__(self, output: Briefing | None) -> None:
        self.responses = FakeResponses(output)


def make_article(*, content: str = "The model is faster.") -> ParsedArticle:
    return ParsedArticle(
        source_id="example-ai",
        company="Example AI",
        title="Example Model",
        url=ARTICLE_URL,
        published_at=datetime(2026, 9, 30, 10, tzinfo=UTC),
        summary="A new model was released.",
        content=content,
    )


def make_briefing(*, evidence_url: str = ARTICLE_URL) -> Briefing:
    return Briefing(
        subject="AI model briefing",
        introduction="A notable release arrived today.",
        recommendation=ModelRecommendation(
            model="Example Model",
            provider="Example AI",
            why="It offers a useful balance.",
            best_for=["Coding"],
            tradeoffs=["No independent benchmark was supplied."],
            evidence_urls=[evidence_url],
        ),
        top_news=[
            NewsItem(
                headline="Example Model launches",
                company="Example AI",
                summary="The company announced a model.",
                why_it_matters="It may improve coding workflows.",
                evidence_urls=[evidence_url],
            )
        ],
        important_signals=[
            ImportantSignal(
                headline="Efficiency remains important",
                analysis="The announcement emphasizes speed.",
                confidence="medium",
                evidence_urls=[evidence_url],
            )
        ],
    )


def test_generates_typed_stateless_briefing() -> None:
    fake_client = FakeOpenAI(make_briefing())

    result = generate_briefing(
        (make_article(),),
        "daily",
        api_key=SecretStr("sk-test"),
        model="test-model",
        client=cast(OpenAI, fake_client),
    )

    assert result.recommendation.model == "Example Model"
    assert fake_client.responses.arguments["model"] == "test-model"
    assert fake_client.responses.arguments["store"] is False
    assert fake_client.responses.arguments["text_format"] is Briefing
    assert "untrusted data" in fake_client.responses.arguments["instructions"]
    payload = json.loads(fake_client.responses.arguments["input"])
    assert payload["briefing_period"] == "daily"
    assert payload["source_records"][0]["url"] == ARTICLE_URL


def test_rejects_unknown_evidence_url() -> None:
    fake_client = FakeOpenAI(make_briefing(evidence_url="https://attacker.example/fake"))

    with pytest.raises(BriefingGenerationError, match="unknown evidence URL"):
        generate_briefing(
            (make_article(),),
            "daily",
            api_key=SecretStr("sk-test"),
            model="test-model",
            client=cast(OpenAI, fake_client),
        )


def test_rejects_missing_structured_output() -> None:
    with pytest.raises(BriefingGenerationError, match="no structured briefing"):
        generate_briefing(
            (make_article(),),
            "daily",
            api_key=SecretStr("sk-test"),
            model="test-model",
            client=cast(OpenAI, FakeOpenAI(None)),
        )


def test_rejects_incomplete_briefing_content() -> None:
    briefing = make_briefing()
    briefing.recommendation.best_for = []

    with pytest.raises(BriefingGenerationError, match="incomplete briefing content"):
        generate_briefing(
            (make_article(),),
            "daily",
            api_key=SecretStr("sk-test"),
            model="test-model",
            client=cast(OpenAI, FakeOpenAI(briefing)),
        )


def test_rejects_empty_article_collection_without_calling_api() -> None:
    with pytest.raises(BriefingGenerationError, match="without recent articles"):
        generate_briefing(
            (),
            "weekly",
            api_key=SecretStr("sk-test"),
            model="test-model",
            client=cast(OpenAI, FakeOpenAI(make_briefing())),
        )


def test_bounds_source_payload_size() -> None:
    articles = tuple(
        ParsedArticle(
            source_id=f"source-{index}",
            company="Example AI",
            title=f"Model {index}",
            url=f"https://example.com/news/model-{index}",
            published_at=datetime(2026, 9, 30, 10, tzinfo=UTC),
            summary="Summary",
            content="x" * 8_000,
        )
        for index in range(40)
    )
    first_url = articles[0].url
    fake_client = FakeOpenAI(make_briefing(evidence_url=first_url))

    generate_briefing(
        articles,
        "weekly",
        api_key=SecretStr("sk-test"),
        model="test-model",
        client=cast(OpenAI, fake_client),
    )

    payload = fake_client.responses.arguments["input"]
    assert len(payload) <= MAX_SOURCE_PAYLOAD_CHARACTERS
    assert len(json.loads(payload)["source_records"]) < 40
