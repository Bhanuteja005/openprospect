"""Pushes every scored lead into Twenty as:
  Company      name, website, address
  Person       the contact email / phone
  Opportunity  "<Business> - Tier A (82)" in the NEW stage, with an estimated deal value
  Note         why the lead scored high, the problems found on their site, the pitch angle

Then keeps the pipeline stage in sync: a reply moves the deal to SCREENING.
Stages: NEW -> SCREENING (replied) -> MEETING -> PROPOSAL -> CUSTOMER."""

from __future__ import annotations

import requests

from openprospect.core import db
from openprospect.core.config import settings
from openprospect.core.log import log, warn
from openprospect.core.text import short_name

from .twenty import Twenty

CALLING = {
    "IN": "+91",
    "US": "+1",
    "CA": "+1",
    "GB": "+44",
    "UK": "+44",
    "AU": "+61",
    "NZ": "+64",
    "IE": "+353",
    "AE": "+971",
    "SG": "+65",
    "ZA": "+27",
    "DE": "+49",
    "FR": "+33",
    "NL": "+31",
}


def phone_fields(raw: str | None, country: str | None = None) -> dict:
    """Local number -> Twenty's format, using the business's own country.
    '080 5550 1234' (IN) -> +91 8055501234, '(512) 555-0123' (US) -> +1 5125550123, '020 7946 0958' (GB) -> +44 2079460958"""
    agency = settings().get("agency", {})
    country = (country or agency.get("phone_country", "US")).upper()
    if country == "UK":
        country = "GB"
    calling = CALLING.get(country, agency.get("phone_calling_code", "+1"))
    raw = (raw or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return {}
    cc = calling.lstrip("+")
    if raw.startswith("+") or (digits.startswith(cc) and len(digits) > 10):
        if not digits.startswith(cc):  # number from another country: keep its own code
            for code in sorted({v.lstrip("+") for v in CALLING.values()}, key=len, reverse=True):
                if digits.startswith(code):
                    return {"primaryPhoneNumber": digits[len(code) :], "primaryPhoneCallingCode": "+" + code}
            return {"primaryPhoneNumber": digits}
        digits = digits[len(cc) :]
    digits = digits.lstrip("0")  # trunk 0 used in IN / GB / AU / NZ / IE
    return {"primaryPhoneNumber": digits, "primaryPhoneCountryCode": country, "primaryPhoneCallingCode": calling}


def _insights(lead) -> str:
    sig = db.loads(lead["signals"], {})
    pains = db.loads(lead["pain_points"], [])
    parts = sig.get("score_parts", {})
    lines = [
        f"**Score {lead['score']} / 100 - Tier {lead['tier']}**  (source: {lead['source']})",
        "",
        "Score breakdown: " + ", ".join(f"{k} {v}" for k, v in parts.items()),
        "",
        f"- Category: {lead['category'] or '-'}",
        f"- Google: {lead['rating'] or '-'} stars from {lead['reviews'] or 0} reviews  {lead['maps_url'] or ''}",
        f"- Phone: {lead['phone'] or '-'}",
        f"- Email: {lead['email'] or '-'} ({lead['email_status'] or 'none'})",
        f"- Website: {lead['website'] or 'NONE'}",
        f"- Problems found: {', '.join(p.replace('_', ' ') for p in pains) or 'none'}",
        f"- Site builder: {', '.join(sig.get('tech', [])) or '-'}; ads pixel: {sig.get('ads_pixel')}; "
        f"analytics: {sig.get('analytics')}; online booking: {sig.get('booking')}",
        f"- Socials: {', '.join(sig.get('socials', {}).values()) or '-'}",
        "",
        f"**Pitch:** {sig.get('offer', '')}",
        "",
        f"**Opening line used:** {lead['icebreaker'] or ''}",
    ]
    return "\n".join(lines)


def sync(conn, limit: int = 300) -> int:
    t = Twenty()
    if not t.ok:
        warn("TWENTY_API_KEY is empty in .env: skipping CRM sync (see docs/getting-started.md)")
        return 0
    if not t.check():
        warn("Twenty CRM is not reachable or the API key is wrong: skipping CRM sync")
        return 0
    cfg = settings()
    values = cfg.get("scoring", {}).get("deal_value", {})
    currency = cfg.get("agency", {}).get("currency", "USD")
    rows = conn.execute(
        "SELECT * FROM leads WHERE scored_at IS NOT NULL AND crm_synced_at IS NULL ORDER BY score DESC LIMIT ?",
        (limit,),
    ).fetchall()
    n = 0
    failed = 0
    for lead in rows:
        try:
            n += _sync_one(t, conn, lead, values, currency)
        except requests.RequestException as e:  # one slow call must not stop the whole sync
            failed += 1
            warn(f"CRM: {lead['name']}: {e}")
            if failed >= 5:
                warn("CRM: too many failures in a row; the rest wait for the next run")
                break
            continue
        failed = 0
        if n % 20 == 0:
            conn.commit()
    conn.commit()
    log(f"  CRM: {n} leads pushed to Twenty")
    return n


def _sync_one(t, conn, lead, values: dict, currency: str) -> int:
    address = {
        "addressStreet1": (lead["address"] or "")[:200],
        "addressCity": lead["city"] or "",
        "addressCountry": lead["country"] or "",
    }
    company = {"name": lead["name"], "address": address}
    if lead["website"]:
        company["domainName"] = {"primaryLinkUrl": lead["website"]}
    cid = t.create("companies", company, quiet_duplicate=True)
    if not cid:  # same website already in the CRM (e.g. another branch): attach to it
        cid = t.find_company(lead["domain"])
    if not cid:
        return 0
    pid = None
    if lead["email"] or lead["phone"]:
        person = {
            "name": {"firstName": "Contact", "lastName": (lead["name"] or "")[:60]},
            "companyId": cid,
            "jobTitle": "Owner / Manager",
        }
        if lead["email"]:
            person["emails"] = {"primaryEmail": lead["email"]}
        if lead["phone"]:
            person["phones"] = phone_fields(lead["phone"], lead["country"])
        pid = t.create("people", person)
        if not pid and "phones" in person and lead["email"]:
            person.pop("phones")  # bad number: save the contact without it
            pid = t.create("people", person)
    opp = {
        "name": f"{short_name(lead['name'])} - Tier {lead['tier']} ({lead['score']})",
        "stage": "NEW",
        "companyId": cid,
        "amount": {"amountMicros": int(values.get(lead["tier"], 0)) * 1_000_000, "currencyCode": currency},
    }
    if pid:
        opp["pointOfContactId"] = pid
    oid = t.create("opportunities", opp)
    t.note(f"Lead insights - Tier {lead['tier']}", _insights(lead), targetCompanyId=cid)
    db.update(
        conn,
        lead["id"],
        crm_company_id=cid,
        crm_person_id=pid,
        crm_opportunity_id=oid,
        crm_synced_at=db.now(),
        crm_stage="NEW",
    )
    return 1


def set_stage(conn, lead, stage: str, note: str | None = None) -> None:
    """Move a lead's deal (e.g. to SCREENING when they reply)."""
    if not lead["crm_opportunity_id"]:
        return
    t = Twenty()
    if not t.ok:
        return
    if lead["crm_stage"] != stage and t.patch("opportunities", lead["crm_opportunity_id"], {"stage": stage}):
        db.update(conn, lead["id"], crm_stage=stage)
    if note:
        t.note(note.split("\n", 1)[0][:80], note, targetOpportunityId=lead["crm_opportunity_id"])
