"""Discovers and scrapes business context from a phone number using Firecrawl."""

import asyncio
import os

from firecrawl import V1FirecrawlApp
from loguru import logger

_MAX_CHARS = 6000


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS] + "\n\n[content truncated]"


def _make_client() -> V1FirecrawlApp:
    return V1FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])


def _scrape(url: str) -> str:
    """Synchronous scrape — call via asyncio.to_thread."""
    fc = _make_client()
    result = fc.scrape_url(url, formats=["markdown"])
    return getattr(result, "markdown", "") or ""


def _search(query: str, limit: int = 5) -> list[dict]:
    """Synchronous search — call via asyncio.to_thread."""
    fc = _make_client()
    result = fc.search(query, limit=limit)
    data = getattr(result, "data", []) or []
    return [
        {
            "url": getattr(item, "url", ""),
            "title": getattr(item, "title", ""),
            "description": getattr(item, "description", ""),
        }
        for item in data
    ]


async def get_business_context(phone_number: str, website: str | None = None) -> str:
    """Return a markdown summary of the business at the given phone number.

    If `website` is provided it is scraped directly.
    Otherwise Firecrawl searches for the phone number to find the site first.
    """
    if website:
        logger.info(f"Scraping provided website: {website}")
        try:
            markdown = await asyncio.to_thread(_scrape, website)
            if markdown:
                logger.info(f"Scraped {len(markdown)} chars from {website}")
                return _truncate(markdown)
            logger.warning(f"Scrape returned no markdown for {website}")
        except Exception as e:
            logger.error(f"Scrape failed for {website}: {e}")
        return ""

    # Search by phone number to find the business website
    query = f'"{phone_number}"'
    logger.info(f"Searching Firecrawl for business: {query}")

    try:
        items = await asyncio.to_thread(_search, query, 5)
    except Exception as e:
        logger.error(f"Firecrawl search failed: {e}")
        return ""

    if not items:
        logger.warning(f"No search results for {phone_number}")
        return ""

    # Try scraping results until we get meaningful content
    skip_domains = ("yelp.com", "yellowpages.com", "whitepages.com", "facebook.com", "tripadvisor.com")
    for item in items:
        url = item.get("url", "")
        if not url or any(d in url for d in skip_domains):
            continue

        logger.info(f"Scraping business site: {url}")
        try:
            markdown = await asyncio.to_thread(_scrape, url)
            if markdown and len(markdown) > 200:
                logger.info(f"Got {len(markdown)} chars from {url}")
                return _truncate(markdown)
        except Exception as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    # Fallback: use search snippet text
    snippets = "\n\n".join(
        f"**{item.get('title', '')}** ({item.get('url', '')})\n{item.get('description', '')}"
        for item in items[:3]
        if item.get("description")
    )
    if snippets:
        logger.info("Using search snippets as fallback context")
        return snippets

    return ""
