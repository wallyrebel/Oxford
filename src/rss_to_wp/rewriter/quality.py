"""Checks that do not rely on a model approving its own output."""

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup


class EditorialSkipError(ValueError):
    """Source needs editorial attention; do not publish or repeatedly buy rewrites."""


def plain_text(value: str) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for node in soup(["script", "style", "nav", "footer", "header"]):
        node.decompose()
    return re.sub(r"\s+", " ", html.unescape(soup.get_text(" "))).strip()


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value).replace("’", "'")).strip().casefold()


UNAVAILABLE = re.compile(
    r"\b(?:this\s+)?(?:content|post|page|video|story)\s+(?:(?:is|isn't|is not|isn’t)\s+)?"
    r"(?:currently\s+|temporarily\s+)?(?:unavailable|not available|isn.t available)\b"
    r"|\bprivacy settings\b|\bshared (?:it )?with (?:a )?(?:small group|limited audience)\b"
    r"|\b(?:unable|failed) to (?:access|retrieve|fetch) (?:the )?(?:content|post|article)\b"
    r"|\b(?:log in|login|sign in) to (?:continue|view (?:this|the) (?:content|post))\b"
    r"|\b(?:no (?:article|content) provided|access denied|enable javascript and cookies)\b",
    re.I,
)


def source_check(title: str, content: str) -> str:
    text = plain_text(content)
    if UNAVAILABLE.search(plain_text(title) + " " + text):
        raise EditorialSkipError("unavailable_or_restricted_source")
    if len(text) < 40 or len(text.split()) < 7:
        raise EditorialSkipError("insufficient_source_text")
    if len(text) > 24000:
        raise EditorialSkipError("source_exceeds_review_limit")
    return text


def canonical_source(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username:
        raise EditorialSkipError("invalid_source_url")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


def source_fingerprint(title: str, content: str) -> str:
    return hashlib.sha256(normalized(title + " " + plain_text(content)).encode()).hexdigest()


def numeric_details(text: str) -> set[str]:
    # Preserve the value when AP style changes "7th" to "7" or "1,000" to "1000".
    return {
        re.sub(r"(?:st|nd|rd|th)$", "", n, flags=re.I).replace(",", "")
        for n in re.findall(r"(?<!\w)\d+(?:[.,:]\d+)*(?:st|nd|rd|th)?(?!\w)", text, re.I)
    }


def source_context(url: str, configured: str = "") -> str:
    """Only expand publisher identities verified by an editor, never an ambiguous acronym."""
    parts = urlsplit(url)
    if parts.hostname in {"facebook.com", "www.facebook.com", "m.facebook.com"} and (
        parts.path.startswith("/1344354927730591/posts/") or parts.path.startswith("/OxfordSD/")
    ):
        return "Publisher: Oxford School District in Oxford, Mississippi. OSD means Oxford School District; OHS means Oxford High School."
    return configured


def validate_draft(draft: dict, source: str, context: str = "") -> dict:
    if set(draft) != {"headline", "excerpt", "paragraphs"}:
        raise EditorialSkipError("invalid_draft_fields")
    if not all(isinstance(draft[k], str) and draft[k].strip() for k in ("headline", "excerpt")):
        raise EditorialSkipError("empty_headline_or_excerpt")
    paragraphs = draft["paragraphs"]
    if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 16:
        raise EditorialSkipError("invalid_paragraphs")
    if not all(isinstance(p, str) and p.strip() for p in paragraphs):
        raise EditorialSkipError("empty_paragraph")
    combined = " ".join([draft["headline"], draft["excerpt"], *paragraphs])
    if re.search(r"<[^>]+>|```", combined):
        raise EditorialSkipError("markup_in_plain_text_draft")
    if UNAVAILABLE.search(combined):
        raise EditorialSkipError("placeholder_in_draft")
    if len(draft["headline"]) > 180 or len(draft["excerpt"]) > 450:
        raise EditorialSkipError("oversized_headline_or_excerpt")
    if len(set(normalized(p) for p in paragraphs)) != len(paragraphs):
        raise EditorialSkipError("repeated_paragraph")
    if "Oxford School District" in context and re.search(
        r"\b(?:Oregon|Osceola) (?:School District|High School)", combined, re.I
    ):
        raise EditorialSkipError("wrong_school_district")
    # The model checker also checks names, spelled-out numbers, dates and attribution.
    if numeric_details(combined) - numeric_details(source):
        raise EditorialSkipError("unsupported_numeric_detail")
    for quote in re.findall(r'[“"]([^“”"]{12,})[”"]', combined):
        if normalized(quote) not in normalized(source):
            raise EditorialSkipError("unsupported_direct_quote")
    return {
        "headline": draft["headline"].strip(),
        "excerpt": draft["excerpt"].strip(),
        "body": "\n".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs),
    }
