"""RSS feed parsing."""

from __future__ import annotations

from typing import Any, Optional

import feedparser

from rss_to_wp.utils import get_logger

logger = get_logger("feeds.parser")


def parse_feed(url: str) -> Optional[dict[str, Any]]:
    """Parse an RSS/Atom feed from URL.

    Args:
        url: URL of the RSS feed.

    Returns:
        Parsed feed dictionary or None if parsing failed.
    """
    logger.info("parsing_feed", url=url)

    try:
        feed = feedparser.parse(url)

        # Check for parsing errors
        if feed.bozo and feed.bozo_exception:
            logger.warning(
                "feed_parse_warning",
                url=url,
                error=str(feed.bozo_exception),
            )
            # Continue anyway - feedparser often recovers

        if not feed.entries:
            logger.info("feed_empty", url=url)
            return feed

        logger.info(
            "feed_parsed",
            url=url,
            entry_count=len(feed.entries),
            feed_title=feed.feed.get("title", "Unknown"),
        )

        return feed

    except Exception as e:
        logger.error("feed_parse_error", url=url, error=str(e))
        return None


def get_entry_content(entry: dict[str, Any]) -> str:
    """Extract the best available content from an RSS entry.

    Prefers full content over summary.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Content string (may be HTML).
    """
    # Try content first (usually full article)
    if "content" in entry and entry["content"]:
        # content is usually a list
        contents = entry["content"]
        if isinstance(contents, list) and len(contents) > 0:
            return contents[0].get("value", "")

    # Fall back to summary
    if "summary" in entry:
        return entry.get("summary", "")

    # Last resort: description
    return entry.get("description", "")


def get_entry_link(entry: dict[str, Any]) -> Optional[str]:
    """Get the link URL from an RSS entry.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Link URL or None.
    """
    # Direct link attribute
    if "link" in entry and entry["link"]:
        return entry["link"]

    # Links list
    if "links" in entry and entry["links"]:
        for link in entry["links"]:
            if link.get("rel") == "alternate" or link.get("type") == "text/html":
                return link.get("href")
        # Return first link as fallback
        return entry["links"][0].get("href")

    return None


def get_entry_title(entry: dict[str, Any]) -> str:
    """Get the title from an RSS entry.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Title string.
    """
    return entry.get("title", "Untitled")
