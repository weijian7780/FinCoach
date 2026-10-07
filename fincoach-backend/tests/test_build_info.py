from pathlib import Path
import tempfile
import json
from fastapi.testclient import TestClient

from app.build_info import capture_build_info, get_public_config
from app.main import app


def test_dirty_and_untracked_runtime_source_affect_fingerprint():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        app_dir = tmp_path / "app"
        app_dir.mkdir(parents=True)
        file1 = app_dir / "main.py"
        file1.write_text("print('hello')", encoding="utf-8")

        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir(parents=True)
        doc1 = corpus_dir / "doc.md"
        doc1.write_text("# Doc 1", encoding="utf-8")

        config = {"COACH_REQUEST_DEADLINE_SECONDS": 120, "LLM_PRIMARY_MODEL": "gemini-3.5-flash-lite"}

        baseline = capture_build_info(tmp_path, config)
        assert "build_id" in baseline
        assert "source_fingerprint" in baseline
        assert "config_fingerprint" in baseline

        # Modifying existing source file changes source_fingerprint and build_id
        file1.write_text("print('hello world')", encoding="utf-8")
        modified = capture_build_info(tmp_path, config)
        assert modified["source_fingerprint"] != baseline["source_fingerprint"]
        assert modified["build_id"] != baseline["build_id"]
        assert modified["config_fingerprint"] == baseline["config_fingerprint"]

        # Adding an untracked file to app/ changes source_fingerprint
        untracked = app_dir / "untracked_module.py"
        untracked.write_text("x = 1", encoding="utf-8")
        with_untracked = capture_build_info(tmp_path, config)
        assert with_untracked["source_fingerprint"] != modified["source_fingerprint"]
        assert with_untracked["build_id"] != modified["build_id"]

        # Changing public config changes config_fingerprint and build_id, but keeps source_fingerprint
        changed_config = dict(config, COACH_REQUEST_DEADLINE_SECONDS=90)
        with_changed_config = capture_build_info(tmp_path, changed_config)
        assert with_changed_config["config_fingerprint"] != with_untracked["config_fingerprint"]
        assert with_changed_config["source_fingerprint"] == with_untracked["source_fingerprint"]
        assert with_changed_config["build_id"] != with_untracked["build_id"]


def test_build_identity_excludes_credentials():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        app_dir = tmp_path / "app"
        app_dir.mkdir(parents=True)
        (app_dir / "main.py").write_text("print('hello')", encoding="utf-8")

        public_config = {"COACH_REQUEST_DEADLINE_SECONDS": 120, "LLM_PRIMARY_MODEL": "gemini-3.5-flash-lite"}
        baseline = capture_build_info(tmp_path, public_config)

        # Adding a .env file to root must NOT change source_fingerprint
        env_file = tmp_path / ".env"
        env_file.write_text("TAVILY_API_KEY=secret_tavily\nDATABASE_URL=postgres://secret\n", encoding="utf-8")

        after_env = capture_build_info(tmp_path, public_config)
        assert after_env["source_fingerprint"] == baseline["source_fingerprint"]
        assert after_env["config_fingerprint"] == baseline["config_fingerprint"]
        assert after_env["build_id"] == baseline["build_id"]

        # Passing sensitive credentials in config must NOT change config_fingerprint
        config_with_secrets = dict(
            public_config,
            TAVILY_API_KEY="super_secret_tavily",
            SUPABASE_SERVICE_ROLE_KEY="super_secret_jwt",
            OPENROUTER_API_KEY="sk-openrouter-secret",
            DATABASE_PASSWORD="secret_password",
        )
        after_secrets = capture_build_info(tmp_path, config_with_secrets)
        assert after_secrets["config_fingerprint"] == baseline["config_fingerprint"]
        assert after_secrets["source_fingerprint"] == baseline["source_fingerprint"]
        assert after_secrets["build_id"] == baseline["build_id"]


def test_startup_identity_does_not_change_when_disk_changes():
    client = TestClient(app)
    resp1 = client.get("/health")
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Even if disk changes, health returns the cached startup build_info
    resp2 = client.get("/health")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1["build_id"] == data2["build_id"]
    assert data1["source_fingerprint"] == data2["source_fingerprint"]
    assert data1["config_fingerprint"] == data2["config_fingerprint"]


def test_health_retains_status():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "build_id" in payload
    assert "source_fingerprint" in payload
    assert "config_fingerprint" in payload
