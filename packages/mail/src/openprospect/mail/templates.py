"""Email bodies: the HTML files in templates/emails/ plus per-lead attributes.

Two kinds of placeholder:
  [[SENDER_NAME]], [[AGENCY_WEBSITE_TEXT]], ...   filled here from settings.yaml (`agency:`)
  {{ .Subscriber.Attribs.first_line }}, ...        filled by Listmonk for each recipient"""

from __future__ import annotations

from openprospect.core import db
from openprospect.core.config import paths, settings
from openprospect.core.text import short_name, subject_name


def attribs_for(lead) -> dict:
    sig = db.loads(lead["signals"], {})
    return {
        "business": short_name(lead["name"]) or lead["name"] or "",
        "first_line": lead["icebreaker"] or "",
        "offer": sig.get("offer", ""),
        "subject": sig.get("subject") or f"quick idea for {short_name(lead['name'])}",
        "short": subject_name(lead["name"]),
        "problem": sig.get("problem", "this"),
        "city": lead["city"] or "",
        "category": (lead["category"] or "").split(",")[0],
        "rating": lead["rating"] or "",
        "reviews": lead["reviews"] or 0,
        "website": lead["website"] or "",
        "tier": lead["tier"] or "",
        "score": lead["score"] or 0,
        "lead_id": lead["id"],
    }


def render_body(step: int) -> str:
    """Load a template file and fill in the [[AGENCY_...]] placeholders from settings.yaml.
    {{ .Subscriber.Attribs.* }} placeholders are left for Listmonk to fill per person."""
    cfg = settings()
    tpl = cfg["sending"]["templates"][step]
    text = (paths.home / tpl["file"]).read_text(encoding="utf-8")
    agency = cfg.get("agency", {})
    cal = agency.get("calendar_link") or ""
    repl = {
        "[[SENDER_NAME]]": agency.get("sender_name", ""),
        "[[SENDER_INTRO]]": agency.get("intro", ""),
        "[[AGENCY_NAME]]": agency.get("name", ""),
        "[[AGENCY_WEBSITE]]": agency.get("website", ""),
        # plain text, not a link: fewer links = better inbox placement
        "[[AGENCY_WEBSITE_TEXT]]": agency.get("website", "").replace("https://", "").replace("http://", "").rstrip("/"),
        "[[POSTAL_ADDRESS]]": agency.get("postal_address", ""),
        "[[CALENDAR_LINE]]": f'Or grab a time that suits you here: <a href="{cal}">{cal}</a>' if cal else "",
    }
    if not repl["[[POSTAL_ADDRESS]]"].strip() or "Your street" in repl["[[POSTAL_ADDRESS]]"]:
        # no address set: drop that line from the footer
        text = text.replace("[[POSTAL_ADDRESS]]<br>\n", "")
        text = text.replace('<p style="font-size:12px;color:#888;">[[POSTAL_ADDRESS]]</p>', "")
        repl["[[POSTAL_ADDRESS]]"] = ""
    for k, v in repl.items():
        text = text.replace(k, v)
    return text
