"""Tests for business_context — mocks Firecrawl to avoid network dependency."""

from unittest.mock import MagicMock, patch

import pytest


def _mock_app(markdown: str = "", search_items: list | None = None):
    """Build a mock V1FirecrawlApp."""
    scrape_result = MagicMock()
    scrape_result.markdown = markdown

    search_result = MagicMock()
    search_result.data = search_items or []

    app = MagicMock()
    app.scrape_url = MagicMock(return_value=scrape_result)
    app.search = MagicMock(return_value=search_result)
    return app


@pytest.mark.asyncio
async def test_get_business_context_with_website():
    """Scrapes provided website URL and returns truncated markdown."""
    import os
    os.environ.setdefault("FIRECRAWL_API_KEY", "dummy")

    app = _mock_app(markdown="# ACME Hotel\nOpen 24/7. " * 100)

    with patch("business_context.V1FirecrawlApp", return_value=app):
        from business_context import get_business_context
        result = await get_business_context("+15551234567", website="https://acmehotel.com")

    assert "ACME Hotel" in result
    assert len(result) <= 6100  # _MAX_CHARS + truncation suffix


@pytest.mark.asyncio
async def test_get_business_context_empty_scrape_returns_empty():
    """Scrape returning no markdown returns empty string."""
    import os
    os.environ.setdefault("FIRECRAWL_API_KEY", "dummy")

    app = _mock_app(markdown="")

    with patch("business_context.V1FirecrawlApp", return_value=app):
        from business_context import get_business_context
        result = await get_business_context("+15551234567", website="https://example.com")

    assert result == ""


@pytest.mark.asyncio
async def test_get_business_context_search_skips_directories():
    """Phone number search skips Yelp/yellowpages and scrapes the business site."""
    import os
    os.environ.setdefault("FIRECRAWL_API_KEY", "dummy")

    yelp_item = MagicMock()
    yelp_item.url = "https://yelp.com/biz/acme"
    yelp_item.title = "Acme on Yelp"
    yelp_item.description = "Reviews"

    business_item = MagicMock()
    business_item.url = "https://acmehotel.com"
    business_item.title = "ACME Hotel"
    business_item.description = "Official site"

    app = _mock_app(markdown="# ACME Hotel content", search_items=[yelp_item, business_item])

    with patch("business_context.V1FirecrawlApp", return_value=app):
        from business_context import get_business_context
        result = await get_business_context("+15551234567")

    # Should have scraped acmehotel.com (not yelp)
    assert app.scrape_url.call_count == 1
    scraped_url = app.scrape_url.call_args[0][0]
    assert "acmehotel.com" in scraped_url
    assert "ACME Hotel" in result
