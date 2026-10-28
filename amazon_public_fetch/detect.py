"""Block / soft-wall detection for Amazon HTML responses."""
from __future__ import annotations

import re
from html import unescape

_ROBOT = re.compile(
    r"robot\s*check|automated\s+access|validatecaptcha|enter\s+the\s+characters|"
    r"api-services-support@amazon\.com|sorry,\s*we\s+just\s+need\s+to\s+make\s+sure",
    re.I,
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_PRODUCT_TITLE = re.compile(r'id="productTitle"[^>]*>\s*([^<]+)', re.I)
_ASIN = re.compile(r"/dp/([A-Z0-9]{10})", re.I)
_ASIN_META = re.compile(
    r'(?:data-asin|asin)["\s:=]+["\']?([A-Z0-9]{10})', re.I
)


def page_title(html: str) -> str | None:
    m = _TITLE.search(html or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip() or None


def product_title(html: str) -> str | None:
    m = _PRODUCT_TITLE.search(html or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip() or None


def looks_blocked(html: str, status: int) -> bool:
    if status in (503, 429, 202):
        return True
    text = html or ""
    low = text.lower()
    if "validatecaptcha" in low or "automated access" in low:
        return True
    if _ROBOT.search(text) and not product_title(text):
        return True
    t = (page_title(text) or "").lower()
    if "robot check" in t:
        return True
    return False


def extract_asin(url: str, html: str = "") -> str | None:
    m = _ASIN.search(url or "")
    if m:
        return m.group(1).upper()
    m = _ASIN_META.search(html or "")
    return m.group(1).upper() if m else None


def is_amazon_url(url: str) -> bool:
    from .urls import normalize_url

    try:
        normalize_url(url)
        return True
    except ValueError:
        return False
