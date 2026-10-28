#!/usr/bin/env python3
"""
Amazon Public Fetch — MCP server for Grok Bot / other MCP clients.

Public Amazon product pages only. No login, Vine, captcha solving, or scrapers
for other sites. Run on a residential IP (home machine) or set AMAZON_FETCH_PROXY.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from amazon_public_fetch import __version__

from mcp.server.fastmcp import FastMCP

from amazon_public_fetch.extract import summarize_product
from amazon_public_fetch.ladder import capabilities, fetch_amazon

mcp = FastMCP("amazon-public-fetch")


@mcp.tool()
def health() -> dict[str, Any]:
    """
    What this connector can do right now: which fetch engines are installed,
    and the honest limits (public pages only; must run on a home/residential machine).
    """
    caps = capabilities()
    return {
        "ok": caps["configuration_error"] is None,
        "name": "amazon-public-fetch",
        "version": __version__,
        "scope": "public Amazon /dp/ product pages only",
        "not_included": [
            "Amazon account login",
            "Vine queues",
            "CAPTCHA solving",
            "hosted proxy service",
            "non-Amazon sites",
        ],
        **caps,
    }


@mcp.tool()
def amazon_fetch(
    url: str,
    include_html: bool = False,
    max_engine: Optional[Literal["httpx", "curl_cffi", "rnet", "playwright"]] = None,
) -> dict[str, Any]:
    """
    Fetch a public Amazon URL (or a 10-char ASIN) through a local fetch ladder:
    httpx → curl_cffi → rnet → playwright. Uses fresh sessions. Stops on rate limits.

    Returns status, engine used, ASIN, titles, and size. Set include_html=true
    only when you need the raw page (large). max_engine caps the ladder
    (httpx|curl_cffi|rnet|playwright).
    """
    outcome = fetch_amazon(url, include_html=include_html, max_engine=max_engine)
    return outcome.public_dict(include_html=include_html)


@mcp.tool()
def amazon_product(url: str, max_engine: Optional[Literal["httpx", "curl_cffi", "rnet", "playwright"]] = None) -> dict[str, Any]:
    """
    Fetch a public Amazon product page and return a small summary:
    ASIN, title, visible price text, and feature bullets. Same ladder as amazon_fetch.
    """
    outcome = fetch_amazon(url, include_html=True, max_engine=max_engine)
    base = outcome.public_dict(include_html=False)
    if not outcome.ok or not outcome.html:
        return {**base, "product": None}
    return {**base, "product": summarize_product(outcome.html, outcome.final_url or outcome.url)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
