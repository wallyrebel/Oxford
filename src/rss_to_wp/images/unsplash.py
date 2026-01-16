"""Unsplash API client for fallback images."""

from __future__ import annotations

import time
from typing import Optional

import requests

from rss_to_wp.utils import get_logger

logger = get_logger("images.unsplash")


class UnsplashClient:
    """Client for Unsplash image search API."""

    BASE_URL = "https://api.unsplash.com"

    def __init__(self, access_key: str):
        """Initialize Unsplash client.

        Args:
            access_key: Unsplash access key.
        """
        self.access_key = access_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
        })
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Ensure we don't exceed rate limits (50/hour for free tier)."""
        min_interval = 1.0  # 1 request per second max
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def search(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "landscape",
    ) -> Optional[dict]:
        """Search for images on Unsplash.

        Args:
            query: Search query string.
            per_page: Number of results to fetch.
            orientation: Image orientation (landscape, portrait, squarish).

        Returns:
            Dictionary with image URL and attribution, or None.
        """
        self._rate_limit()

        # Clean up query - remove special characters
        clean_query = " ".join(query.split()[:5])  # Max 5 words

        logger.info("unsplash_search", query=clean_query)

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search/photos",
                params={
                    "query": clean_query,
                    "per_page": per_page,
                    "orientation": orientation,
                },
                timeout=(10, 30),
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("results"):
                logger.info("unsplash_no_results", query=clean_query)
                return None

            # Get first photo
            photo = data["results"][0]

            # Get regular size (1080px width)
            image_url = photo["urls"].get("regular") or photo["urls"].get("small")
            photographer = photo.get("user", {}).get("name", "Unknown")
            photographer_username = photo.get("user", {}).get("username", "")

            # Unsplash requires attribution with link
            result = {
                "url": image_url,
                "photographer": photographer,
                "source": "Unsplash",
                "alt_text": f"Photo by {photographer} on Unsplash",
                "photo_id": photo.get("id"),
                "photographer_url": f"https://unsplash.com/@{photographer_username}",
                "download_location": photo.get("links", {}).get("download_location"),
            }

            logger.info(
                "unsplash_image_found",
                url=image_url,
                photographer=photographer,
            )

            # Trigger download tracking (required by Unsplash API guidelines)
            self._track_download(photo)

            return result

        except requests.exceptions.HTTPError as e:
            logger.error("unsplash_http_error", error=str(e), status=e.response.status_code)
            return None
        except requests.exceptions.RequestException as e:
            logger.error("unsplash_request_error", error=str(e))
            return None
        except Exception as e:
            logger.error("unsplash_error", error=str(e))
            return None

    def _track_download(self, photo: dict) -> None:
        """Track download as required by Unsplash API.

        Args:
            photo: Photo data from search results.
        """
        download_url = photo.get("links", {}).get("download_location")
        if not download_url:
            return

        try:
            # This doesn't actually download, just tracks
            self.session.get(download_url, timeout=(5, 10))
        except Exception:
            pass  # Best effort, don't fail on tracking errors

    def get_random(self, query: Optional[str] = None) -> Optional[dict]:
        """Get a random photo.

        Args:
            query: Optional query to filter random photos.

        Returns:
            Dictionary with image URL and attribution, or None.
        """
        self._rate_limit()

        logger.info("unsplash_random_search", query=query)

        try:
            params = {}
            if query:
                params["query"] = query

            response = self.session.get(
                f"{self.BASE_URL}/photos/random",
                params=params,
                timeout=(10, 30),
            )
            response.raise_for_status()
            photo = response.json()

            image_url = photo["urls"].get("regular") or photo["urls"].get("small")
            photographer = photo.get("user", {}).get("name", "Unknown")

            return {
                "url": image_url,
                "photographer": photographer,
                "source": "Unsplash",
                "alt_text": f"Photo by {photographer} on Unsplash",
            }

        except Exception as e:
            logger.error("unsplash_random_error", error=str(e))
            return None
