# Security and privacy

This package runs locally over standard input/output. It exposes three read-only MCP tools and does not start a public listener. Keep your computer-connection service and MCP client access restricted to people you trust.

## Data flow

The client supplies an ASIN or product URL. The package accepts an exact marketplace hostname and an HTTPS `/dp/` path, constructs a canonical product URL, and discards tracking parameters, fragments and referral suffixes before fetching. HTTP redirects pass through the same validation. Other sites and Amazon account routes are not supported.

HTTP sessions are temporary and do not load browser cookies. Playwright starts a fresh nonpersistent context, disables page scripts, service workers and subresources, and validates main-document navigation. It does not attach to an existing browser or read its profile. Host DNS, installed dependencies, local proxy configuration and the operating system remain trusted components; this is not an isolated network sandbox.

No project telemetry, developer callback, credential store or on-disk response cache is implemented. Amazon receives request metadata and the egress IP. A configured proxy receives connection metadata and handles any configured proxy credentials. MCP clients receive results and can log them. Optional raw HTML can include upstream request/session identifiers. The package does not make the user anonymous.

## Secrets

No API key is required. Proxy configuration comes only from the documented environment variables. Real `.env` files, keys, cookie exports and logs are ignored by Git. `.env.example` has only a loopback example; `.env` files are not auto-loaded. Error results contain fixed reason codes or exception class names, never raw exception messages, proxy URLs or credentials. Invalid URL input is not echoed. Dependencies and the host's diagnostics are outside that output guarantee.

## Bounds

A 5 MiB decoded body limit is enforced while streaming with the HTTP engines. Chromium first loads the document, then its serialized HTML size is checked; this is not a browser memory limit. Per-request/navigation timeouts are 20 seconds and at most three redirects are allowed. Multiple engines can extend total call duration. Calls are intended for individual lookups, not bulk scraping. There is no distributed rate limiter or hosted service.

## Reporting

For a vulnerability, use the repository's private security-reporting option if available. Otherwise open an issue requesting a private reporting channel without exploit details or secrets. Never include real proxy URLs, credentials, account data, browser cookies or private local paths in a public issue.
