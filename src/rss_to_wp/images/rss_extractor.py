"""Extract images from RSS entries."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from rss_to_wp.utils import get_logger

logger = get_logger("images.rss_extractor")

# Valid image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# Valid image MIME types
IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}


def is_valid_image_url(url: str) -> bool:
    """Check if URL appears to be a valid image.

    Args:
        url: URL to validate.

    Returns:
        True if URL looks like an image.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # Check extension
        path_lower = parsed.path.lower()
        for ext in IMAGE_EXTENSIONS:
            if path_lower.endswith(ext):
                return True

        # Some CDN URLs don't have extensions but are still valid
        # Allow URLs from known image CDNs
        known_image_hosts = [
            "pexels.com",
            "unsplash.com",
            "cloudinary.com",
            "imgix.net",
            "wp.com",
            "wordpress.com",
            "flickr.com",
            "staticflickr.com",
        ]
        for host in known_image_hosts:
            if host in parsed.netloc.lower():
                return True

        return False

    except Exception:
        return False


def find_rss_image(entry: dict[str, Any], base_url: str = "") -> Optional[str]:
    """Find an image URL from an RSS entry.

    Checks multiple sources in order of preference:
    1. media:content
    2. media:thumbnail
    3. enclosure with image type
    4. <img> tags in content/summary

    Args:
        entry: RSS entry dictionary from feedparser.
        base_url: Base URL for resolving relative URLs.

    Returns:
        Image URL or None if no image found.
    """
    image_url = None

    # 1. Check media:content (media_content in feedparser)
    if "media_content" in entry and entry["media_content"]:
        for media in entry["media_content"]:
            url = media.get("url", "")
            media_type = media.get("type", "")
            medium = media.get("medium", "")

            # Check if it's an image
            if media_type in IMAGE_MIME_TYPES or medium == "image":
                if is_valid_image_url(url):
                    image_url = url
                    logger.debug("found_media_content_image", url=url)
                    break
            elif is_valid_image_url(url):
                image_url = url
                logger.debug("found_media_content_image", url=url)
                break

    # 2. Check media:thumbnail (media_thumbnail in feedparser)
    if not image_url and "media_thumbnail" in entry and entry["media_thumbnail"]:
        for thumb in entry["media_thumbnail"]:
            url = thumb.get("url", "")
            if is_valid_image_url(url):
                image_url = url
                logger.debug("found_media_thumbnail", url=url)
                break

    # 3. Check enclosures
    if not image_url and "enclosures" in entry and entry["enclosures"]:
        for enclosure in entry["enclosures"]:
            enc_type = enclosure.get("type", "")
            url = enclosure.get("href", "") or enclosure.get("url", "")
            if enc_type in IMAGE_MIME_TYPES or is_valid_image_url(url):
                if url:
                    image_url = url
                    logger.debug("found_enclosure_image", url=url)
                    break

    # 4. Check links for image type
    if not image_url and "links" in entry and entry["links"]:
        for link in entry["links"]:
            if link.get("type", "") in IMAGE_MIME_TYPES:
                url = link.get("href", "")
                if url:
                    image_url = url
                    logger.debug("found_link_image", url=url)
                    break

    # 5. Parse images from content/summary HTML
    if not image_url:
        html_content = ""
        if "content" in entry and entry["content"]:
            html_content = entry["content"][0].get("value", "")
        elif "summary" in entry:
            html_content = entry.get("summary", "")
        elif "description" in entry:
            html_content = entry.get("description", "")

        if html_content:
            image_url = extract_first_image_from_html(html_content, base_url)

    if image_url:
        logger.info("rss_image_found", url=image_url)
    else:
        logger.debug("no_rss_image_found", entry_title=entry.get("title", "unknown"))

    return image_url


def extract_first_image_from_html(html: str, base_url: str = "") -> Optional[str]:
    """Extract the first image URL from HTML content.

    Args:
        html: HTML content string.
        base_url: Base URL for resolving relative URLs.

    Returns:
        Image URL or None.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find all img tags
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src:
                continue

            # Skip common placeholder/tracking patterns
            skip_patterns = [
                "pixel",
                "spacer",
                "blank",
                "1x1",
                "tracking",
                "beacon",
                "analytics",
                "gravatar",
                "avatar",
            ]
            if any(pattern in src.lower() for pattern in skip_patterns):
                continue

            # Resolve relative URLs
            if base_url and not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)

            if is_valid_image_url(src):
                logger.debug("found_html_image", url=src)
                return src

    except Exception as e:
        logger.warning("html_image_extraction_error", error=str(e))

    return None
