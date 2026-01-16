"""Email notification utilities."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

# Import directly from logging module to avoid circular import
from rss_to_wp.utils.logging import get_logger

logger = get_logger("utils.email")


def send_email_notification(
    smtp_email: str,
    smtp_password: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """Send an email notification.

    Args:
        smtp_email: Sender email address.
        smtp_password: SMTP password (app password for Gmail).
        to_email: Recipient email address.
        subject: Email subject.
        html_body: HTML email body.
        text_body: Plain text body (optional fallback).
        smtp_server: SMTP server address.
        smtp_port: SMTP port.

    Returns:
        True if email sent successfully.
    """
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = to_email

        # Add text and HTML parts
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Connect and send
        logger.info("sending_email", to=to_email, subject=subject)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

        logger.info("email_sent_successfully", to=to_email)
        return True

    except Exception as e:
        logger.error("email_send_error", error=str(e))
        return False


def build_summary_email(
    processed_articles: list[dict],
    skipped_count: int,
    error_count: int,
    site_name: str = "TippahNews",
) -> tuple[str, str]:
    """Build a summary email for the RSS run.

    Args:
        processed_articles: List of dicts with title, url, feed_name.
        skipped_count: Number of skipped duplicates.
        error_count: Number of errors.
        site_name: Name of the site.

    Returns:
        Tuple of (subject, html_body).
    """
    article_count = len(processed_articles)

    # Subject
    if article_count > 0:
        subject = f"📰 {site_name}: {article_count} New Article{'s' if article_count != 1 else ''} Published"
    else:
        subject = f"📰 {site_name}: No New Articles (Run Complete)"

    # HTML Body
    html_parts = [
        f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #1a365d; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .article {{ background: #f7fafc; border-left: 4px solid #3182ce; padding: 15px; margin: 10px 0; }}
                .article-title {{ color: #2c5282; font-size: 16px; font-weight: bold; text-decoration: none; }}
                .article-feed {{ color: #718096; font-size: 12px; }}
                .stats {{ background: #edf2f7; padding: 15px; margin-top: 20px; border-radius: 5px; }}
                .footer {{ text-align: center; color: #a0aec0; font-size: 12px; padding: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📰 {site_name} Update</h1>
            </div>
            <div class="content">
        """
    ]

    if article_count > 0:
        html_parts.append("<h2>✅ New Articles Published</h2>")
        for article in processed_articles:
            title = article.get("title", "Untitled")
            url = article.get("url", "#")
            feed = article.get("feed_name", "Unknown Feed")
            html_parts.append(f"""
                <div class="article">
                    <a href="{url}" class="article-title">{title}</a>
                    <div class="article-feed">From: {feed}</div>
                </div>
            """)
    else:
        html_parts.append("<h2>ℹ️ No New Articles</h2>")
        html_parts.append("<p>No new articles were found in the configured feeds within the 48-hour window.</p>")

    # Stats
    html_parts.append(f"""
        <div class="stats">
            <strong>Run Statistics:</strong><br>
            📝 Articles Published: {article_count}<br>
            ⏭️ Duplicates Skipped: {skipped_count}<br>
            ❌ Errors: {error_count}
        </div>
    """)

    html_parts.append("""
            </div>
            <div class="footer">
                <p>This is an automated notification from RSS to WordPress Automation</p>
            </div>
        </body>
        </html>
    """)

    html_body = "".join(html_parts)

    return subject, html_body
