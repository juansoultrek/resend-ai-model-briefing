from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from xml.etree.ElementTree import Element, ParseError

from bs4 import BeautifulSoup
from bs4.element import Tag
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from ai_model_briefing.sources import Source

MAX_TITLE_CHARACTERS = 300
MAX_SUMMARY_CHARACTERS = 3_000
MAX_CONTENT_CHARACTERS = 8_000


class SourceParseError(ValueError):
    """Raised when a source document cannot be safely parsed."""


@dataclass(frozen=True, slots=True)
class ParsedArticle:
    source_id: str
    company: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    content: str = ""


def parse_listing(document: str, source: Source) -> tuple[ParsedArticle, ...]:
    if source.type == "rss":
        return parse_feed(document, source)
    if source.type == "sitemap":
        return parse_sitemap(document, source)
    return parse_html_index(document, source)


def parse_feed(document: str, source: Source) -> tuple[ParsedArticle, ...]:
    root = _parse_xml(document)
    articles: list[ParsedArticle] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"item", "entry"}:
            continue
        url = _feed_link(node)
        normalized_url = _normalize_article_url(url, source) if url else None
        if not normalized_url:
            continue
        title = _clean_text(_child_text(node, "title"), MAX_TITLE_CHARACTERS)
        summary = _clean_text(
            _child_text(node, "description", "summary", "content", "encoded"),
            MAX_SUMMARY_CHARACTERS,
        )
        published_at = _parse_date(_child_text(node, "pubDate", "published", "updated", "date"))
        articles.append(
            ParsedArticle(
                source_id=source.id,
                company=source.company,
                title=title,
                url=normalized_url,
                published_at=published_at,
                summary=summary,
            )
        )
    return _deduplicate_and_limit(articles, source.max_items)


def parse_sitemap(document: str, source: Source) -> tuple[ParsedArticle, ...]:
    root = _parse_xml(document)
    articles: list[ParsedArticle] = []
    for node in root.iter():
        if _local_name(node.tag) != "url":
            continue
        url = _child_text(node, "loc")
        normalized_url = _normalize_article_url(url, source) if url else None
        if not normalized_url:
            continue
        articles.append(
            ParsedArticle(
                source_id=source.id,
                company=source.company,
                title="",
                url=normalized_url,
                published_at=_parse_date(_child_text(node, "lastmod")),
            )
        )
    return _deduplicate_and_limit(articles, source.max_items)


def parse_html_index(document: str, source: Source) -> tuple[ParsedArticle, ...]:
    soup = BeautifulSoup(document, "html.parser")
    articles: list[ParsedArticle] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        normalized_url = _normalize_article_url(urljoin(str(source.url), href), source)
        if not normalized_url:
            continue
        container = anchor.find_parent("article")
        articles.append(
            ParsedArticle(
                source_id=source.id,
                company=source.company,
                title=_clean_text(anchor.get_text(" "), MAX_TITLE_CHARACTERS),
                url=normalized_url,
                published_at=_article_card_date(container),
                summary=_article_card_summary(container),
            )
        )
    return _deduplicate_and_limit(articles, source.max_items)


def enrich_from_article_page(
    article: ParsedArticle, document: str, source: Source
) -> ParsedArticle:
    soup = BeautifulSoup(document, "html.parser")
    for unwanted in soup.select("script, style, noscript, nav, footer, header, form"):
        unwanted.decompose()

    title = _first_meta_content(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ")
    summary = _first_meta_content(soup, "description", "og:description", "twitter:description")
    date_text = _first_meta_content(
        soup,
        "article:published_time",
        "date",
        "datePublished",
        "publish-date",
    )
    if not date_text:
        time_element = soup.find("time", datetime=True)
        if isinstance(time_element, Tag):
            datetime_value = time_element.get("datetime")
            date_text = datetime_value if isinstance(datetime_value, str) else ""

    content_node = soup.find("article") or soup.find("main") or soup.body
    content = content_node.get_text(" ") if content_node else ""
    return replace(
        article,
        title=_clean_text(title, MAX_TITLE_CHARACTERS) or article.title,
        summary=_clean_text(summary, MAX_SUMMARY_CHARACTERS) or article.summary,
        published_at=_parse_date(date_text) or article.published_at,
        content=_clean_text(content, MAX_CONTENT_CHARACTERS),
    )


def _parse_xml(document: str) -> Element:
    try:
        return ElementTree.fromstring(document)
    except (ParseError, DefusedXmlException) as error:
        raise SourceParseError("source returned invalid or unsafe XML") from error


def _feed_link(node: Element) -> str:
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        relation = child.attrib.get("rel", "alternate")
        if href and relation == "alternate":
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _child_text(node: Element, *names: str) -> str:
    expected = set(names)
    for child in node:
        if _local_name(child.tag) in expected:
            return "".join(child.itertext()).strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _normalize_article_url(value: str, source: Source) -> str | None:
    parsed = urlsplit(urljoin(str(source.url), value.strip()))
    if parsed.scheme != "https" or parsed.hostname not in source.effective_allowed_hosts:
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        return None
    decoded_segments = unquote(parsed.path).split("/")
    if ".." in decoded_segments:
        return None
    if source.include_paths and not any(
        parsed.path.startswith(path) for path in source.include_paths
    ):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    parsed: datetime | None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            parsed = _parse_short_date(value)
            if parsed is None:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_short_date(value: str) -> datetime | None:
    for date_format in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _article_card_date(container: Tag | None) -> datetime | None:
    if container is None:
        return None
    time_element = container.find("time")
    if isinstance(time_element, Tag):
        datetime_value = time_element.get("datetime")
        if isinstance(datetime_value, str) and (parsed := _parse_date(datetime_value)):
            return parsed
        if parsed := _parse_date(time_element.get_text(" ", strip=True)):
            return parsed
    date_element = container.select_one('[class*="date"]')
    if isinstance(date_element, Tag):
        return _parse_date(date_element.get_text(" ", strip=True))
    return None


def _article_card_summary(container: Tag | None) -> str:
    if container is None:
        return ""
    summary = container.find("p")
    if not isinstance(summary, Tag):
        return ""
    return _clean_text(summary.get_text(" "), MAX_SUMMARY_CHARACTERS)


def _clean_text(value: str, limit: int) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for unwanted in soup.select("script, style, noscript"):
        unwanted.decompose()
    normalized = " ".join(soup.get_text(" ").split())
    return normalized[:limit]


def _first_meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        meta = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if isinstance(meta, Tag):
            content = meta.get("content")
            if isinstance(content, str):
                return content
    return ""


def _deduplicate_and_limit(
    articles: list[ParsedArticle], max_items: int
) -> tuple[ParsedArticle, ...]:
    unique: dict[str, ParsedArticle] = {}
    for article in articles:
        unique.setdefault(article.url, article)
    return tuple(unique.values())[:max_items]
