"""Job boards: fresh remote / freelance postings from free, keyless sources.

Remotive, Remote OK, Himalayas, We Work Remotely (RSS), Jobicy, Working Nomads, and the
Hacker News "Who is hiring?" / "Freelancer? Seeking freelancer?" threads. Every fetcher
returns the same posting shape (see `_posting`), and one dead source never stops the hunt."""

from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from openprospect.core.log import warn

from .filters import role_ok, rules


def plain(html_text: str) -> str:
    t = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", html_text or "", flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def _posting(source, pid, company, title, url, location, posted, text, apply_url="", website=""):
    return {
        "source": source,
        "id": f"{source}:{pid}",
        "company": (company or "").strip(),
        "title": (title or "").strip(),
        "url": url,
        "location": location or "",
        "posted": posted,
        "text": text[:6000],
        "apply_url": apply_url or "",
        "website": website or "",
    }


def fetch_remotive(s, max_age_days: int = 3) -> list[dict]:
    out = []
    for cat in ("software-dev", "ai-ml", "devops"):
        try:
            jobs = s.get(f"https://remotive.com/api/remote-jobs?category={cat}", timeout=30).json().get("jobs", [])
        except Exception as e:  # noqa: BLE001 - one dead source must not stop the hunt
            warn(f"remotive {cat}: {e}")
            continue
        for j in jobs:
            out.append(
                _posting(
                    "remotive",
                    j.get("id"),
                    j.get("company_name"),
                    j.get("title"),
                    j.get("url"),
                    j.get("candidate_required_location"),
                    j.get("publication_date", "")[:10],
                    plain(j.get("description", "")),
                )
            )
    return out


def fetch_remoteok(s, max_age_days: int = 3) -> list[dict]:
    try:
        data = s.get("https://remoteok.com/api", timeout=30).json()[1:]
    except Exception as e:  # noqa: BLE001
        warn(f"remoteok: {e}")
        return []
    out = []
    for j in data:
        posted = datetime.fromtimestamp(int(j.get("epoch", 0)), UTC).strftime("%Y-%m-%d")
        out.append(
            _posting(
                "remoteok",
                j.get("id"),
                j.get("company"),
                j.get("position"),
                j.get("url"),
                j.get("location"),
                posted,
                plain(j.get("description", "")),
                j.get("apply_url"),
            )
        )
    return out


def fetch_himalayas(s, max_age_days: int = 3, pages: int = 6) -> list[dict]:
    out, cursor = [], ""
    cutoff = time.time() - max_age_days * 86400
    for _ in range(pages):
        try:
            j = s.get(
                "https://himalayas.app/jobs/api?limit=100" + (f"&cursor={cursor}" if cursor else ""), timeout=30
            ).json()
        except Exception as e:  # noqa: BLE001
            warn(f"himalayas: {e}")
            break
        for x in j.get("jobs", []):
            if "Developer" not in (x.get("parentCategories") or []) and not role_ok(x.get("title", "")):
                continue
            restr = x.get("locationRestrictions") or []
            loc = "Worldwide" if not restr else ", ".join(restr)
            posted = datetime.fromtimestamp(int(x.get("pubDate", 0)), UTC).strftime("%Y-%m-%d")
            out.append(
                _posting(
                    "himalayas",
                    x.get("guid"),
                    x.get("companyName"),
                    x.get("title"),
                    x.get("guid"),
                    loc,
                    posted,
                    plain(x.get("description", "")),
                    x.get("applicationLink"),
                )
            )
        cursor = j.get("nextCursor") or ""
        last = (j.get("jobs") or [{}])[-1].get("pubDate")
        if not cursor or (last and int(last) < cutoff):
            break
    return out


def fetch_wwr(s, max_age_days: int = 3) -> list[dict]:
    out = []
    for cat in (
        "remote-full-stack-programming-jobs",
        "remote-back-end-programming-jobs",
        "remote-front-end-programming-jobs",
        "remote-devops-sysadmin-jobs",
    ):
        try:
            root = ET.fromstring(s.get(f"https://weworkremotely.com/categories/{cat}.rss", timeout=30).content)
        except Exception as e:  # noqa: BLE001
            warn(f"wwr {cat}: {e}")
            continue
        for it in root.iter("item"):
            title = it.findtext("title") or ""
            company, _, role = title.partition(":")
            try:
                posted = datetime.strptime(
                    (it.findtext("pubDate") or "")[:25].strip(), "%a, %d %b %Y %H:%M:%S"
                ).strftime("%Y-%m-%d")
            except ValueError:
                posted = ""
            out.append(
                _posting(
                    "wwr",
                    it.findtext("guid") or it.findtext("link"),
                    company,
                    role or title,
                    it.findtext("link"),
                    it.findtext("region") or "",
                    posted,
                    plain(it.findtext("description") or ""),
                )
            )
    return out


def fetch_jobicy(s, max_age_days: int = 3) -> list[dict]:
    out = []
    for tag in ("developer", "python", "react", "ai"):
        try:
            jobs = s.get(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}", timeout=30).json().get("jobs", [])
        except Exception as e:  # noqa: BLE001
            warn(f"jobicy {tag}: {e}")
            continue
        for j in jobs:
            kind = ", ".join(j.get("jobType") or [])
            out.append(
                _posting(
                    "jobicy",
                    j.get("id"),
                    j.get("companyName"),
                    j.get("jobTitle"),
                    j.get("url"),
                    j.get("jobGeo"),
                    (j.get("pubDate") or "")[:10],
                    f"{kind}\n" + plain(j.get("jobDescription", "")),
                )
            )
    return out


def fetch_workingnomads(s, max_age_days: int = 3) -> list[dict]:
    try:
        jobs = s.get("https://www.workingnomads.com/api/exposed_jobs/", timeout=30).json()
    except Exception as e:  # noqa: BLE001
        warn(f"workingnomads: {e}")
        return []
    return [
        _posting(
            "workingnomads",
            j.get("url"),
            j.get("company_name"),
            j.get("title"),
            j.get("url"),
            j.get("location"),
            (j.get("pub_date") or "")[:10],
            plain(j.get("description", "")),
        )
        for j in jobs
        if j.get("category_name") == "Development"
    ]


def fetch_hn(s, max_age_days: int = 3) -> list[dict]:
    """Top-level comments from the latest 'Who is hiring?' and 'Freelancer? Seeking freelancer?'."""
    out = []
    try:
        hits = (
            s.get(
                "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10", timeout=30
            )
            .json()
            .get("hits", [])
        )
    except Exception as e:  # noqa: BLE001
        warn(f"hn: {e}")
        return out
    role_re = rules().roles
    for kind in ("who is hiring", "seeking freelancer"):
        story = next((h for h in hits if kind in (h.get("title") or "").lower()), None)
        if not story:
            continue
        sid = story["objectID"]
        since = int(story.get("created_at_i") or 0)  # the whole month's thread; the seen file stops repeats
        try:
            com = (
                s.get(
                    f"https://hn.algolia.com/api/v1/search_by_date?tags=comment,story_{sid}"
                    f"&numericFilters=created_at_i>{since}&hitsPerPage=1000",
                    timeout=30,
                )
                .json()
                .get("hits", [])
            )
        except Exception as e:  # noqa: BLE001
            warn(f"hn comments: {e}")
            continue
        for c in com:
            if str(c.get("parent_id")) != str(sid):
                continue
            text = plain(c.get("comment_text") or "")
            head = text[:300].lower()
            # people offering themselves ("SEEKING WORK", "Location: ... Résumé:") are not hiring
            if "seeking work" in head or re.match(r"\s*location\s*:", head):
                continue
            if kind == "seeking freelancer" and "seeking freelancer" not in head:
                continue
            # the thread asks posters to write REMOTE when remote is possible; no REMOTE = onsite
            if "remote" not in head:
                continue
            first = text.split("\n", 1)[0]
            parts = [p.strip() for p in first.split("|")]
            company = parts[0][:80] if parts else ""
            title = next((p for p in parts[1:] if role_re.search(p)), first[:120])
            loc = " | ".join(p for p in parts if re.search(r"remote|onsite|hybrid", p, re.I))
            out.append(
                _posting(
                    "hn",
                    c["objectID"],
                    company,
                    title,
                    f"https://news.ycombinator.com/item?id={c['objectID']}",
                    loc,
                    datetime.fromtimestamp(c["created_at_i"], UTC).strftime("%Y-%m-%d"),
                    text,
                )
            )
    return out


BOARDS = [
    ("Hacker News", fetch_hn),
    ("Remotive", fetch_remotive),
    ("Remote OK", fetch_remoteok),
    ("Himalayas", fetch_himalayas),
    ("We Work Remotely", fetch_wwr),
    ("Jobicy", fetch_jobicy),
    ("Working Nomads", fetch_workingnomads),
]
