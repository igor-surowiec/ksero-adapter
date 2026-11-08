"""Configuration loading for the KS adapter.

Configuration lives in a YAML file (``config/config.yaml`` by default).  Values may
reference environment variables with ``${NAME}`` or ``${NAME:-default}`` syntax and
the most important settings can additionally be overridden with dedicated ``KS_*``
environment variables (see :data:`_ENV_OVERRIDES`).

``database.path`` accepts an absolute path, a path relative to the project root
(e.g. ``BAZAMS.FDB`` for a database file kept next to ``config/``) or a path as
seen by a remote Firebird server when ``database.host`` is set.
"""

from __future__ import annotations

import codecs
import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

import yaml

CONFIG_ENV_VAR = "KS_CONFIG"
# Directory containing ``config/`` and the ``ks_adapter`` package.  Relative
# ``database.path`` values are resolved against it.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")
_ENV_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")

_MISSING = object()


class ConfigError(ValueError):
    """Raised when the configuration file is missing, malformed or inconsistent."""


def resolve_database_path(path: str, host: str | None = None) -> str:
    """Return the file path handed to the Firebird client.

    * Remote databases (``host`` set) keep the configured path untouched, because
      it is resolved by the Firebird *server*, not by this machine.
    * Absolute paths are returned unchanged.
    * Relative paths are resolved against :data:`PROJECT_ROOT`.  Without this the
      Firebird client would resolve them against the current working directory,
      so the same configuration would only work when the adapter was started
      from the project directory.

    Blank values are returned unchanged so that :class:`DatabaseSettings` can
    report them as missing.
    """
    if host or not path.strip():
        return path
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return path
    return str((PROJECT_ROOT / candidate).resolve())


@dataclass(frozen=True)
class DatabaseSettings:
    """Firebird connection settings."""

    path: str
    user: str = "SYSDBA"
    password: str = ""
    charset: str = "UTF8"
    host: str | None = None
    port: int = 3050
    client_library: str | None = None
    pool_size: int = 5
    acquire_timeout: float = 10.0
    health_check: bool = True
    check_path: bool = True

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ConfigError("'database.path' must not be empty")
        if not self.user.strip():
            raise ConfigError("'database.user' must not be empty")
        if not 1 <= self.port <= 65535:
            raise ConfigError("'database.port' must be between 1 and 65535")
        if self.pool_size < 1:
            raise ConfigError("'database.pool_size' must be at least 1")
        if self.acquire_timeout <= 0:
            raise ConfigError("'database.acquire_timeout' must be greater than 0")
        if self.check_path and not self.host:
            candidate = Path(self.path)
            if candidate.is_absolute() and not candidate.is_file():
                raise ConfigError(
                    f"'database.path' does not point to an existing file: {self.path}"
                )

    @property
    def dsn(self) -> str:
        """Firebird DSN, including host/port for remote connections."""
        if self.host:
            return f"{self.host}/{self.port}:{self.path}"
        return self.path


@dataclass(frozen=True)
class ServerSettings:
    """HTTP server settings used by ``python -m ks_adapter``."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ConfigError("'server.port' must be between 1 and 65535")
        if self.log_level.lower() not in LOG_LEVELS:
            raise ConfigError(
                "'server.log_level' must be one of: " + ", ".join(LOG_LEVELS)
            )
        object.__setattr__(self, "log_level", self.log_level.lower())


@dataclass(frozen=True)
class ApiSettings:
    """Behaviour of the HTTP API."""

    prefix: str = "/api/v1"
    default_limit: int = 50
    max_limit: int = 1000
    max_query_rows: int = 5000
    schema_cache_ttl: float = 300.0
    blob_encoding: str = "cp1250"
    decimal_as_string: bool = False
    api_key: str | None = None
    #: Master switch for the write endpoints (``POST /clients``).  Off by
    #: default, so an adapter built without the setting stays read-only.
    allow_writes: bool = False
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        prefix = self.prefix.strip()
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        object.__setattr__(self, "prefix", prefix.rstrip("/") or "/")
        if self.default_limit < 1:
            raise ConfigError("'api.default_limit' must be at least 1")
        if self.max_limit < 1:
            raise ConfigError("'api.max_limit' must be at least 1")
        if self.default_limit > self.max_limit:
            raise ConfigError("'api.default_limit' must not exceed 'api.max_limit'")
        if self.max_query_rows < 1:
            raise ConfigError("'api.max_query_rows' must be at least 1")
        if self.schema_cache_ttl < 0:
            raise ConfigError("'api.schema_cache_ttl' must not be negative")
        try:
            codecs.lookup(self.blob_encoding)
        except LookupError as exc:
            raise ConfigError(f"Unknown 'api.blob_encoding': {self.blob_encoding}") from exc


@dataclass(frozen=True)
class AppSettings:
    """Complete application configuration."""

    database: DatabaseSettings
    server: ServerSettings = field(default_factory=ServerSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    config_path: Path | None = None


_ENV_OVERRIDES: dict[str, dict[str, str]] = {
    "database": {
        "path": "KS_DB_PATH",
        "user": "KS_DB_USER",
        "password": "KS_DB_PASSWORD",
        "charset": "KS_DB_CHARSET",
        "host": "KS_DB_HOST",
        "port": "KS_DB_PORT",
        "client_library": "KS_FB_CLIENT",
        "pool_size": "KS_DB_POOL_SIZE",
        "health_check": "KS_DB_HEALTH_CHECK",
        "check_path": "KS_DB_CHECK_PATH",
    },
    "server": {
        "host": "KS_SERVER_HOST",
        "port": "KS_SERVER_PORT",
        "log_level": "KS_LOG_LEVEL",
        "reload": "KS_RELOAD",
    },
    "api": {
        "api_key": "KS_API_KEY",
        "allow_writes": "KS_ALLOW_WRITES",
        "default_limit": "KS_DEFAULT_LIMIT",
        "max_limit": "KS_MAX_LIMIT",
        "max_query_rows": "KS_MAX_QUERY_ROWS",
        "decimal_as_string": "KS_DECIMAL_AS_STRING",
    },
}

# The settings dataclasses define the accepted keys; parsing stays explicit below.
_ALLOWED_KEYS = {
    name: {item.name for item in fields(model)}
    for name, model in (
        ("database", DatabaseSettings),
        ("server", ServerSettings),
        ("api", ApiSettings),
    )
}


def load_config(path: str | os.PathLike[str] | None = None) -> AppSettings:
    """Load and validate the YAML configuration.

    Resolution order for the file path: explicit ``path`` argument, ``KS_CONFIG``
    environment variable, then ``config/config.yaml`` next to the project.
    """
    raw_path = path or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH
    config_path = Path(raw_path).expanduser()
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read configuration file '{config_path}': {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in '{config_path}': {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ConfigError("Configuration file must contain a YAML mapping at the top level")

    data = _expand_env(dict(raw))
    _apply_env_overrides(data)
    return _build_settings(data, config_path.resolve())


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``${VAR:-default}`` references."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group("name")
            default = match.group("default")
            env_value = os.environ.get(name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            raise ConfigError(
                f"Environment variable '{name}' referenced in the configuration is not set"
            )

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, Mapping):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def _apply_env_overrides(data: dict[str, Any]) -> None:
    for section_name, mapping in _ENV_OVERRIDES.items():
        for key, env_name in mapping.items():
            env_value = os.environ.get(env_name)
            if env_value is None or env_value == "":
                continue
            section = data.setdefault(section_name, {})
            if not isinstance(section, dict):
                raise ConfigError(f"'{section_name}' must be a mapping")
            section[key] = env_value


def _build_settings(data: Mapping[str, Any], config_path: Path) -> AppSettings:
    _check_keys(data, {"database", "server", "api"}, "the configuration root")
    database_section = _section(data, "database")
    server_section = _section(data, "server")
    api_section = _section(data, "api")
    _check_keys(database_section, _ALLOWED_KEYS["database"], "'database' section")
    _check_keys(server_section, _ALLOWED_KEYS["server"], "'server' section")
    _check_keys(api_section, _ALLOWED_KEYS["api"], "'api' section")

    database_host = _optional_str(database_section, "database.host")
    database = DatabaseSettings(
        path=resolve_database_path(
            _str(database_section, "database.path"), database_host
        ),
        user=_str(database_section, "database.user", "SYSDBA"),
        password=_str(database_section, "database.password", ""),
        charset=_str(database_section, "database.charset", "UTF8"),
        host=database_host,
        port=_int(database_section, "database.port", 3050),
        client_library=_optional_str(database_section, "database.client_library"),
        pool_size=_int(database_section, "database.pool_size", 5),
        acquire_timeout=_float(database_section, "database.acquire_timeout", 10.0),
        health_check=_bool(database_section, "database.health_check", True),
        check_path=_bool(database_section, "database.check_path", True),
    )
    server = ServerSettings(
        host=_str(server_section, "server.host", "127.0.0.1"),
        port=_int(server_section, "server.port", 8000),
        log_level=_str(server_section, "server.log_level", "info"),
        reload=_bool(server_section, "server.reload", False),
    )
    api = ApiSettings(
        prefix=_str(api_section, "api.prefix", "/api/v1"),
        default_limit=_int(api_section, "api.default_limit", 50),
        max_limit=_int(api_section, "api.max_limit", 1000),
        max_query_rows=_int(api_section, "api.max_query_rows", 5000),
        schema_cache_ttl=_float(api_section, "api.schema_cache_ttl", 300.0),
        blob_encoding=_str(api_section, "api.blob_encoding", "cp1250"),
        decimal_as_string=_bool(api_section, "api.decimal_as_string", False),
        api_key=_optional_str(api_section, "api.api_key"),
        allow_writes=_bool(api_section, "api.allow_writes", False),
        cors_origins=_str_tuple(api_section, "api.cors_origins"),
    )
    return AppSettings(
        database=database, server=server, api=api, config_path=config_path
    )


def _section(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"'{name}' must be a mapping")
    return dict(value)


def _check_keys(section: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ConfigError(f"Unknown key(s) in {label}: {', '.join(unknown)}")


def _get(section: Mapping[str, Any], key: str, default: Any = _MISSING) -> Any:
    name = key.rsplit(".", 1)[-1]
    if name in section:
        return section[name]
    if default is _MISSING:
        raise ConfigError(f"Missing required setting '{key}'")
    return default


def _str(section: Mapping[str, Any], key: str, default: Any = _MISSING) -> str:
    value = _get(section, key, default)
    if not isinstance(value, str):
        raise ConfigError(f"'{key}' must be a string")
    return value


def _optional_str(
    section: Mapping[str, Any], key: str, default: str | None = None
) -> str | None:
    value = _get(section, key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"'{key}' must be a string or null")
    value = value.strip()
    return value or None


def _int(section: Mapping[str, Any], key: str, default: Any = _MISSING) -> int:
    value = _get(section, key, default)
    if isinstance(value, bool):
        raise ConfigError(f"'{key}' must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{key}' must be an integer") from exc


def _float(section: Mapping[str, Any], key: str, default: Any = _MISSING) -> float:
    value = _get(section, key, default)
    if isinstance(value, bool):
        raise ConfigError(f"'{key}' must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{key}' must be a number") from exc


def _bool(section: Mapping[str, Any], key: str, default: Any = _MISSING) -> bool:
    value = _get(section, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    raise ConfigError(f"'{key}' must be a boolean")


def _str_tuple(
    section: Mapping[str, Any], key: str, default: tuple[str, ...] = ()
) -> tuple[str, ...]:
    value = _get(section, key, list(default))
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ConfigError(f"'{key}' must be a list of strings")
    return tuple(value)



