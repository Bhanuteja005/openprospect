"""Fetches web pages: directly first, through Firecrawl when it is running and a site needs it.

Firecrawl (https://github.com/firecrawl/firecrawl, `docker compose --profile firecrawl up -d`)
renders JavaScript-only sites and gets past simple bot blocks. Without it the built-in reader
handles most small-business sites."""

from __future__ import annotations

import time

import requests

from openprospect.core.config import env, settings
from openprospect.core.http import is_up, session
from openprospect.core.log import log


class Reader:
    """Fetches pages directly; falls back to Firecrawl when available."""

    def __init__(self):
        self.s = session()
        self.timeout = float(settings().get("enrich", {}).get("timeout_seconds", 15))
        self.firecrawl = env("FIRECRAWL_URL").rstrip("/")
        self.firecrawl_up = bool(self.firecrawl) and is_up(self.firecrawl, timeout=2)
        if self.firecrawl_up:
            log("  Firecrawl is running: using it for JavaScript-heavy or blocked sites")

    def direct(self, url: str) -> tuple[str, str, float]:
        """Returns (final_url, html, seconds). Raises on failure."""
        t0 = time.monotonic()
        r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
        elapsed = time.monotonic() - t0
        r.raise_for_status()
        self.last_headers = dict(r.headers)
        self.last_tls = None
        try:  # TLS version the server negotiated (normal handshake, nothing extra sent)
            self.last_tls = r.raw.connection.sock.version()
        except Exception:
            pass
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return r.url, "", elapsed
        r.encoding = r.encoding or r.apparent_encoding
        return r.url, r.text, elapsed

    def via_firecrawl(self, url: str) -> str:
        if not self.firecrawl_up:
            return ""
        try:
            r = requests.post(
                f"{self.firecrawl}/v1/scrape",
                json={"url": url, "formats": ["rawHtml"], "onlyMainContent": False, "timeout": 30000},
                timeout=60,
            )
            data = r.json().get("data") or {}
            return data.get("rawHtml") or data.get("html") or ""
        except (requests.RequestException, ValueError):
            return ""

    def fetch(self, url: str) -> tuple[str, str, float | None, bool]:
        """Returns (final_url, html, seconds or None, ok)."""
        self.last_error = None
        try:
            final, html, secs = self.direct(url)
            # Very small pages are usually JS shells (Wix, React). Let Firecrawl render them.
            if len(html) < 3000 and self.firecrawl_up:
                html = self.via_firecrawl(final) or html
            return final, html, secs, True
        except requests.exceptions.SSLError:
            self.last_error = "ssl"  # browsers show "Your connection is not private"
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            # 401/403/429 = the site blocks bots but works for people: not a problem to pitch
            self.last_error = "blocked" if code in (401, 403, 406, 429) else "down"
        except requests.exceptions.ConnectionError as e:
            self.last_error = "dns" if "NameResolution" in str(e) or "getaddrinfo" in str(e) else "down"
        except requests.RequestException:
            self.last_error = "down"
        html = self.via_firecrawl(url)
        return url, html, None, bool(html)
