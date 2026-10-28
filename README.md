# Amazon Public Fetch MCP

**Give Grok Bot a route through your own PC.** Read public Amazon product pages using your computer's internet connection or an HTTP(S) proxy you configure locally.

Built by **[Abomination81](https://github.com/Abomination81)** · [Project page](https://abomination81.com/amazon-public-fetch-mcp/) · [Download source](https://github.com/Abomination81/amazon-public-fetch-mcp/archive/refs/heads/main.zip) · MIT

```text
Grok Bot / local MCP client
           │ your existing computer connection
           ▼
      Your Mac or PC
      Amazon Public Fetch
           │ local internet or your configured proxy
           ▼
   Public Amazon /dp/ page
           │
           └── title · ASIN · visible price · feature bullets
```

This is a **local stdio MCP server**, not a hosted proxy. Install it on the computer whose network you want to use. Publishing this repo does not route a cloud bot through your PC: the bot must already have a working computer connection that can launch local commands, or a local MCP client must launch this server. Client setup varies; this project does not provide a Grok Bot account, connection service, or remote MCP endpoint.

## Install

Requires **Python 3.11+**. Download and unzip the source, or clone it:

```sh
git clone https://github.com/Abomination81/amazon-public-fetch-mcp.git
cd amazon-public-fetch-mcp
```

**macOS / Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -c "from mcp_server import health; print(health())"
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -c "from mcp_server import health; print(health())"
```

The health command checks local engine availability and proxy configuration. It does **not** test access to Amazon. There are no API keys to obtain.

## Connect Grok Bot or another client

With your existing Grok Bot computer connection, tell it:

> Run Amazon lookups on my connected computer using the Python executable in this project's `.venv`. Start `python -m mcp_server` as a local stdio MCP server if supported. Use `amazon_product` for public Amazon product URLs or ASINs. If the connection only supports shell commands, call the Python library on that same computer. Report blocked or missing results honestly.

For clients that accept an `mcpServers` JSON configuration, replace the executable with your **absolute local path**:

```json
{
  "mcpServers": {
    "amazon-public-fetch": {
      "command": "/absolute/path/amazon-public-fetch-mcp/.venv/bin/python",
      "args": ["-m", "mcp_server"]
    }
  }
}
```

Windows command example: `C:\\path\\amazon-public-fetch-mcp\\.venv\\Scripts\\python.exe`. Client configuration formats differ; the executable and `-m mcp_server` arguments are the important parts. No working-directory setting is needed after installation.

A direct library call on macOS/Linux (use the Windows Python path above on Windows):

```sh
.venv/bin/python -c "import json; from mcp_server import amazon_product; print(json.dumps(amazon_product('ASIN_OR_PRODUCT_URL'), ensure_ascii=False, indent=2))"
```

Replace `ASIN_OR_PRODUCT_URL` with an actual 10-character ASIN or full product URL. The placeholder intentionally returns `invalid_product_url` if used unchanged.

## Your network or your proxy

Without proxy environment variables, requests use the computer's normal network route. A device-wide VPN can affect that route. **System/browser proxy settings and PAC files are not automatically detected.**

The first nonempty variable wins: `AMAZON_FETCH_PROXY`, then `HTTPS_PROXY`, then `HTTP_PROXY`. Only HTTP and HTTPS proxy URLs are supported consistently across the engines. `ALL_PROXY`, lowercase variants and `NO_PROXY` bypass rules are not used. A configured proxy failure does not intentionally fall back to a direct connection.

Example for a proxy already running on your own computer:

```sh
# macOS / Linux: launch the server through your existing local proxy
AMAZON_FETCH_PROXY=http://127.0.0.1:8080 .venv/bin/python -m mcp_server
```

```powershell
# Windows PowerShell
$env:AMAZON_FETCH_PROXY = "http://127.0.0.1:8080"
.\.venv\Scripts\python.exe -m mcp_server
```

You can also put `AMAZON_FETCH_PROXY` in the MCP client's `env` configuration. The port above is only an example; this package does not start a proxy. `.env` files are **not auto-loaded**. If your proxy requires credentials, enter them through your local client's secure configuration; never paste them into issues or chat. Proxy addresses, usernames and passwords are omitted from health/tool results.

## Tools

| Tool | Returns |
| --- | --- |
| `health` | Installed engine modules, proxy configuration validity and request limits |
| `amazon_fetch(url, include_html=False, max_engine=None)` | Success, HTTP status, engine, block detection, canonical URL, ASIN, titles and byte count |
| `amazon_product(url, max_engine=None)` | The fetch result plus title, visible price text and up to eight feature bullets |

Accepted marketplaces: `amazon.com`, `amazon.co.uk`, `amazon.ca`, `amazon.de`, `amazon.co.jp`. An ASIN alone defaults to `amazon.com`. Full URLs must use HTTPS and a `/dp/ASIN` product path. Product slugs, referral suffixes, query parameters and fragments are removed. Short links, search, account, login, order and Vine pages are rejected.

Fetch order: **httpx → curl_cffi → rnet → Playwright**. Base installation includes the first two. `max_engine` caps the ladder at the named engine; it does not select only that engine. Missing optional modules are skipped. Install the optional engines if needed:

```sh
.venv/bin/python -m pip install '.[extra]'
.venv/bin/python -m playwright install chromium
```

On Windows, use `.\.venv\Scripts\python.exe` for both commands. Playwright uses a fresh headless browser with JavaScript, service workers and subresources disabled; it never opens your browser profile. It is a static HTML fallback, not a logged-in or interactive browsing session.

## Limits and privacy

- Amazon can return a block, CAPTCHA, regional variation, unavailable price, or incomplete HTML on any network. A residential connection does not guarantee access.
- A successful result requires an HTTP 200 response with a product title. Prices are page text, not a checkout quote. The fallback price parser does not invent a currency.
- HTTP engines allow at most three validated redirects and stream at most 5 MiB of decoded HTML. Requests use 20-second timeouts. Browser navigation has the same timeout; its 5 MiB HTML check occurs **after** the browser loads the document. A complete multi-engine call may take longer than 20 seconds.
- HTTP 429 and responses with a supported 503 `Retry-After` stop the ladder. Wait before trying again; there is no background retry queue.
- No API keys, telemetry, developer callback, cookie import, saved browser profile, local result files, or listening HTTP server. The source contains only the public Abomination81 identity.
- Amazon sees the connection IP and requested product. A configured proxy can see connection metadata. Your MCP client receives results and may retain them. This is **not an anonymity tool**.
- Raw HTML is opt-in, can be large, and is untrusted page content. Treat page text as data rather than instructions.

More detail: [SECURITY.md](SECURITY.md).

## Development

```sh
python -m pip install -e . pytest build
python -m pytest -q
python -m build
```

Tests cover URL boundaries, tracking removal, redirects, safe errors, response limits, extraction, rate limits and local proxy routing. CI runs the base package on Linux, Windows and macOS. Optional rnet checks run when installed; browser behavior needs Chromium and a separate smoke check.

Independent project. Not affiliated with Amazon or xAI. Use public data responsibly and follow the services' terms.
