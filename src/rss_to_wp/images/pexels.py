"""Pexels API client for fallback images."""

from __future__ import annotations

import time
from typing import Optional

import requests

from rss_to_wp.utils import get_logger

logger = get_logger("images.pexels")


class PexelsClient:
    """Client for Pexels image search API."""

    BASE_URL = "https://api.pexels.com/v1"

    def __init__(self, api_key: str):
        """Initialize Pexels client.

        Args:
            api_key: Pexels API key.
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key,
        })
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Ensure we don't exceed rate limits."""
        min_interval = 0.5  # 2 requests per second max
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
        """Search for images on Pexels.

        Args:
            query: Search query string.
            per_page: Number of results to fetch.
            orientation: Image orientation (landscape, portrait, square).

        Returns:
            Dictionary with image URL and attribution, or None.
        """
        self._rate_limit()

        # Clean up query - remove special characters
        clean_query = " ".join(query.split()[:5])  # Max 5 words

        logger.info("pexels_search", query=clean_query)

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params={
                    "query": clean_query,
                    "per_page": per_page,
                    "orientation": orientation,
                },
                timeout=(10, 30),
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("photos"):
                logger.info("pexels_no_results", query=clean_query)
                return None

            # Get first photo
            photo = data["photos"][0]

            # Get best size - prefer large
            image_url = photo["src"].get("large") or photo["src"].get("medium")
            photographer = photo.get("photographer", "Unknown")

            result = {
                "url": image_url,
                "photographer": photographer,
                "source": "Pexels",
                "alt_text": f"Photo by {photographer} on Pexels",
                "photo_id": photo.get("id"),
                "photographer_url": photo.get("photographer_url", ""),
            }

            logger.info(
                "pexels_image_found",
                url=image_url,
                photographer=photographer,
            )

            return result

        except requests.exceptions.HTTPError as e:
            logger.error("pexels_http_error", error=str(e), status=e.response.status_code)
            return None
        except requests.exceptions.RequestException as e:
            logger.error("pexels_request_error", error=str(e))
            return None
        except Exception as e:
            logger.error("pexels_error", error=str(e))
            return None

    def get_curated(self, per_page: int = 5) -> Optional[dict]:
        """Get curated photos as a fallback.

        Args:
            per_page: Number of results to fetch.

        Returns:
            Dictionary with image URL and attribution, or None.
        """
        self._rate_limit()

        logger.info("pexels_curated_search")

        try:
            response = self.session.get(
                f"{self.BASE_URL}/curated",
                params={"per_page": per_page},
                timeout=(10, 30),
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("photos"):
                return None

            # Get first photo
            photo = data["photos"][0]
            image_url = photo["src"].get("large") or photo["src"].get("medium")
            photographer = photo.get("photographer", "Unknown")

            return {
                "url": image_url,
                "photographer": photographer,
                "source": "Pexels",
                "alt_text": f"Photo by {photographer} on Pexels",
            }

        except Exception as e:
            logger.error("pexels_curated_error", error=str(e))
            return None
