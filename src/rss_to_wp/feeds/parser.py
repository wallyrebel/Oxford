"""RSS feed parsing."""

from __future__ import annotations

from typing import Any, Optional

import feedparser
import pendulum
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from rss_to_wp.utils import get_logger

logger = get_logger("feeds.parser")

UNIVERSITY_NEWS = "https://olemiss.edu/news/"


def university_page(url):
    response = requests.get(url, timeout=(5, 15), allow_redirects=False,
                            headers={"User-Agent": "OxfordMSNews/1.0 (+https://oxfordmsnews.com/)"})
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError("University newsroom did not return the requested page")
    return BeautifulSoup(response.content, "html.parser")


def university_news():
    listing = university_page(UNIVERSITY_NEWS)
    urls = dict.fromkeys(urljoin(UNIVERSITY_NEWS, a["href"]) for a in listing.select("main a[href]"))
    releases = [u for u in urls if re.fullmatch(r"https://olemiss\.edu/news/\d{4}/\d{2}/[a-z0-9-]+/index\.html", u)]
    if not releases:
        raise ValueError("University newsroom listing has no release links")
    entries = []
    for url in releases[:6]:
        page = university_page(url)
        title = page.select_one("main h1")
        label = next((n for n in page.select("main h2.small-text")
                      if n.get_text(strip=True) == "Published"), None)
        date = label.find_next_sibling() if label else None
        body = page.select_one("main section.news-content .wysiwyg")
        if not title or not date or not body:
            raise ValueError("University release lacks a title, publication date or body")
        stamp = pendulum.from_format(date.get_text(strip=True), "MMMM D, YYYY", tz="America/Chicago")
        for node in body.select("figure, aside, script, style"):
            node.decompose()
        paragraphs = [node.get_text(" ", strip=True) for node in body.select("p, li")]
        entries.append(feedparser.FeedParserDict(title=title.get_text(" ", strip=True),
                       link=url, published=stamp.isoformat(), summary="\n\n".join(paragraphs)))
    return feedparser.FeedParserDict(bozo=False, entries=entries, feed={"title": "University of Mississippi News"})

def parse_feed(url: str) -> Optional[dict[str, Any]]:
    """Parse an RSS/Atom feed from URL.

    Args:
        url: URL of the RSS feed.

    Returns:
        Parsed feed dictionary or None if parsing failed.
    """
    logger.info("parsing_feed", url=url)

    try:
        feed = university_news() if url == UNIVERSITY_NEWS else feedparser.parse(url)

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
