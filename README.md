# ks-adapter

Read-only HTTP API (FastAPI) in front of a Firebird database (verified against
Firebird 2.5.9 / `BAZAMS.FDB`, charset `WIN1250`).

The adapter never modifies data: every statement is validated, table and column
names are quoted identifiers, values are always bound as parameters and the
number of returned rows is capped.

## Features

- Schema browsing: list tables/views, inspect columns with readable SQL types.
- Paginated row access with sorting and JSON based filters.
- Curated, stable views of `KLIENT` (`/clients`) and `UMOWACPC` (`/agreements`).
- Free-form `SELECT`/`WITH` queries with bound parameters and row limits.
- Connection pool with health checks, TTL based schema cache, API key auth.
- Automatic serialisation of `NUMERIC`/`DECIMAL`, date/time and `BLOB` values.

## Requirements

- Python 3.10+
- Firebird client library (`fbclient.dll` on Windows, `libfbclient.so` on Linux)
- Network/local access to the `.fdb` file and valid credentials

## Installation

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash); use .venv\Scripts\activate on cmd
pip install -r requirements.txt
pip install -r requirements-dev.txt  # pytest + httpx, only for development
```

## Configuration

Settings live in `config/config.yaml`. Any value may reference environment
variables using `${NAME}` (required) or `${NAME:-default}` (with fallback):

```yaml
server:
  host: 127.0.0.1
  port: ${KS_SERVER_PORT:-8000}
  log_level: ${KS_LOG_LEVEL:-info}

database:
  path: ${KS_DB_PATH:-BAZAMS.FDB}
  user: ${KS_DB_USER:-SYSDBA}
  password: ${KS_DB_PASSWORD:-masterkey}
  charset: ${KS_DB_CHARSET:-WIN1250}
  client_library: ${KS_FB_CLIENT:-}
  pool_size: 5
  check_path: true

api:
  prefix: /api/v1
  default_limit: 50
  max_limit: 1000
  max_query_rows: 5000
  blob_encoding: cp1250
  api_key: ${KS_API_KEY:-}
```

A relative `database.path` is resolved against the project root (the directory
containing `config/` and `ks_adapter/`), so `BAZAMS.FDB` points at a database
file kept next to this README regardless of the working directory the server is
started from. Absolute paths are used as-is, and when `database.host` is set the
path is passed to the Firebird server untouched.

`database.client_library` is optional: leave it empty to let the driver locate
the native Firebird client on the system library path, or set `KS_FB_CLIENT` (or
the YAML key) to pin a specific build.

Unknown keys are rejected, so typos fail fast instead of being silently ignored.
Passwords may be supplied only through the environment by referencing
`${KS_DB_PASSWORD}` in the YAML file.

### Environment overrides

The most important settings can be overridden without touching the file:

| Variable | Setting |
| --- | --- |
| `KS_CONFIG` | Path to the YAML file (default `config/config.yaml`) |
| `KS_DB_PATH` | `database.path` |
| `KS_DB_USER` / `KS_DB_PASSWORD` | `database.user` / `database.password` |
| `KS_DB_CHARSET` | `database.charset` |
| `KS_DB_HOST` / `KS_DB_PORT` | Remote Firebird host and port |
| `KS_FB_CLIENT` | `database.client_library` |
| `KS_DB_POOL_SIZE` | Number of pooled connections |
| `KS_DB_HEALTH_CHECK` | Ping connections before reuse |
| `KS_DB_CHECK_PATH` | Verify the local database file exists at startup |
| `KS_SERVER_HOST` / `KS_SERVER_PORT` | `server.host` / `server.port` |
| `KS_LOG_LEVEL` / `KS_RELOAD` | `server.log_level` / `server.reload` |
| `KS_API_KEY` | Require `X-API-Key` on every data/schema request |
| `KS_DEFAULT_LIMIT` / `KS_MAX_LIMIT` | Default and maximum page size |
| `KS_MAX_QUERY_ROWS` | Hard cap for `POST /query` results |
| `KS_DECIMAL_AS_STRING` | Serialise `NUMERIC`/`DECIMAL` as strings |

## Running

```bash
python -m ks_adapter --check        # validate config + connect to Firebird, then exit
python -m ks_adapter                # start the HTTP server
python -m ks_adapter --port 9000 --log-level debug
python -m ks_adapter --reload       # auto-reload during development
```

`--check` prints the resolved DSN, the server version and the number of
tables/views, which makes it a good first smoke test in CI or on a new machine.

Interactive documentation is served at <http://127.0.0.1:8000/docs> and the raw
OpenAPI schema at `/openapi.json`.

## Endpoints

All routes live under the configured prefix (`/api/v1` by default).

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Ping the database and report pool statistics (never requires an API key) |
| `GET` | `/api/v1/tables` | List user tables and views |
| `GET` | `/api/v1/tables/{table}` | Describe a table or view with its columns |
| `GET` | `/api/v1/tables/{table}/rows` | Read a page of rows |
| `GET` | `/api/v1/clients` | List contractors (`KLIENT`) with id, name, address and contacts |
| `GET` | `/api/v1/agreements` | List service agreements (`UMOWACPC`) with number, parties, dates and finances |
| `POST` | `/api/v1/schema/refresh` | Drop and reload the cached schema |
| `POST` | `/api/v1/query` | Run a single read-only `SELECT`/`WITH` statement |

### Browsing rows

`GET /api/v1/tables/KLIENCI/rows?limit=25&offset=50&order_by=NAZWA%20ASC&filters={"TYP":1}`

Query parameters:

- `limit` – page size, defaults to `api.default_limit`, capped at `api.max_limit`.
- `offset` – rows to skip (default `0`).
- `order_by` – comma separated `COLUMN [ASC|DESC]` list, e.g. `NAZWA ASC, ID DESC`.
- `filters` – JSON object describing equality/range predicates (see below).

Response:

```json
{
  "table": "KLIENCI",
  "columns": ["ID", "NAZWA"],
  "rows": [{"ID": 1, "NAZWA": "Kowalski"}],
  "row_count": 1,
  "total": 128,
  "limit": 25,
  "offset": 50
}
```

`total` is the number of rows matching the filters (not the page size).

### Filters

```json
{"NAZWA": "Kowalski"}
{"ID": {"op": "gt", "value": 100}}
{"TYP": {"op": "in", "value": [1, 2, 3]}}
{"NAZWA": {"op": "contains", "value": "owal"}}
{"EMAIL": {"op": "isnull"}}
```

Supported operators: `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `like`, `contains`,
`startswith`, `endswith`, `in`, `isnull`, `notnull`. A bare value means `eq`.
Unknown columns or operators return `400`, `LIKE` wildcards in the value are
escaped automatically.

### Clients (contractors)

`GET /api/v1/clients?limit=50&offset=0&search=kowal`

A dedicated, stable view of the contractor table `KLIENT` instead of all 61 raw
columns. Query parameters:

- `limit` – clients per page, defaults to `api.default_limit`, capped at
  `api.max_limit`.
- `offset` – clients to skip (default `0`), use it to page through everything.
- `search` – optional substring matched against `NAZWA`, `NAZWA_S`, `NIP`,
  `REGON`, `E_MAIL`, `TELEFON`, `KOD` and `POCZTA`. It is case sensitive (as
  Firebird `LIKE` is) and wildcards are escaped, so `%` is matched literally.

Results are ordered by `NAZWA`, then `ID_KLIENT_TABLE`, so pages are stable.

```json
{
  "total": 128,
  "count": 1,
  "limit": 50,
  "offset": 0,
  "clients": [
    {
      "id": 12,
      "client_id": 12,
      "name": "Kowalski Jan",
      "short_name": "Kowalski",
      "nip": "1234567890",
      "regon": "123456789",
      "address": "ul. Polna 1",
      "postcode": "00-001",
      "city": "Warszawa",
      "province": 14,
      "phone": "600100200",
      "email": "jan@example.com",
      "website": "https://example.com",
      "type": "Odbiorca",
      "active": "T",
      "payment_method": "Przelew",
      "payment_days": 14,
      "discount": 0,
      "last_contact": "2024-05-01"
    }
  ]
}
```

`id` is the surrogate key `ID_KLIENT_TABLE`, `client_id` the business key
`ID_KLIENT`; every other field comes from the column of the same meaning
(`name` → `NAZWA`, `postcode` → `KOD`, `city` → `POCZTA`, ...). Columns that are
missing in a given database are omitted instead of failing the request, and
`total` is the number of clients matching `search` (not the page size).

### Agreements (contracts)

`GET /api/v1/agreements?limit=50&offset=0&search=cpc`

A dedicated, stable view of the service agreement table `UMOWACPC` (83 columns in
the BAZAMS schema) exposing only the useful fields: identifiers, agreement number
and type, the client/recipient/company/branch keys, the responsible people,
dates, terms, the financial summary (`costs`, `revenue`, `profit`, `discount`),
payment terms and the printing volumes. The per-printer parameters
(`FRAPAR1..12`, `FRANAZ1..10` / `IDMAG1..10`) and the unit prices (`UOPLATA*`,
`OPLATA_*`) are deliberately left out.

Query parameters behave exactly like in `/clients`:

- `limit` – agreements per page, defaults to `api.default_limit`, capped at
  `api.max_limit`.
- `offset` – agreements to skip (default `0`), use it to page through everything.
- `search` – optional substring matched against `UMOWA`, `TYP`, `HANDLOWIEC`,
  `OPIEKUN`, `OPIEKUNMAIL`, `FRAEMAIL` and `PLIK`. It is case sensitive (as
  Firebird `LIKE` is) and wildcards are escaped, so `%` is matched literally.

Results are ordered by `UMOWA`, then `ID_UMOWACPC_TABLE`, so pages are stable.

```json
{
  "total": 4,
  "count": 1,
  "limit": 50,
  "offset": 0,
  "agreements": [
    {
      "id": 5,
      "agreement_id": 5,
      "branch_id": 1,
      "client_id": 12,
      "recipient_id": null,
      "company_id": 1,
      "number": "CPC/2024/001",
      "type": "CPC",
      "salesperson": "Nowak Anna",
      "supervisor": "Kowalski Jan",
      "supervisor_email": "jan@example.com",
      "supervisor_phone": "600100200",
      "start_date": "2024-01-01",
      "end_date": "2024-12-31",
      "terms": "2 poprawki miesięcznie",
      "notes": "umowa przedłużona",
      "costs": 1200.0,
      "revenue": 5400.0,
      "profit": 4200.0,
      "discount": 5.0,
      "payment_method": "Przelew",
      "payment_days": 14,
      "active": "T",
      "pages_mono": 5000,
      "pages_color": 1200,
      "scans": 300,
      "invoice_email": "faktury@example.com",
      "file": "CPC_2024_001.pdf"
    }
  ]
}
```

`id` is the surrogate key `ID_UMOWACPC_TABLE`, `agreement_id` the business key
`ID_UMOWACPC`; every other field comes from the column of the same meaning
(`number` → `UMOWA`, `supervisor` → `OPIEKUN`, `costs` → `KOSZTY`, ...).
`client_id`, `recipient_id`, `company_id` and `branch_id` are the raw foreign keys
stored in `UMOWACPC` (they are not resolved to names). Columns that are missing in
a given database are omitted instead of failing the request, and `total` is the
number of agreements matching `search` (not the page size).

### Custom queries

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT ID, NAZWA FROM KLIENCI WHERE ID > ? ORDER BY ID", "limit": 10, "parameters": [100]}'
```

`sql` must be a single `SELECT`/`WITH` statement, `parameters` is an optional
array of scalars bound to `?` placeholders. Results are capped by `limit`
(defaults to and never exceeds `api.max_query_rows`); `truncated` reports
whether more rows were available.

### Errors

Errors are returned as JSON with a stable HTTP status:

```json
{"detail": "Table or view 'NOPE' does not exist", "error": "TableNotFound"}
```

| Status | Meaning |
| --- | --- |
| `400` | Invalid request: bad filters, unknown column, forbidden SQL |
| `401` | Missing or invalid `X-API-Key` |
| `404` | Unknown table/view |
| `422` | Request schema validation failure (FastAPI) |
| `500` | Firebird or connection failure |
| `503` | Database unavailable |

## Read-only guarantees

- Only a single statement is accepted; trailing semicolons are stripped and any
  second statement is rejected.
- The statement must start with `SELECT` or `WITH`; write/DDL keywords
  (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `EXECUTE`,
  `COMMIT`, ...) are rejected after comments and literals are stripped.
- Table and column names are taken from the schema cache and emitted as quoted
  identifiers, so values can never be injected as SQL.
- All filter values and query parameters are bound as `?` placeholders.
- Row counts are always bounded by `api.max_limit` / `api.max_query_rows`.

## Tests

```bash
python -m pytest              # unit + API tests, no database required
python -m pytest -m integration   # only the live database tests
```

The integration tests are skipped unless `KS_TEST_DB_PATH` is set:

```bash
export KS_TEST_DB_PATH="BAZAMS.FDB"          # relative to the project root
export KS_TEST_DB_PASSWORD="masterkey"        # optional, defaults to masterkey
python -m pytest tests/test_integration.py
```

Unit tests cover configuration parsing, the SQL guard and filter builder,
value serialisation, schema introspection/type mapping, the service query
builder and every HTTP endpoint (using an injected fake service).

## Project layout

```
config/config.yaml      # configuration (env placeholders + defaults)
ks_adapter/
    __main__.py         # CLI: run server, --check, overrides
    app.py              # FastAPI factory, error handlers, CORS
    api.py              # routes and API key dependency
    config.py           # YAML loader, validation, env overrides
    errors.py           # AdapterError hierarchy with HTTP statuses
    pool.py             # thread-safe Firebird connection pool
    schema.py           # catalog introspection + TTL cache
    serialization.py    # JSON-safe conversion of Firebird values
    service.py          # query building and database access
    schemas.py          # Pydantic response models
docs/ARCHITECTURE.md    # program flow + file-by-file reference for developers
tests/                  # pytest suite (unit, API, opt-in integration)
```
