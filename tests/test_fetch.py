import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
import pytest

from amazon_public_fetch import ladder
from amazon_public_fetch.extract import summarize_product
from amazon_public_fetch.urls import normalize_url

ASIN = "B000000001"
URL = f"https://www.amazon.com/dp/{ASIN}"
HTML = '''<html><title>Public product</title><span id="productTitle">Example &amp; Co</span>
<div class="a-price"><span class="a-offscreen">£12.34</span></div>
<div id="feature-bullets"><ul><li><span>A <b>useful</b> feature</span></li></ul></div></html>'''


@pytest.mark.parametrize("url", [ASIN, URL + "?tag=private-affiliate&token=example#private",
                                  URL.replace('/dp/', '/product-name/dp/') + '/ref=tracking'])
def test_canonicalization(url):
    assert normalize_url(url) == URL


@pytest.mark.parametrize("url", ["https://amazon.com.evil.test/dp/" + ASIN,
    "https://evil.test/?amazon.com", "https://amazon.com@localhost/dp/" + ASIN,
    "http://www.amazon.com/dp/" + ASIN, "https://www.amazon.com:444/dp/" + ASIN,
    "https://www.amazon.com/ap/signin", "https://www.amazon.com/vine/", "https://amzn.to/abc",
    "file:///amazon.com", "https://127.0.0.1/amazon.com", "https://user:private@amazon.com/dp/" + ASIN,
    "https://www.amazon.com/dp/" + ASIN + "\n", "x" * 2049])
def test_rejects_unsafe_urls_without_echoing_input(url):
    # Outer whitespace is harmless; embedded control characters are not.
    if url.endswith("\n"):
        url = url.replace("/dp/", "/d\np/")
    result = ladder.fetch_amazon(url).public_dict()
    assert result["reason"] == "invalid_product_url"
    assert result["url"] == ""


def test_price_entities_nested_bullets():
    product = summarize_product(HTML, URL)
    assert product["title"] == "Example & Co"
    assert product["price_text"] == "£12.34"
    assert product["bullets"] == ["A useful feature"]


def test_failure_does_not_echo_exception_or_proxy(monkeypatch):
    monkeypatch.setenv("AMAZON_FETCH_PROXY", "http://test-user:test-pass@127.0.0.1:9")
    def failure(url):
        raise RuntimeError("test-pass /private/example")
    with patch.object(ladder, "_ENGINES", [("httpx", failure)]):
        result = ladder.fetch_amazon(URL).public_dict()
    assert result["reason"] == "httpx_error:RuntimeError"
    assert not result["blocked"]
    assert "test-pass" not in json.dumps(result)
    assert "test-user" not in json.dumps(ladder.capabilities())


def test_rate_limit_stops_ladder():
    def forbidden(url):
        pytest.fail("Rate limit must not trigger another request")
    with patch.object(ladder, "_ENGINES", [
        ("httpx", lambda url: (429, "rate limited", url)), ("curl_cffi", forbidden)]):
        result = ladder.fetch_amazon(URL)
    assert result.blocked and result.status == 429


def test_success_requires_product_and_raw_html_is_opt_in():
    with patch.object(ladder, "_ENGINES", [("httpx", lambda url: (200, HTML, url))]):
        assert ladder.fetch_amazon(URL).ok
        assert "html" not in ladder.fetch_amazon(URL).public_dict()
        assert ladder.fetch_amazon(URL, include_html=True).html == HTML
    with patch.object(ladder, "_ENGINES", [("httpx", lambda url: (200, "x" * 700, url))]):
        assert not ladder.fetch_amazon(URL).ok


def test_response_size_limit():
    with pytest.raises(ladder.FetchStop, match="response_too_large"):
        ladder._read([b"a" * (ladder.MAX_BYTES + 1)], ladder.time.monotonic())


def test_unsafe_redirect_never_requested():
    visited = []
    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
    real_client = httpx.Client
    with patch.dict(os.environ, {}, clear=True), patch("httpx.Client", side_effect=lambda **kw:
            real_client(transport=httpx.MockTransport(handler), **kw)):
        result = ladder.fetch_amazon(URL, max_engine="httpx")
    assert result.reason == "unsafe_redirect"
    assert visited == [URL]


def test_allowed_redirect_is_scrubbed():
    visited = []
    def request(url):
        visited.append(url)
        if len(visited) == 1:
            return 302, "", "https://www.amazon.ca/dp/B000000002?tag=tracking"
        return 200, HTML, None
    assert ladder._http_ladder(URL, request)[2] == "https://www.amazon.ca/dp/B000000002"
    assert "?" not in visited[1]


def test_invalid_proxy_fails_closed(monkeypatch):
    monkeypatch.setenv("AMAZON_FETCH_PROXY", "not-a-proxy")
    assert ladder.fetch_amazon(URL).reason == "invalid_proxy_configuration"
    assert ladder.capabilities()["configuration_error"] == "invalid_proxy_configuration"


def test_playwright_proxy_credentials_are_separate():
    assert ladder._playwright_proxy("http://test%40user:test%3Apass@localhost:8080") == {
        "server": "http://localhost:8080", "username": "test@user", "password": "test:pass"}


@pytest.mark.parametrize("engine", ["httpx", "curl_cffi", "rnet"])
def test_engine_reaches_configured_local_proxy(engine):
    pytest.importorskip(engine)
    connects = []
    class Proxy(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            connects.append(self.path)
            self.send_response(502)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict(os.environ, {"AMAZON_FETCH_PROXY": f"http://127.0.0.1:{server.server_port}"}, clear=True):
            try:
                dict(ladder._ENGINES)[engine](URL)
            except Exception:
                pass  # The fake proxy deliberately rejects the tunnel.
        assert connects and set(connects) == {"www.amazon.com:443"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
