"""CLI interface for RSS to WordPress automation."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from rss_to_wp import __version__
from rss_to_wp.config import (
    AppSettings,
    FeedConfig,
    get_app_settings,
    load_feeds_config,
)
from rss_to_wp.feeds import (
    generate_entry_key,
    get_entry_content,
    get_entry_link,
    get_entry_title,
    parse_feed,
    pick_entries,
)
from rss_to_wp.images import download_image, find_fallback_image, find_rss_image
from rss_to_wp.rewriter import OpenAIRewriter
from rss_to_wp.storage import DedupeStore
from rss_to_wp.utils import get_logger, setup_logging, send_email_notification, build_summary_email
from rss_to_wp.wordpress import WordPressClient

# Load environment variables from .env file
load_dotenv()

app = typer.Typer(
    name="rss-to-wp",
    help="Automated RSS feed to WordPress publisher with AI rewriting.",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"rss-to-wp version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """RSS to WordPress automation CLI."""
    pass


@app.command()
def run(
    config: Path = typer.Option(
        Path("feeds.yaml"),
        "--config",
        "-c",
        help="Path to feeds configuration file.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Process feeds without publishing to WordPress.",
    ),
    single_feed: Optional[str] = typer.Option(
        None,
        "--single-feed",
        "-f",
        help="Process only a specific feed by name.",
    ),
    hours: int = typer.Option(
        48,
        "--hours",
        "-h",
        help="Time window in hours for entries (strictly enforced).",
    ),
) -> None:
    """Run the RSS to WordPress automation.

    Fetches RSS feeds, rewrites content, and publishes to WordPress.
    """
    # Load settings
    try:
        settings = get_app_settings()
    except Exception as e:
        typer.echo(f"Error loading settings: {e}", err=True)
        typer.echo("Make sure you have a .env file with required variables.", err=True)
        raise typer.Exit(1)

    # Setup logging
    logger = setup_logging(
        level=settings.log_level,
        log_file=settings.log_file,
    )

    logger.info(
        "starting_rss_to_wp",
        version=__version__,
        dry_run=dry_run,
        config=str(config),
    )

    # Load feeds config
    try:
        feeds_config = load_feeds_config(config)
    except FileNotFoundError:
        logger.error("config_not_found", path=str(config))
        raise typer.Exit(1)
    except Exception as e:
        logger.error("config_load_error", error=str(e))
        raise typer.Exit(1)

    feeds = feeds_config.feeds

    # Filter to single feed if specified
    if single_feed:
        feeds = [f for f in feeds if f.name.lower() == single_feed.lower()]
        if not feeds:
            logger.error("feed_not_found", name=single_feed)
            raise typer.Exit(1)

    logger.info("feeds_loaded", count=len(feeds))

    # Initialize components
    dedupe_store = DedupeStore()
    rewriter = OpenAIRewriter(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    wp_client = None
    if not dry_run:
        wp_client = WordPressClient(
            base_url=settings.wordpress_base_url,
            username=settings.wordpress_username,
            password=settings.wordpress_app_password,
            default_status=settings.wordpress_post_status,
        )

    # Process each feed
    total_processed = 0
    total_skipped = 0
    total_errors = 0
    published_articles: list[dict] = []  # Track for email notification

    for feed_config in feeds:
        try:
            processed, skipped, errors = process_feed(
                feed_config=feed_config,
                settings=settings,
                dedupe_store=dedupe_store,
                rewriter=rewriter,
                wp_client=wp_client,
                dry_run=dry_run,
                hours=hours,
                logger=logger,
                published_articles=published_articles,  # Pass for tracking
            )
            total_processed += processed
            total_skipped += skipped
            total_errors += errors

            # Rate limit between feeds
            time.sleep(1)

        except Exception as e:
            logger.error(
                "feed_processing_error",
                feed=feed_config.name,
                error=str(e),
            )
            total_errors += 1
            continue

    # Summary
    logger.info(
        "run_complete",
        total_processed=total_processed,
        total_skipped=total_skipped,
        total_errors=total_errors,
    )

    # Send email notification ONLY if new articles were published
    if (not dry_run 
        and published_articles  # Only if there are new articles
        and settings.smtp_email 
        and settings.smtp_password 
        and settings.notification_email):
        try:
            subject, html_body = build_summary_email(
                processed_articles=published_articles,
                skipped_count=total_skipped,
                error_count=total_errors,
                site_name="TippahNews",
            )
            send_email_notification(
                smtp_email=settings.smtp_email,
                smtp_password=settings.smtp_password,
                to_email=settings.notification_email,
                subject=subject,
                html_body=html_body,
            )
        except Exception as e:
            logger.error("email_notification_error", error=str(e))

    # Only fail if nothing was processed AND nothing was skipped (complete failure)
    # Partial failures (some articles succeed, some fail) should not cause the run to fail
    if total_errors > 0 and total_processed == 0 and total_skipped == 0:
        raise typer.Exit(1)


def process_feed(
    feed_config: FeedConfig,
    settings: AppSettings,
    dedupe_store: DedupeStore,
    rewriter: OpenAIRewriter,
    wp_client: Optional[WordPressClient],
    dry_run: bool,
    hours: int,
    logger,
    published_articles: Optional[list[dict]] = None,
) -> tuple[int, int, int]:
    """Process a single feed.

    Returns:
        Tuple of (processed_count, skipped_count, error_count)
    """
    logger.info("processing_feed", name=feed_config.name, url=feed_config.url)

    processed = 0
    skipped = 0
    errors = 0

    # Parse feed
    feed = parse_feed(feed_config.url)
    if not feed or not feed.entries:
        logger.warning("feed_empty_or_failed", name=feed_config.name)
        return (0, 0, 1)

    # Filter entries
    entries = pick_entries(
        entries=feed.entries,
        max_count=feed_config.max_per_run,
        hours_window=hours,
        timezone=settings.timezone,
    )

    if not entries:
        logger.info("no_valid_entries", name=feed_config.name)
        return (0, 0, 0)

    logger.info("entries_to_process", name=feed_config.name, count=len(entries))

    for entry in entries:
        try:
            # Generate unique key
            entry_key = generate_entry_key(entry, feed_config.url)

            # Check if already processed
            if dedupe_store.is_processed(entry_key):
                logger.info(
                    "entry_skipped_duplicate",
                    key=entry_key,
                    title=get_entry_title(entry)[:50],
                )
                skipped += 1
                continue

            # Process entry
            result = process_entry(
                entry=entry,
                feed_config=feed_config,
                settings=settings,
                rewriter=rewriter,
                wp_client=wp_client,
                dry_run=dry_run,
                logger=logger,
            )

            if result:
                # Mark as processed
                dedupe_store.mark_processed(
                    entry_key=entry_key,
                    feed_url=feed_config.url,
                    entry_title=get_entry_title(entry),
                    entry_link=get_entry_link(entry) or "",
                    wp_post_id=result.get("id"),
                    wp_post_url=result.get("link"),
                )
                processed += 1
                
                # Track for email notification
                if published_articles is not None and result.get("link"):
                    published_articles.append({
                        "title": result.get("title", {}).get("rendered", get_entry_title(entry)),
                        "url": result.get("link"),
                        "feed_name": feed_config.name,
                    })
            else:
                errors += 1

            # Rate limit between entries
            time.sleep(1)

        except Exception as e:
            logger.error(
                "entry_processing_error",
                title=get_entry_title(entry)[:50],
                error=str(e),
            )
            errors += 1
            continue

    return (processed, skipped, errors)


def process_entry(
    entry,
    feed_config: FeedConfig,
    settings: AppSettings,
    rewriter: OpenAIRewriter,
    wp_client: Optional[WordPressClient],
    dry_run: bool,
    logger,
) -> Optional[dict]:
    """Process a single RSS entry.

    Returns:
        WordPress post data if successful, None otherwise.
    """
    title = get_entry_title(entry)
    content = get_entry_content(entry)
    link = get_entry_link(entry)

    logger.info("processing_entry", title=title[:50])

    # Rewrite with OpenAI
    rewritten = rewriter.rewrite(
        content=content,
        original_title=title,
        use_original_title=feed_config.use_original_title,
    )

    if not rewritten:
        logger.error("rewrite_failed", title=title[:50])
        return None

    # Find image
    featured_media_id = None

    # Try RSS image first
    image_url = find_rss_image(entry, base_url=link or "")
    image_alt = ""

    if image_url:
        logger.info("using_rss_image", url=image_url)
        image_result = download_image(image_url)
        if image_result:
            image_bytes, filename, _ = image_result
            image_alt = title[:100]  # Use title as alt for RSS images
        else:
            image_url = None

    # Fallback to stock photos
    if not image_url:
        fallback = find_fallback_image(
            title=title,
            feed_name=feed_config.name,
            pexels_key=settings.pexels_api_key,
            unsplash_key=settings.unsplash_access_key,
        )
        if fallback:
            logger.info("using_fallback_image", source=fallback["source"])
            image_result = download_image(fallback["url"])
            if image_result:
                image_bytes, filename, _ = image_result
                image_alt = fallback["alt_text"]
            else:
                fallback = None

        if not fallback:
            logger.warning("no_image_available", title=title[:50])

    # Upload image to WordPress
    if not dry_run and wp_client and image_result:
        featured_media_id = wp_client.upload_media(
            image_bytes=image_bytes,
            filename=filename,
            alt_text=image_alt,
        )

    # Get/create category
    category_id = None
    if not dry_run and wp_client and feed_config.default_category:
        category_id = wp_client.get_or_create_category(feed_config.default_category)

    # Get/create tags
    tag_ids = []
    if not dry_run and wp_client and feed_config.default_tags:
        tag_ids = wp_client.get_or_create_tags(feed_config.default_tags)

    # Create post
    if dry_run:
        logger.info(
            "dry_run_would_publish",
            headline=rewritten["headline"][:50],
            body_length=len(rewritten["body"]),
            has_image=featured_media_id is not None or image_result is not None,
            category=feed_config.default_category,
            tags=feed_config.default_tags,
        )
        return {"id": 0, "link": "dry-run://not-published"}

    if not wp_client:
        return None

    post = wp_client.create_post(
        title=rewritten["headline"],
        content=rewritten["body"],
        excerpt=rewritten.get("excerpt", ""),
        category_id=category_id,
        tag_ids=tag_ids,
        featured_media_id=featured_media_id,
        source_url=link,
    )

    return post


@app.command()
def status() -> None:
    """Show status of processed entries."""
    logger = setup_logging()
    dedupe_store = DedupeStore()

    count = dedupe_store.get_processed_count()
    logger.info("processed_entries_count", count=count)

    recent = dedupe_store.get_recent_entries(limit=10)
    if recent:
        typer.echo("\nRecent entries:")
        for entry in recent:
            typer.echo(f"  - {entry['entry_title'][:60]}...")
            typer.echo(f"    Processed: {entry['processed_at']}")
            if entry.get("wp_post_url"):
                typer.echo(f"    URL: {entry['wp_post_url']}")


@app.command()
def clear_db(
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Confirm database clear without prompting.",
    ),
) -> None:
    """Clear the processed entries database."""
    if not confirm:
        confirm = typer.confirm("Are you sure you want to clear all processed entries?")

    if confirm:
        dedupe_store = DedupeStore()
        count = dedupe_store.clear_all()
        typer.echo(f"Cleared {count} entries from database.")
    else:
        typer.echo("Cancelled.")


if __name__ == "__main__":
    app()
