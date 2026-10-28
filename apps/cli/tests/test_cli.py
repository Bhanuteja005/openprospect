import shutil
from datetime import datetime
from pathlib import Path

import pytest

from openprospect.cli import daemon
from openprospect.cli import main as cli
from openprospect.core import config

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "argv",
    [
        ["init"],
        ["up"],
        ["up", "--firecrawl"],
        ["down"],
        ["setup"],
        ["doctor"],
        ["run"],
        ["run", "--no-remote"],
        ["daemon"],
        ["scrape"],
        ["scrape", "--all"],
        ["remote"],
        ["remote", "25"],
        ["enrich"],
        ["verify"],
        ["score"],
        ["score", "--all"],
        ["crm"],
        ["intent"],
        ["replies"],
        ["send"],
        ["prep"],
        ["stats"],
        ["export"],
        ["export", "out.csv"],
        ["import-csv", "f.csv"],
        ["jobs", "find"],
        ["jobs", "write", "--day", "2026-10-28"],
        ["jobs", "send", "--dry-run"],
        ["jobs", "daily"],
    ],
)
def test_parser_accepts_every_command(argv):
    a = cli.build_parser().parse_args(argv)
    assert a.cmd == argv[0]


def test_parser_values():
    p = cli.build_parser()
    assert p.parse_args(["remote", "25"]).limit == 25
    assert p.parse_args(["score", "--all"]).all is True
    a = p.parse_args(["jobs", "send", "--dry-run", "--day", "2026-10-28"])
    assert (a.jobs_cmd, a.dry_run, a.day) == ("send", True, "2026-10-28")


def test_parser_rejects_unknown_and_incomplete():
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["nope"])
    with pytest.raises(SystemExit):
        p.parse_args(["jobs"])  # a step is required


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "openprospect" in capsys.readouterr().out


def test_init_creates_workspace(tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    for f in (REPO / "config").glob("*.example.*"):
        shutil.copyfile(f, tmp_path / "config" / f.name)
    monkeypatch.setenv("OPENPROSPECT_HOME", str(tmp_path))
    config.reload_settings()

    assert cli.main(["init"]) == 0
    assert (tmp_path / ".env").exists()
    for name in ("settings.yaml", "queries.txt", "profile.md"):
        assert (tmp_path / "config" / name).exists(), name
    assert "workspace ready" in capsys.readouterr().out
    # the copied example settings are valid and loadable
    assert isinstance(config.settings(), dict)
    config.reload_settings()


def test_stats_on_empty_workspace(workspace, capsys):
    assert cli.main(["stats"]) == 0
    assert "Leads total ........ 0" in capsys.readouterr().out


def test_due_logic():
    now = datetime(2026, 10, 28, 6, 30)
    assert daemon._due("06:00", None, now) is True
    assert daemon._due("06:00", "2026-10-28", now) is False  # already ran today
    assert daemon._due("06:00", "2026-10-27", now) is True
    assert daemon._due("13:00", None, now) is False
    assert daemon._due("", None, now) is False


@pytest.mark.parametrize(
    "value, expected", [("06:00", (6, 0)), ("13:30", (13, 30)), (360, (6, 0)), ("", None), (None, None)]
)
def test_schedule_times_quoted_or_not(value, expected):
    from openprospect.cli.daemon import parse_time

    assert parse_time(value) == expected
