"""SQLite-based deduplication storage."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from rss_to_wp.config import get_data_dir
from rss_to_wp.utils import get_logger

logger = get_logger("storage.dedupe")


class DedupeStore:
    """SQLite-based store for tracking processed entries."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the deduplication store.

        Args:
            db_path: Path to SQLite database. Defaults to data/processed.db
        """
        if db_path is None:
            db_path = get_data_dir() / "processed.db"

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_key TEXT UNIQUE NOT NULL,
                    feed_url TEXT,
                    entry_title TEXT,
                    entry_link TEXT,
                    wp_post_id INTEGER,
                    wp_post_url TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entry_key
                ON processed_entries(entry_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feed_url
                ON processed_entries(feed_url)
            """)
            conn.commit()

        logger.debug("database_initialized", path=str(self.db_path))

    @contextmanager
    def _get_connection(self):
        """Get a database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def is_processed(self, entry_key: str) -> bool:
        """Check if an entry has already been processed.

        Args:
            entry_key: Unique key for the entry.

        Returns:
            True if entry was already processed.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_entries WHERE entry_key = ?",
                (entry_key,),
            )
            result = cursor.fetchone() is not None

        if result:
            logger.debug("entry_already_processed", key=entry_key)

        return result

    def mark_processed(
        self,
        entry_key: str,
        feed_url: str,
        entry_title: str,
        entry_link: str,
        wp_post_id: Optional[int] = None,
        wp_post_url: Optional[str] = None,
    ) -> None:
        """Mark an entry as processed.

        Args:
            entry_key: Unique key for the entry.
            feed_url: URL of the source feed.
            entry_title: Title of the entry.
            entry_link: Original link of the entry.
            wp_post_id: WordPress post ID (if published).
            wp_post_url: WordPress post URL (if published).
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_entries
                (entry_key, feed_url, entry_title, entry_link, wp_post_id, wp_post_url, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_key,
                    feed_url,
                    entry_title,
                    entry_link,
                    wp_post_id,
                    wp_post_url,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

        logger.info(
            "entry_marked_processed",
            key=entry_key,
            wp_post_id=wp_post_id,
        )

    def get_processed_count(self, feed_url: Optional[str] = None) -> int:
        """Get count of processed entries.

        Args:
            feed_url: Optional filter by feed URL.

        Returns:
            Number of processed entries.
        """
        with self._get_connection() as conn:
            if feed_url:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM processed_entries WHERE feed_url = ?",
                    (feed_url,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM processed_entries")

            return cursor.fetchone()[0]

    def get_recent_entries(
        self,
        limit: int = 100,
        feed_url: Optional[str] = None,
    ) -> list[dict]:
        """Get recently processed entries.

        Args:
            limit: Maximum entries to return.
            feed_url: Optional filter by feed URL.

        Returns:
            List of entry dictionaries.
        """
        with self._get_connection() as conn:
            if feed_url:
                cursor = conn.execute(
                    """
                    SELECT * FROM processed_entries
                    WHERE feed_url = ?
                    ORDER BY processed_at DESC
                    LIMIT ?
                    """,
                    (feed_url, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM processed_entries
                    ORDER BY processed_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            return [dict(row) for row in cursor.fetchall()]

    def clear_all(self) -> int:
        """Clear all processed entries.

        Returns:
            Number of entries deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM processed_entries")
            count = cursor.rowcount
            conn.commit()

        logger.warning("database_cleared", deleted_count=count)
        return count
