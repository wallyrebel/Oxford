"""Image download and fallback orchestration."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

import requests
from PIL import Image

from rss_to_wp.images.pexels import PexelsClient
from rss_to_wp.images.unsplash import UnsplashClient
from rss_to_wp.utils import get_logger

logger = get_logger("images.downloader")


def download_image(
    url: str,
    max_size_mb: float = 5.0,
    timeout: tuple[int, int] = (10, 30),
) -> Optional[tuple[bytes, str, str]]:
    """Download an image from URL.

    Args:
        url: Image URL to download.
        max_size_mb: Maximum file size in MB.
        timeout: Request timeout (connect, read).

    Returns:
        Tuple of (image_bytes, filename, content_type) or None on failure.
    """
    logger.info("downloading_image", url=url)

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "RSS-to-WP-Bot/1.0"},
            stream=True,
        )
        response.raise_for_status()

        # Check content length
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_size_mb * 1024 * 1024:
            logger.warning("image_too_large", url=url, size_mb=int(content_length) / (1024 * 1024))
            return None

        # Read content
        content = response.content

        # Validate it's actually an image
        try:
            img = Image.open(BytesIO(content))
            img.verify()
        except Exception as e:
            logger.warning("invalid_image", url=url, error=str(e))
            return None

        # Determine filename and type
        content_type = response.headers.get("Content-Type", "image/jpeg")
        filename = _extract_filename(url, content_type)

        logger.info(
            "image_downloaded",
            url=url,
            size_bytes=len(content),
            content_type=content_type,
        )

        return (content, filename, content_type)

    except requests.exceptions.RequestException as e:
        logger.error("image_download_error", url=url, error=str(e))
        return None
    except Exception as e:
        logger.error("image_download_error", url=url, error=str(e))
        return None


def _extract_filename(url: str, content_type: str) -> str:
    """Extract or generate a filename from URL or content type.

    Args:
        url: Image URL.
        content_type: Content-Type header.

    Returns:
        Filename string.
    """
    # Try to get from URL path
    parsed = urlparse(url)
    path = parsed.path

    # Get the last path component
    if path:
        filename = path.split("/")[-1]
        # Clean up query strings etc
        filename = filename.split("?")[0]
        if filename and "." in filename:
            return filename

    # Generate based on content type
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    ext = ext_map.get(content_type, ".jpg")

    return f"featured-image{ext}"


def extract_keywords(text: str, max_words: int = 5) -> str:
    """Extract keywords from text for image search.

    Args:
        text: Source text (title, feed name, etc.).
        max_words: Maximum number of keywords.

    Returns:
        Cleaned keyword string.
    """
    # Remove common stop words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "be", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "shall", "can", "need",
        "this", "that", "these", "those", "it", "its", "their", "our", "your",
        "new", "announces", "released", "says", "reports", "today", "week",
    }

    # Clean text
    text = re.sub(r"[^\w\s]", " ", text.lower())
    words = text.split()

    # Filter stop words and short words
    keywords = [w for w in words if w not in stop_words and len(w) > 2]

    # Return top N unique words
    seen = set()
    unique_keywords = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique_keywords.append(w)
        if len(unique_keywords) >= max_words:
            break

    return " ".join(unique_keywords)


def find_fallback_image(
    title: str,
    feed_name: str,
    pexels_key: Optional[str] = None,
    unsplash_key: Optional[str] = None,
) -> Optional[dict]:
    """Find a fallback image from stock photo providers.

    Tries Pexels first, then Unsplash.

    Args:
        title: Article title for keyword extraction.
        feed_name: Feed name for additional context.
        pexels_key: Pexels API key (optional).
        unsplash_key: Unsplash access key (optional).

    Returns:
        Dictionary with url, photographer, source, alt_text, or None.
    """
    if not pexels_key and not unsplash_key:
        logger.warning("no_fallback_providers_configured")
        return None

    # Build search query from title and feed name
    query = extract_keywords(f"{title} {feed_name}")

    if not query:
        query = "news"  # Fallback to generic news

    logger.info("fallback_image_search", query=query)

    # Try Pexels first (more generous rate limit)
    if pexels_key:
        try:
            pexels = PexelsClient(pexels_key)
            result = pexels.search(query)
            if result:
                return result
        except Exception as e:
            logger.warning("pexels_fallback_error", error=str(e))

    # Try Unsplash
    if unsplash_key:
        try:
            unsplash = UnsplashClient(unsplash_key)
            result = unsplash.search(query)
            if result:
                return result
        except Exception as e:
            logger.warning("unsplash_fallback_error", error=str(e))

    logger.warning("no_fallback_image_found", query=query)
    return None
