"""Discovers and scrapes business context from a phone number using Firecrawl."""

import os

from firecrawl import AsyncFirecrawl
from loguru import logger

# Cap content sent to the LLM — enough to understand the business, not the whole site
_MAX_CHARS = 6000


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS] + "\n\n[content truncated]"


async def get_business_context(phone_number: str, website: str | None = None) -> str:
    """Return a markdown summary of the business at the given phone number.

    If `website` is provided it is scraped directly.
    Otherwise Firecrawl searches for the phone number to find the site first.
    """
    fc = AsyncFirecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])

    if website:
        logger.info(f"Scraping provided website: {website}")
        result = await fc.scrape_url(website, params={"formats": ["markdown"]})
        markdown = result.get("markdown", "")
        if markdown:
            return _truncate(markdown)
        logger.warning(f"Scrape returned no markdown for {website}")
        return ""

    # Search by phone number to find the business website
    query = f'"{phone_number}"'
    logger.info(f"Searching Firecrawl for business: {query}")

    search_result = await fc.search(query, params={"limit": 5})
    items = search_result.get("data", [])

    if not items:
        logger.warning(f"No search results for {phone_number}")
        return ""

    # Try scraping results until we get meaningful content
    for item in items:
        url = item.get("url", "")
        if not url:
            continue

        # Skip aggregators / directories — prefer the business's own site
        skip_domains = ("yelp.com", "yellowpages.com", "whitepages.com", "facebook.com", "tripadvisor.com")
        if any(d in url for d in skip_domains):
            logger.debug(f"Skipping directory URL: {url}")
            continue

        logger.info(f"Scraping business site: {url}")
        try:
            scrape = await fc.scrape_url(url, params={"formats": ["markdown"]})
            markdown = scrape.get("markdown", "")
            if markdown and len(markdown) > 200:
                return _truncate(markdown)
        except Exception as e:
            logger.warning(f"Failed to scrape {url}: {e}")
            continue

    # Fall back to search snippet text if no site could be scraped
    snippets = "\n\n".join(
        f"**{item.get('title', '')}** ({item.get('url', '')})\n{item.get('description', '')}"
        for item in items[:3]
        if item.get("description")
    )
    if snippets:
        logger.info("Using search snippets as fallback business context")
        return snippets

    return ""
