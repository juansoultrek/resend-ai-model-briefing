from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from ai_model_briefing.http import SafeHttpClient, SourceFetchError
from ai_model_briefing.parsers import (
    ParsedArticle,
    SourceParseError,
    enrich_from_article_page,
    parse_listing,
)
from ai_model_briefing.sources import Source, SourceCatalog

BriefingMode = Literal["daily", "weekly"]
ClientFactory = Callable[[frozenset[str]], SafeHttpClient]

WINDOWS: dict[BriefingMode, timedelta] = {
    "daily": timedelta(hours=36),
    "weekly": timedelta(days=8),
}
MAX_SOURCE_WORKERS = 4
MAX_ARTICLE_ENRICHMENTS_PER_SOURCE = 4


@dataclass(frozen=True, slots=True)
class CollectionIssue:
    source_id: str
    stage: Literal["listing_fetch", "listing_parse", "article_fetch", "article_parse"]


@dataclass(frozen=True, slots=True)
class CollectionResult:
    articles: tuple[ParsedArticle, ...]
    issues: tuple[CollectionIssue, ...]


def collect_recent_articles(
    catalog: SourceCatalog,
    mode: BriefingMode,
    *,
    now: datetime | None = None,
    client_factory: ClientFactory | None = None,
) -> CollectionResult:
    reference_time = _as_utc(now or datetime.now(UTC))
    cutoff = reference_time - WINDOWS[mode]
    factory = client_factory or _make_client
    collected: list[ParsedArticle] = []
    issues: list[CollectionIssue] = []

    enabled_sources = tuple(source for source in catalog.sources if source.enabled)
    worker_count = min(MAX_SOURCE_WORKERS, len(enabled_sources))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        source_results = executor.map(
            lambda source: _collect_source(source, factory, cutoff, reference_time),
            enabled_sources,
        )

    for articles, source_issues in source_results:
        issues.extend(source_issues)
        collected.extend(
            article
            for article in articles
            if _is_complete_and_recent(article, cutoff, reference_time)
        )

    unique = {article.url: article for article in collected}
    ordered = sorted(
        unique.values(),
        key=lambda article: article.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return CollectionResult(articles=tuple(ordered), issues=tuple(issues))


def _collect_source(
    source: Source,
    factory: ClientFactory,
    cutoff: datetime,
    reference_time: datetime,
) -> tuple[tuple[ParsedArticle, ...], tuple[CollectionIssue, ...]]:
    issues: list[CollectionIssue] = []
    with factory(source.effective_allowed_hosts) as client:
        try:
            listing = client.get_text(str(source.url))
        except SourceFetchError:
            return (), (CollectionIssue(source.id, "listing_fetch"),)

        try:
            candidates = parse_listing(listing, source)
        except SourceParseError:
            return (), (CollectionIssue(source.id, "listing_parse"),)

        articles: list[ParsedArticle] = []
        enrichment_count = 0
        for candidate in candidates:
            if _has_date_outside_window(candidate, cutoff, reference_time):
                continue
            if not _needs_enrichment(candidate):
                articles.append(candidate)
                continue
            if enrichment_count >= MAX_ARTICLE_ENRICHMENTS_PER_SOURCE:
                continue
            enrichment_count += 1
            try:
                article_page = client.get_text(candidate.url)
            except SourceFetchError:
                _add_issue_once(issues, CollectionIssue(source.id, "article_fetch"))
                continue
            try:
                articles.append(enrich_from_article_page(candidate, article_page, source))
            except (SourceParseError, ValueError):
                _add_issue_once(issues, CollectionIssue(source.id, "article_parse"))

    return tuple(articles), tuple(issues)


def _make_client(allowed_hosts: frozenset[str]) -> SafeHttpClient:
    return SafeHttpClient(allowed_hosts=allowed_hosts)


def _needs_enrichment(article: ParsedArticle) -> bool:
    return not article.title or article.published_at is None or not article.summary


def _has_date_outside_window(
    article: ParsedArticle, cutoff: datetime, reference_time: datetime
) -> bool:
    return bool(article.published_at and not cutoff <= article.published_at <= reference_time)


def _is_complete_and_recent(
    article: ParsedArticle, cutoff: datetime, reference_time: datetime
) -> bool:
    return bool(
        article.title
        and (article.summary or article.content)
        and article.published_at
        and cutoff <= article.published_at <= reference_time
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("the collection reference time must include a timezone")
    return value.astimezone(UTC)


def _add_issue_once(issues: list[CollectionIssue], issue: CollectionIssue) -> None:
    if issue not in issues:
        issues.append(issue)
