"""WordPress media upload functionality."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

import requests

from rss_to_wp.utils import get_logger

logger = get_logger("wordpress.media")


def wp_upload_media(
    image_bytes: bytes,
    filename: str,
    alt_text: str,
    base_url: str,
    username: str,
    password: str,
    session: Optional[requests.Session] = None,
) -> Optional[int]:
    """Upload an image to WordPress Media Library.

    Args:
        image_bytes: Image content as bytes.
        filename: Filename for the upload.
        alt_text: Alt text for the image.
        base_url: WordPress base URL.
        username: WordPress username.
        password: WordPress application password.
        session: Optional requests session.

    Returns:
        Media ID or None on failure.
    """
    if session is None:
        session = requests.Session()

    url = f"{base_url}/wp-json/wp/v2/media"

    # Determine content type
    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        content_type = "image/jpeg"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
    }

    logger.info("uploading_media", filename=filename, size_bytes=len(image_bytes))

    try:
        response = session.post(
            url,
            data=image_bytes,
            headers=headers,
            auth=(username, password),
            timeout=(10, 60),
        )
        response.raise_for_status()

        media_data = response.json()
        media_id = media_data.get("id")

        if not media_id:
            logger.error("media_upload_no_id", response=media_data)
            return None

        logger.info("media_uploaded", media_id=media_id, filename=filename)

        # Update alt text if provided
        if alt_text:
            _update_media_alt(media_id, alt_text, base_url, username, password, session)

        return media_id

    except requests.exceptions.HTTPError as e:
        logger.error(
            "media_upload_http_error",
            error=str(e),
            status=e.response.status_code,
            response=e.response.text[:500],
        )
        return None
    except requests.exceptions.RequestException as e:
        logger.error("media_upload_error", error=str(e))
        return None


def _update_media_alt(
    media_id: int,
    alt_text: str,
    base_url: str,
    username: str,
    password: str,
    session: requests.Session,
) -> None:
    """Update the alt text for a media item.

    Args:
        media_id: WordPress media ID.
        alt_text: Alt text to set.
        base_url: WordPress base URL.
        username: WordPress username.
        password: WordPress application password.
        session: Requests session.
    """
    url = f"{base_url}/wp-json/wp/v2/media/{media_id}"

    try:
        response = session.post(
            url,
            json={"alt_text": alt_text},
            auth=(username, password),
            timeout=(10, 30),
        )
        response.raise_for_status()
        logger.debug("media_alt_updated", media_id=media_id)

    except Exception as e:
        # Don't fail on alt text update error
        logger.warning("media_alt_update_error", media_id=media_id, error=str(e))
