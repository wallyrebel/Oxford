from bs4 import BeautifulSoup
from rss_to_wp.feeds import parser
from rss_to_wp.feeds.filter import parse_entry_date


def test_blood_service_preserves_rss_publication_date(monkeypatch):
    class Response:
        status_code = 200
        content = b"""<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
        <item><title>Holiday hours</title><link>https://msblood.com/holiday/</link>
        <pubDate>Sun, 22 Nov 2026 12:00:06 +0000</pubDate>
        <content:encoded>Oxford center hours</content:encoded></item></channel></rss>"""

        def raise_for_status(self):
            pass

    monkeypatch.setattr(parser.requests, "get", lambda *args, **kwargs: Response())
    entry, = parser.parse_feed(parser.BLOOD_NEWS).entries
    assert parse_entry_date(entry).isoformat() == "2026-11-22T12:00:06+00:00"


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
