from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import TracebackType

import pytest

from ai_model_briefing.collector import CollectionIssue, collect_recent_articles
from ai_model_briefing.http import SourceFetchError
from ai_model_briefing.sources import SourceCatalog

NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


class FakeClient:
    def __init__(self, responses: Mapping[str, str | Exception]) -> None:
        self._responses = responses

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def get_text(self, url: str) -> str:
        response = self._responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def make_catalog(*, include_broken_source: bool = False) -> SourceCatalog:
    sources: list[dict[str, object]] = [
        {
            "id": "example-ai",
            "company": "Example AI",
            "type": "rss",
            "url": "https://example.com/feed",
            "include_paths": ["/news/"],
        }
    ]
    if include_broken_source:
        sources.append(
            {
                "id": "broken-ai",
                "company": "Broken AI",
                "type": "rss",
                "url": "https://broken.example/feed",
                "include_paths": ["/news/"],
            }
        )
    return SourceCatalog.model_validate({"version": 1, "sources": sources})


def make_factory(responses: Mapping[str, str | Exception]):
    def factory(allowed_hosts: frozenset[str]) -> FakeClient:
        assert allowed_hosts
        return FakeClient(responses)

    return factory


def test_collects_only_complete_articles_in_daily_window() -> None:
    feed = """
    <rss><channel>
      <item><title>Current</title><link>https://example.com/news/current</link>
        <pubDate>Tue, 29 Sep 2026 14:00:00 GMT</pubDate><description>Useful.</description></item>
      <item><title>Old</title><link>https://example.com/news/old</link>
        <pubDate>Sun, 27 Sep 2026 12:00:00 GMT</pubDate><description>Old.</description></item>
      <item><title>Future</title><link>https://example.com/news/future</link>
        <pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate><description>Future.</description></item>
    </channel></rss>
    """

    result = collect_recent_articles(
        make_catalog(),
        "daily",
        now=NOW,
        client_factory=make_factory({"https://example.com/feed": feed}),
    )

    assert [article.title for article in result.articles] == ["Current"]
    assert result.issues == ()


def test_weekly_window_includes_older_article() -> None:
    feed = """
    <rss><channel><item><title>Weekly</title>
      <link>https://example.com/news/weekly</link>
      <pubDate>Thu, 24 Sep 2026 12:00:00 GMT</pubDate>
      <description>Still relevant.</description>
    </item></channel></rss>
    """

    result = collect_recent_articles(
        make_catalog(),
        "weekly",
        now=NOW,
        client_factory=make_factory({"https://example.com/feed": feed}),
    )

    assert [article.title for article in result.articles] == ["Weekly"]


def test_does_not_fetch_an_old_incomplete_article() -> None:
    feed = """
    <rss><channel><item><title>Old</title>
      <link>https://example.com/news/old</link>
      <pubDate>Sun, 27 Sep 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>
    """

    result = collect_recent_articles(
        make_catalog(),
        "daily",
        now=NOW,
        client_factory=make_factory({"https://example.com/feed": feed}),
    )

    assert result.articles == ()
    assert result.issues == ()


def test_enriches_incomplete_listing_item() -> None:
    feed = """
    <rss><channel><item><link>https://example.com/news/model</link></item></channel></rss>
    """
    page = """
    <html><head><meta property="og:title" content="Model" />
      <meta name="description" content="Release details." />
      <meta property="article:published_time" content="2026-09-30T10:00:00Z" />
    </head><body><article>Full release.</article></body></html>
    """

    result = collect_recent_articles(
        make_catalog(),
        "daily",
        now=NOW,
        client_factory=make_factory(
            {"https://example.com/feed": feed, "https://example.com/news/model": page}
        ),
    )

    assert len(result.articles) == 1
    assert result.articles[0].title == "Model"
    assert result.articles[0].content == "Full release."


def test_source_failure_does_not_discard_other_sources() -> None:
    feed = """
    <rss><channel><item><title>Available</title>
      <link>https://example.com/news/available</link>
      <pubDate>Wed, 30 Sep 2026 10:00:00 GMT</pubDate>
      <description>Release.</description>
    </item></channel></rss>
    """
    result = collect_recent_articles(
        make_catalog(include_broken_source=True),
        "daily",
        now=NOW,
        client_factory=make_factory(
            {
                "https://example.com/feed": feed,
                "https://broken.example/feed": SourceFetchError("unavailable"),
            }
        ),
    )

    assert [article.title for article in result.articles] == ["Available"]
    assert result.issues == (CollectionIssue("broken-ai", "listing_fetch"),)


def test_article_failure_is_reported_once_and_items_are_skipped() -> None:
    feed = """
    <rss><channel>
      <item><link>https://example.com/news/one</link></item>
      <item><link>https://example.com/news/two</link></item>
    </channel></rss>
    """
    failure = SourceFetchError("unavailable")

    result = collect_recent_articles(
        make_catalog(),
        "daily",
        now=NOW,
        client_factory=make_factory(
            {
                "https://example.com/feed": feed,
                "https://example.com/news/one": failure,
                "https://example.com/news/two": failure,
            }
        ),
    )

    assert result.articles == ()
    assert result.issues == (CollectionIssue("example-ai", "article_fetch"),)


def test_rejects_naive_reference_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        collect_recent_articles(
            make_catalog(),
            "daily",
            now=datetime(2026, 9, 30, 12),
            client_factory=make_factory({}),
        )
