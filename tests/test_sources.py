from pathlib import Path

import pytest

from ai_model_briefing.sources import SourceConfigurationError, load_source_catalog


def write_catalog(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_valid_catalog(tmp_path: Path) -> None:
    catalog_path = write_catalog(
        tmp_path / "sources.yaml",
        """
version: 1
sources:
  - id: example-ai
    company: Example AI
    type: rss
    url: https://example.com/news.xml
    include_paths: [/news/]
""",
    )

    catalog = load_source_catalog(catalog_path)

    assert catalog.version == 1
    assert catalog.sources[0].id == "example-ai"
    assert catalog.sources[0].max_items == 10


@pytest.mark.parametrize(
    "content",
    [
        """
version: 1
sources:
  - {id: duplicate, company: First, type: rss, url: https://example.com/one.xml}
  - {id: duplicate, company: Second, type: rss, url: https://example.com/two.xml}
""",
        """
version: 1
sources:
  - {id: insecure, company: Insecure, type: rss, url: http://example.com/feed.xml}
""",
        """
version: 1
sources:
  - id: traversal
    company: Traversal
    type: sitemap
    url: https://example.com/sitemap.xml
    include_paths: [/news/../private/]
""",
    ],
)
def test_rejects_unsafe_or_ambiguous_catalogs(tmp_path: Path, content: str) -> None:
    catalog_path = write_catalog(tmp_path / "sources.yaml", content)

    with pytest.raises(SourceConfigurationError):
        load_source_catalog(catalog_path)


def test_rejects_oversized_catalog(tmp_path: Path) -> None:
    catalog_path = write_catalog(tmp_path / "sources.yaml", "x" * 65_537)

    with pytest.raises(SourceConfigurationError, match="exceeds"):
        load_source_catalog(catalog_path)
