from unittest.mock import MagicMock

import pytest

from app import startup


def test_should_skip_when_skip_env(monkeypatch):
    monkeypatch.setenv("SKIP_STARTUP_TASKS", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert startup.should_skip_startup_tasks() is True


def test_should_skip_when_pytest_marker(monkeypatch):
    monkeypatch.delenv("SKIP_STARTUP_TASKS", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/backend/app/test_startup.py::x")
    assert startup.should_skip_startup_tasks() is True


def test_should_not_skip_outside_test_mode(monkeypatch):
    monkeypatch.delenv("SKIP_STARTUP_TASKS", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert startup.should_skip_startup_tasks() is False


def test_load_environment_calls_dotenv(monkeypatch):
    called = {}

    def fake_load_dotenv(path):
        called["path"] = path

    monkeypatch.setattr(startup, "load_dotenv", fake_load_dotenv)
    startup.load_environment()
    assert called["path"] == startup.BACKEND_ROOT / ".env"


def test_validate_security_rejects_insecure_secrets(monkeypatch):
    for secret in ("", "super-secret-key", "change-me", "  change-me  "):
        monkeypatch.setenv("SESSION_SECRET", secret)
        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            startup.validate_security_settings()


def test_validate_security_accepts_strong_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "ci-test-session-secret-value-32chars!!")
    startup.validate_security_settings()


def test_run_db_migrations_skips_missing_ini(monkeypatch, tmp_path):
    monkeypatch.setattr(startup, "BACKEND_ROOT", tmp_path)
    upgrade = MagicMock()
    monkeypatch.setattr(startup.command, "upgrade", upgrade)
    startup.run_db_migrations()
    upgrade.assert_not_called()


def test_run_db_migrations_applies_with_database_url(monkeypatch, tmp_path):
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
    (tmp_path / "alembic").mkdir()
    monkeypatch.setattr(startup, "BACKEND_ROOT", tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    captured = {}

    class FakeConfig:
        def __init__(self, path):
            captured["ini"] = path

        def set_main_option(self, key, value):
            captured[key] = value

    upgrade = MagicMock()
    monkeypatch.setattr(startup, "Config", FakeConfig)
    monkeypatch.setattr(startup.command, "upgrade", upgrade)

    startup.run_db_migrations()

    assert captured["ini"] == str(tmp_path / "alembic.ini")
    assert captured["script_location"] == str(tmp_path / "alembic")
    assert captured["sqlalchemy.url"] == "sqlite+pysqlite:///:memory:"
    upgrade.assert_called_once()
    assert upgrade.call_args.args[1] == "head"


def test_run_db_migrations_without_database_url(monkeypatch, tmp_path):
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
    (tmp_path / "alembic").mkdir()
    monkeypatch.setattr(startup, "BACKEND_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    captured = {}

    class FakeConfig:
        def __init__(self, path):
            captured["ini"] = path

        def set_main_option(self, key, value):
            captured[key] = value

    upgrade = MagicMock()
    monkeypatch.setattr(startup, "Config", FakeConfig)
    monkeypatch.setattr(startup.command, "upgrade", upgrade)

    startup.run_db_migrations()
    assert "sqlalchemy.url" not in captured
    upgrade.assert_called_once()


def test_run_startup_tasks_skips_in_test_mode(monkeypatch):
    monkeypatch.setenv("SKIP_STARTUP_TASKS", "1")
    load_env = MagicMock()
    monkeypatch.setattr(startup, "load_environment", load_env)
    startup.run_startup_tasks()
    load_env.assert_not_called()


def test_run_startup_tasks_full_happy_path(monkeypatch):
    monkeypatch.delenv("SKIP_STARTUP_TASKS", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    load_env = MagicMock()
    validate = MagicMock()
    migrate = MagicMock()
    bootstrap = MagicMock()
    monkeypatch.setattr(startup, "load_environment", load_env)
    monkeypatch.setattr(startup, "validate_security_settings", validate)
    monkeypatch.setattr(startup, "run_db_migrations", migrate)
    monkeypatch.setattr("app.bootstrap.run_bootstrap_admin", bootstrap)

    startup.run_startup_tasks()

    load_env.assert_called_once()
    validate.assert_called_once()
    migrate.assert_called_once()
    bootstrap.assert_called_once()


def test_run_startup_tasks_reraises_migration_failure(monkeypatch):
    monkeypatch.delenv("SKIP_STARTUP_TASKS", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    monkeypatch.setattr(startup, "load_environment", MagicMock())
    monkeypatch.setattr(startup, "validate_security_settings", MagicMock())
    monkeypatch.setattr(
        startup,
        "run_db_migrations",
        MagicMock(side_effect=RuntimeError("migrate failed")),
    )
    bootstrap = MagicMock()
    monkeypatch.setattr("app.bootstrap.run_bootstrap_admin", bootstrap)

    with pytest.raises(RuntimeError, match="migrate failed"):
        startup.run_startup_tasks()
    bootstrap.assert_not_called()
