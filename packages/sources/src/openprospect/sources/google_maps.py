"""Google Maps leads via gosom/google-maps-scraper (https://github.com/gosom/google-maps-scraper).

Runs the scraper in Docker for every new search in config/queries.txt (and, when that runs
out, auto-generated "niche in city" searches) and loads the results - name, phone, website,
rating, reviews, emails - into the lead store. Each search is only ever scraped once."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openprospect.core import db
from openprospect.core.config import env, paths, settings
from openprospect.core.log import log, warn
from openprospect.core.text import city_from_address, clean_emails, domain_of, normalize_url

DEFAULT_IMAGE = "gosom/google-maps-scraper"


def raw_dir() -> Path:
    return paths.data / "raw"


def read_queries() -> list[str]:
    if not paths.queries_file.exists():
        return []
    out = []
    for line in paths.queries_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def auto_queries(skip: set, n: int) -> list[str]:
    """Next unused 'niche in city' searches, rotating through countries so each day has a mix.
    `weights` gives a country more picks per round, e.g. {US: 2} -> 2 US, 1 GB, 1 AU, 2 US, ..."""
    cfg = settings().get("scrape", {}).get("auto_queries") or {}
    if not cfg.get("enabled") or n <= 0:
        return []
    niches = cfg.get("niches") or []
    per_country = []
    for _country, cities in (cfg.get("cities") or {}).items():
        per_country.append([f"{niche} in {city}" for city in cities for niche in niches])
    weights = {str(k): int(v) for k, v in (cfg.get("weights") or {}).items()}
    names = list((cfg.get("cities") or {}).keys())
    out: list[str] = []
    idx = [0] * len(per_country)
    while len(out) < n and any(i < len(lst) for i, lst in zip(idx, per_country, strict=False)):
        for k, lst in enumerate(per_country):
            for _ in range(weights.get(names[k], 1)):
                while idx[k] < len(lst) and lst[idx[k]] in skip:
                    idx[k] += 1
                if idx[k] < len(lst) and len(out) < n:
                    out.append(lst[idx[k]])
                    skip.add(lst[idx[k]])
                    idx[k] += 1
    return out


def pending_queries(conn) -> list[str]:
    """Searches not scraped yet, at most scrape.max_queries_per_run per run so the daily job
    finishes in time; the rest are picked up by the next runs."""
    done = {r["query"] for r in conn.execute("SELECT query FROM done_queries")}
    todo = [q for q in read_queries() if q not in done]
    cap = int(settings().get("scrape", {}).get("max_queries_per_run", 8))
    if len(todo) < cap:
        todo += auto_queries(done | set(todo), cap - len(todo))
    if len(todo) > cap:
        log(f"  {len(todo)} searches waiting; doing {cap} now, the rest in the next runs")
    return todo[:cap]


def run_scraper(queries: list[str], out_csv: Path) -> bool:
    cfg = settings().get("scrape", {})
    raw = raw_dir()
    raw.mkdir(parents=True, exist_ok=True)
    qfile = raw / (out_csv.stem + ".queries.txt")
    qfile.write_text("\n".join(queries) + "\n", encoding="utf-8")

    # When the CLI itself runs in a container (the `runner` compose profile), `docker run` talks
    # to the host's Docker daemon, so the volume must be the HOST path of data/raw.
    host_data = env("OPENPROSPECT_HOST_DATA_DIR")
    mount = f"{host_data.rstrip('/')}/raw" if host_data else str(raw.resolve())
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        "gmaps-playwright-cache:/opt",
        "-v",
        f"{mount}:/work",
        cfg.get("image") or DEFAULT_IMAGE,
        "-input",
        f"/work/{qfile.name}",
        "-results",
        f"/work/{out_csv.name}",
        "-depth",
        str(cfg.get("depth", 2)),
        "-c",
        str(cfg.get("concurrency", 2)),
        "-lang",
        str(cfg.get("language", "en")),
        "-exit-on-inactivity",
        str(cfg.get("exit_on_inactivity", "3m")),
    ]
    if cfg.get("extract_emails", True):
        cmd.append("-email")
    log(f"  running Google Maps scraper for {len(queries)} search(es). This takes a few minutes...")
    proc = subprocess.run(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        warn(f"scraper exited with code {proc.returncode}")
    return out_csv.exists() and out_csv.stat().st_size > 0


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def load_csv(conn, path: Path, queries: list[str]) -> tuple[int, int]:
    csv.field_size_limit(10_000_000)
    new = total = 0
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            if (row.get("status") or "").lower().startswith("permanently closed"):
                continue
            pid = row.get("place_id") or row.get("cid") or row.get("link")
            if not pid:
                continue
            website = normalize_url(row.get("website"))
            emails = clean_emails(row.get("emails"))
            complete = {}
            try:
                complete = json.loads(row.get("complete_address") or "{}") or {}
            except ValueError:
                pass
            lead = {
                "source": "google_maps",
                "source_id": f"gmaps:{pid}",
                "name": row.get("title"),
                "category": row.get("category"),
                "address": row.get("address"),
                "city": complete.get("city") or city_from_address(row.get("address", "")),
                "country": (complete.get("country") or "").upper(),
                "timezone": row.get("timezone") or "",
                "phone": row.get("phone"),
                "website": website,
                "domain": domain_of(website),
                "rating": _float(row.get("review_rating")),
                "reviews": _int(row.get("review_count")),
                "price_range": row.get("price_range"),
                "maps_url": row.get("link"),
                "query": row.get("input_id") or "",
                "description": (row.get("descriptions") or "")[:1000],
                "emails": emails,
            }
            if db.upsert_lead(conn, lead):
                new += 1
    for q in queries:
        conn.execute("INSERT OR REPLACE INTO done_queries(query, done_at) VALUES (?, ?)", (q, db.now()))
    conn.commit()
    return new, total


def scrape(conn, only_new: bool = True, queries: list[str] | None = None) -> int:
    queries = queries or (pending_queries(conn) if only_new else read_queries())
    if not queries:
        log("  no new searches in config/queries.txt (add lines to scrape more)")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = raw_dir() / f"gmaps_{stamp}.csv"
    if not run_scraper(queries, out_csv):
        warn("scraper produced no results (Google may be rate-limiting; try fewer searches or lower depth)")
        return 0
    new, total = load_csv(conn, out_csv, queries)
    log(f"  Google Maps: {total} places found, {new} new leads saved")
    return new


def import_csv(conn, path: str) -> int:
    """Load a CSV you exported yourself from the scraper's web UI."""
    new, total = load_csv(conn, Path(path), [])
    log(f"  imported {total} rows, {new} new leads")
    return new
