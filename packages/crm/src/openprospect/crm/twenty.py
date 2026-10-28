"""Twenty CRM REST client (https://github.com/twentyhq/twenty).

Twenty allows 100 API calls a minute per key, so every call goes through `_req`, which spaces
calls out and waits + retries when the server answers 429."""

from __future__ import annotations

import time

import requests

from openprospect.core.config import env
from openprospect.core.log import warn


class Twenty:
    def __init__(self):
        self.base = env("TWENTY_URL").rstrip("/") + "/rest"
        key = env("TWENTY_API_KEY")
        self.ok = bool(key)
        self.h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self._last = 0.0

    def _req(self, method: str, url: str, timeout: int = 30, **kw) -> requests.Response:
        """Twenty allows 100 API calls a minute: space calls out, and wait + retry on a 429."""
        for attempt in range(4):
            wait = 0.65 - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = requests.request(method, url, headers=self.h, timeout=timeout, **kw)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))  # busy server: give it a moment
                continue
            if r.status_code != 429:
                return r
            time.sleep(20 * (attempt + 1))
        return r

    @staticmethod
    def _id(payload) -> str | None:
        """Twenty wraps created records as {"data": {"createCompany": {...}}}; find the id."""
        if isinstance(payload, dict):
            if "id" in payload and isinstance(payload["id"], str):
                return payload["id"]
            for v in payload.values():
                found = Twenty._id(v)
                if found:
                    return found
        return None

    def create(self, obj: str, body: dict, quiet_duplicate: bool = False) -> str | None:
        r = self._req("POST", f"{self.base}/{obj}", json=body)
        if r.status_code >= 400:
            if not (quiet_duplicate and "duplicate" in r.text.lower()):
                warn(f"Twenty {obj}: {r.status_code} {r.text[:200]}")
            return None
        return self._id(r.json())

    def patch(self, obj: str, rec_id: str, body: dict) -> bool:
        r = self._req("PATCH", f"{self.base}/{obj}/{rec_id}", json=body)
        if r.status_code >= 400:
            warn(f"Twenty {obj} update: {r.status_code} {r.text[:200]}")
        return r.status_code < 400

    def find_company(self, domain: str) -> str | None:
        """Twenty allows one company per website domain; find the one that already exists."""
        if not domain:
            return None
        for f in (f'domainName.primaryLinkUrl[eq]:"{domain}"', f'domainName.primaryLinkUrl[like]:"%{domain}%"'):
            r = self._req("GET", f"{self.base}/companies", params={"filter": f, "limit": 1})
            if r.status_code == 200:
                found = (r.json().get("data") or {}).get("companies") or []
                if found:
                    return found[0]["id"]
        return None

    def note(self, title: str, markdown: str, **targets) -> None:
        note_id = self.create("notes", {"title": title, "bodyV2": {"markdown": markdown}})
        if note_id:
            self.create("noteTargets", {"noteId": note_id, **targets})

    def check(self) -> bool:
        try:
            r = self._req("GET", f"{self.base}/companies?limit=1", timeout=10)
            return r.status_code == 200
        except requests.RequestException:
            return False
