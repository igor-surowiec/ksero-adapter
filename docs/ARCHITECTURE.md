# ks-adapter — architecture

`ks-adapter` is a small **HTTP gateway in front of a Firebird database**
(verified against Firebird 2.5). It is one Python package, started as
`python -m ks_adapter`, which serves a FastAPI app through uvicorn. It is
read-only by default: the writing routes (`POST /clients`, `POST /machines`, `POST /agreements/{id_klient}`,
`PATCH /clients/{id_klient}`, `PATCH /machines/{id_maszyna}`,
`PATCH /agreements/{id_umowacpc}`,
`DELETE /clients/{id_klient}`)
are disabled unless `api.allow_writes` is set.

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
- Each service call borrows **one** connection. `pool.session()` always rolls it back,
  so no transaction or record lock outlives a read request — together with the query
  guard that is what keeps every read read-only. `pool.write_session()` (used by curated writes) commits on success and rolls back on any
  exception.
- Identifiers can only come from the catalog snapshot (`TableInfo.column_map`); every
  user value is a bound parameter. SQL text is built only in `sql.py`/`service.py`.
- `SchemaCache.get()` is consulted by the table-oriented endpoints only
  (`/tables/...`, `/clients`, `/agreements`, `/machines`, `/orders`, `/invoices`);
  `/health` and `/query` skip it.

### 1.3 Example traces

`GET /api/v1/machines?limit=5&offset=5&search=konica`

1. `api.list_machines` — API key check, `limit ≤ api.max_limit`, `search ≤ 100` chars.
2. `service.fetch_machines` → `check_limit()` → `_projection_page(MACHINES_TABLE,
   MACHINE_COLUMNS, MACHINE_SEARCH_COLUMNS, limit=..., offset=...,
   order_columns=("ID_MASZYNA", "ID_MASZYNA_TABLE"), label="machine")`.
3. `_projection_page` — `SchemaCache.get("MASZYNA")`, `sql.build_search()` over the
   searchable columns that actually exist, then `COUNT(*)` and the page query
   (`ROWS 6 TO 10`) on the **same** connection.
4. Rows → JSON-safe values → keyed by the lower-cased column name (`MARKA` → `marka`,
   ...) → `MachinePage` → JSON.

Variations:

- `/orders` is the same call with `ORDER_COLUMNS`/`ORDER_SEARCH_COLUMNS`; `ZLECENIE` is
  the widest table of the schema, so both lists are size-bounded (Firebird rejects a
  statement message wider than 64 KB with `-204 Implementation limit exceeded`, which
  `SELECT *` on a very wide table or a `LIKE` over every text column would eventually
  hit — see `sql.MAX_SEARCH_COLUMNS`).
- `/invoices` is the same call with `INVOICE_COLUMNS`/`INVOICE_SEARCH_COLUMNS` over
  `FAKTURA`. That table is the invoice **header**: the positions live in `FPOZYCJA`
  and are not exposed, and the per-VAT-rate matrix, the pre-correction block, the
  `F_*` marker flags and the synchronisation bookkeeping columns are left out of the
  projection. Ordering is `DATA_WYST, ID_FAKTURA_TABLE` so pages stay stable.
- `POST /query` runs `sql.ensure_read_only()` (single `SELECT`/`WITH`; write/DDL/session
  keywords and a second statement rejected), caps rows at `api.max_query_rows`, and
  fetches one extra row only to set `truncated`.
- `/tables/{table}/rows` adds `sql.parse_filters()` + `build_where()` (bad JSON,
  operator or column → `400`) and `_order_clause()` for `order_by`.
- `POST /clients` is a trace that writes. `WritesDisabled` → `403` when
  `api.allow_writes` is off, `InvalidRequest` → `400` for a missing/blank `nazwa`, an
  unknown field or an over-long value, then `_insert_plan()` merges the payload with
  `CLIENT_INSERT_DEFAULTS` — the row profile the legacy program writes (`ID_FIRMA` `0`,
  `TYP` `Odbiorca`, `PLATNOSC` `Gotówka`, `KOD_KRAJU` `PL`, empty strings, zeroed
  flags) — and `build_insert("KLIENT", columns, returning=CLIENT_COLUMNS)` runs with
  one bound parameter per column inside `pool.write_session()`. The defaults are not
  cosmetics: the program filters its contractor list by `ID_FIRMA` and never shows a
  row carrying the trigger fallback of `1`. `RETURNING` hands back the row the
  `INS_KLIENT_RECORD` trigger completed (the generated
  `ID_KLIENT_TABLE`/`ID_KLIENT`), so the answer is the same `Client` projection
  `GET /clients` serves, with `201`.
- `POST /machines` follows the same shape. The `MachineCreate` body is dumped without
  its `null` fields, `service.create_machine` maps the keys onto
  `MACHINE_WRITE_COLUMNS` (trimming strings, dropping blanks, rejecting unknown fields
  and invalid supplied client IDs), keeps only the columns present in the catalog
  snapshot, merges `MACHINE_INSERT_DEFAULTS` (`ID_KLIENT` defaults to `0` for
  unassigned machines) through `_insert_plan()`, and calls `build_insert("MASZYNA", columns, returning=MACHINE_COLUMNS)`
  inside `pool.write_session()`. `RETURNING` yields the row `INS_MASZYNA_RECORD`
  completed (generated `ID_MASZYNA_TABLE`/`ID_MASZYNA`, default `ID_ODDZIAL` and
  `ID_FIRMA`), so the answer is a `Machine` with `201`. `SYNWP` is never set, so
  nothing is queued for synchronisation.

`POST /agreements/{id_klient}` validates `AgreementCreate` and calls `create_agreement()`.
A positive `ID_KLIENT` comes from the URL path; the optional body contains
only agreement details. Both agreement identifiers are read-only.
The service normalises `AGREEMENT_WRITE_COLUMNS` with `AGREEMENT_TEXT_LENGTHS`
and merges `AGREEMENT_INSERT_DEFAULTS` through `_insert_plan()`. It opens
`pool.write_session(reserve_table="UMOWACPC")`, which rolls back any idle health
check transaction and starts READ COMMITTED with a PROTECTED WRITE reservation.
This serialises agreement writers across connections and service processes.
The lock timeout uses `database.acquire_timeout` in whole seconds (minimum one).

`sql.build_next_available_id()` finds the smallest unused positive INTEGER
from candidate `1` and successors of occupied IDs, ignoring nonpositive IDs and
avoiding INTEGER overflow. The service binds that ID into `build_insert()` and
serialises RETURNING before committing the same transaction. Deletions therefore
make IDs reusable; concurrent allocations cannot choose the same gap. Firebird
still generates the surrogate `ID_UMOWACPC_TABLE`. The response is an `Agreement`
with `201`. Calculated financial totals remain excluded from the payload.
The static profile matches legacy agreement `ID_UMOWACPC=1`, including
`AKTYWNA=TAK`. If `U_START` is omitted or null, the service reads Firebird
`CURRENT_DATE` within the reserved transaction and inserts that date. Supplied
start dates and active flags win. Type, company, agreement number and end date
have no inferred default. No new database objects are needed.

Agreement payloads also accept an optional `machines` array. `_agreement_payload()`
separates it from column values, validates positive INTEGER IDs, limits list
size and removes repeated entries. Machine metadata is loaded before opening
the write transaction, so a pool with one connection also works. After the
agreement insert/update, `_link_agreement_machines()` uses that same cursor:
it resolves each `ID_MASZYNA` to exactly one surrogate key, then applies
`sql.build_update()` to set only `MASZYNA.ID_UMOWACPC`. Missing and ambiguous
records raise `RecordNotFound` / `RecordConflict`, rolling back the agreement
and every prior machine link. Machine ownership is preserved. Omission is represented by None and leaves
links unchanged. A supplied list (including empty) replaces all links: a bound
`build_update()` clears this agreement's existing references to NULL before
assigning the requested records. Missing/ambiguous IDs roll back those clears
as well. Other agreements' unlisted machines remain untouched.

`PATCH /agreements/{id_umowacpc}` validates `AgreementUpdate`, preserves omitted
fields and opens the same reserved agreement transaction. A bounded SELECT
rejects missing/ambiguous agreement business IDs. It updates supplied columns
with `build_update()` / RETURNING, optionally links machines, serialises the
agreement and commits. It does not apply insertion defaults. A request may
contain only the machine array; a completely empty update is refused.

`PATCH /clients/{id_klient}` passes only explicitly supplied fields from
`ClientUpdate` to `DatabaseService.update_client()`. It uses the same write gate
and field whitelist, preserving explicit nulls and blanks when normalising.
The service rejects an empty patch, a cleared name and unavailable columns.
`sql.build_update()` builds `UPDATE ... WHERE ID_KLIENT = ? RETURNING ...`
with bound values and a bound unique key. It runs in `pool.write_session()`;
missing records (including Firebird's NULL-filled RETURNING tuple) raise
`RecordNotFound` inside the transaction and roll back. Successful updates return
the client projection with `200`. Insert defaults are never merged into updates.

`PATCH /machines/{id_maszyna}` passes only explicitly supplied `MachineUpdate`
fields to `update_machine()`. The service enforces the write gate, a positive
business ID, `MACHINE_WRITE_COLUMNS`, text widths and catalog nullability.
`id_klient=0` unassigns ownership; null is invalid for non-nullable columns.
Inside one `write_session()`, a bound `SELECT FIRST 2` checks whether the
business ID is ambiguous (`RecordConflict`, `409`), since the database does not
constrain it to be unique. A parameterised `build_update()` with `RETURNING`
changes supplied columns only. Missing records raise `RecordNotFound` (`404`);
errors roll back. Successful responses are the stored `Machine` with `200`.
Existing update triggers, including propagation to related orders, still run.

`DELETE /clients/{id_klient}` calls `DatabaseService.delete_client()` with a
positive business identifier. The service enforces `_require_writes()`, resolves
the key through the catalog and uses `sql.build_delete()` to produce
`DELETE FROM "KLIENT" WHERE "ID_KLIENT" = ? RETURNING "ID_KLIENT"`.
`_write_row()` detects missing clients (`RecordNotFound`, `404`) and commits only
on success. The existing `DEL_KLIENT_RECORD` trigger deletes matching machines
and contacts within the same transaction. The route returns an empty `204`.

CPC settlements use `GET /cpc-settlement`, `GET /cpc-settlement/{id_cpc_table}`, `POST /cpc-settlement`,
`PATCH /cpc-settlement/{id_cpc_table}` and `DELETE /cpc-settlement/{id_cpc_table}`. The generated
primary key is the only record identifier, including legacy key 0. `fetch_cpc()`
uses `_projection_page()` with optional JSON filters combined with invoice/notes
search. `get_cpc()` uses a guarded bound SELECT and returns 404 for no match.

`CPC_COLUMNS` omits internal version bookkeeping. `CpcCreate` requires parent
IDs; omitted/null year and month come independently from Firebird CURRENT_DATE
inside the insert transaction, while supplied period values are preserved. `CpcUpdate` permits only settlement fields, preserving
parent IDs because the legacy trigger recalculates only NEW references.
`CPC_TEXT_LENGTHS` and Decimal constraints mirror catalog widths/precision.
`CPC_INSERT_DEFAULTS` records shared zero/empty values from existing CPC rows.
`create_cpc()` merges defaults with `_insert_plan()`. `update_cpc()` validates
supplied fields/catalog nullability without applying defaults. `delete_cpc()`
uses `build_delete()`. All writes use existing SQL builders and `_write_row()`
inside `write_session()` and require the write gate; missing records roll back.

The native SUM_UMOWA_CPC and DEL_CPC_RECORD triggers recalculate machine and
agreement aggregates. No settlement pricing or meter-to-charge formula is
invented by the API; supplied amounts are stored as such. Live tests create
isolated parents and verify totals across insertion, update and deletion.

### 1.4 Errors and shutdown

| Raised in | Type | HTTP |
| --- | --- | --- |
| `sql.py`, `service.py` | `InvalidRequest`, `QueryNotAllowed`, `ColumnNotFound` | `400` |
| `api.py` | `AuthenticationError` | `401` |
| `service.py` (writes) | `WritesDisabled` | `403` |
| `schema.py` | `TableNotFound` | `404` |
| `service.py` | `RecordNotFound` | `404` |
| `service.py` | `RecordConflict` | `409` |
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
registers the router, enables GET/POST/PATCH/DELETE CORS for configured origins, and serves the
unauthenticated `GET /` liveness route.

**`api.py`** — the whole HTTP surface, built as a factory. `create_router(settings)`,
`get_service()`, `require_api_key(settings)` (returns the `check_api_key` dependency,
`hmac.compare_digest`, disabled when `api.api_key` is `None`), `FILTERS_DESCRIPTION`.
Routes: `GET /`, `GET /health` (public), `GET /tables`, `GET /tables/{table}`,
`POST /schema/refresh`, `GET /tables/{table}/rows`, `GET /clients`, `POST /clients`,
`PATCH /clients/{id_klient}`, `DELETE /clients/{id_klient}`,
`GET /agreements`, `POST /agreements/{id_klient}`,
`PATCH /agreements/{id_umowacpc}`, `GET /machines`, `POST /machines`, `PATCH /machines/{id_maszyna}`, `GET /orders`,
`GET /invoices`, `POST /query` (relative to `api.prefix`); everything except the
first two is protected by the shared `protected` dependency list. Parameter bounds
are generated from the settings; handlers return plain dicts and the declared
`response_model` does validation + OpenAPI.

**`config.py`** — the only module that reads files or the environment. `load_config()`
runs a fixed pipeline: explicit path → `$KS_CONFIG` → `<project>/config/config.yaml` →
`yaml.safe_load` → `_expand_env` → `_apply_env_overrides` → `_build_settings` (per-section
dataclass-derived whitelist → frozen dataclasses → `__post_init__` validation) → `resolve_database_path()`.
Public objects: `ConfigError`, `AppSettings`, `DatabaseSettings` (with the `dsn`
property), `ServerSettings`, `ApiSettings`, `PROJECT_ROOT`, `DEFAULT_CONFIG_PATH`.
A relative `database.path` is resolved against `PROJECT_ROOT`, so the adapter works from
any working directory; unknown YAML keys raise instead of being silently ignored.

**`errors.py`** — the error hierarchy that couples failures to HTTP semantics:
`AdapterError` (500, base) → `InvalidRequest`, `QueryNotAllowed`, `ColumnNotFound`
(400), `AuthenticationError` (401), `WritesDisabled` (403), `TableNotFound` (404),
`DatabaseUnavailable` (503).

**`pool.py`** — the only module that calls `fdb.connect()`. `connect(settings)` (dsn,
credentials, charset, `sql_dialect=3`, optional `fb_library_name`) and `ConnectionPool`:
a lock-guarded LIFO queue of at most `pool_size` connections with `session()` (borrow →
yield → rollback → return), `write_session()` (borrow → yield → **commit**, or rollback
when the block raises; the only committing code path), `ping()` (a trivial query plus
`server_version`), `stats` (`created`/`idle`/`capacity` for `/health`) and `close()`.
Saturation waits up to `acquire_timeout` and then raises `DatabaseUnavailable` (503,
never a hang); broken connections are discarded, so the pool survives a restart.

**`schema.py`** — catalog introspection + TTL cache. Reads `RDB$RELATIONS` and
`RDB$RELATION_FIELDS`/`RDB$FIELDS`/`RDB$CHARACTER_SETS`, maps `RDB$FIELD_TYPE` ids to SQL
types (`describe_type()` → `VARCHAR(50)`, `NUMERIC(15,2)`, `BLOB SUB_TYPE TEXT`) and
produces frozen `ColumnInfo` / `TableInfo`. `SchemaCache` offers `tables()`,
`get(name)` (case-insensitive, else `TableNotFound`), `invalidate()` and the
`api.schema_cache_ttl` expiry. `TableInfo.column_map` is the whitelist that every filter,
search and sort column must pass.

**`sql.py`** — all SQL text assembly. `quote_identifier()` (``"NAME"``, embedded quotes
doubled), `ensure_read_only()`, `strip_sql_literals()` (drops comments and `'...'`/`"..."`
literals before the keyword scan), `build_insert()` (quoted column list, `?` placeholders,
optional `RETURNING`), `build_update()` (bound assignments and unique key),
`build_delete()` (bound unique key and `RETURNING`),
`build_next_available_id()` (first unused positive INTEGER), `Filter`, `parse_filters()`, `build_where()`, `build_search()`.
Operators: `eq, ne, gt, ge, lt, le, like, contains, startswith,
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
`fetch_cpc()`, `get_cpc()`, `create_cpc()`, `update_cpc()`, `delete_cpc()`,
`fetch_agreements()`, `fetch_machines()`, `fetch_orders()`, `fetch_invoices()`,
`create_client()`, `create_machine()`, `create_agreement()`, `update_client()`,
`delete_client()`, `update_machine()`, `update_agreement()`,
`run_query()`, plus the helpers `check_limit()`,
`_order_clause()`, `_projection_page()`, `_default_order_clause()`,
`_check_parameters()`, `_write_row()`, `_serialize_row()`, `_require_writes()`
and `_prepared_write_values()`, plus the
module-level `_insert_plan()` that merges a payload with the legacy default profile.
constants define the curated read models:
`CLIENTS_TABLE`/`CLIENT_COLUMNS` + `CLIENT_SEARCH_COLUMNS`,
`AGREEMENTS_TABLE`/`AGREEMENT_COLUMNS` + `AGREEMENT_SEARCH_COLUMNS`,
`MACHINES_TABLE`/`MACHINE_COLUMNS` + `MACHINE_SEARCH_COLUMNS`,
`ORDERS_TABLE`/`ORDER_COLUMNS` + `ORDER_SEARCH_COLUMNS`,
`INVOICES_TABLE`/`INVOICE_COLUMNS` + `INVOICE_SEARCH_COLUMNS`. Each is a small hand-picked
subset of the table's columns, which keeps the endpoint stable even though the underlying
tables are very wide, and each row is keyed by the lower-cased column name, so there is no
alias table to keep in sync. `_projection_page()` is the shared implementation of
`/clients`, `/agreements`, `/machines`, `/orders` and `/invoices`: `COUNT(*)` plus the page
query on one connection, columns missing from the connected database silently skipped.

The insert methods `create_client()` and `create_machine()` both refuse with
`WritesDisabled` unless `api.allow_writes` is set, build their statement with
`sql.build_insert()` and execute it inside `pool.write_session()`, so the row is
committed or the transaction rolled back. Both take a mapping keyed by the lower-cased
column names and normalise it with `_prepared_write_values()`: only the constants'
columns are accepted (`CLIENT_WRITE_COLUMNS` / `MACHINE_WRITE_COLUMNS`, both subsets of
the matching `*_COLUMNS` projection), strings are trimmed, blanks are dropped and each
text value is limited with `CLIENT_TEXT_LENGTHS` / `MACHINE_TEXT_LENGTHS` (mirroring the
column widths). `create_client()` then requires a non-blank `NAZWA`, merges the payload
with `CLIENT_INSERT_DEFAULTS` through `_insert_plan()` and inserts the result with
`RETURNING` built from `CLIENT_COLUMNS`; `create_machine()` accepts an optional non-negative
`ID_KLIENT`, defaults it to `0` (unassigned) through `MACHINE_INSERT_DEFAULTS`,
and returns `RETURNING` built from `MACHINE_COLUMNS`.
`_write_row()` executes each curated write and converts its returned row with
`_serialize_row()` before committing. Missing update targets and conversion
failures therefore roll back the transaction. `_serialize_row()` also handles
curated reads through the shared `serialization.row_to_dict()` helper.

`CLIENT_INSERT_DEFAULTS` deserves its own paragraph: it holds the column values the
legacy application itself writes into a new `KLIENT` row (`ID_FIRMA` `0`, `TYP`
`Odbiorca`, `PLATNOSC` `Gotówka`, `KOD_KRAJU` `PL`, `IDW` `-1`, `''` instead of `NULL`
for text, zeroed flags). A row that keeps the Firebird `NULL`s — and the
`INS_KLIENT_RECORD` fallback `ID_FIRMA = 1` — is a valid contractor for SQL but does
not appear in the program's client list, which is why the adapter reproduces that
profile instead of relying on the column defaults. `OSTATNIO` and `GUSDATA` stay out:
they belong to the program's clock and data version.

**`schemas.py`** — the wire format, and therefore the OpenAPI contract. `ServiceInfo`,
`HealthResponse`/`DatabaseInfo`/`PoolInfo`, `TableSummary`, `TableListResponse`,
`TableDetail`/`ColumnModel`, `SchemaRefreshResponse`, `RowPage`, `Client`/`ClientPage`,
`ClientUpdate` (partial update body), `ClientCreate` (the `POST /clients` body: required `nazwa` plus the optional client
columns, unknown fields rejected),
`Agreement`/`AgreementPage`, `AgreementCreate` (optional details/machines; client ID in the URL),
`AgreementUpdate` (partial agreement update),
`Machine`/`MachinePage`, `MachineUpdate` (partial machine update), `MachineCreate` (the
`POST /machines` body: all machine columns optional; `id_klient` defaults to `0`, unknown fields
rejected), `Order`/`OrderPage`,
`Invoice`/`InvoicePage`, `QueryRequest`/`QueryResponse`. Projection
fields are all optional, so a missing column never breaks validation, and money columns
use `DecimalValue = float | str`. Every projection field is named after its column,
lower-cased (`nazwa`, `id_klient`, `suma_brutto`, ...), which is also the JSON key the
client sees.

### Repository files

**`config/config.yaml`** — the single settings file. `server` (host, port, log_level,
reload), `database` (path, host, port, user, password, charset, client_library,
pool_size, acquire_timeout, health_check, check_path) and `api` (prefix, default_limit,
max_limit, max_query_rows, schema_cache_ttl, blob_encoding, decimal_as_string, api_key,
allow_writes, cors_origins). Values are `${VAR:-default}` placeholders, so the file
documents the defaults while the environment stays authoritative (this is how the
password is supplied without committing it). `database.path` is deliberately relative and
is resolved against the project root, `database.charset` and `api.blob_encoding` must
describe the same encoding, an empty `api_key` disables authentication, empty
`cors_origins` skips the middleware and `allow_writes` is the switch that turns the
`POST /clients` and `POST /machines` write paths on.

**`tests/`** — the pytest suite: `conftest.py` (settings fixture, `FakeService`, app and
client fixtures), `test_api.py` (routes through `TestClient`), `test_service.py`
(scripted fake cursors: generated SQL, bound parameters, field mapping, limits),
`test_config.py`, `test_sql.py`, `test_serialization.py`, `test_schema.py` (pure unit
tests of one module each), and `test_integration.py` (marked `integration`, runs only
when `KS_TEST_DB_PATH` points at a real database; the write tests additionally need
`KS_TEST_DB_WRITABLE=1` because they insert and delete a disposable contractor).

**`pytest.ini`** — limits collection to `tests/` and registers the `integration` marker.

**`requirements.txt`** — runtime only: `fastapi`, `uvicorn`, `fdb`, `PyYAML`.
**`requirements-dev.txt`** — the above plus `pytest` and `httpx` (required by
`TestClient`).

**`.gitignore`** — bytecode, virtualenvs, `.pytest_cache/`, coverage, logs, `.tmp_*` and
`*.fdb`/`*.FDB`, so the database (and its customer data) is never committed.

**`README.md`** — the short user manual: what the project is, install, configuration
(environment variables), the endpoint table with a few `curl` examples, error codes and
tests. Read it first; this file is the companion for implementers.

**`AGENTS.md`** — the working agreement for AI agents and new contributors: the write
switch/parameter/64 KB invariants, environment commands, layout, recipes for adding a
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
   A **writing** endpoint is the exception: it must be gated by `api.allow_writes`
   (raise `errors.WritesDisabled` → `403`), build its statement with
   `sql.build_insert()` / `sql.build_update()`, execute via `_write_row()`, and have a
   `KS_TEST_DB_WRITABLE=1` integration test that cleans up after itself.
2. **New field on a projection** — add the column name to the matching `*_COLUMNS`
   constant (plus `*_SEARCH_COLUMNS` if it must be searchable) and the optional field to
   the Pydantic model, named after the column in lower case; response details live in the
   OpenAPI schema, so `README.md` only changes when the endpoint description does.
3. **New setting** — `config.py` (`_ENV_OVERRIDES`, dataclass field,
   `_build_settings`), `config/config.yaml`, plus the `README.md` environment table when the
   variable should be public.
4. Verify with `python -m ks_adapter --check` and `python -m pytest`.

