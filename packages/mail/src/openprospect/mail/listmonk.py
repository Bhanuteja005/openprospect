"""Listmonk client (https://github.com/knadh/listmonk): the self-hosted sender for the
agency sequence. One-time setup puts your SMTP inbox and a human sending speed into it."""

from __future__ import annotations

import re

import requests

from openprospect.core import db
from openprospect.core.config import env, settings, write_env_value
from openprospect.core.log import log, warn

from .templates import attribs_for

PLAIN_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.5; color: #222;">
{{ template "content" . }}
</body></html>
"""


class ListmonkError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Listmonk:
    def __init__(self):
        self.base = env("LISTMONK_URL").rstrip("/") + "/api"
        user, token = env("LISTMONK_API_USER"), env("LISTMONK_API_TOKEN")
        self.ok = bool(user and token)
        self.auth = (user, token)

    def req(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.base}{path}", auth=self.auth, timeout=60, **kw)
        if r.status_code >= 400:
            raise ListmonkError(r.status_code, f"Listmonk {method} {path}: {r.status_code} {r.text[:300]}")
        return (r.json() or {}).get("data") if r.content else None

    def check(self) -> bool:
        import time

        # Listmonk restarts itself after a settings change; give it a moment.
        for _attempt in range(6):
            try:
                self.req("GET", "/lists?per_page=1")
                return True
            except Exception:
                time.sleep(5)
        return False

    # ---------- one-time setup ----------
    def configure(self) -> None:
        """Put your SMTP inbox and safe sending speed into Listmonk's settings."""
        s = self.req("GET", "/settings")
        frm = env("FROM_EMAIL") or env("SMTP_USER")
        sender = settings().get("agency", {}).get("sender_name", "")
        if frm:
            s["app.from_email"] = f"{sender} <{frm}>" if sender else frm
        s["app.concurrency"] = 1
        s["app.message_rate"] = 1
        # never more than this many emails per hour, so sends look human
        s["app.message_sliding_window"] = True
        s["app.message_sliding_window_duration"] = "1h"
        s["app.message_sliding_window_rate"] = 20
        # Listmonk's own unsubscribe header points at localhost, which recipients can't open.
        # We add a mailto: unsubscribe header to each campaign instead.
        s["privacy.unsubscribe_header"] = False
        s["app.send_optin_confirmation"] = False
        host, user, pw = env("SMTP_HOST"), env("SMTP_USER"), env("SMTP_PASSWORD")
        if host and user and pw:
            port = int(env("SMTP_PORT") or 587)
            smtp = {
                "name": "primary",
                "enabled": True,
                "host": host,
                "hello_hostname": "",
                "port": port,
                "auth_protocol": "login",
                "username": user,
                "password": pw,
                "email_headers": [],
                "max_conns": 2,
                "max_msg_retries": 2,
                "msg_retry_delay": "30s",
                "idle_timeout": "15s",
                "wait_timeout": "5s",
                "tls_type": "TLS" if port == 465 else "STARTTLS",
                "tls_skip_verify": False,
            }
            old = s.get("smtp") or []
            if old and old[0].get("uuid"):
                smtp["uuid"] = old[0]["uuid"]
            s["smtp"] = [smtp] + [{**o, "enabled": False} for o in old[1:]]
        else:
            warn("SMTP_USER / SMTP_PASSWORD not set in .env: Listmonk can't send until you add them")
        self.req("PUT", "/settings", json=s)
        log("  Listmonk configured (sender, SMTP, 20 emails/hour max)")

    def template_id(self, conn) -> int:
        tid = db.kv_get(conn, "listmonk_template_id")
        if tid:
            return int(tid)
        data = self.req(
            "POST", "/templates", json={"name": "OpenProspect (plain)", "type": "campaign", "body": PLAIN_TEMPLATE}
        )
        db.kv_set(conn, "listmonk_template_id", str(data["id"]))
        conn.commit()
        return int(data["id"])

    # ---------- subscribers ----------
    def find_subscriber(self, email: str) -> int | None:
        q = f"subscribers.email = '{email.replace(chr(39), '')}'"
        data = self.req("GET", "/subscribers", params={"query": q, "per_page": 1})
        results = (data or {}).get("results") or []
        return results[0]["id"] if results else None

    def upsert_subscriber(self, lead, list_id: int) -> int:
        attribs = attribs_for(lead)
        body = {
            "email": lead["email"],
            "name": lead["name"] or lead["email"],
            "status": "enabled",
            "lists": [list_id],
            "attribs": attribs,
            "preconfirm_subscriptions": True,
        }
        try:
            return self.req("POST", "/subscribers", json=body)["id"]
        except RuntimeError as e:
            if "409" not in str(e) and "exists" not in str(e).lower():
                raise
        sid = lead["listmonk_id"] or self.find_subscriber(lead["email"])
        self.req("PATCH", f"/subscribers/{sid}", json={"attribs": attribs})
        self.req(
            "PUT",
            "/subscribers/lists",
            json={"ids": [sid], "action": "add", "target_list_ids": [list_id], "status": "confirmed"},
        )
        return sid

    def remove_from_lists(self, sid: int, list_ids: list[int]) -> None:
        """Take someone out of lists whose campaigns haven't reached them yet."""
        if list_ids:
            self.req("PUT", "/subscribers/lists", json={"ids": [sid], "action": "remove", "target_list_ids": list_ids})

    def blocklist(self, sid: int) -> None:
        try:
            self.req("PUT", f"/subscribers/{sid}/blocklist")
        except RuntimeError as e:
            warn(str(e))


def create_api_user() -> bool:
    """Log in as the Listmonk admin from .env and create the API user the pipeline uses."""
    base = env("LISTMONK_URL").rstrip("/")
    s = requests.Session()
    page = s.get(f"{base}/admin/login", timeout=30).text
    form = {
        "username": env("LISTMONK_ADMIN_USER") or "admin",
        "password": env("LISTMONK_ADMIN_PASSWORD"),
        "next": "/admin",
    }
    m = re.search(r'name="nonce"\s+value="([^"]+)"', page)
    if m:
        form["nonce"] = m.group(1)
    r = s.post(f"{base}/admin/login", data=form, timeout=30, allow_redirects=False)
    if r.status_code not in (200, 302) or "session" not in "".join(s.cookies.keys()).lower():
        warn(f"Listmonk admin login failed ({r.status_code}). Create an API user by hand (docs/getting-started.md).")
        return False
    r = s.post(
        f"{base}/api/users",
        json={
            "username": "openprospect-api",
            "name": "openprospect-api",
            "type": "api",
            "status": "enabled",
            "user_role_id": 1,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        warn(f"Could not create Listmonk API user: {r.status_code} {r.text[:200]}")
        return False
    token = r.json()["data"].get("password")
    if not token:
        warn("Listmonk did not return an API token")
        return False
    write_env_value("LISTMONK_API_USER", "openprospect-api")
    write_env_value("LISTMONK_API_TOKEN", token)
    log("  Listmonk API user created and saved to .env")
    return True


def setup(conn) -> None:
    lm = Listmonk()
    if not lm.ok and create_api_user():
        lm = Listmonk()
    if not lm.ok or not lm.check():
        warn("Listmonk API user/token missing or wrong in .env (see docs/getting-started.md)")
        return
    lm.configure()
    lm.template_id(conn)
