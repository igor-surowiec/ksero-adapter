# ks-adapter — architecture and program flow

This document explains **how a request travels through the code** and **what every
file in the repository is responsible for**. Installation, configuration keys and
the HTTP contract are documented in [`README.md`](../README.md); this file focuses on
internals. The `tests/` package is intentionally not covered here.

---

## 1. What the program is

`ks-adapter` is a small, read-only HTTP gateway in front of a Firebird database
(verified against Firebird 2.5.9, database `BAZAMS.FDB`, charset `WIN1250`).

It is one Python package (`ks_adapter`) run as `python -m ks_adapter`, which starts
a FastAPI application on top of uvicorn. Inside, the layers are strictly separated:

```
HTTP request
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ api.py        routes, query-parameter validation, X-API-Key   │  transport
├──────────────────────────────────────────────────────────────┤
│ schemas.py    Pydantic response models (= OpenAPI contract)   │
├──────────────────────────────────────────────────────────────┤
│ service.py    use cases: health, tables, rows, clients,       │  business logic
│               agreements and ad-hoc read-only queries         │
├──────────────────────────────────────────────────────────────┤
│ schema.py     catalog introspection + TTL cache               │
│ sql.py        SQL builder: quoting, filters, read-only guard  │  helpers
│ serialization.py  Firebird values -> JSON                     │
├──────────────────────────────────────────────────────────────┤
│ pool.py       thread-safe pool of fdb connections             │  infrastructure
├──────────────────────────────────────────────────────────────┤
│ config.py     YAML + env settings, validation, DSN            │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
fdb (Firebird client library) ──► Firebird server / .FDB file
```

Nothing above `pool.py` opens a connection itself (`app.py` only imports `fdb` to
catch `fdb.Error`), and nothing below `service.py` knows that HTTP exists. That is
what makes the stack testable with a fake service (see `tests/conftest.py`).

---

## 2. Repository map

```
ks-adapter/
├── config/
│   └── config.yaml          # the single source of runtime settings
├── ks_adapter/
│   ├── __init__.py          # package marker + __version__
│   ├── __main__.py          # CLI entry point: run server | --check
│   ├── app.py               # FastAPI factory, lifespan, error handlers, CORS
│   ├── api.py               # routes + API-key dependency
│   ├── config.py            # YAML loader, env expansion/overrides, validation
│   ├── errors.py            # AdapterError hierarchy carrying HTTP statuses
│   ├── pool.py              # connection pool over the fdb driver
│   ├── schema.py            # RDB$ catalog queries, type mapping, TTL cache
│   ├── serialization.py     # Firebird values -> JSON-safe Python objects
│   ├── service.py           # DatabaseService: all database use cases
│   ├── schemas.py           # Pydantic request/response models
│   └── sql.py               # identifier quoting, filters, read-only SQL guard
├── tests/                   # pytest suite (not described here)
├── docs/ARCHITECTURE.md     # this file
├── pytest.ini               # test paths + `integration` marker
├── requirements.txt         # runtime dependencies
├── requirements-dev.txt     # runtime + pytest + httpx
├── README.md                # user documentation (config, endpoints, usage)
└── BAZAMS.FDB               # the database file itself (git-ignored)
```

---

## 3. Runtime flow

### 3.1 Process start

1. **`python -m ks_adapter`** → `ks_adapter/__main__.py::main()` (via `if __name__
   == "__main__"`), which parses the CLI arguments (`-c/--config`, `--host`,
   `--port`, `--log-level`, `--reload`, `--check`).
2. **`config.load_config(args.config)`** resolves the YAML file in this order:
   CLI argument → `KS_CONFIG` environment variable → `config/config.yaml` next to
   the project. Any `ConfigError` (missing file, bad YAML, unknown key, invalid
   value, missing `.fdb`) is printed and the process exits with **code 2** before
   any server or database work happens.
3. CLI flags override the file: `--host`, `--port`, `--log-level`, `--reload`.
4. `logging.basicConfig(...)` is configured with the chosen level and the format
   `time level logger: message`.
5. If `--check` was passed, `_check(settings)` creates a `DatabaseService`, calls
   `health()` (opens one pooled connection, runs `SELECT 1 FROM RDB$DATABASE`,
   reads `connection.server_version`) plus `list_tables()` (loads the schema
   cache) and prints the configuration path, DSN, Firebird version and the
   table/view count. It exits with `0` on success, `1` when the database is
   unreachable.
6. Otherwise the server starts:
   - **without** `--reload`: `create_app(settings)` is called directly and the
     returned app object is handed to `uvicorn.run(...)`;
   - **with** `--reload`: uvicorn needs an import string, so the config path is
     exported to `KS_CONFIG` and uvicorn is given
     `"ks_adapter.app:create_app", factory=True`, which re-loads the config in the
     reloader child process.
7. **`app.create_app(settings)`** builds the FastAPI instance: title/version from
   `ks_adapter.__version__`, the OpenAPI description, the `lifespan` context
   manager, `app.state.settings` + `app.state.service` (the service is created
   here when it was not injected), CORS middleware (only when
   `api.cors_origins` is non-empty), the router from `api.create_router(settings)`,
   the two exception handlers and an unauthenticated `/` index route.
8. On the first request that needs the catalog, `SchemaCache` lazily loads
   `RDB$RELATIONS` / `RDB$RELATION_FIELDS`, and `ConnectionPool` lazily opens
   Firebird connections. Nothing touches the database during startup itself, so a
   temporarily unavailable database yields `503` responses instead of a crash.

### 3.2 Generic request pipeline

```
uvicorn (ASGI)                     Threadpool worker (sync endpoint)
   │                                        │
   ├─ routing ──► api.create_router.<endpoint>
   │                   │
   │                   ├─ Depends(require_api_key)   → 401 AuthenticationError?
   │                   ├─ FastAPI Query validation   → 422?
   │                   ├─ Depends(get_service)       → app.state.service
   │                   │
   │                   ▼
   │              service.DatabaseService.<method>
   │                   ├─ schema.SchemaCache.get(...)   ── 404 TableNotFound
   │                   │      └─ (miss) pool.session() ── catalog SQL
   │                   ├─ sql.parse_filters / build_where / build_search
   │                   ├─ sql.quote_identifier (identifiers from the catalog)
   │                   └─ pool.session()
   │                          ├─ _acquire(): idle conn? health check : new conn
   │                          ├─ cursor.execute(sql, params)  ← bound parameters
   │                          └─ _release(): rollback + back to LIFO queue
   │                   │
   │                   ▼
   │        serialization.serialize_rows / to_jsonable
   │                   │
   │        Pydantic response_model (schemas.py) → JSON
   ▼                   │
response ◄─────────────┘
```

Key properties:

- Every endpoint is a **synchronous** `def`, so Starlette executes it in a worker
  thread; blocking `fdb` calls never block the event loop. Concurrency is therefore
  bounded by the threadpool and by `database.pool_size` connections.
- Each request borrows **exactly one** connection per service call and returns it
  to the pool afterwards; the pool performs a `ROLLBACK` on return, so no
  transaction state (and no lock) leaks between requests.
- Any `AdapterError` raised anywhere below the route becomes a JSON error response
  with a stable status code (see 3.6).

### 3.3 Trace: `GET /api/v1/clients?limit=2&search=kowal`

1. `api.py::list_clients` is selected by the router.
2. Dependencies run: `require_api_key(settings)` (a no-op when `api.api_key` is
   unset, otherwise an `hmac.compare_digest` check of `X-API-Key` → `401`), then
   `get_service` returns the `DatabaseService` from `app.state`.
3. FastAPI validates the query string: `limit ≥ 1` and `≤ api.max_limit`,
   `offset ≥ 0`, `search` at most 100 characters → `422` on violation.
   `limit=None` means "use `api.default_limit`".
4. `service.fetch_clients(limit=2, offset=0, search="kowal")`:
   - `schema.get("KLIENT")` → the schema cache (loaded on first use, valid for
     `api.schema_cache_ttl` seconds) returns a `TableInfo` with all 61 columns, or
     raises `TableNotFound` (`404`).
   - `check_limit()` applies `api.default_limit` / `api.max_limit`; a negative
     offset raises `InvalidRequest` (`400`).
   - `CLIENT_FIELDS` is intersected with the real column list, so unknown columns
     are skipped instead of breaking the endpoint.
   - `sql.build_search()` produces
     `WHERE ("NAZWA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE '\' OR ...)` with the
     pattern `%kowal%` repeated as one bind parameter per searched column
     (`CLIENT_SEARCH_COLUMNS`).
   - Two statements are executed on one pooled connection:
     `SELECT COUNT(*) FROM "KLIENT" WHERE ...` (→ `total`) and
     `SELECT "ID_KLIENT_TABLE", "ID_KLIENT", ... FROM "KLIENT" WHERE ...
     ORDER BY "NAZWA", "ID_KLIENT_TABLE" ROWS 1 TO 2` (→ the page). `ROWS n TO m`
     is dialect-3 Firebird pagination; the explicit `ORDER BY` keeps pages stable.
   - Raw tuples are mapped to the JSON field names of `CLIENT_FIELDS` through
     `serialization.to_jsonable`.
5. The dict is validated against `schemas.ClientPage` (Pydantic) and serialised to
   JSON: `{"total": ..., "count": ..., "limit": ..., "offset": ..., "clients": [...]}`.

`GET /api/v1/agreements` is the same trace with `AGREEMENTS_TABLE` (`UMOWACPC`),
`AGREEMENT_FIELDS` and `AGREEMENT_SEARCH_COLUMNS`, ordered by `UMOWA` and then
`ID_UMOWACPC_TABLE`; both endpoints run through `service._projection_page()`, so the
only differences are the table, the column projection and the default ordering.

### 3.4 Trace: `GET /api/v1/tables/{table}/rows?filters=...&order_by=...`

Same skeleton, with two extra translation steps before the SQL is built:

- `sql.parse_filters(filters)` turns the JSON object into `Filter` objects and
  rejects malformed JSON, unsupported operators and unknown keys (`400`).
- `sql.build_where(filters, info.column_map)` maps each column name to its
  canonical spelling from the catalog (unknown column → `ColumnNotFound` = `400`),
  emits quoted identifiers and appends every value to the parameter list.
- `service._order_clause()` validates `COLUMN [ASC|DESC]` tokens the same way.
- The `COUNT(*)` companion query provides `total`, and `serialize_rows()` handles
  duplicate column names (`NAME`, `NAME_2`, ...).

### 3.5 Trace: `POST /api/v1/query`

1. Body model `schemas.QueryRequest` (`sql`, optional `limit`, optional
   `parameters`) is validated by FastAPI → `422` for a missing/empty statement.
2. `sql.ensure_read_only(sql)`:
   - strips trailing semicolons and rejects a second statement after
     `strip_sql_literals()` removed comments and `'...'` / `"..."` literals,
   - requires the first keyword to be `SELECT` or `WITH`,
   - rejects a list of write/DDL/session keywords (`INSERT`, `UPDATE`, `DELETE`,
     `MERGE`, `EXECUTE`, `CREATE`, `ALTER`, `DROP`, `GRANT`, `COMMIT`, ...).
3. `check_limit()` caps the result at `api.max_query_rows` (both default and hard
   maximum); `_check_parameters()` allows only JSON scalars.
4. The cursor fetches `limit + 1` rows: the extra row only sets `truncated`.

### 3.6 Error flow

| Raised where | Type | Result |
| --- | --- | --- |
| `sql.py`, `service.py` | `InvalidRequest` / `QueryNotAllowed` / `ColumnNotFound` | `400` |
| `api.py` | `AuthenticationError` | `401` |
| `schema.py` | `TableNotFound` | `404` |
| `pool.py`, `schema.py` | `DatabaseUnavailable` | `503` |
| request/response models | Pydantic `ValidationError` | `422` (FastAPI) |
| anywhere | uncaught `fdb.Error` | `500` via `_firebird_error_handler` (traceback logged, first message line returned) |
| `config.py` at startup | `ConfigError` | printed to stderr, exit code `2` (`1` when `--check` cannot reach the database) |

`app._adapter_error_handler` renders any `AdapterError` as
`{"detail": <message>, "error": <exception class name>}` using the class'
`status_code`, so a new error type only needs a subclass in `errors.py`.

### 3.7 Shutdown

uvicorn stops → the `lifespan` context manager exits → `DatabaseService.close()` →
`ConnectionPool.close()` marks the pool closed, closes every idle connection and
rejects further acquisitions. The service is only closed when `create_app` created
it itself (an injected service belongs to the caller, e.g. a test fixture).

---

## 4. Cross-cutting behaviour

### 4.1 Read-only guarantees (four independent layers)

| Layer | Mechanism | Where |
| --- | --- | --- |
| Statement shape | only one `SELECT`/`WITH`, trailing `;` stripped, forbidden keywords rejected after comments/literals are stripped | `sql.ensure_read_only` |
| Identifiers | table and column names never come from the request, only from the catalog snapshot, and are always emitted as `"QUOTED"` identifiers | `sql.quote_identifier`, `schema.TableInfo.column_map` |
| Values | every filter/search/query value is bound as a `?` placeholder | `sql.build_where`, `sql.build_search` |
| Transactions | borrowed connections are always rolled back on return, and row counts are capped | `pool.ConnectionPool._release`, `service.check_limit` |

### 4.2 Concurrency and connection lifecycle

- `ConnectionPool` keeps idle connections in a `LifoQueue` sized `pool_size`
  (default 5). LIFO means the most recently used connection is reused first, which
  keeps the number of server-side attachments low.
- Borrow (`_acquire`): take an idle connection → `_is_healthy()` (a cheap
  `SELECT 1 FROM RDB$DATABASE` when `database.health_check` is on) → reuse; if it
  fails, discard it and retry. If no idle connection exists and the `_created`
  counter is below capacity, open a new one; otherwise block on the queue until
  `database.acquire_timeout` (default 10 s) and then raise `DatabaseUnavailable`.
- Return (`_release`): `rollback()` (so no transaction or record lock survives) and
  put the connection back; a broken connection is closed and the slot freed.
- `stats` reports `created` / `idle` / `capacity` and is surfaced by `/health`.

### 4.3 Schema cache

- One `SchemaCache` per service, holding a `dict[str, TableInfo]` keyed by the
  canonical (upper-case) table name, protected by a `threading.Lock` with a
  double-checked load so only one thread queries the catalog.
- `api.schema_cache_ttl` (default 300 s) controls staleness; `0` disables expiry
  (load once, never reload automatically).
- `POST /api/v1/schema/refresh` calls `invalidate()`, forcing the next request to
  reload, and returns the new table count.
- Lookups are case-insensitive (`get("klient")` finds `KLIENT`) and fail with
  `TableNotFound` (`404`) otherwise.

### 4.4 Configuration resolution

`load_config()` is a fixed pipeline:

```
explicit arg → $KS_CONFIG → <project>/config/config.yaml     (which file)
        ↓
yaml.safe_load                                              (parse)
        ↓
_expand_env()      ${VAR} / ${VAR:-default}                 (interpolate)
        ↓
_apply_env_overrides()   KS_DB_* / KS_SERVER_* / KS_API_*   (override)
        ↓
_build_settings()  unknown-key check → dataclasses → __post_init__ validation
        ↓
resolve_database_path()   relative path → PROJECT_ROOT
        ↓
AppSettings(database, server, api, config_path)
```

- The root mapping and each of the `database`/`server`/`api` sections are checked
  against a whitelist (`_check_keys`), so unknown keys and typos raise `ConfigError`
  instead of being silently ignored.
- Every section is an immutable (`frozen=True`) dataclass that validates itself in
  `__post_init__` (ports, limits, log level, encoding, non-empty path/user).
  `ApiSettings.__post_init__` also normalises the prefix (`api/v1` → `/api/v1`).
- `DatabaseSettings.dsn` joins `host`/`port` and `path` for remote servers
  (`host/port:path`) and returns `path` unchanged for local files.
- `database.path` resolution is delegated to `resolve_database_path()`:
  absolute paths, blank values and remote DSNs (`host` set) pass through; a
  relative path is resolved against `PROJECT_ROOT` (the directory containing
  `config/` and `ks_adapter/`), which makes the adapter independent of the
  current working directory. `check_path` then verifies the **resolved** file.
- `PROJECT_ROOT` and `DEFAULT_CONFIG_PATH` are module constants, so moving the
  project is enough — no path needs editing.

### 4.5 Serialisation rules

`serialization.to_jsonable()` maps Firebird/Python values to JSON:

| Value | JSON |
| --- | --- |
| `None`, `bool`, `int`, `str` | unchanged |
| `float` (finite / not finite) | number / `null` |
| `Decimal` | `float`, or `str` when `api.decimal_as_string` |
| `datetime`, `date`, `time` | ISO-8601 string (`isoformat()`) |
| `timedelta` | number of seconds |
| `bytes`/`bytearray`/`memoryview` | decoded with `api.blob_encoding` (default `cp1250`), otherwise `{"base64": ..., "length": ...}` |
| list/tuple/dict | recursively converted, dict keys stringified |
| anything else | `str(value)` |

### 4.6 Logging

`__main__.main()` configures the root logger once. Each module uses
`logging.getLogger(__name__)`, so the logger names are `ks_adapter.app`,
`ks_adapter.pool`, `ks_adapter.schema` and `ks_adapter.service`:

- `app` — startup (version + DSN), shutdown, uncaught Firebird errors with traceback;
- `pool` — connection open (`DEBUG`), pool closed (`DEBUG`);
- `schema` — number of loaded tables/views (`DEBUG`);
- `service` — a module logger exists but currently emits nothing (the service
  reports through return values and exceptions).

`--log-level` / `server.log_level` / `KS_LOG_LEVEL` select the verbosity.

---

## 5. File-by-file reference

Each entry lists the file's purpose, its public objects and the details that are
easy to miss. Files are ordered by layer, from the outside in.

### `ks_adapter/__init__.py`

Package marker. It defines `__version__ = "1.0.0"`, which is the single source of
the version shown in the OpenAPI schema (`FastAPI(version=...)`), in `GET /`,
`GET /api/v1/` and in the startup log line. Bump it here only.

### `ks_adapter/__main__.py` — CLI entry point

Executed by `python -m ks_adapter`. Contains no database logic itself.

| Object | Role |
| --- | --- |
| `build_parser()` | `argparse` parser: `-c/--config`, `--host`, `--port`, `--log-level`, `--reload`, `--check` |
| `main(argv)` | load config → apply CLI overrides → configure logging → `--check` or start uvicorn |
| `_check(settings)` | one-shot smoke test: `health()` + `list_tables()`, prints DSN/version/table count |

Notes:

- `main()` returns an exit code instead of calling `sys.exit`, and the module ends
  with `raise SystemExit(main())`, which keeps the function testable.
- `ConfigError` → message on stderr, exit `2`; a failed `--check` → exit `1`;
  success → `0`.
- `getattr(logging, log_level.upper(), logging.INFO)` means the extra `trace` level
  accepted by the config falls back to `INFO` (the standard library has no `TRACE`).
- `--reload` cannot be combined with an app object, so the resolved config path is
  exported to `KS_CONFIG` and uvicorn loads `ks_adapter.app:create_app` as a
  factory instead.
- `uvicorn`, `DatabaseService` and `AdapterError` are imported lazily so
  `--help`/config errors do not require the Firebird client library.

### `ks_adapter/app.py` — application factory

Builds the ASGI app; the only module that knows about FastAPI internals besides
`api.py`.

| Object | Role |
| --- | --- |
| `create_app(settings=None, service=None)` | factory used by `uvicorn` (also reachable as an import string for `--reload`) |
| `DESCRIPTION` | long text rendered in `/docs` |
| `_adapter_error_handler` | `AdapterError` → JSON with `error.status_code` |
| `_firebird_error_handler` | raw `fdb.Error` → logged traceback + `500` |

Notes:

- `settings` defaults to `load_config()`, so the factory works standalone.
- `service` is an injection point: when provided, the app does **not** close it on
  shutdown (`owns_service` flag); when omitted, `DatabaseService(settings)` is
  created here and closed by the `lifespan` handler.
- `app.state.settings` and `app.state.service` are the bridge to `api.get_service`.
- CORS middleware is added only when `api.cors_origins` is non-empty, and allows
  `GET`/`POST` with any header.
- `GET /` (outside the API prefix, hidden from the OpenAPI schema) returns the
  service name, version, prefix and docs URL — handy as a liveness probe.

### `ks_adapter/api.py` — routes and authentication

Declares the HTTP surface as a factory, so the prefix and limits come from the
loaded settings rather than from module-level state.

| Object | Role |
| --- | --- |
| `get_service(request)` | FastAPI dependency returning `request.app.state.service` |
| `require_api_key(settings)` | dependency **factory** returning a `check_api_key` closure |
| `create_router(settings)` | builds the `APIRouter` with all routes |
| `FILTERS_DESCRIPTION` | text shown for the `filters` query parameter in `/docs` |

Routes (all relative to `api.prefix`):

| Method & path | Handler | Auth | Delegates to |
| --- | --- | --- | --- |
| `GET /` | `service_info` | no | constant `ServiceInfo` |
| `GET /health` | `health` | no | `service.health()` |
| `GET /tables` | `list_tables` | yes | `service.list_tables()` |
| `GET /tables/{table}` | `describe_table` | yes | `service.describe_table()` |
| `POST /schema/refresh` | `refresh_schema` | yes | `service.refresh_schema()` |
| `GET /tables/{table}/rows` | `read_rows` | yes | `service.fetch_rows()` |
| `GET /clients` | `list_clients` | yes | `service.fetch_clients()` |
| `GET /agreements` | `list_agreements` | yes | `service.fetch_agreements()` |
| `POST /query` | `run_query` | yes | `service.run_query()` |

Notes:

- Protection is a single shared list, `protected = [Depends(require_api_key(settings))]`,
  attached via `dependencies=` — health and service info stay public so a
  container orchestrator can probe them without credentials.
- When `api.api_key` is `None` the closure returns immediately; comparison uses
  `hmac.compare_digest` to avoid timing leaks.
- Query-parameter bounds (`ge=1`, `le=api.max_limit`, `max_length=100`) are
  generated from the settings, so `api.max_limit` is enforced twice: by FastAPI
  (`422`) and by `service.check_limit()` (`400`, also used internally).
- Handlers return plain dicts; the declared `response_model` performs the
  validation/serialisation and generates the OpenAPI schema.

### `ks_adapter/config.py` — settings

The largest module, and the only one that reads files or environment variables.
See 4.4 for the pipeline; below is the inventory.

| Object | Role |
| --- | --- |
| `ConfigError` | `ValueError` subclass for every configuration problem |
| `PROJECT_ROOT` | `Path(__file__).resolve().parent.parent` — anchor for relative DB paths |
| `DEFAULT_CONFIG_PATH` | `PROJECT_ROOT / "config" / "config.yaml"` |
| `CONFIG_ENV_VAR` | `"KS_CONFIG"` |
| `LOG_LEVELS` | allowed `server.log_level` values (incl. `trace`) |
| `resolve_database_path(path, host=None)` | relative → project-relative, absolute/remote/blank untouched |
| `DatabaseSettings` | `path, user, password, charset, host, port, client_library, pool_size, acquire_timeout, health_check, check_path` |
| `ServerSettings` | `host, port, log_level, reload` |
| `ApiSettings` | `prefix, default_limit, max_limit, max_query_rows, schema_cache_ttl, blob_encoding, decimal_as_string, api_key, cors_origins` |
| `AppSettings` | `database, server, api, config_path` |
| `load_config(path=None)` | public entry point used by `__main__` and `create_app` |
| `_ENV_OVERRIDES` / `_ALLOWED_KEYS` | mapping of setting → environment variable, and per-section whitelist |
| `_expand_env`, `_apply_env_overrides`, `_build_settings` | pipeline stages |
| `_section`, `_check_keys`, `_get`, `_str`, `_optional_str`, `_int`, `_float`, `_bool`, `_str_tuple` | typed coercion helpers that raise `ConfigError` with the full key name |

Notes:

- All four dataclasses are `frozen=True`; `ServerSettings`/`ApiSettings` normalise
  values by `object.__setattr__` in `__post_init__` (lower-cased log level,
  `api/v1` → `/api/v1`, trailing slash removed).
- `DatabaseSettings.__post_init__` requires a non-empty `path`/`user`, a valid
  `port`, `pool_size ≥ 1`, `acquire_timeout > 0`, and — when `check_path` is on and
  no `host` is set — that the path points to an existing file. The check runs on the
  **resolved** path because `_build_settings` calls `resolve_database_path()` first.
- `DatabaseSettings.dsn` is a property, not stored state: `"{host}/{port}:{path}"`
  when remote, otherwise just `path`.
- `ApiSettings.__post_init__` cross-validates `default_limit ≤ max_limit` and
  verifies `blob_encoding` with `codecs.lookup()`.
- Environment overrides are applied *after* `${...}` expansion, so `KS_DB_PATH`
  always wins over the YAML default; values are parsed by the same `_bool`/`_int`
  helpers (an empty string is treated as "unset" by `_apply_env_overrides`).
- Unknown keys are rejected at the root and inside each section (`_check_keys`), so
  a typo fails fast instead of being ignored.
- `config_path` on `AppSettings` is the absolute, resolved YAML path and is printed
  by `--check` and logged at startup.

### `ks_adapter/errors.py` — domain errors

A tiny hierarchy that couples business errors to HTTP semantics:

| Class | `status_code` | Meaning |
| --- | --- | --- |
| `AdapterError` | `500` | base class; stores `message` |
| `InvalidRequest` | `400` | malformed/unsupported request |
| `QueryNotAllowed` | `400` | SQL is not a single read-only `SELECT`/`WITH` |
| `ColumnNotFound` | `400` | filter/sort references an unknown column |
| `AuthenticationError` | `401` | missing/invalid `X-API-Key` |
| `TableNotFound` | `404` | table or view does not exist |
| `DatabaseUnavailable` | `503` | pool exhausted/closed or Firebird unreachable |

Because `app._adapter_error_handler` is registered for the base class, adding a new
subclass with a `status_code` is enough to get a correct HTTP response — no change
in `api.py` or `app.py` is needed.

### `ks_adapter/pool.py` — connection pool

Wraps the `fdb` DB-API driver. `api.py`, `schema.py` and `service.py` never call
`fdb.connect()` themselves.

| Object | Role |
| --- | --- |
| `connect(settings)` | opens one connection: `dsn`, `user`, `password`, `charset`, `sql_dialect=3`, plus `fb_library_name` when `database.client_library` is set |
| `ConnectionPool(settings)` | thread-safe LIFO pool of at most `pool_size` connections |
| `ConnectionPool.session()` | `@contextmanager` yielding a connection and always returning/discarding it |
| `ConnectionPool.ping()` | `SELECT 1 FROM RDB$DATABASE` + returns `connection.server_version` |
| `ConnectionPool.stats` | `{"created", "idle", "capacity"}` for `/health` |
| `ConnectionPool.close()` | idempotent drain of idle connections; later borrows fail with `DatabaseUnavailable` |

Notes:

- Borrowing is optimistic: `_take_idle()` → `_is_healthy()` → use; otherwise
  `_try_reserve_slot()` (guarded by `threading.Lock`, increments `_created`) →
  `_new_connection()`. When the pool is saturated the caller waits on the queue
  until `acquire_timeout`, then gets `DatabaseUnavailable` (`503`, not a hang).
- `_is_healthy()` skips the probe when `database.health_check` is `False` and only
  inspects `connection.closed`.
- `_release()` rolls back before returning the connection, which is what makes the
  adapter read-only in practice (no uncommitted work, no lingering record locks).
- A connection that fails `rollback()`, is flagged closed, or cannot be re-queued is
  closed and its slot released, so the pool self-heals after a Firebird restart.
- `fdb.connect()` failures are wrapped into `DatabaseUnavailable` with the DSN in
  the message, which is what the client sees in the `503` body.

### `ks_adapter/schema.py` — catalog introspection and cache

Turns the Firebird system tables into `TableInfo` objects with readable SQL types.

| Object | Role |
| --- | --- |
| `_TABLES_SQL` | `RDB$RELATIONS` filtered by `RDB$SYSTEM_FLAG = 0` → name, type, description |
| `_COLUMNS_SQL` | join of `RDB$RELATION_FIELDS`, `RDB$FIELDS`, `RDB$RELATIONS`, `RDB$CHARACTER_SETS` → name, position, null flag, default source, field type/sub-type/length/precision/scale, charset |
| `_FIELD_TYPES` | `RDB$FIELD_TYPE` id → SQL type (`7`→SMALLINT, `8`→INTEGER, `12`→DATE, `35`→TIMESTAMP, `37`→VARCHAR, `261`→BLOB, ...) |
| `describe_type(...)` | builds `VARCHAR(50)`, `NUMERIC(15,2)`, `BLOB SUB_TYPE TEXT`, ... |
| `ColumnInfo` | frozen dataclass with `to_dict()` |
| `TableInfo` | frozen dataclass with `column_names`, `column_map` (UPPER → canonical) and `to_dict(include_columns=False)` |
| `SchemaCache` | TTL cache: `tables()`, `names()`, `get(name)`, `invalidate()`, `loaded`, `ttl` |
| `_row_dict`, `_clean_text`, `_optional_int`, `_char_length` | result-set and type-conversion helpers |

Notes:

- Character length is derived from the byte length divided by the charset width
  (`UTF8` = 4, `UNICODE_FSS` = 3, single-byte charsets = 1), which is why a
  `VARCHAR(50)` in `WIN1250` is reported as 50 and not 200.
- `NUMERIC`/`DECIMAL` are detected by a non-zero scale; subtypes `1`/`2` of `BLOB`
  distinguish `BLOB SUB_TYPE TEXT` from a binary `BLOB`.
- `column_map` is the safety mechanism used by `sql.build_where`,
  `build_search` and `service._order_clause`: a request can only ever reference a
  column that really exists, spelled exactly as Firebird stores it.
- `SchemaCache.tables()` checks the snapshot outside the lock first, then again
  inside, so a burst of concurrent first requests triggers a single catalog read.
- `get()` falls back to a case-insensitive scan (handles `klient` vs `KLIENT`) and
  raises `TableNotFound` when nothing matches.
- A failing catalog query is wrapped into `DatabaseUnavailable` so the API answers
  `503` instead of leaking a driver exception.

### `ks_adapter/sql.py` — SQL construction and the read-only guard

The only place where SQL text is assembled. It never concatenates user *values*
into a statement; only validated identifiers.

| Object | Role |
| --- | --- |
| `quote_identifier(name)` | `"NAME"`, doubling embedded quotes; rejects empty input |
| `ensure_read_only(sql)` | validates a statement and returns it without trailing `;` |
| `strip_sql_literals(sql)` | removes `--` and `/* */` comments plus `'...'`/`"..."` literals |
| `Filter` | frozen dataclass (`column`, `operator`, `value`) |
| `parse_filters(raw)` | JSON → `list[Filter]`; bare value means `eq` |
| `build_where(filters, columns)` | `(" WHERE ...", [params])` |
| `build_search(term, columns, candidates)` | `(" WHERE (... OR ...)", [params])` |
| `_COMPARISON_OPERATORS` / `_PATTERN_OPERATORS` / `_OPERATORS` | `eq, ne, gt, ge, lt, le` → `=, <>, >, >=, <, <=`; `like, contains, startswith, endswith, in, isnull, notnull` |
| `_scalar`, `_like_pattern` | value validation and LIKE escaping |

Notes:

- The literal stripper is a small state machine. It understands doubled quotes
  (`''` inside a string), so `"SELECT 'delete' FROM ..."` passes the guard while an
  actual `DELETE` after a `--` comment is still caught; an unterminated comment or
  literal is rejected outright.
- Two statements are refused by splitting the sanitised text on `;` — string
  literals can contain `;` safely because they were already replaced by a space.
- `_FORBIDDEN_KEYWORDS` is scanned with word boundaries on the sanitised, lower-cased
  statement; it also blocks `SET`, `BEGIN`, `CONNECT`, `COMMIT`, `ROLLBACK`, so
  session or transaction control cannot be smuggled in.
- `_LIKE_PARAMETER = "CAST(? AS VARCHAR(1024))"` exists because Firebird derives a
  parameter's length from the column it is compared with; a long pattern over a
  short column such as `KOD` would otherwise raise "arithmetic exception, numeric
  overflow". The cast widens the parameter for every `LIKE`.
- `_like_pattern()` escapes `\`, `%` and `_` and the generated SQL always uses
  `ESCAPE '\'`, so a search term is matched literally.
- `IS NULL` / `IS NOT NULL` are emitted for `isnull`/`notnull` and for
  `eq`/`ne` with a `null` value (`IN` requires a non-empty array).

### `ks_adapter/serialization.py` — value conversion

Pure functions, no database access, therefore trivially unit-testable.

| Object | Role |
| --- | --- |
| `to_jsonable(value, decimal_as_string, blob_encoding)` | converts a single value (see the table in 4.5) |
| `unique_column_names(description, fallback="column")` | cursor column names, duplicates suffixed `_2`, `_3` |
| `row_to_dict(row, names, ...)` | `{column: jsonable}` |
| `serialize_rows(description, rows, ...)` | `(names, [row_dict, ...])` — used by `fetch_rows` and `run_query` |

The module docstring explains *why* it exists: `fdb` returns `Decimal`,
`datetime`, `bytes` and friends, which FastAPI cannot serialise natively.

### `ks_adapter/service.py` — business logic

`DatabaseService` is the only class the API layer talks to; it owns the pool and the
schema cache.

```
DatabaseService(settings, pool=None)
    self.pool    = ConnectionPool(settings.database)
    self.schema  = SchemaCache(self.pool, settings.api.schema_cache_ttl)
```

| Member | Behaviour |
| --- | --- |
| `close()` | closes the pool (called from the app lifespan) |
| `health()` | `pool.ping()` + DSN/charset/server version + pool stats + `latency_ms` |
| `list_tables()` | `schema.tables()` → summaries sorted case-insensitively |
| `describe_table(table)` | summary + columns; `TableNotFound` → `404` |
| `refresh_schema()` | `invalidate()` then reload; returns the table count |
| `fetch_rows(table, limit, offset, order_by, filters)` | `COUNT(*)` + one page |
| `fetch_clients(limit, offset, search)` | stable client projection of `KLIENT` |
| `fetch_agreements(limit, offset, search)` | stable agreement projection of `UMOWACPC` |
| `run_query(sql, limit, parameters)` | guarded ad-hoc `SELECT`/`WITH` |
| `check_limit(limit, maximum=None, default=None)` | clamps to `api.*` limits, raises `InvalidRequest` |
| `_order_clause(order_by, info)` | validates `COLUMN ASC` / `COLUMN DESC` entries, quotes names |
| `_projection_page(table, fields, search_columns, ...)` | shared `COUNT(*)` + page query of the curated endpoints |
| `_default_order_clause(info, columns)` | `ORDER BY` over the first available `columns` (`"NAZWA"`, `"ID_KLIENT_TABLE"` for clients, `"UMOWA"`, `"ID_UMOWACPC_TABLE"` for agreements) |
| `_check_parameters(parameters)` | only `str`/`bool`/`int`/`float`/`None` |

Module constants:

- `CLIENTS_TABLE = "KLIENT"`.
- `CLIENT_FIELDS` — 19 `(column, json alias)` pairs: `ID_KLIENT_TABLE`→`id`,
  `ID_KLIENT`→`client_id`, `NAZWA`→`name`, `NAZWA_S`→`short_name`, `NIP`, `REGON`,
  `ADRES`→`address`, `KOD`→`postcode`, `POCZTA`→`city`, `WOJEWODZTWO`→`province`,
  `TELEFON`→`phone`, `E_MAIL`→`email`, `WWW`→`website`, `TYP`→`type`,
  `AKTYWNY`→`active`, `PLATNOSC`→`payment_method`, `TERMIN`→`payment_days`,
  `RABAT`→`discount`, `OSTATNIO`→`last_contact`.
- `CLIENT_SEARCH_COLUMNS` — the eight columns matched by `search`.
- `AGREEMENTS_TABLE = "UMOWACPC"` — service agreements (contracts).
- `AGREEMENT_FIELDS` — 28 `(column, json alias)` pairs: `ID_UMOWACPC_TABLE`→`id`,
  `ID_UMOWACPC`→`agreement_id`, `ID_ODDZIAL`→`branch_id`, `ID_KLIENT`→`client_id`,
  `ID_ODBIORCA`→`recipient_id`, `ID_FIRMA`→`company_id`, `UMOWA`→`number`,
  `TYP`→`type`, `HANDLOWIEC`→`salesperson`, `OPIEKUN`→`supervisor`,
  `OPIEKUNMAIL`→`supervisor_email`, `OPIEKUNTEL`→`supervisor_phone`,
  `U_START`→`start_date`, `U_STOP`→`end_date`, `WARUNKI`→`terms`, `UWAGI`→`notes`,
  `KOSZTY`→`costs`, `PRZYCHODY`→`revenue`, `WYNIK`→`profit`, `RABAT`→`discount`,
  `PLATNOSC`→`payment_method`, `TERMIN`→`payment_days`, `AKTYWNA`→`active`,
  `STRONY_MONO`→`pages_mono`, `STRONY_KOLOR`→`pages_color`, `SKANY`→`scans`,
  `FRAEMAIL`→`invoice_email`, `PLIK`→`file`. The printing parameters
  (`FRAPAR1..12`, `FRANAZ1..10`/`IDMAG1..10`) and the unit prices (`UOPLATA*`,
  `OPLATA_*`) are intentionally not exposed.
- `AGREEMENT_SEARCH_COLUMNS` — the seven columns matched by `search`
  (`UMOWA`, `TYP`, `HANDLOWIEC`, `OPIEKUN`, `OPIEKUNMAIL`, `FRAEMAIL`, `PLIK`).

Notes:

- `fetch_clients` / `fetch_agreements` are the reason the adapter is not a generic
  table browser: they keep a hand-picked, stable projection instead of exposing all
  61 columns of `KLIENT` or all 83 columns of `UMOWACPC`, and silently drop fields
  that the connected database does not have.
- Both page queries use `ROWS {offset+1} TO {offset+limit}` (dialect 3). The values
  are Python ints validated by `check_limit`/`offset`, never raw strings.
- `fetch_rows`, `fetch_clients` and `fetch_agreements` run the `COUNT(*)` and the
  page query on the **same** connection, inside one `pool.session()`, so `total`
  and the page cannot disagree because of a reconnect.
- `run_query` returns an empty result set when `cursor.description is None` (a
  statement without a result set) instead of failing.
- Read-only intent is also expressed here: no `commit()` ever happens; the pool
  rolls back after each session.

### `ks_adapter/schemas.py` — Pydantic models

Defines the wire format; FastAPI uses these for validation, serialisation and the
OpenAPI document.

| Group | Models |
| --- | --- |
| Meta | `ServiceInfo`, `HealthResponse` (`DatabaseInfo`, `PoolInfo`) |
| Schema | `TableSummary`, `TableListResponse`, `TableDetail` (adds `columns: list[ColumnModel]`), `ColumnModel`, `SchemaRefreshResponse` |
| Data | `RowPage`, `Client`, `ClientPage`, `Agreement`, `AgreementPage`, `QueryRequest`, `QueryResponse` |
| Errors | `ErrorResponse` (`detail`, `error`) |

Notes:

- `Client` uses JSON names (`name`, `nip`, `payment_days`, ...) and mirrors
  `service.CLIENT_FIELDS`; every field is optional, so a missing database column
  never breaks validation. `Agreement` does the same for `service.AGREEMENT_FIELDS`
  and uses the `DecimalValue = float | str` alias, because `NUMERIC`/`DECIMAL`
  columns are serialised as floats by default and as strings when
  `api.decimal_as_string` is on.
- `TableDetail` inherits `TableSummary`, so listing and detail responses always
  share `name`, `kind`, `column_count`, `description`.
- `ErrorResponse` is documentation only: the handlers in `app.py` build the JSON
  dict themselves, which keeps the body identical for domain and driver errors.
- Request models (`QueryRequest`) are the only place that constrains *input*
  besides the query parameters declared in `api.py`.

### `config/config.yaml` — the configuration file

The only settings file; read by `config.load_config()` (see 4.4). Structure:

| Section | Keys | Consumed by |
| --- | --- | --- |
| `server` | `host`, `port`, `log_level`, `reload` | `__main__.main()` (uvicorn + logging) |
| `database` (connection) | `path`, `host`, `port`, `user`, `password`, `charset`, `client_library` | `DatabaseSettings` → `pool.connect()`, `dsn` |
| `database` (behaviour) | `pool_size`, `acquire_timeout`, `health_check`, `check_path` | `ConnectionPool` limits, startup validation |
| `api` | `prefix`, `default_limit`, `max_limit`, `max_query_rows`, `schema_cache_ttl`, `blob_encoding`, `decimal_as_string`, `api_key`, `cors_origins` | `ApiSettings` → router, service limits, serialisation, CORS |

Notes:

- Values are mostly `${VAR:-default}` placeholders, so the file documents the
  defaults while the environment stays authoritative (this is how passwords are
  supplied without committing them).
- `database.path: ${KS_DB_PATH:-BAZAMS.FDB}` is intentionally relative: it resolves
  to `<project>/BAZAMS.FDB` from any working directory. Set an absolute path or a
  remote `host` to point elsewhere.
- `charset: WIN1250` and `blob_encoding: cp1250` are paired — both reflect the
  Polish `BAZAMS.FDB` data. `UTF8` in the YAML would need a matching
  `blob_encoding` such as `utf-8`.
- `client_library` is commented out, letting `fdb` find `fbclient.dll` /
  `libfbclient.so` on the system path; set it (or `KS_FB_CLIENT`) to an absolute
  path to pin a specific Firebird installation.
- `api.api_key: ${KS_API_KEY:-}` resolves to an empty string, which
  `_optional_str()` converts to `None` → authentication disabled by default.
- `cors_origins: []` → the CORS middleware is not installed at all.

### `requirements.txt`

Runtime dependencies only:

| Package | Why |
| --- | --- |
| `fastapi>=0.100,<1.0` | routing, request/response validation, OpenAPI |
| `uvicorn>=0.23,<1.0` | ASGI server |
| `fdb>=2.0.4,<3.0` | Firebird DB-API 2.0 driver (needs the native client library) |
| `PyYAML>=6.0,<7.0` | reading `config/config.yaml` |

### `requirements-dev.txt`

`-r requirements.txt` plus `pytest>=7.4` (test runner) and `httpx>=0.25` (required by
FastAPI's `TestClient`). Nothing else is used, so production installs stay small.

### `pytest.ini`

```ini
[pytest]
testpaths = tests
markers =
    integration: requires a live Firebird database (set KS_TEST_DB_PATH to enable)
```

It limits collection to `tests/` (so `docs/` or a stray script cannot be collected)
and registers the `integration` marker, which `tests/test_integration.py` uses to opt
in only when a real database is available.

### `.gitignore`

Ignores Python bytecode, `.venv/`/`venv/`, `.pytest_cache/`, coverage output, logs,
temporary `.tmp_*` files and — importantly — `*.fdb` / `*.FDB`, so the database file
(and any customer data inside it) is never committed. Note that the project
directory is not a git repository (yet), so the file has no effect until `git init`.

### `README.md`

The user-facing manual: features, requirements, installation, configuration
(including the relative-`database.path` rule), the environment-variable table, how to
run and `--check`, the full endpoint reference with examples, the error-code table,
the read-only guarantees, the test instructions and the project layout. It is the
document to read first; this file is the companion for implementers.

### `BAZAMS.FDB`

The Firebird database the adapter reads (the current copy holds a single `KLIENT`
row and an empty `UMOWACPC` table). It is a binary asset, not code: it is
referenced by `database.path` and git-ignored. Moving or replacing it only requires
changing `config/config.yaml` / `KS_DB_PATH`.

### `docs/ARCHITECTURE.md`

This document.

---

## 6. Import graph and layering rules

```
__main__.py ──► config.py
    └──► app.py ──► api.py ──► config.py, errors.py, schemas.py, service.py
              ├──► service.py ──► config.py, errors.py, pool.py, schema.py,
              │                                 sql.py, serialization.py
              ├──► errors.py
              └──► config.py
pool.py ──► config.py, errors.py, fdb
schema.py ──► errors.py, pool.py
sql.py ──► errors.py
serialization.py ──► (stdlib only)
schemas.py ──► pydantic
```

Rules to preserve when extending the adapter:

1. Only `pool.py` (and `app.py`, for the `fdb.Error` handler) imports `fdb`.
2. Only `app.py` / `api.py` import `fastapi`; nothing below `api.py` returns an HTTP
   concept. Errors travel as `AdapterError` subclasses.
3. SQL text is produced only in `service.py` and `sql.py`, and every identifier in it
   comes from `schema.TableInfo.column_map`.
4. `config.py` is read-only after import: settings are passed down as immutable
   dataclasses, never re-read from the environment in the middle of a request.

---

## 7. Where to change what

| Task | Files to touch |
| --- | --- |
| Point at a different `.fdb` | `config/config.yaml` (`database.path`) or `KS_DB_PATH` only |
| Connect to a remote Firebird server | `database.host` (+ `database.port`) in the YAML; the path becomes server-side |
| Add a field to `GET /clients` | `service.CLIENT_FIELDS` (+ `service.CLIENT_SEARCH_COLUMNS` if it should be searchable) and `schemas.Client`; update `README.md` |
| Add a field to `GET /agreements` | `service.AGREEMENT_FIELDS` (+ `service.AGREEMENT_SEARCH_COLUMNS` if it should be searchable) and `schemas.Agreement`; update `README.md` |
| Expose another table as a dedicated endpoint | new method in `service.DatabaseService` (reuse `_projection_page` for a curated view), new response model in `schemas.py`, new route in `api.create_router`, README |
| Add a new config setting | `config.py` (`_ALLOWED_KEYS`, `_ENV_OVERRIDES`, dataclass field, `_build_settings`), `config/config.yaml`, `README.md` |
| Change page limits / cache TTL / API key | `api.*` in the YAML or the matching `KS_*` variable; no code change |
| Tune connection handling | `database.pool_size`, `acquire_timeout`, `health_check` |
| Add a new error kind | subclass in `errors.py` with a `status_code`; raise it from `service.py`/`sql.py` |
| Change value serialisation | `serialization.py` (`to_jsonable`) and/or `api.decimal_as_string`, `api.blob_encoding` |
| Change the Firebird client library | `database.client_library` / `KS_FB_CLIENT`, or leave empty to use the system path |

### Checklist for a new endpoint

1. `service.py` — add a method that validates input, builds SQL with quoted
   identifiers and bound parameters, and runs it inside `self.pool.session()`.
2. `schemas.py` — describe the response (and a request model if there is a body).
3. `api.py` — add the route inside `create_router`, add `dependencies=protected`
   unless the endpoint must stay public, and declare bounds for its parameters.
4. `README.md` — document the route in the endpoint table.
5. Verify with `python -m ks_adapter --check` and `python -m pytest`.
