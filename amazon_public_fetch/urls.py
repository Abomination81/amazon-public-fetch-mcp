"""Canonical public product URLs. No account paths, tracking or short links."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

DOMAINS = ("amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.co.jp")
_ASIN = re.compile(r"[A-Z0-9]{10}", re.I)
_PATH = re.compile(r"/(?:[^/]+/)?dp/([A-Z0-9]{10})(?:/[^?]*)?", re.I)


def normalize_url(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("invalid_product_url")
    value = value.strip()
    if _ASIN.fullmatch(value):
        return f"https://www.amazon.com/dp/{value.upper()}"
    if value.startswith("www."):
        value = "https://" + value
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("invalid_product_url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        domain = host.removeprefix("www.")
        match = _PATH.fullmatch(parsed.path)
        if (parsed.scheme != "https" or domain not in DOMAINS
                or host not in (domain, "www." + domain)
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or not match):
            raise ValueError("invalid_product_url")
    except ValueError:
        raise ValueError("invalid_product_url") from None
    return f"https://www.{domain}/dp/{match.group(1).upper()}"
