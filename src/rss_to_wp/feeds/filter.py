"""RSS entry filtering by date and count."""

from __future__ import annotations

import hashlib
from datetime import datetime
from time import mktime, struct_time
from typing import Any, Optional

import pendulum

from rss_to_wp.utils import get_logger

logger = get_logger("feeds.filter")


def parse_entry_date(entry: dict[str, Any]) -> Optional[datetime]:
    """Parse the publication date from an RSS entry.

    Tries multiple date fields in order of preference.

    Args:
        entry: RSS entry dictionary.

    Returns:
        Datetime object or None if no date found.
    """
    date_fields = [
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ]

    for field in date_fields:
        if field in entry and entry[field]:
            try:
                time_struct: struct_time = entry[field]
                timestamp = mktime(time_struct)
                return datetime.fromtimestamp(timestamp, tz=pendulum.UTC)
            except (TypeError, ValueError, OverflowError):
                continue

    # Try string date fields
    string_fields = ["published", "updated", "created"]
    for field in string_fields:
        if field in entry and entry[field]:
            try:
                return pendulum.parse(entry[field])
            except Exception:
                continue

    return None


def is_within_window(
    entry_date: datetime,
    hours: int = 48,
    timezone: str = "UTC",
) -> bool:
    """Check if entry date is within the time window.

    Args:
        entry_date: Entry publication date.
        hours: Number of hours for the window (default 48).
        timezone: Timezone for calculations.

    Returns:
        True if entry is within the window.
    """
    tz = pendulum.timezone(timezone)
    now = pendulum.now(tz)
    cutoff = now.subtract(hours=hours)

    # Convert entry_date to pendulum for comparison
    entry_pendulum = pendulum.instance(entry_date)

    return entry_pendulum >= cutoff


def pick_entries(
    entries: list[dict[str, Any]],
    max_count: int = 5,
    hours_window: int = 48,
    timezone: str = "UTC",
) -> list[dict[str, Any]]:
    """Filter and sort entries by date, returning newest first.

    Strict 48-hour enforcement: entries outside window are skipped.

    Args:
        entries: List of RSS entry dictionaries.
        max_count: Maximum entries to return.
        hours_window: Time window in hours (strictly enforced).
        timezone: Timezone for date calculations.

    Returns:
        List of filtered entries, newest first.
    """
    valid_entries: list[tuple[datetime, dict[str, Any]]] = []

    for entry in entries:
        # Get entry link for logging
        link = entry.get("link", "unknown")

        # Parse date
        entry_date = parse_entry_date(entry)
        if entry_date is None:
            logger.debug("skipping_no_date", link=link)
            continue

        # Check if within window (strict enforcement)
        if not is_within_window(entry_date, hours_window, timezone):
            logger.debug(
                "skipping_outside_window",
                link=link,
                entry_date=str(entry_date),
                hours_window=hours_window,
            )
            continue

        # Validate has link
        if not entry.get("link"):
            logger.debug("skipping_no_link", title=entry.get("title", "unknown"))
            continue

        valid_entries.append((entry_date, entry))

    # Sort by date descending (newest first)
    valid_entries.sort(key=lambda x: x[0], reverse=True)

    # Take top N
    result = [entry for _, entry in valid_entries[:max_count]]

    logger.info(
        "entries_filtered",
        total=len(entries),
        valid=len(valid_entries),
        selected=len(result),
    )

    return result


def generate_entry_key(entry: dict[str, Any], feed_url: str) -> str:
    """Generate a unique key for deduplication.

    Priority:
    1. entry.id / guid
    2. entry.link
    3. hash of (title + date + feed_url)

    Args:
        entry: RSS entry dictionary.
        feed_url: URL of the source feed.

    Returns:
        Unique string key for the entry.
    """
    # Try guid/id first
    if "id" in entry and entry["id"]:
        return f"id:{entry['id']}"

    if "guid" in entry and entry["guid"]:
        return f"guid:{entry['guid']}"

    # Try link
    if "link" in entry and entry["link"]:
        return f"link:{entry['link']}"

    # Fall back to hash
    title = entry.get("title", "")
    date_str = ""
    entry_date = parse_entry_date(entry)
    if entry_date:
        date_str = entry_date.isoformat()

    hash_input = f"{title}|{date_str}|{feed_url}"
    hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    return f"hash:{hash_value}"
