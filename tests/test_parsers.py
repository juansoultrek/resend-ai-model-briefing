from datetime import UTC, datetime

import pytest

from ai_model_briefing.parsers import (
    ParsedArticle,
    SourceParseError,
    enrich_from_article_page,
    parse_feed,
    parse_html_index,
    parse_sitemap,
)
from ai_model_briefing.sources import Source


def make_source(source_type: str) -> Source:
    return Source.model_validate(
        {
            "id": "example-ai",
            "company": "Example AI",
            "type": source_type,
            "url": "https://example.com/feed",
            "include_paths": ["/news/"],
        }
    )


def test_parses_rss_and_removes_untrusted_markup() -> None:
    document = """
    <rss><channel><item>
      <title>Model One</title>
      <link>https://example.com/news/model-one</link>
      <pubDate>Tue, 29 Sep 2026 14:00:00 GMT</pubDate>
      <description><![CDATA[<p>New model.</p><script>ignore()</script>]]></description>
    </item></channel></rss>
    """

    articles = parse_feed(document, make_source("rss"))

    assert len(articles) == 1
    assert articles[0].title == "Model One"
    assert articles[0].summary == "New model."
    assert articles[0].published_at == datetime(2026, 9, 29, 14, tzinfo=UTC)


def test_parses_atom_link() -> None:
    document = """
    <feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Model Two</title>
      <link rel="alternate" href="https://example.com/news/model-two" />
      <updated>2026-09-29T15:00:00Z</updated>
      <summary>Faster and smaller.</summary>
    </entry></feed>
    """

    articles = parse_feed(document, make_source("rss"))

    assert articles[0].url == "https://example.com/news/model-two"
    assert articles[0].summary == "Faster and smaller."


def test_parses_and_filters_sitemap() -> None:
    document = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/news/included</loc><lastmod>2026-09-29</lastmod></url>
      <url><loc>https://example.com/careers/excluded</loc></url>
    </urlset>
    """

    articles = parse_sitemap(document, make_source("sitemap"))

    assert [article.url for article in articles] == ["https://example.com/news/included"]


def test_parses_html_index_and_deduplicates_links() -> None:
    document = """
    <a href="/news/model-three">Model Three</a>
    <a href="/news/model-three#details">Duplicate</a>
    <a href="https://attacker.example/news/fake">External</a>
    """

    articles = parse_html_index(document, make_source("html"))

    assert len(articles) == 1
    assert articles[0].title == "Model Three"


def test_parses_html_article_card_metadata() -> None:
    source = Source.model_validate(
        {
            "id": "example-ai",
            "company": "Example AI",
            "type": "html",
            "url": "https://example.com/releases",
            "allowed_hosts": ["example.com", "models.example.com"],
            "include_paths": ["/ExampleAI/"],
        }
    )
    document = """
    <article>
      <span class="release-date">09/30/26</span>
      <h3><a href="https://models.example.com/ExampleAI/model-five">Model Five</a></h3>
      <p>A smaller reasoning model.</p>
    </article>
    """

    articles = parse_html_index(document, source)

    assert len(articles) == 1
    assert articles[0].published_at == datetime(2026, 9, 30, tzinfo=UTC)
    assert articles[0].summary == "A smaller reasoning model."


def test_enriches_article_from_page_metadata() -> None:
    article = ParsedArticle(
        source_id="example-ai",
        company="Example AI",
        title="",
        url="https://example.com/news/model-four",
    )
    document = """
    <html><head>
      <meta property="og:title" content="Model Four" />
      <meta name="description" content="A useful release." />
      <meta property="article:published_time" content="2026-09-29T16:00:00Z" />
    </head><body><nav>Navigation</nav><article>Detailed release notes.</article></body></html>
    """

    enriched = enrich_from_article_page(article, document, make_source("html"))

    assert enriched.title == "Model Four"
    assert enriched.summary == "A useful release."
    assert enriched.content == "Detailed release notes."


def test_rejects_xml_entities() -> None:
    document = """<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <rss><channel><item><title>&xxe;</title></item></channel></rss>"""

    with pytest.raises(SourceParseError, match="unsafe XML"):
        parse_feed(document, make_source("rss"))
