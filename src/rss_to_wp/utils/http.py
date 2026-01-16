"""HTTP utilities with retry logic and timeouts."""

from __future__ import annotations

from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.util.retry import Retry


def create_http_session(
    timeout: tuple[int, int] = (10, 30),
    max_retries: int = 3,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """Create a configured requests session with retry logic.

    Args:
        timeout: Tuple of (connect_timeout, read_timeout) in seconds.
        max_retries: Maximum number of retries for failed requests.
        backoff_factor: Multiplier for exponential backoff between retries.

    Returns:
        Configured requests.Session object.
    """
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set default headers
    session.headers.update({
        "User-Agent": "RSS-to-WP-Bot/1.0 (https://github.com/tippahnews)",
        "Accept": "application/json, text/html, application/xml, */*",
    })

    # Store timeout for later use
    session.timeout = timeout  # type: ignore

    return session


def get_with_timeout(
    session: requests.Session,
    url: str,
    **kwargs,
) -> requests.Response:
    """Make a GET request with configured timeout.

    Args:
        session: Configured requests session.
        url: URL to fetch.
        **kwargs: Additional arguments to pass to session.get().

    Returns:
        Response object.

    Raises:
        requests.RequestException: If request fails after retries.
    """
    timeout = kwargs.pop("timeout", getattr(session, "timeout", (10, 30)))
    return session.get(url, timeout=timeout, **kwargs)


def post_with_timeout(
    session: requests.Session,
    url: str,
    **kwargs,
) -> requests.Response:
    """Make a POST request with configured timeout.

    Args:
        session: Configured requests session.
        url: URL to post to.
        **kwargs: Additional arguments to pass to session.post().

    Returns:
        Response object.

    Raises:
        requests.RequestException: If request fails after retries.
    """
    timeout = kwargs.pop("timeout", getattr(session, "timeout", (10, 30)))
    return session.post(url, timeout=timeout, **kwargs)


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def fetch_url_content(url: str, timeout: tuple[int, int] = (10, 30)) -> bytes:
    """Fetch URL content with retry logic.

    Args:
        url: URL to fetch.
        timeout: Tuple of (connect_timeout, read_timeout).

    Returns:
        Response content as bytes.

    Raises:
        requests.RequestException: If all retries fail.
    """
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "RSS-to-WP-Bot/1.0"},
    )
    response.raise_for_status()
    return response.content
