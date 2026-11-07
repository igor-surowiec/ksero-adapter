# ks-adapter — architecture

`ks-adapter` is a small **read-only HTTP gateway in front of a Firebird database**
(verified against Firebird 2.5). It is one Python package, started as
`python -m ks_adapter`, which serves a FastAPI app through uvicorn.

The document has two parts — **the flow of a request** and **what every file does** —
plus a short change checklist at the end. Installation, configuration keys and the full
HTTP contract are in [`README.md`](../README.md).

---

## 1. Flow of the app

### 1.1 Startup

```
python -m ks_adapter [--config C] [--host H] [--port P] [--log-level L] [--reload] [--check]
        │
  __main__.main()      argparse → config.load_config() → CLI overrides → root logger
        ├── --check    → service.health() + service.list_tables()
        │                print config path / DSN / Firebird version / table count → exit 0 (1 if DB down)
        └── otherwise  → uvicorn.run(...)
                             │
                      app.create_app(settings)
                             ├─ FastAPI(title, version = ks_adapter.__version__, lifespan,
                             │          error handlers, CORS only if api.cors_origins)
                             ├─ app.state.settings / app.state.service = DatabaseService(settings)
                             ├─ api.create_router(settings)   → all routes, prefix from settings
                             └─ GET /  (public liveness route, outside the API prefix)
```

- Settings come from `config/config.yaml`, then `${VAR}` expansion, then `KS_*`
  environment overrides (`load_config()` returns immutable dataclasses).
- `create_app` only **owns** the service it created itself; an injected service
  (`create_app(settings, service)`, used by tests) is not closed on shutdown.
- **Nothing touches the database at startup**: the schema cache and the connection
  pool fill lazily on the first request, so an unreachable database gives `503`
  instead of a failed boot.
- `--reload` cannot receive an app object, so the config path is exported to
  `KS_CONFIG` and uvicorn imports `ks_adapter.app:create_app` as a factory.

### 1.2 Request pipeline

```
uvicorn (ASGI)                     worker thread (every endpoint is a sync `def`)
   │                                     │
   ├─ routing ──────────────────────────► api.create_router.<handler>
   │                                        ├─ Depends(require_api_key)  → 401
   │                                        ├─ FastAPI param/body checks → 422
   │                                        └─ Depends(get_service)      → app.state.service
   │                                                │
   │                                        service.DatabaseService.<method>()
   │                                                ├─ schema.SchemaCache.get()  → 404 TableNotFound
   │                                                ├─ sql.build_where / build_search
   │                                                │      (quoted identifiers, ? parameters)
   │                                                ├─ service.check_limit()     → 400
   │                                                └─ pool.session()
   │                                                       ├─ borrow idle conn / open new (≤ pool_size)
   │                                                       ├─ cursor.execute(sql, params)
   │                                                       └─ rollback + return to the pool
   │                                                │
   │                                        serialization.to_jsonable / serialize_rows
   │                                                │
   │                                        Pydantic response_model (schemas.py)
   ▼                                                │
response ◄──────────────────────────────────────────┘
```

- Sync handlers run in Starlette's threadpool, so blocking `fdb` calls never block the
  event loop; concurrency is bounded by the threadpool and `database.pool_size`.
- Each service call borrows **one** connection and always rolls it back, so no
  transaction or record lock outlives a request — that, plus the query guard, is what
  makes the adapter read-only.
- Identifiers can only come from the catalog snapshot (`TableInfo.column_map`); every
  user value is a bound parameter. SQL text is built only in `sql.py`/`service.py`.
- `SchemaCache.get()` is consulted by the table-oriented endpoints only
  (`/tables/...`, `/clients`, `/agreements`, `/machines`, `/orders`, `/invoices`);
  `/health` and `/query` skip it.

### 1.3 Example traces

`GET /api/v1/machines?limit=5&offset=5&search=konica`

1. `api.list_machines` — API key check, `limit ≤ api.max_limit`, `search ≤ 100` chars.
2. `service.fetch_machines` → `check_limit()` → `_projection_page(MACHINES_TABLE,
   MACHINE_FIELDS, MACHINE_SEARCH_COLUMNS, limit=..., offset=...,
   order_columns=("ID_MASZYNA", "ID_MASZYNA_TABLE"), label="machine")`.
3. `_projection_page` — `SchemaCache.get("MASZYNA")`, `sql.build_search()` over the
   searchable columns that actually exist, then `COUNT(*)` and the page query
   (`ROWS 6 TO 10`) on the **same** connection.
4. Rows → JSON-safe values → aliased (`MARKA` → `brand`, ...) → `MachinePage` → JSON.

Variations:

- `/orders` is the same call with `ORDER_FIELDS`/`ORDER_SEARCH_COLUMNS`; `ZLECENIE` is
  the widest table of the schema, so both lists are size-bounded (Firebird rejects a
  statement message wider than 64 KB with `-204 Implementation limit exceeded`, which
  `SELECT *` on a very wide table or a `LIKE` over every text column would eventually
  hit — see `sql.MAX_SEARCH_COLUMNS`).
- `/invoices` is the same call with `INVOICE_FIELDS`/`INVOICE_SEARCH_COLUMNS` over
  `FAKTURA`. That table is the invoice **header**: the positions live in `FPOZYCJA`
  and are not exposed, and the per-VAT-rate matrix, the pre-correction block, the
  `F_*` marker flags and the synchronisation bookkeeping columns are left out of the
  projection. Ordering is `DATA_WYST, ID_FAKTURA_TABLE` so pages stay stable.
- `/tables/{table}/rows` adds `sql.parse_filters()` + `build_where()` (bad JSON,
  operator or column → `400`) and `_order_clause()` for `order_by`.
- `POST /query` runs `sql.ensure_read_only()` (single `SELECT`/`WITH`; write/DDL/session
  keywords and a second statement rejected), caps rows at `api.max_query_rows`, and
  fetches one extra row only to set `truncated`.

### 1.4 Errors and shutdown

| Raised in | Type | HTTP |
| --- | --- | --- |
| `sql.py`, `service.py` | `InvalidRequest`, `QueryNotAllowed`, `ColumnNotFound` | `400` |
| `api.py` | `AuthenticationError` | `401` |
| `schema.py` | `TableNotFound` | `404` |
| `pool.py`, `schema.py` | `DatabaseUnavailable` | `503` |
| request/response models | Pydantic `ValidationError` | `422` |
| anywhere | uncaught `fdb.Error` | `500` (traceback logged) |
| `config.py` at startup | `ConfigError` | stderr + exit `2` |

`app._adapter_error_handler` renders any `AdapterError` as
`{"detail": ..., "error": <class name>}` using its `status_code`, so a new error kind is
just a new subclass in `errors.py`.

Shutdown: uvicorn stops → `lifespan` exits → `DatabaseService.close()` →
`ConnectionPool.close()` (marks the pool closed, closes idle connections).

---

## 2. Files

### Package `ks_adapter/`

**`__init__.py`** — package marker. Defines `__version__`, the single source of the
version in the OpenAPI schema, `GET /`, `GET /api/v1/` and the startup log line.

**`__main__.py`** — CLI entry point, no database logic. `build_parser()`, `main(argv)`
(returns an exit code; the module ends with `raise SystemExit(main())`), and
`_check(settings)`. `uvicorn` and `DatabaseService` are imported lazily, so `--help` and
config errors work without the Firebird client. `ConfigError` → exit `2`, failed
`--check` → `1`, success → `0`.

**`app.py`** — application factory. `create_app(settings=None, service=None)`,
`DESCRIPTION` (text rendered in `/docs`), `_adapter_error_handler`,
`_firebird_error_handler`. Owns the `lifespan` (closes the service it created),
registers the router, adds CORS only when origins are configured, and serves the
unauthenticated `GET /` liveness route.

**`api.py`** — the whole HTTP surface, built as a factory. `create_router(settings)`,
`get_service()`, `require_api_key(settings)` (returns the `check_api_key` dependency,
`hmac.compare_digest`, disabled when `api.api_key` is `None`), `FILTERS_DESCRIPTION`.
Routes: `GET /`, `GET /health` (public), `GET /tables`, `GET /tables/{table}`,
`POST /schema/refresh`, `GET /tables/{table}/rows`, `GET /clients`, `GET /agreements`,
`GET /machines`, `GET /orders`, `GET /invoices`, `POST /query` (relative to
`api.prefix`); everything except the first two is protected by the shared `protected`
dependency list. Parameter bounds are generated from the settings; handlers return
plain dicts and the declared `response_model` does validation + OpenAPI.

**`config.py`** — the only module that reads files or the environment. `load_config()`
runs a fixed pipeline: explicit path → `$KS_CONFIG` → `<project>/config/config.yaml` →
`yaml.safe_load` → `_expand_env` → `_apply_env_overrides` → `_build_settings` (per-section
whitelist → frozen dataclasses → `__post_init__` validation) → `resolve_database_path()`.
Public objects: `ConfigError`, `AppSettings`, `DatabaseSettings` (with the `dsn`
property), `ServerSettings`, `ApiSettings`, `PROJECT_ROOT`, `DEFAULT_CONFIG_PATH`.
A relative `database.path` is resolved against `PROJECT_ROOT`, so the adapter works from
any working directory; unknown YAML keys raise instead of being silently ignored.

**`errors.py`** — the error hierarchy that couples failures to HTTP semantics:
`AdapterError` (500, base) → `InvalidRequest`, `QueryNotAllowed`, `ColumnNotFound`
(400), `AuthenticationError` (401), `TableNotFound` (404), `DatabaseUnavailable` (503).

**`pool.py`** — the only module that calls `fdb.connect()`. `connect(settings)` (dsn,
credentials, charset, `sql_dialect=3`, optional `fb_library_name`) and `ConnectionPool`:
a lock-guarded LIFO queue of at most `pool_size` connections with `session()` (borrow →
yield → rollback → return), `ping()` (`SELECT 1 FROM RDB$DATABASE` + `server_version`),
`stats` (`created`/`idle`/`capacity` for `/health`) and `close()`. Saturation waits up to
`acquire_timeout` and then raises `DatabaseUnavailable` (503, never a hang); broken
connections are discarded, so the pool survives a Firebird restart.

**`schema.py`** — catalog introspection + TTL cache. Reads `RDB$RELATIONS` and
`RDB$RELATION_FIELDS`/`RDB$FIELDS`/`RDB$CHARACTER_SETS`, maps `RDB$FIELD_TYPE` ids to SQL
types (`describe_type()` → `VARCHAR(50)`, `NUMERIC(15,2)`, `BLOB SUB_TYPE TEXT`) and
produces frozen `ColumnInfo` / `TableInfo`. `SchemaCache` offers `tables()`, `names()`,
`get(name)` (case-insensitive, else `TableNotFound`), `invalidate()` and the
`api.schema_cache_ttl` expiry. `TableInfo.column_map` is the whitelist that every filter,
search and sort column must pass.

**`sql.py`** — all SQL text assembly. `quote_identifier()` (``"NAME"``, embedded quotes
doubled), `ensure_read_only()`, `strip_sql_literals()` (drops comments and `'...'`/`"..."`
literals before the keyword scan), `Filter`, `parse_filters()`, `build_where()`,
`build_search()`. Operators: `eq, ne, gt, ge, lt, le, like, contains, startswith,
endswith, in, isnull, notnull`. Values are always `?` parameters; `LIKE` patterns escape
`\ % _`, use `ESCAPE '\'`, and wrap the parameter in `CAST(? AS VARCHAR(1024))` to avoid
Firebird's "arithmetic exception" on long patterns compared with short columns.
`LIKE_PARAMETER_BYTES`, `MAX_MESSAGE_BYTES` (65535) and `MAX_SEARCH_COLUMNS` (63) record
the other Firebird limit: a statement message may not exceed 64 KB, so one `WHERE`
cannot carry more than 63 such parameters. `build_search()` refuses a longer candidate
list instead of letting the server answer `-204 Implementation limit exceeded`.

**`serialization.py`** — pure value conversion, no database access. `to_jsonable()`
(`Decimal` → float, or str when `api.decimal_as_string`; dates/times → ISO-8601;
`timedelta` → seconds; bytes decoded with `api.blob_encoding` or `{"base64": ...}`;
non-finite floats → `null`), `unique_column_names()` (duplicates → `NAME_2`),
`row_to_dict()`, `serialize_rows()`.

**`service.py`** — `DatabaseService`, the only class the API layer talks to; it owns the
pool and the schema cache. Methods: `close()`, `health()`, `list_tables()`,
`describe_table()`, `refresh_schema()`, `fetch_rows()`, `fetch_clients()`,
`fetch_agreements()`, `fetch_machines()`, `fetch_orders()`, `fetch_invoices()`,
`run_query()`, plus the helpers `check_limit()`, `_order_clause()`,
`_projection_page()`, `_default_order_clause()` and `_check_parameters()`. Module
constants define the curated read models:
`CLIENTS_TABLE`/`CLIENT_FIELDS` + `CLIENT_SEARCH_COLUMNS`,
`AGREEMENTS_TABLE`/`AGREEMENT_FIELDS` + `AGREEMENT_SEARCH_COLUMNS`,
`MACHINES_TABLE`/`MACHINE_FIELDS` + `MACHINE_SEARCH_COLUMNS`,
`ORDERS_TABLE`/`ORDER_FIELDS` + `ORDER_SEARCH_COLUMNS`,
`INVOICES_TABLE`/`INVOICE_FIELDS` + `INVOICE_SEARCH_COLUMNS`. Each is a small hand-picked
subset of the table's columns, which keeps the endpoint stable even though the underlying
tables are very wide. `_projection_page()` is the shared implementation of `/clients`,
`/agreements`, `/machines`, `/orders` and `/invoices`: `COUNT(*)` plus the page query on
one connection, columns missing from the connected database silently skipped.

**`schemas.py`** — the wire format, and therefore the OpenAPI contract. `ServiceInfo`,
`HealthResponse`/`DatabaseInfo`/`PoolInfo`, `TableSummary`, `TableListResponse`,
`TableDetail`/`ColumnModel`, `SchemaRefreshResponse`, `RowPage`, `Client`/`ClientPage`,
`Agreement`/`AgreementPage`, `Machine`/`MachinePage`, `Order`/`OrderPage`,
`Invoice`/`InvoicePage`, `QueryRequest`/`QueryResponse`, `ErrorResponse`. Projection
fields are all optional, so a missing column never breaks validation, and money columns
use `DecimalValue = float | str`.

### Repository files

**`config/config.yaml`** — the single settings file. `server` (host, port, log_level,
reload), `database` (path, host, port, user, password, charset, client_library,
pool_size, acquire_timeout, health_check, check_path) and `api` (prefix, default_limit,
max_limit, max_query_rows, schema_cache_ttl, blob_encoding, decimal_as_string, api_key,
cors_origins). Values are `${VAR:-default}` placeholders, so the file documents the
defaults while the environment stays authoritative (this is how the password is supplied
without committing it). `database.path` is deliberately relative and is resolved against
the project root, `database.charset` and `api.blob_encoding` must describe the same
encoding, an empty `api_key` disables authentication and empty `cors_origins` skips the
middleware.

**`tests/`** — the pytest suite: `conftest.py` (settings fixture, `FakeService`, app and
client fixtures), `test_api.py` (routes through `TestClient`), `test_service.py`
(scripted fake cursors: generated SQL, bound parameters, field mapping, limits),
`test_config.py`, `test_sql.py`, `test_serialization.py`, `test_schema.py` (pure unit
tests of one module each), and `test_integration.py` (marked `integration`, runs only
when `KS_TEST_DB_PATH` points at a real database).

**`pytest.ini`** — limits collection to `tests/` and registers the `integration` marker.

**`requirements.txt`** — runtime only: `fastapi`, `uvicorn`, `fdb`, `PyYAML`.
**`requirements-dev.txt`** — the above plus `pytest` and `httpx` (required by
`TestClient`).

**`.gitignore`** — bytecode, virtualenvs, `.pytest_cache/`, coverage, logs, `.tmp_*` and
`*.fdb`/`*.FDB`, so the database (and its customer data) is never committed.

**`README.md`** — the short user manual: what the project is, install, configuration
(environment variables), the endpoint table with a few `curl` examples, error codes and
tests. Read it first; this file is the companion for implementers.

**`AGENTS.md`** — the working agreement for AI agents and new contributors: the
read-only/parameter/64 KB invariants, environment commands, layout, recipes for adding a
field, an endpoint or a setting, testing rules, style and the definition of done.

**`*.fdb`** — the Firebird database file the adapter reads. A binary, git-ignored asset
that lives outside the source tree and is referenced only by `database.path`; pointing at
another database needs no code change.

**`docs/ARCHITECTURE.md`** — this document.

---

## 3. Adding an endpoint, a field or a setting

1. **New endpoint** — method in `service.py` (reuse `_projection_page()` for a curated
   view), response model in `schemas.py`, route inside `api.create_router` with
   `dependencies=protected`, then a row in the `README.md` endpoint table.
2. **New field on a projection** — add the `(column, alias)` pair to the matching
   `*_FIELDS` constant (plus `*_SEARCH_COLUMNS` if it must be searchable) and the optional
   field in the Pydantic model; response details live in the OpenAPI schema, so `README.md`
   only changes when the endpoint description does.
3. **New setting** — `config.py` (`_ALLOWED_KEYS`, `_ENV_OVERRIDES`, dataclass field,
   `_build_settings`), `config/config.yaml`, plus the `README.md` environment table when the
   variable should be public.
4. Verify with `python -m ks_adapter --check` and `python -m pytest`.

