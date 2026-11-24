from bs4 import BeautifulSoup
from rss_to_wp.feeds import parser
from rss_to_wp.feeds.filter import parse_entry_date


def test_manual_public_records_revision_only_changes_that_feed_fetch(monkeypatch):
    from unittest.mock import Mock
    revision = "a" * 40
    fetch = Mock(return_value=parser.feedparser.FeedParserDict(bozo=False, entries=[]))
    monkeypatch.setattr(parser.feedparser, "parse", fetch)
    monkeypatch.setenv("PUBLIC_RECORDS_COMMIT", revision)
    parser.parse_feed(parser.PUBLIC_RECORDS)
    fetch.assert_called_with(parser.PUBLIC_RECORDS.replace("/main/", f"/{revision}/"))
    parser.parse_feed("https://example.org/news.xml")
    fetch.assert_called_with("https://example.org/news.xml")
    monkeypatch.setenv("PUBLIC_RECORDS_COMMIT", "other/branch")
    assert parser.parse_feed(parser.PUBLIC_RECORDS) is None
    assert fetch.call_count == 2
    monkeypatch.delenv("PUBLIC_RECORDS_COMMIT")
    parser.parse_feed(parser.PUBLIC_RECORDS)
    fetch.assert_called_with(parser.PUBLIC_RECORDS)


def test_blood_service_preserves_rss_publication_date(monkeypatch):
    class Response:
        status_code = 200
        content = b"""<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
        <item><title>Holiday hours</title><link>https://msblood.com/holiday/</link>
        <pubDate>Sun, 22 Nov 2026 12:00:06 +0000</pubDate>
        <content:encoded><![CDATA[<p>Flowood Donor Center, Flowood, MS</p><ul><li>Wednesday, November 25: 7:30 AM</li></ul>
        <p>Oxford Donor Center<br>2627 West Oxford Loop, Suite C, Oxford, MS</p>
        <ul><li>Wednesday, November 25: 9 AM to 2:30 PM</li></ul><h3>Giveaway</h3>]]></content:encoded></item></channel></rss>"""

        def raise_for_status(self):
            pass

    monkeypatch.setattr(parser.requests, "get", lambda *args, **kwargs: Response())
    entry, = parser.parse_feed(parser.BLOOD_NEWS).entries
    assert parse_entry_date(entry).isoformat() == "2026-11-22T12:00:06+00:00"
    assert "9 AM to 2:30 PM" in entry.summary and "Flowood" not in entry.summary and "Giveaway" not in entry.summary


def test_newsroom_uses_live_feed_entry_point_and_only_release_text(monkeypatch):
    url = parser.UNIVERSITY_NEWS + "2026/11/food-drive/index.html"
    listing = f'<main><a href="{url}">Release</a><a href="https://example.org/">Outside</a></main>'
    release = """<main><h1>Food drive</h1><h2 class="small-text">Published</h2>
    <div>November 15, 2026</div><section class="news-content"><div class="wysiwyg">
    <p>Volunteers distributed food.</p><figure>Image caption</figure></div></section></main>"""
    pages = {parser.UNIVERSITY_NEWS: listing, url: release}
    monkeypatch.setattr(parser, "university_page", lambda target: BeautifulSoup(pages[target], "html.parser"))
    feed = parser.parse_feed(parser.UNIVERSITY_NEWS)
    assert [e.link for e in feed.entries] == [url]
    assert parser.get_entry_content(feed.entries[0]) == "Volunteers distributed food."
    assert parse_entry_date(feed.entries[0]).date().isoformat() == "2026-11-15"
