import pytest

from openprospect.core import config, db


def test_init_workspace_copies_examples_and_generates_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPROSPECT_HOME", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.example.yaml").write_text("agency: {}\n", encoding="utf-8")
    (tmp_path / "config" / "queries.example.txt").write_text("dentist in Austin TX\n", encoding="utf-8")

    added = config.init_workspace()

    assert "config/settings.yaml" in added and "config/queries.txt" in added
    assert (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8") == "agency: {}\n"
    values = config.read_env_file()
    for key in config.GENERATED_SECRETS:
        assert len(values[key]) == 32
    assert values["LISTMONK_ADMIN_USER"] == "admin"
    assert values["TWENTY_URL"] == "http://localhost:3740"


def test_init_workspace_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPROSPECT_HOME", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.example.yaml").write_text("example: 1\n", encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text("mine: 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TWENTY_DB_PASSWORD=keepme\nTWENTY_URL=http://crm:9\n", encoding="utf-8")

    config.init_workspace()
    second = config.init_workspace()

    assert (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8") == "mine: 1\n"
    values = config.read_env_file()
    assert values["TWENTY_DB_PASSWORD"] == "keepme"
    assert values["TWENTY_URL"] == "http://crm:9"
    assert second == []


def test_env_precedence(workspace, monkeypatch):
    config.write_env_value("SMTP_HOST", "smtp.from-dotenv.test")
    assert config.env("SMTP_HOST") == "smtp.from-dotenv.test"
    monkeypatch.setenv("SMTP_HOST", "smtp.from-os.test")
    assert config.env("SMTP_HOST") == "smtp.from-os.test"
    assert config.env("IMAP_HOST") == "imap.gmail.com"  # built-in default
    assert config.env("NOT_A_KEY") == ""


def test_write_env_value_replaces_in_place(workspace):
    (workspace / ".env").write_text("# comment\nA=1\nB=2\n", encoding="utf-8")
    config.write_env_value("A", "9")
    config.write_env_value("C", "3")
    assert (workspace / ".env").read_text(encoding="utf-8") == "# comment\nA=9\nB=2\nC=3\n"


def test_settings_missing_file_explains_init(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPROSPECT_HOME", str(tmp_path))
    config.reload_settings()
    with pytest.raises(FileNotFoundError, match="openprospect init"):
        config.settings()
    config.reload_settings()


def test_set_huginn_feed_url_keeps_comments(workspace):
    f = workspace / "config" / "settings.yaml"
    f.write_text('# keep me\nintent:\n  huginn_feed_url: ""   # filled by setup\n', encoding="utf-8")
    config.reload_settings()
    config.set_huginn_feed_url("http://h/feed.json")
    text = f.read_text(encoding="utf-8")
    assert "# keep me" in text and "# filled by setup" in text
    assert config.settings()["intent"]["huginn_feed_url"] == "http://h/feed.json"


def test_connect_creates_schema(conn):
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"leads", "sends", "done_queries", "suppression", "kv"} <= tables


def test_upsert_lead_inserts_then_only_fills_empty_fields(conn):
    lead = {"source": "google_maps", "source_id": "gmaps:1", "name": "Acme", "phone": "", "emails": ["a@acme.com"]}
    assert db.upsert_lead(conn, lead) is True
    row = conn.execute("SELECT * FROM leads WHERE source_id = 'gmaps:1'").fetchone()
    assert db.loads(row["emails"], []) == ["a@acme.com"]
    db.update(conn, row["id"], stage="emailing")

    again = {"source": "google_maps", "source_id": "gmaps:1", "name": "Renamed", "phone": "555-0100"}
    assert db.upsert_lead(conn, again) is False
    row = conn.execute("SELECT * FROM leads WHERE source_id = 'gmaps:1'").fetchone()
    assert row["name"] == "Acme"  # existing value kept
    assert row["phone"] == "555-0100"  # empty field filled
    assert row["stage"] == "emailing"  # progress kept


def test_suppression_by_email_and_domain(conn):
    db.suppress(conn, "Bob@Acme.com", "opt-out")
    db.suppress(conn, "@spam.io", "bounce")
    assert db.is_suppressed(conn, "bob@acme.com")
    assert db.is_suppressed(conn, "anyone@spam.io")
    assert not db.is_suppressed(conn, "alice@acme.com")
    assert not db.is_suppressed(conn, "")


def test_kv_roundtrip(conn):
    assert db.kv_get(conn, "missing", "dflt") == "dflt"
    db.kv_set(conn, "k", "1")
    db.kv_set(conn, "k", "2")
    assert db.kv_get(conn, "k") == "2"


def test_loads_is_forgiving():
    assert db.loads(None, []) == []
    assert db.loads("not json", {}) == {}
    assert db.loads('{"a": 1}', {}) == {"a": 1}
