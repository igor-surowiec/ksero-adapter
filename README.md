# ks-adapter

HTTP API (FastAPI) in front of a Firebird database (verified against Firebird 2.5,
`WIN1250` data).

Every request runs a single SQL statement with quoted identifiers, bound
parameters and a capped row count. Reads never modify anything; the only writes
are curated client/machine inserts and client updates, and they stay off
unless `api.allow_writes` is enabled. Interactive docs are served at `/docs`,
the developer reference lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
| `KS_ALLOW_WRITES` | enable the write endpoints (`POST /clients`, `PATCH /clients/{id_klient}`, `POST /machines`) |
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
| `POST` | `/clients` | create a contractor (`KLIENT`), `nazwa` plus optional fields |
| `PATCH` | `/clients/{id_klient}` | update supplied contractor fields by client identifier |
| `GET` | `/agreements` | service agreements (`UMOWACPC`) |
| `GET` | `/machines` | machines and devices (`MASZYNA`) |
| `POST` | `/machines` | create a machine (`MASZYNA`), only `id_klient` required |
| `GET` | `/orders` | service orders (`ZLECENIE`) |
| `GET` | `/invoices` | invoices (`FAKTURA`, header only) |
| `POST` | `/schema/refresh` | drop and reload the schema cache |
| `POST` | `/query` | one read-only `SELECT`/`WITH` with parameters |

List endpoints take `limit` (default `api.default_limit`, max `api.max_limit`)
and `offset`. The curated ones (`/clients`, `/agreements`, `/machines`,
`/orders`, `/invoices`) also take `search`, a case-sensitive substring with
escaped wildcards, and return a hand-picked column subset that stays inside
Firebird's 64 KB statement-message limit - the reason `ZLECENIE` is never
`SELECT *`ed. `/invoices` returns invoice headers only; the positions live in
`FPOZYCJA` and are not exposed.
The curated endpoints keep the **original Polish column names**: every row is
keyed by the lower-cased database column (`nazwa`, `nazwa_s`, `id_klient`,
`kod`, `poczta`, `suma_brutto`, ...), so client code needs no name translation.
Only the envelope keys (`total`, `count`, `limit`, `offset`, `clients`,
`agreements`, ...) stay English.
Every response field is documented in the OpenAPI schema (`/docs` or
`/openapi.json`).

The writing routes return the stored row (`201` for inserts, `200` for
updates), use the same `X-API-Key` as the read routes and
answer `403` unless `api.allow_writes` / `KS_ALLOW_WRITES=true` is set.

`POST /clients` takes the lower-cased column names of the `GET /clients`
projection (`nazwa`, `nip`, `regon`, `adres`, `kod`, `poczta`, `telefon`,
`e_mail`, `www`, `typ`, `platnosc`, `termin`, `rabat`, ...) and inserts one
`KLIENT` row; `nazwa` (`NAZWA`, trimmed, at most 500 characters) is the only
value you have to send. Strings are trimmed, every text value is checked against
its column width, and an unknown field name answers `422` instead of being
dropped silently.

Every column you leave out is filled with the values the legacy application
writes into a new contractor (`CLIENT_INSERT_DEFAULTS`: `ID_FIRMA` `0`, `TYP`
`Odbiorca`, `PLATNOSC` `Gotówka`, `KOD_KRAJU` `PL`, `IDW` `-1`, empty strings
instead of `NULL`, zeroed flags). That profile is what makes the row show up in
that program: its contractor list is filtered by `ID_FIRMA`, and a row that
keeps the trigger fallback of `1` (or plain `NULL`s) never appears there. The
generated keys still come from `INS_KLIENT_RECORD`, and `ID_ODDZIAL` keeps its
column default of `1`.

`PATCH /clients/{id_klient}` updates an existing contractor using the
unique `id_klient` returned by `GET /clients`, also used by machines and
related records. It accepts the same writable fields as `POST /clients`, all
optional. Only supplied fields change: omitted fields and the stored legacy
profile stay untouched. Strings are trimmed; `""` clears a text field and
`null` clears an optional field. A supplied `nazwa` cannot be null or blank.
An empty update returns `400`; unknown or overlong fields return `422`;
an unknown record returns `404`. Generated keys and `ostatnio` cannot be
changed. The response is the updated `Client` projection with `200`.

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/clients/1001 -H 'Content-Type: application/json' -d '{"telefon": "123456789", "e_mail": "office@example.com"}'
```

`POST /machines` takes the lower-cased column names of the `GET /machines`
projection (`marka`, `model`, `serial`, `instalacja`, `oplata`, ...) and inserts
one `MASZYNA` row; `id_klient` is the only required value, because
`INS_MASZYNA_RECORD` assigns `ID_MASZYNA_TABLE` and `ID_MASZYNA` while
`ID_ODDZIAL` and `ID_FIRMA` fall back to their column defaults. Omitted, `null`
and blank fields are not inserted at all, strings are trimmed, and an unknown
field name answers `422` instead of being dropped silently. Columns the
application derives from other data (`licznik_total`, `last_m`, `last_w`,
`next_w`, `koszty`, `przychody`, `wynik`, `synwp`) cannot be written.

```bash
curl 'http://127.0.0.1:8000/api/v1/tables/KLIENCI/rows?limit=25&order_by=NAZWA%20ASC&filters={"TYP":1}'
curl 'http://127.0.0.1:8000/api/v1/orders?limit=50&search=przeglad'
curl 'http://127.0.0.1:8000/api/v1/invoices?limit=20&search=2026'
curl -X POST http://127.0.0.1:8000/api/v1/query -H 'Content-Type: application/json' -d '{"sql": "SELECT ID, NAZWA FROM KLIENCI WHERE ID > ? ORDER BY ID", "limit": 10, "parameters": [100]}'
curl -X POST http://127.0.0.1:8000/api/v1/clients -H 'Content-Type: application/json' -d '{"nazwa": "ACME Sp. z o.o.", "nip": "1234567890", "poczta": "Warszawa"}'
curl -X POST http://127.0.0.1:8000/api/v1/machines -H 'Content-Type: application/json' -d '{"id_klient": 42, "marka": "KONICA", "model": "C224", "serial": "SN-0001", "instalacja": "2026-01-02"}'
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
`403` writes disabled (`api.allow_writes` off), `404` unknown table or client record, `422`
validation, `500`/`503` database failure. When `api.api_key` is set, send it as
`X-API-Key` on every route except `/health`.

## Tests

```bash
python -m pytest                              # unit + API, no database
KS_TEST_DB_PATH=BAZAMS.FDB python -m pytest   # adds the live Firebird tests
KS_TEST_DB_PATH=BAZAMS.FDB KS_TEST_DB_WRITABLE=1 python -m pytest
                                              # + the create-client tests
```

The write tests insert a disposable contractor and delete it again, which is why
they need the extra opt-in variable.

## Layout

```
config/config.yaml   # configuration (env placeholders + defaults)
ks_adapter/          # application package (routes, service, pool, SQL, models)
docs/ARCHITECTURE.md # program flow and file-by-file reference
tests/               # pytest suite (unit, API, opt-in integration)
```
