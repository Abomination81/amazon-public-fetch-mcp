"""Local public-product fetch ladder. Credentials and exceptions stay out of results."""
from __future__ import annotations

import importlib.util
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urljoin, urlsplit

from .detect import extract_asin, looks_blocked, page_title, product_title
from .urls import normalize_url as _normalize_url

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 20
MAX_REDIRECTS = 3
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}


@dataclass
class FetchOutcome:
    ok: bool
    status: int | None
    engine: str
    blocked: bool
    url: str
    final_url: str | None
    asin: str | None
    title: str | None
    product_title: str | None
    html_bytes: int
    elapsed_ms: int
    reason: str | None = None
    html: str | None = None

    def public_dict(self, include_html: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_html:
            result.pop("html", None)
        return result


class FetchStop(Exception):
    """A fixed, non-sensitive reason to stop the entire ladder."""


def _proxy() -> str | None:
    for key in ("AMAZON_FETCH_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = (os.environ.get(key) or "").strip()
        if value:
            try:
                parsed = urlsplit(value)
                if (parsed.scheme not in ("http", "https") or not parsed.hostname
                        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                        or any(ord(c) < 32 for c in value)):
                    raise ValueError
                _ = parsed.port
            except ValueError:
                raise FetchStop("invalid_proxy_configuration") from None
            return value
    return None


def capabilities() -> dict[str, Any]:
    engines = {name: importlib.util.find_spec(name) is not None
               for name in ("httpx", "curl_cffi", "rnet", "playwright")}
    try:
        proxy = _proxy()
        error = None
    except FetchStop:
        proxy = None
        error = "invalid_proxy_configuration"
    return {
        "engines": engines,
        "proxy_configured": bool(proxy),
        "configuration_error": error,
        "max_response_bytes": MAX_BYTES,
        "timeout_seconds_per_request": TIMEOUT,
        "max_redirects": MAX_REDIRECTS,
        "notes": "Run on your PC. Optional HTTP(S) proxy; no OS proxy auto-discovery. "
                 "Playwright also needs its Chromium download. Public product pages only; "
                 "Amazon can still block requests. No login or CAPTCHA solving.",
    }


def _read(chunks: Iterable[bytes], started: float) -> str:
    body = bytearray()
    for chunk in chunks:
        if time.monotonic() - started > TIMEOUT:
            raise FetchStop("request_timeout")
        if len(body) + len(chunk) > MAX_BYTES:
            raise FetchStop("response_too_large")
        body.extend(chunk)
    return body.decode("utf-8", errors="replace")


def _redirect(current: str, location: str) -> str:
    try:
        return _normalize_url(urljoin(current, location))
    except ValueError:
        raise FetchStop("unsafe_redirect") from None


def _http_ladder(url: str, request: Callable) -> tuple[int, str, str]:
    seen: set[str] = set()
    for _ in range(MAX_REDIRECTS + 1):
        if url in seen:
            raise FetchStop("redirect_loop")
        seen.add(url)
        status, html, location = request(url)
        if status not in (301, 302, 303, 307, 308):
            return status, html, url
        if not location:
            raise FetchStop("invalid_redirect")
        url = _redirect(url, location)
    raise FetchStop("too_many_redirects")


def _fetch_httpx(url: str) -> tuple[int, str, str]:
    import httpx

    with httpx.Client(http2=True, headers=_HEADERS, proxy=_proxy(),
                      trust_env=False, follow_redirects=False, timeout=TIMEOUT) as client:
        def request(target: str):
            started = time.monotonic()
            client.cookies.clear()
            with client.stream("GET", target) as response:
                if response.status_code == 503 and response.headers.get("retry-after"):
                    raise FetchStop("retry_after")
                return (response.status_code, _read(response.iter_bytes(), started),
                        response.headers.get("location"))
        return _http_ladder(url, request)


def _fetch_curl_cffi(url: str) -> tuple[int, str, str]:
    from curl_cffi import CurlOpt, requests

    with requests.Session(trust_env=False, curl_options={CurlOpt.NOPROXY: ""}) as client:
        def request(target: str):
            started = time.monotonic()
            client.cookies.clear()
            response = client.get(target, headers=_HEADERS, impersonate="chrome131",
                                  proxy=_proxy() or "", timeout=TIMEOUT,
                                  allow_redirects=False, stream=True)
            try:
                if response.status_code == 503 and response.headers.get("retry-after"):
                    raise FetchStop("retry_after")
                return (response.status_code, _read(response.iter_content(), started),
                        response.headers.get("location"))
            finally:
                response.close()
        return _http_ladder(url, request)


def _fetch_rnet(url: str) -> tuple[int, str, str]:
    import rnet

    proxy = _proxy()
    client = rnet.BlockingClient(
        impersonate=rnet.Impersonate.Chrome131, timeout=TIMEOUT,
        allow_redirects=False, cookie_store=False, no_proxy=not bool(proxy),
        proxies=[rnet.Proxy.all(proxy)] if proxy else None,
    )
    def request(target: str):
        started = time.monotonic()
        with client.get(target, headers=_HEADERS) as response:
            if response.status == 503 and response.headers.get("retry-after"):
                raise FetchStop("retry_after")
            location = response.headers.get("location")
            with response.stream() as chunks:
                html = _read(chunks, started)
            return response.status, html, location.decode() if location else None
    return _http_ladder(url, request)


def _playwright_proxy(proxy: str) -> dict[str, str]:
    parsed = urlsplit(proxy)
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    result = {"server": f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "")}
    if parsed.username is not None:
        result["username"] = unquote(parsed.username)
        result["password"] = unquote(parsed.password or "")
    return result


def _fetch_playwright(url: str) -> tuple[int, str, str]:
    from playwright.sync_api import sync_playwright

    proxy = _proxy()
    with sync_playwright() as playwright:
        options: dict[str, Any] = {"headless": True}
        if proxy:
            options["proxy"] = _playwright_proxy(proxy)
        else:
            options["args"] = ["--no-proxy-server"]
        browser = playwright.chromium.launch(**options)
        try:
            # Fresh, nonpersistent context; never attach to the user's browser.
            context = browser.new_context(user_agent=_UA, locale="en-US",
                                          java_script_enabled=False, service_workers="block")
            page = context.new_page()
            rejected: list[str] = []
            documents = 0
            def route_request(route):
                nonlocal documents
                request = route.request
                if request.resource_type != "document" or request.frame != page.main_frame:
                    route.abort()
                    return
                documents += 1
                try:
                    canonical = _normalize_url(request.url)
                    parsed = urlsplit(request.url)
                    # Canonicalize input before launch; never forward redirect tracking.
                    if (parsed.query or parsed.fragment or canonical != request.url
                            or documents > MAX_REDIRECTS + 1):
                        raise ValueError
                except ValueError:
                    rejected.append("unsafe_redirect")
                    route.abort()
                    return
                route.continue_(headers={**request.headers, "cookie": ""})
            context.route("**/*", route_request)
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
            except Exception:
                if rejected:
                    raise FetchStop("unsafe_redirect") from None
                raise
            if response and response.status == 503 and response.headers.get("retry-after"):
                raise FetchStop("retry_after")
            html = page.content()
            if len(html.encode("utf-8")) > MAX_BYTES:
                raise FetchStop("response_too_large")
            return response.status if response else 0, html, _normalize_url(page.url)
        finally:
            browser.close()


_ENGINES = [("httpx", _fetch_httpx), ("curl_cffi", _fetch_curl_cffi),
            ("rnet", _fetch_rnet), ("playwright", _fetch_playwright)]


def fetch_amazon(url: str, *, include_html: bool = False,
                 max_engine: str | None = None) -> FetchOutcome:
    """Fetch a canonical Amazon product page; return explicit, sanitized failures."""
    started = time.monotonic()
    result = FetchOutcome(False, None, "none", False, "", None, None, None, None, 0, 0)
    try:
        result.url = _normalize_url(url)
    except ValueError:
        result.reason = "invalid_product_url"
        return result
    result.asin = extract_asin(result.url)
    names = [name for name, _ in _ENGINES]
    if max_engine is not None and max_engine not in names:
        result.reason = "invalid_max_engine"
        return result
    try:
        _proxy()
    except FetchStop as error:
        result.reason = str(error)
        return result
    engines = _ENGINES[:names.index(max_engine) + 1] if max_engine else _ENGINES
    for name, fetch in engines:
        result.engine = name
        try:
            status, html, final = fetch(result.url)
            final = _normalize_url(final)
        except ModuleNotFoundError:
            result.reason = f"{name}_not_installed"
            continue
        except FetchStop as error:
            result.reason = str(error)
            break
        except Exception as error:
            # Exception messages can contain proxy credentials or local paths.
            result.reason = f"{name}_error:{type(error).__name__}"
            continue
        result.status = status
        result.final_url = final
        result.blocked = looks_blocked(html, status) or status == 403
        result.title = page_title(html)
        result.product_title = product_title(html)
        result.html_bytes = len(html.encode("utf-8"))
        result.ok = status == 200 and not result.blocked and bool(result.product_title)
        if result.ok:
            result.asin = extract_asin(final)
            result.reason = None
            result.html = html if include_html else None
            break
        result.reason = "blocked" if result.blocked else (
            "product_not_found" if status == 200 else f"status_{status}")
        # Never hammer rate limits, missing products or other terminal client errors.
        if status == 429 or (400 <= status < 500 and status != 403):
            break
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result
