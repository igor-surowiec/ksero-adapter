"""Tests for the YAML configuration loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ks_adapter.config import (
    PROJECT_ROOT,
    ConfigError,
    load_config,
    resolve_database_path,
)

KS_VARS = [
    "KS_CONFIG",
    "KS_DB_PATH",
    "KS_DB_USER",
    "KS_DB_PASSWORD",
    "KS_DB_CHARSET",
    "KS_DB_HOST",
    "KS_DB_PORT",
    "KS_FB_CLIENT",
    "KS_DB_POOL_SIZE",
    "KS_DB_HEALTH_CHECK",
    "KS_DB_CHECK_PATH",
    "KS_SERVER_HOST",
    "KS_SERVER_PORT",
    "KS_LOG_LEVEL",
    "KS_RELOAD",
    "KS_API_KEY",
    "KS_DEFAULT_LIMIT",
    "KS_MAX_LIMIT",
    "KS_MAX_QUERY_ROWS",
    "KS_DECIMAL_AS_STRING",
]

MINIMAL = """
database:
  path: C:/fake/test.fdb
  check_path: false
"""


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in KS_VARS:
        monkeypatch.delenv(name, raising=False)


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_load_minimal_configuration(tmp_path: Path) -> None:
    settings = load_config(write_config(tmp_path, MINIMAL))

    assert settings.database.path == "C:/fake/test.fdb"
    assert settings.database.user == "SYSDBA"
    assert settings.database.charset == "UTF8"
    assert settings.database.pool_size == 5
    assert settings.database.dsn == "C:/fake/test.fdb"
    assert settings.server.host == "127.0.0.1"
    assert settings.server.port == 8000
    assert settings.api.prefix == "/api/v1"
    assert settings.api.default_limit == 50
    assert settings.api.max_limit == 1000
    assert settings.api.blob_encoding == "cp1250"
    assert settings.api.api_key is None
    assert settings.api.cors_origins == ()
    assert settings.config_path is not None


def test_environment_variable_defaults(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: ${KS_DB_PATH:-D:/fake/fallback.fdb}
          password: ${SOME_UNSET_PASSWORD:-secret}
          charset: ${ANOTHER_UNSET:-WIN1250}
          check_path: false
        """,
    )
    settings = load_config(config)
    assert settings.database.path == "D:/fake/fallback.fdb"
    assert settings.database.password == "secret"
    assert settings.database.charset == "WIN1250"


def test_environment_variable_without_default_is_required(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/test.fdb
          password: ${SOME_UNSET_PASSWORD}
          check_path: false
        """,
    )
    with pytest.raises(ConfigError, match="SOME_UNSET_PASSWORD"):
        load_config(config)


def test_ks_overrides_replace_file_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KS_DB_PASSWORD", "secret")
    monkeypatch.setenv("KS_DB_POOL_SIZE", "9")
    monkeypatch.setenv("KS_SERVER_PORT", "9000")
    monkeypatch.setenv("KS_API_KEY", "key-from-env")

    settings = load_config(write_config(tmp_path, MINIMAL))

    assert settings.database.password == "secret"
    assert settings.database.pool_size == 9
    assert settings.server.port == 9000
    assert settings.api.api_key == "key-from-env"


def test_ks_config_variable_selects_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write_config(tmp_path, MINIMAL)
    monkeypatch.setenv("KS_CONFIG", str(config))
    settings = load_config()
    assert settings.config_path == config.resolve()


def test_missing_configuration_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")



def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/test.fdb
          check_path: false
          surprise: true
        """,
    )
    with pytest.raises(ConfigError, match="surprise"):
        load_config(config)


def test_unknown_root_section_is_rejected(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/test.fdb
          check_path: false
        cache:
          enabled: true
        """,
    )
    with pytest.raises(ConfigError, match="cache"):
        load_config(config)


@pytest.mark.parametrize(
    "snippet",
    [
        "server:\n  port: 0",
        "server:\n  log_level: loud",
        "api:\n  default_limit: 100\n  max_limit: 10",
        "api:\n  blob_encoding: no-such-codec",
    ],
)
def test_invalid_server_and_api_values(tmp_path: Path, snippet: str) -> None:
    config = write_config(tmp_path, MINIMAL + snippet + "\n")
    with pytest.raises(ConfigError):
        load_config(config)


@pytest.mark.parametrize(
    "snippet",
    [
        "port: 70000",
        "pool_size: 0",
        "acquire_timeout: 0",
        "health_check: maybe",
    ],
)
def test_invalid_database_values(tmp_path: Path, snippet: str) -> None:
    config = write_config(
        tmp_path,
        f"""
        database:
          path: C:/fake/test.fdb
          check_path: false
          {snippet}
        """,
    )
    with pytest.raises(ConfigError):
        load_config(config)


def test_empty_database_path_is_rejected(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: ''
          check_path: false
        """,
    )
    with pytest.raises(ConfigError):
        load_config(config)


def test_check_path_rejects_missing_database_file(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/missing/database.fdb
        """,
    )
    with pytest.raises(ConfigError, match="existing file"):
        load_config(config)


def test_relative_database_path_is_resolved_against_project_root(
    tmp_path: Path,
) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: BAZAMS.FDB
          check_path: false
        """,
    )
    settings = load_config(config)

    assert settings.database.path == str((PROJECT_ROOT / "BAZAMS.FDB").resolve())
    assert Path(settings.database.path).is_absolute()
    assert settings.database.dsn == settings.database.path


def test_relative_database_path_may_point_into_a_subdirectory(
    tmp_path: Path,
) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: data/baza.fdb
          check_path: false
        """,
    )
    settings = load_config(config)

    expected = (PROJECT_ROOT / "data" / "baza.fdb").resolve()
    assert settings.database.path == str(expected)


def test_relative_database_path_comes_from_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KS_DB_PATH", "BAZAMS.FDB")

    settings = load_config(write_config(tmp_path, MINIMAL))

    assert settings.database.path == str((PROJECT_ROOT / "BAZAMS.FDB").resolve())


def test_check_path_applies_to_relative_database_path(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: no-such-database.fdb
        """,
    )
    with pytest.raises(ConfigError, match="existing file"):
        load_config(config)


def test_remote_database_keeps_relative_path_untouched(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: BAZAMS.FDB
          host: firebird.example.com
        """,
    )
    settings = load_config(config)

    assert settings.database.path == "BAZAMS.FDB"
    assert settings.database.dsn == "firebird.example.com/3050:BAZAMS.FDB"


@pytest.mark.parametrize(
    ("path", "host", "expected"),
    [
        ("C:/fake/baza.fdb", None, "C:/fake/baza.fdb"),
        ("C:/fake/baza.fdb", "10.0.0.5", "C:/fake/baza.fdb"),
        ("BAZAMS.FDB", None, str((PROJECT_ROOT / "BAZAMS.FDB").resolve())),
        ("BAZAMS.FDB", "10.0.0.5", "BAZAMS.FDB"),
    ],
)
def test_resolve_database_path(path: str, host: str | None, expected: str) -> None:
    assert resolve_database_path(path, host) == expected


def test_remote_database_uses_host_in_dsn(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/test.fdb
          host: 10.0.0.5
          port: 3051
        """,
    )
    settings = load_config(config)
    assert settings.database.dsn == "10.0.0.5/3051:C:/fake/test.fdb"


def test_empty_api_key_disables_authentication(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
        database:
          path: C:/fake/test.fdb
          check_path: false
        api:
          api_key: ''
          cors_origins:
            - http://localhost:3000
            - https://example.com
        """,
    )
    settings = load_config(config)
    assert settings.api.api_key is None
    assert settings.api.cors_origins == ("http://localhost:3000", "https://example.com")
