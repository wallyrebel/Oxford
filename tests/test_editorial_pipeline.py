import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import feedparser
import pytest

from rss_to_wp.cli import process_entry, process_feed
from rss_to_wp.config import AppSettings, FeedConfig, load_feeds_config
from rss_to_wp.feeds.filter import generate_entry_key, is_within_window, parse_entry_date
from rss_to_wp.rewriter.openai_client import OpenAIRewriter
from rss_to_wp.rewriter.quality import (
    EditorialSkipError,
    canonical_source,
    source_check,
    validate_draft,
)
from rss_to_wp.storage.dedupe import DedupeStore
from rss_to_wp.wordpress.client import WordPressClient

SOURCE = "All OSD schools and offices will be closed Monday, Sept. 7 for Labor Day. Have a safe and happy long weekend, Chargers!"
TITLE = "Labor Day closure"
LINK = "https://www.facebook.com/1344354927730591/posts/1554233276742754"
DRAFT = {
    "headline": "Oxford schools to close Sept. 7 for Labor Day",
    "excerpt": "Oxford School District announced the holiday closure.",
    "paragraphs": [
        "Oxford School District announced that all schools and offices will be closed Monday, Sept. 7 for Labor Day."
    ],
}


def rewriter(responses):
    obj = OpenAIRewriter("test-key")
    obj.client = Mock()
    obj.client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(refusal=None, content=json.dumps(r)),
                )
            ],
            usage=None,
        )
        for r in responses
    ]
    return obj


def facts():
    return {
        "usable": True,
        "reason": "A complete school closure notice",
        "facts": [
            {
                "fact": "Schools closed Sept. 7",
                "evidence": "schools and offices will be closed Monday, Sept. 7 for Labor Day",
            }
        ],
    }


@pytest.mark.parametrize(
    "text",
    [
        "This content isn't available right now. The owner may have shared it with a small group.",
        "Content unavailable due to privacy settings or deletion.",
        "This post is currently unavailable. Log in to continue.",
        "Unable to retrieve the article. No content provided.",
        "<p>Some event information.</p><p>Privacy settings prevented access to this post.</p>",
    ],
)
def test_unavailable_sources_cost_nothing(text):
    obj = rewriter([])
    with pytest.raises(EditorialSkipError):
        obj.rewrite(text, "Community notice")
    obj.client.chat.completions.create.assert_not_called()


def test_real_phone_outage_is_not_a_placeholder():
    assert source_check(
        "Phone line temporarily unavailable",
        "The sheriff's office phone line is down. In an emergency, call 911.",
    )


def test_ordinal_dates_can_be_written_in_ap_style():
    assert validate_draft(DRAFT, SOURCE.replace("7 for", "7th for"), "Oxford School District")


def test_short_factual_notice_passes_all_three_stages():
    obj = rewriter([facts(), DRAFT, {"approved": True, "issues": []}])
    result = obj.rewrite(SOURCE, TITLE, source_url=LINK)
    assert result["body"].startswith("<p>Oxford School District")
    calls = obj.client.chat.completions.create.call_args_list
    assert [c.kwargs["model"] for c in calls] == ["gpt-4.1-nano", "gpt-5.6-luna", "gpt-5.4-mini"]
    assert all("max_completion_tokens" in c.kwargs and "max_tokens" not in c.kwargs for c in calls)
    assert "temperature" not in calls[1].kwargs
    assert SOURCE in calls[2].kwargs["messages"][1]["content"]
    assert calls[2].kwargs["response_format"]["json_schema"]["strict"] is True


def test_extractor_cannot_invent_its_evidence():
    extraction = facts()
    extraction["facts"][0]["evidence"] = "School will reopen on Sept. 8."
    obj = rewriter([extraction])
    with pytest.raises(EditorialSkipError, match="evidence_not_in_source"):
        obj.rewrite(SOURCE, TITLE)
    assert obj.client.chat.completions.create.call_count == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"headline": "Oregon School District closure"}, "wrong_school_district"),
        ({"paragraphs": ["Schools will reopen on Sept. 8."]}, "unsupported_numeric_detail"),
        (
            {"paragraphs": ['The superintendent said, "We will reopen the schools tomorrow."']},
            "unsupported_direct_quote",
        ),
        ({"paragraphs": ["<script>alert(1)</script>"]}, "markup_in_plain_text"),
        ({"paragraphs": ["The district announced a closure."] * 2}, "repeated_paragraph"),
    ],
)
def test_known_hallucinations_and_unsafe_output_are_blocked(change, reason):
    with pytest.raises(EditorialSkipError, match=reason):
        validate_draft({**DRAFT, **change}, SOURCE, "Oxford School District")


def test_checker_failure_never_returns_a_publishable_article():
    rejection = {"approved": False, "issues": ["Unsupported attribution"]}
    obj = rewriter([facts(), DRAFT, rejection, DRAFT, rejection])
    with pytest.raises(EditorialSkipError, match="checker_rejected"):
        obj.rewrite(SOURCE, TITLE, source_url=LINK)
    assert obj.client.chat.completions.create.call_count == 5


def test_corrected_draft_requires_a_fresh_check_against_original_source():
    rejection = {"approved": False, "issues": ["Remove unsupported attribution"]}
    obj = rewriter([facts(), DRAFT, rejection, DRAFT, {"approved": True, "issues": []}])
    assert obj.rewrite(SOURCE, TITLE, source_url=LINK)["headline"] == DRAFT["headline"]
    calls = obj.client.chat.completions.create.call_args_list
    assert calls[3].kwargs["response_format"]["json_schema"]["name"] == "revise_article"
    assert SOURCE in calls[3].kwargs["messages"][1]["content"]
    assert SOURCE in calls[4].kwargs["messages"][1]["content"]
    assert calls[4].kwargs["response_format"]["json_schema"]["name"] == "check_article"


def test_truncated_api_response_is_an_operational_failure():
    obj = rewriter([])
    obj.client.chat.completions.create.side_effect = None
    obj.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length", message=SimpleNamespace(content="{}", refusal=None)
            )
        ]
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        obj.rewrite(SOURCE, TITLE)


def settings():
    return AppSettings(
        _env_file=None,
        openai_api_key="test-key",
        wordpress_base_url="https://example.com",
        wordpress_username="editor",
        wordpress_app_password="test-password",
    )


def entry(i):
    return {
        "id": str(i),
        "link": f"https://example.com/news/{i}",
        "title": f"Notice {i}",
        "summary": SOURCE,
        "published": datetime.now(timezone.utc).isoformat(),
    }


def test_duplicates_do_not_starve_unseen_articles_or_dry_run_consume_them(tmp_path, monkeypatch):
    feed = FeedConfig(name="Local", url="https://example.com/feed", max_per_run=2)
    entries = [entry(i) for i in range(8)]
    store = DedupeStore(tmp_path / "state.db")
    # The newest five are duplicates; old code sliced them before deduplication.
    for e in entries[-5:]:
        store.mark_processed(generate_entry_key(e, feed.url), feed.url, e["title"], e["link"])
    monkeypatch.setattr("rss_to_wp.cli.parse_feed", lambda _: SimpleNamespace(entries=entries))
    publish = Mock(return_value={"id": 0, "link": "dry-run://not-published"})
    monkeypatch.setattr("rss_to_wp.cli.process_entry", publish)
    monkeypatch.setattr("rss_to_wp.cli.time.sleep", lambda _: None)
    result = process_feed(feed, settings(), store, Mock(), None, True, 48, Mock())
    assert result[0] == 2
    assert publish.call_count == 2
    assert store.get_processed_count() == 5


def test_rejected_source_is_remembered_until_text_changes(tmp_path):
    store = DedupeStore(tmp_path / "state.db")
    store.mark_rejected("x", "version1", "Placeholder", LINK, "unavailable")
    assert store.is_rejected("x", "version1")
    assert not store.is_rejected("x", "version2")
    assert store.get_processed_count() == 0
    assert store.get_rejected_entries()[0]["reason"] == "unavailable"


@pytest.mark.parametrize("missing", ["image", "category", "tags", "upload"])
def test_missing_required_publication_metadata_never_creates_post(monkeypatch, missing):
    monkeypatch.setattr(
        "rss_to_wp.cli.find_rss_image",
        lambda *a, **k: "https://example.com/photo.jpg" if missing != "image" else None,
    )
    monkeypatch.setattr(
        "rss_to_wp.cli.download_image", lambda *a: (b"image", "image.jpg", "image/jpeg")
    )
    monkeypatch.setattr("rss_to_wp.cli.find_fallback_image", lambda **k: None)
    wp = Mock()
    wp.upload_media.return_value = None if missing == "upload" else 100
    wp.get_or_create_category.return_value = None if missing == "category" else 5
    wp.get_or_create_tags.return_value = [] if missing == "tags" else [1, 2]
    writer = Mock()
    writer.rewrite.return_value = {
        "headline": TITLE,
        "excerpt": "A closure notice",
        "body": "<p>Notice</p>",
    }
    with pytest.raises(RuntimeError, match="required"):
        process_entry(
            entry(1),
            FeedConfig(
                name="Local", url="https://example.com/feed", default_category="Oxford News"
            ),
            settings(),
            writer,
            wp,
            False,
            Mock(),
        )
    wp.create_post.assert_not_called()


def test_complete_metadata_can_publish(monkeypatch):
    monkeypatch.setattr(
        "rss_to_wp.cli.find_rss_image", lambda *a, **k: "https://example.com/photo.jpg"
    )
    monkeypatch.setattr(
        "rss_to_wp.cli.download_image", lambda *a: (b"image", "image.jpg", "image/jpeg")
    )
    wp = Mock()
    wp.upload_media.return_value = 100
    wp.get_or_create_category.return_value = 5
    wp.get_or_create_tags.return_value = [1, 2]
    wp.create_post.return_value = {"id": 77, "link": "https://example.com/news"}
    writer = Mock()
    writer.rewrite.return_value = {
        "headline": TITLE,
        "excerpt": "A closure notice",
        "body": "<p>Notice</p>",
    }
    result = process_entry(
        entry(1),
        FeedConfig(name="Local", url="https://example.com/feed", default_category="Oxford News"),
        settings(),
        writer,
        wp,
        False,
        Mock(),
    )
    assert result["id"] == 77
    assert wp.create_post.call_args.kwargs["featured_media_id"] == 100
    assert wp.create_post.call_args.kwargs["category_id"] == 5
    assert wp.create_post.call_args.kwargs["tag_ids"] == [1, 2]


def test_duplicate_lookup_failure_defers_publication():
    wp = WordPressClient("https://example.com", "editor", "password")
    wp.session = Mock()
    wp.session.get.side_effect = RuntimeError("network down")
    with pytest.raises(RuntimeError, match="publishing deferred"):
        wp.create_post("News", "<p>News</p>", source_url=LINK)
    wp.session.post.assert_not_called()


def test_source_url_tracking_and_escaped_query_deduplication():
    assert (
        canonical_source("https://example.com/a?utm_source=x&id=7#top")
        == "https://example.com/a?id=7"
    )
    wp = WordPressClient("https://example.com", "editor", "password")
    wp.session = Mock()
    wp.session.get.return_value.json.return_value = [
        {"content": {"rendered": '<a href="https://example.com/a?id=7&amp;x=2">source</a>'}}
    ]
    assert wp.check_duplicate_by_source_url("https://example.com/a?id=7&x=2")


def test_feed_configuration_has_categories_tags_and_respects_enabled():
    feeds = load_feeds_config("feeds.yaml").feeds
    assert len(feeds) == 8
    assert all(f.default_category and f.default_tags and f.max_per_run == 5 for f in feeds)
    assert (
        FeedConfig(name="Legacy", url="https://example.com", category="News", enabled=False).enabled
        is False
    )
    assert (
        FeedConfig(name="Legacy", url="https://example.com", category="News").default_category
        == "News"
    )


def test_rss_dates_are_utc_and_future_entries_are_excluded():
    parsed = feedparser.parse(
        '<rss version="2.0"><channel><item><title>Notice</title><pubDate>Tue, 08 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'
    )
    assert parse_entry_date(parsed.entries[0]).hour == 12
    assert not is_within_window(datetime.now(timezone.utc) + timedelta(days=1))
