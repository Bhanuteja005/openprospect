"""Does a posting fit you? Role, location and stack rules, all from settings.yaml (`jobs:`).

  roles            regex fragments for titles you want ("full[- ]?stack", "python", ...)
  exclude_roles    title words that rule a posting out ("sales", "designer", ...)
  stack            keywords that raise a posting's fit score
  open_to          words meaning you may apply ("worldwide", "anywhere", your country...)
  blocked_regions  region words that exclude you unless an open_to word is also present

Missing keys fall back to the defaults below, so the track works before you configure it."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from openprospect.core.config import settings

DEFAULT_ROLES = [
    r"full[- ]?stack",
    r"front[- ]?end",
    r"back[- ]?end",
    r"software (engineer|developer)",
    r"web developer",
    r"ai engineer",
    r"ml engineer",
    r"llm",
    r"machine learning engineer",
    r"genai",
    r"applied ai",
    r"react",
    r"next\.?js",
    r"node(\.js)?",
    r"python",
    r"typescript",
    r"javascript",
    r"product engineer",
    r"founding engineer",
    r"automation engineer",
    r"ai agents?",
]
DEFAULT_EXCLUDE = [
    "sales",
    r"account (executive|manager)",
    "marketing",
    "designer",
    "recruiter",
    r"customer (success|support)",
    r"support (engineer|specialist|agent)",
    "writer",
    "copywriter",
    "legal",
    "counsel",
    "accountant",
    "finance",
    "bookkeep",
    "data entry",
    "annotation",
    "annotator",
    "trainer",
    "tutor",
    "teacher",
    "nurse",
    "ios",
    "android",
    "embedded",
    "firmware",
    "hardware",
    "mechanical",
    "electrical",
    "salesforce",
    "sap",
    "qa",
    "tester",
    "manual test",
    "devops",
    "sre",
    "site reliability",
    "data engineer",
    "analytics",
    "data analyst",
    "security engineer",
    r"cloud (infrastructure|engineer)",
    "network",
    "solutions engineer",
    "director",
    "vp",
    "manager",
]
DEFAULT_STACK = [
    "react",
    "next.js",
    "nextjs",
    "typescript",
    "javascript",
    "node",
    "python",
    "fastapi",
    "django",
    "flask",
    "llm",
    "openai",
    "gpt",
    "claude",
    "langchain",
    "langgraph",
    "rag",
    "agent",
    "ai",
    "full-stack",
    "full stack",
    "fullstack",
    "postgres",
    "mongodb",
    "aws",
    "docker",
    "voice",
    "automation",
    "tailwind",
    "saas",
]
DEFAULT_OPEN_TO = ["worldwide", "anywhere", "global", "globally", "remote (global)", "all countries", "any location"]
DEFAULT_BLOCKED = [
    "us",
    "u.s.",
    "usa",
    "united states",
    "canada",
    "north america",
    "americas",
    "amer",
    "latam",
    "brazil",
    "mexico",
    "europe",
    "european",
    "eu",
    "emea",
    "cet",
    "cest",
    "gmt",
    "uk",
    "germany",
    "poland",
    "romania",
    "spain",
    "france",
    "ireland",
    "netherlands",
    "portugal",
    "residents",
    "select countries",
    "eastern",
    "central",
    "pacific",
    "est",
    "pst",
]


@dataclass(frozen=True)
class Rules:
    roles: re.Pattern
    exclude: re.Pattern
    stack: tuple[str, ...]
    open_to: re.Pattern
    regions: re.Pattern
    geo_block: re.Pattern


def _words(words) -> str:
    """Alternation of literal words, matched as whole words (works for 'u.s.' too)."""
    return "(?<![a-z])(" + "|".join(re.escape(str(w).lower()) for w in words) + ")(?![a-z])"


def _build(cfg: dict) -> Rules:
    roles = cfg.get("roles") or DEFAULT_ROLES
    exclude = cfg.get("exclude_roles") or DEFAULT_EXCLUDE
    regions = cfg.get("blocked_regions") or DEFAULT_BLOCKED
    open_to = cfg.get("open_to") or DEFAULT_OPEN_TO
    r = "(" + "|".join(re.escape(str(w).lower()) for w in regions) + ")"
    # explicit restrictions: "US only", "must reside in the EU", "US citizens", "remote (Canada)"...
    block = "|".join(
        [
            rf"(?<![a-z]){r} only(?![a-z])",
            rf"must (be|reside|live) in (the )?{r}(?![a-z])",
            rf"(?<![a-z]){r}[- ]based(?![a-z])",
            rf"based in (the )?{r}(?![a-z])",
            rf"(?<![a-z]){r} citizens?(?![a-z])",
            rf"(?<![a-z]){r} time ?zones? only",
            rf"(?<![a-z]){r} remote(?![a-z])",
            rf"remote[ -]{r}(?![a-z])",
            rf"remote[ -]?\({r}(?![a-z])[^)]*\)",
        ]
    )
    return Rules(
        roles=re.compile(r"\b(" + "|".join(roles) + r")\b", re.I),
        exclude=re.compile(r"\b(" + "|".join(exclude) + r")\b", re.I),
        stack=tuple(str(k).lower() for k in (cfg.get("stack") or DEFAULT_STACK)),
        open_to=re.compile(_words(open_to), re.I),
        regions=re.compile(_words(regions), re.I),
        geo_block=re.compile(block, re.I),
    )


_cache: tuple[dict, Rules] | None = None


def rules() -> Rules:
    """Compiled once per settings load (settings() returns a new dict after a reload)."""
    global _cache
    try:
        cfg = settings()
    except FileNotFoundError:
        cfg = {}
    # keep the settings dict itself (not its id) so a reloaded dict can never be mistaken for it
    if _cache is None or _cache[0] is not cfg:
        _cache = (cfg, _build(cfg.get("jobs") or {}))
    return _cache[1]


@functools.lru_cache(maxsize=512)
def _word(keyword: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])")


def fit_score(text: str) -> int:
    """How many of your stack keywords the posting mentions, as whole words ("ai" not in "maintain")."""
    low = text.lower()
    return sum(1 for k in rules().stack if _word(k).search(low))


def role_ok(title: str, text: str = "") -> bool:
    r = rules()
    head = f"{title} {text[:300]}"
    return bool(r.roles.search(head)) and not r.exclude.search(title)


def geo_ok(location: str, text: str = "", lenient: bool = False) -> bool:
    """lenient: Hacker News posts say REMOTE plus a restriction in brackets when there is one,
    so no blocked restriction means open to anyone."""
    r = rules()
    loc = location or ""
    if r.geo_block.search(loc) or r.geo_block.search(text[:1500]):
        return False
    if r.regions.search(loc) and not r.open_to.search(loc):  # "REMOTE (CET)", "US / Canada", "Poland"
        return False
    if lenient or not loc.strip() or r.open_to.search(loc):
        return True
    # a location string that names other places only (e.g. "Berlin") is a no
    return False
