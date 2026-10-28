"""The `openprospect` command.

Run it from your workspace (the cloned repo) or set OPENPROSPECT_HOME. `openprospect --help`
lists every command; `openprospect <command> --help` explains one."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version

from openprospect import crm, enrich, jobs, mail, scoring, verify
from openprospect.core import db
from openprospect.core.config import init_workspace, paths
from openprospect.core.log import log
from openprospect.sources import buyer_intent, google_maps, remote_companies

from . import daemon, pipeline, report, services

TAGLINE = "OpenProspect: find leads, verify them, reach out, track replies. Self-hosted and free."


def _version() -> str:
    try:
        return version("openprospect")
    except PackageNotFoundError:
        return "dev"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="openprospect", description=TAGLINE)
    p.add_argument("--version", action="version", version=f"openprospect {_version()}")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_, description=help_)

    # setup and services
    add("init", "create .env (random passwords) and config/ from the examples; never overwrites")
    up = add("up", "start the services in Docker (CRM, email sender, verifier, intent watcher)")
    up.add_argument("--firecrawl", action="store_true", help="also start Firecrawl (needs ~4 GB more RAM)")
    add("down", "stop the services")
    add("setup", "one-time: Listmonk API user, SMTP + sending speed, Huginn buyer-intent scenario")
    add("doctor", "check every service, connection and setting")

    # the agency track
    run = add("run", "THE DAILY JOB: replies, send, scrape, enrich, verify, score, CRM, intent, send")
    run.add_argument("--no-remote", action="store_true", help="skip the remote-friendly companies source")
    add("daemon", "stay running and start each track daily at the times in settings.yaml (schedule:)")
    sc = add("scrape", "Google Maps: run new searches from config/queries.txt (+ auto searches)")
    sc.add_argument("--all", action="store_true", help="re-run every line of queries.txt, not only new ones")
    rm = add("remote", "add remote-friendly companies from remoteintech/remote-jobs")
    rm.add_argument("limit", nargs="?", type=int, help="how many (default: remote_companies.limit_per_run)")
    add("enrich", "read each new lead's website: emails, problems, budget signals")
    add("verify", "check emails before anything is sent")
    s = add("score", "score + tier leads and write each email's first line")
    s.add_argument("--all", action="store_true", help="re-score everything (after editing settings.yaml)")
    add("crm", "push scored leads to Twenty CRM")
    add("intent", "pull Reddit buyer-intent posts from Huginn into the CRM")
    add("replies", "read the inbox: replies, opt-outs, bounces")
    add("send", "create today's Listmonk campaigns (intro + follow-ups)")
    add("prep", "enrich + verify + score + CRM + intent (no scraping, no sending)")
    add("stats", "numbers + top 10 leads")
    ex = add("export", "save all leads to a CSV")
    ex.add_argument("path", nargs="?", help="output file (default: data/exports/leads_<time>.csv)")
    ic = add("import-csv", "load a CSV exported from the Google Maps scraper web UI")
    ic.add_argument("path")

    # the job / freelance track
    j = add("jobs", "job & freelance track: find openings, write emails with AI, send")
    jsub = j.add_subparsers(dest="jobs_cmd", metavar="<step>", required=True)
    for name, help_ in (
        ("find", "collect fresh remote/freelance openings that fit you + who to email"),
        ("write", "AI (Claude Code) researches each company and writes drafts.json"),
        ("send", "send the approved drafts, safely and only once"),
        ("daily", "find + write + send"),
    ):
        jp = jsub.add_parser(name, help=help_, description=help_)
        jp.add_argument("--day", help="YYYY-MM-DD (default: today)")
        if name == "send":
            jp.add_argument("--dry-run", action="store_true", help="list what would be sent, send nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = build_parser()
    a = parser.parse_args(argv)
    if not a.cmd:
        parser.print_help()
        return 0

    # commands that need no database
    if a.cmd == "init":
        added = init_workspace()
        log(f"workspace ready at {paths.home}" + (f" (added: {', '.join(added)})" if added else " (nothing to add)"))
        log("next: edit config/settings.yaml, then `openprospect up`")
        return 0
    if a.cmd == "up":
        return services.up(a.firecrawl)
    if a.cmd == "down":
        return services.down()
    if a.cmd == "doctor":
        report.doctor()
        return 0
    if a.cmd == "daemon":
        daemon.run_forever()
        return 0
    if not paths.settings_file.exists():
        log(
            f"no workspace here ({paths.settings_file} is missing): run `openprospect init` in your "
            "OpenProspect folder, or set OPENPROSPECT_HOME"
        )
        return 1
    if a.cmd == "jobs":
        day = a.day
        with pipeline.Tee("jobs"):
            if a.jobs_cmd == "find":
                jobs.find(day)
            elif a.jobs_cmd == "write":
                jobs.write(day)
            elif a.jobs_cmd == "send":
                jobs.send(day, dry_run=a.dry_run)
            else:
                jobs.daily(day)
        return 0

    conn = db.connect()
    try:
        commands = {
            "setup": lambda: (mail.setup(conn), pipeline.step("Huginn", buyer_intent.setup_huginn)),
            "run": lambda: pipeline.run_all(conn, with_remote=not a.no_remote),
            "prep": lambda: pipeline.prep(conn),
            "scrape": lambda: google_maps.scrape(conn, only_new=not a.all),
            "remote": lambda: remote_companies.import_companies(conn, a.limit),
            "enrich": lambda: enrich.enrich(conn),
            "verify": lambda: verify.verify(conn),
            "score": lambda: scoring.score(conn, rescore=a.all),
            "crm": lambda: crm.sync(conn),
            "intent": lambda: buyer_intent.pull(conn),
            "replies": lambda: mail.check_replies(conn),
            "send": lambda: mail.send(conn),
            "stats": lambda: report.stats(conn),
            "export": lambda: report.export(conn, a.path),
            "import-csv": lambda: google_maps.import_csv(conn, a.path),
        }
        if a.cmd == "run":
            with pipeline.Tee("run"):
                commands["run"]()
        else:
            commands[a.cmd]()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
