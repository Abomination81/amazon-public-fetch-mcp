"""Light product field extraction from Amazon HTML (public pages)."""
from __future__ import annotations

import re
from html import unescape
from typing import Any

from .detect import extract_asin, page_title, product_title

_PRICE = re.compile(
    r'class="a-price[^"]*"[^>]*>.*?class="a-offscreen"[^>]*>\s*([^<]+)',
    re.I | re.S,
)
_PRICE_WHOLE = re.compile(
    r'class="a-price-whole"[^>]*>([^<]+).*?class="a-price-fraction"[^>]*>([^<]+)',
    re.I | re.S,
)
_FEATURE = re.compile(
    r'id="feature-bullets"[\s\S]*?<ul[^>]*>([\s\S]*?)</ul>', re.I
)
_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S)


def summarize_product(html: str, url: str = "") -> dict[str, Any]:
    bullets: list[str] = []
    m = _FEATURE.search(html or "")
    if m:
        for li in _LI.findall(m.group(1)):
            t = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", li))).strip()
            if t and t.lower() not in ("about this item",) and len(t) > 2:
                bullets.append(t)
            if len(bullets) >= 8:
                break

    price = None
    m = _PRICE.search(html or "")
    if m:
        price = re.sub(r"\s+", " ", unescape(m.group(1))).strip()
    else:
        m = _PRICE_WHOLE.search(html or "")
        if m:
            whole = m.group(1).replace(",", "").rstrip(".")
            price = f"{whole}.{m.group(2)}"  # Do not invent a currency.

    return {
        "asin": extract_asin(url, html),
        "title": product_title(html) or page_title(html),
        "price_text": price,
        "bullets": bullets,
        "page_title": page_title(html),
    }
