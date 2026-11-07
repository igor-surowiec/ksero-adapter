# ks-adapter

Read-only HTTP API (FastAPI) in front of a Firebird database (verified against
Firebird 2.5, `WIN1250` data).

The adapter never modifies data: each request runs a single `SELECT`/`WITH`
statement with quoted identifiers, bound parameters and a capped row count.
Interactive docs are served at `/docs`, the developer reference lives in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

Python 3.10+ and the native Firebird client (`fbclient.dll` on Windows,
`libfbclient.so` on Linux) are required.

```bash
python -m venv .venv
source .venv/Scripts/activate     # Git Bash; .venv/Scripts/activate.bat on cmd
pip install -r requirements.txt
python -m ks_adapter --check      # config + Firebird smoke test, then exit
python -m ks_adapter              # serve on http://127.0.0.1:8000
```

## Configuration

Everything lives in `config/config.yaml`; values may use `${VAR}` (required) or
`${VAR:-default}` (fallback) placeholders, so most settings can be overridden
without touching the file:

| Variable | Setting |
| --- | --- |
| `KS_CONFIG` | path to the YAML file (default `config/config.yaml`) |
| `KS_DB_PATH`, `KS_DB_USER`, `KS_DB_PASSWORD`, `KS_DB_CHARSET` | database and credentials |
| `KS_DB_HOST`, `KS_DB_PORT`, `KS_FB_CLIENT` | remote server, native library |
| `KS_SERVER_HOST`, `KS_SERVER_PORT`, `KS_LOG_LEVEL` | server |
| `KS_API_KEY` | require `X-API-Key` on data/schema requests |
| `KS_DEFAULT_LIMIT`, `KS_MAX_LIMIT`, `KS_MAX_QUERY_ROWS` | row caps |

Unknown keys are rejected, the password is meant to come from the environment,
and a relative `database.path` is resolved against the project root (so
`BAZAMS.FDB` works from any working directory). The remaining settings
(`pool_size`, `check_path`, `schema_cache_ttl`, `decimal_as_string`,
`cors_origins`, ...) are documented inline in the YAML file.

## Endpoints

Routes live under `api.prefix` (`/api/v1`).

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/health` | database ping and pool statistics (no API key) |
| `GET` | `/tables` | user tables and views |
| `GET` | `/tables/{table}` | columns with readable SQL types |
| `GET` | `/tables/{table}/rows` | page of rows, sorting, JSON filters |
| `GET` | `/clients` | contractors (`KLIENT`) |
| `GET` | `/agreements` | service agreements (`UMOWACPC`) |
| `GET` | `/machines` | machines and devices (`MASZYNA`) |
| `GET` | `/orders` | service orders (`ZLECENIE`) |
| `POST` | `/schema/refresh` | drop and reload the schema cache |
| `POST` | `/query` | one read-only `SELECT`/`WITH` with parameters |

List endpoints take `limit` (default `api.default_limit`, max `api.max_limit`)
and `offset`. The curated ones (`/clients`, `/agreements`, `/machines`,
`/orders`) also take `search`, a case-sensitive substring with escaped
wildcards, and return a hand-picked column subset that stays inside Firebird's
64 KB statement-message limit - the reason `ZLECENIE` is never `SELECT *`ed.
Every response field is documented in the OpenAPI schema (`/docs` or
`/openapi.json`).

```bash
curl 'http://127.0.0.1:8000/api/v1/tables/KLIENCI/rows?limit=25&order_by=NAZWA%20ASC&filters={"TYP":1}'
curl 'http://127.0.0.1:8000/api/v1/orders?limit=50&search=przeglad'
curl -X POST http://127.0.0.1:8000/api/v1/query -H 'Content-Type: application/json' -d '{"sql": "SELECT ID, NAZWA FROM KLIENCI WHERE ID > ? ORDER BY ID", "limit": 10, "parameters": [100]}'
```

`filters` is a JSON object whose values are either a literal (means `eq`) or an
operator object:

```json
{"NAZWA": "Kowalski"}
{"ID": {"op": "gt", "value": 100}}
{"TYP": {"op": "in", "value": [1, 2, 3]}}
{"EMAIL": {"op": "isnull"}}
```

Supported operators: `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `like`, `contains`,
`startswith`, `endswith`, `in`, `isnull`, `notnull`; unknown columns or
operators give `400`. `POST /query` binds `parameters` to `?` placeholders,
caps rows at `api.max_query_rows` and reports `truncated`.

## Errors and auth

```json
{"detail": "Table or view 'NOPE' does not exist", "error": "TableNotFound"}
```

`400` invalid request or forbidden SQL, `401` missing/invalid `X-API-Key`,
`404` unknown table, `422` validation, `500`/`503` database failure. When
`api.api_key` is set, send it as `X-API-Key` on every route except `/health`.

## Tests

```bash
python -m pytest                              # unit + API, no database
KS_TEST_DB_PATH=BAZAMS.FDB python -m pytest   # adds the live Firebird tests
```

## Layout

```
config/config.yaml   # configuration (env placeholders + defaults)
ks_adapter/          # application package (routes, service, pool, SQL, models)
docs/ARCHITECTURE.md # program flow and file-by-file reference
tests/               # pytest suite (unit, API, opt-in integration)
```
