# ks-adapter

HTTP API (FastAPI) in front of a Firebird database (verified against Firebird 2.5,
`WIN1250` data).

Requests use quoted identifiers, bound parameters and capped read results.
Reads never modify anything. Writes are limited to curated client, machine,
agreement and CPC routes, disabled unless `api.allow_writes` is enabled.
Interactive docs are served at `/docs`; the developer reference lives in
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
| `KS_ALLOW_WRITES` | enable the write endpoints (`POST /clients`, `POST /agreements/{id_klient}`, `PATCH /clients/{id_klient}`, `DELETE /clients/{id_klient}`, `POST /machines`, `PATCH /machines/{id_maszyna}`, `PATCH /agreements/{id_umowacpc}`, `POST/PATCH/DELETE /cpc-settlement`) |
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
| `DELETE` | `/clients/{id_klient}` | delete a contractor and trigger-managed machines/contacts (`204`) |
| `GET` | `/agreements` | service agreements (`UMOWACPC`) |
| `POST` | `/agreements/{id_klient}` | create an agreement (`UMOWACPC`); only `id_klient` required |
| `PATCH` | `/agreements/{id_umowacpc}` | update agreement details and optionally link machines |
| `GET` | `/machines` | machines and devices (`MASZYNA`) |
| `POST` | `/machines` | create a machine (`MASZYNA`), all fields optional; unassigned owner is `0` |
| `POST` | `/machines/{id_klient}` | create a machine with the client ID from the URL |
| `PATCH` | `/machines/{id_maszyna}` | update supplied machine fields by business identifier |
| `GET` | `/cpc-settlement` | paginated CPC settlement records, search and JSON filters |
| `GET` | `/cpc-settlement/{id_cpc_table}` | one CPC settlement |
| `POST` | `/cpc-settlement` | create a CPC settlement |
| `PATCH` | `/cpc-settlement/{id_cpc_table}` | update settlement readings, counts, charges and notes |
| `DELETE` | `/cpc-settlement/{id_cpc_table}` | delete a settlement (`204`) |
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

Insert and update routes return the stored row (`201` and `200` respectively);
deletion returns `204` with no body. All write routes use the same `X-API-Key`
as the read routes and answer `403` unless `api.allow_writes` / `KS_ALLOW_WRITES=true` is set.

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

`DELETE /clients/{id_klient}` permanently removes the contractor identified by
`ID_KLIENT` and returns `204` with no response body. An unknown client returns
`404`. The existing `DEL_KLIENT_RECORD` database trigger also deletes that
client's machines (`MASZYNA`) and contacts (`KONTAKT`) in the same transaction.
Other references are handled by the connected database's constraints and
triggers. Requires `KS_ALLOW_WRITES=true` and the configured API key.

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/clients/42
```

`POST /agreements/{id_klient}` inserts a service agreement into `UMOWACPC`. The positive
`id_klient` (contractor) comes from the URL path. The request body is optional;
omit it or send `{}` to use defaults. Do not include `id_klient` in the body. The adapter assigns `id_umowacpc` as the
lowest unused positive integer, starting at `1` and reusing gaps (existing IDs
`1, 2, 4` produce `3`). The trigger generates `id_umowacpc_table`. Both IDs are
read-only and rejected if included in the request.

Allocation and insertion run in one transaction with a protected write
reservation on `UMOWACPC`, so concurrent requests cannot select the same free
ID. The reservation is released on commit or rollback; lock waits are bounded
using `database.acquire_timeout` (whole seconds, minimum one). No database
schema changes or new generators are required.

Optional fields are `id_oddzial`, `id_odbiorca`, `id_firma`, `umowa`, `typ`,
`handlowiec`, `opiekun`, `opiekunmail`, `opiekuntel`, `u_start`, `u_stop`,
`warunki`, `uwagi`, `rabat`, `platnosc`, `termin`, `aktywna`, `strony_mono`,
`strony_kolor`, `skany`, `fraemail` and `plik`. Dates use `YYYY-MM-DD` and
`rabat` accepts a decimal value. Strings are trimmed and checked against the
column widths. Unknown fields, generated table keys and calculated financial
totals (`koszty`, `przychody`, `wynik`) are rejected with `422`.

Omitted/null/blank optional fields use the shared legacy profile
(`AGREEMENT_INSERT_DEFAULTS`: empty contact and notes fields, zeroed flags,
mono/colour counts and fee slots, and the legacy payment marker `$_$`) or column
defaults. The profile matches the legacy agreement with `ID_UMOWACPC = 1`,
including `aktywna = "TAK"`. Omitted or null `u_start` uses Firebird
`CURRENT_DATE` at insertion (the database server's date). Explicit `u_start`
and `aktywna` values override these defaults. If `umowa` is omitted, null or
blank, it defaults to `{generated ID_UMOWACPC}/{current database year}`, e.g.
`4/2026`. A supplied nonblank number is preserved; an explicit start date does
not change the numbering year. Type, end date and company are left to the caller; reference-specific values are not copied. The response is the stored `Agreement` projection with `201`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agreements/42 -H 'Content-Type: application/json' -d '{"umowa": "CPC/2026/001", "u_start": "2026-11-08", "aktywna": "TAK"}'
```

Agreement requests accept an optional `machines` array of positive
`ID_MASZYNA` values. On creation, each listed machine gets the generated
agreement ID in `MASZYNA.ID_UMOWACPC`. On update, it gets the agreement ID from
the URL. Existing agreement links on listed machines are reassigned; machine
ownership (`ID_KLIENT`) stays unchanged. Omitting `machines` preserves current
links. A supplied array is the complete desired list: machines previously
linked to this agreement but absent from it have `ID_UMOWACPC` cleared to NULL.
Sending `[]` clears all of this agreement's links. Other agreements' machine
links are untouched. Repeated list entries are processed once.
Arrays accept up to 1000 integer IDs; null, strings, booleans and nonpositive
values are rejected with `422`.

`PATCH /agreements/{id_umowacpc}` updates supplied agreement fields only and
returns the stored agreement with `200`. Its URL identifies an agreement;
the POST URL identifies a client. The optional array can accompany agreement
details or be the only field. Omitted fields retain their values; null clears
nullable columns. Creation defaults are never reapplied. An empty object `{}` returns `400`; `{"machines": []}` is a valid request to
clear all links. Generated agreement IDs and
calculated totals remain read-only. `id_klient` may be supplied as a positive
integer to change the agreement's client.

Agreement changes and all listed machine links commit in one transaction.
A missing agreement or machine returns `404`; duplicate business IDs matching
multiple records return `409`. Any such failure rolls back the agreement and
all links, including machines already processed in that request. Both routes
require writes enabled and the configured API key.

```http
POST /api/v1/agreements/42
Content-Type: application/json

{"umowa": "CPC/2026/001", "machines": [4, 7, 12]}
```

```http
PATCH /api/v1/agreements/3
Content-Type: application/json

{"uwagi": "Updated agreement", "machines": [15, 18]}
```

`GET /cpc-settlement` returns `{total, count, limit, offset, cpc}` with lower-cased
settlement column names. It accepts `limit`, `offset`, `search` (invoice number
and notes), and the same JSON `filters` syntax as the generic row endpoint.
Use filters for `id_klient`, `id_maszyna`, `id_umowacpc`, `rok` or `miesiac`.
`GET /cpc-settlement/{id_cpc_table}` returns one record or `404`. Record keys are
non-negative: existing legacy key `0` is supported.

`POST /cpc-settlement` requires positive `id_klient`, `id_maszyna` and
`id_umowacpc`. Optional `rok` (1–9999) and `miesiac` (1–12) default independently
to the database current year/month when omitted or null. Explicit values are
preserved, including when only one period field is supplied. Updates never
reapply these defaults. Firebird generates `id_cpc_table`. Optional fields
include mono/colour/A3/scan start/end readings, copy and page counts, rates,
recorded charges, costs, invoice reference and notes. Monetary values use
`DECIMAL(10,4)`; text widths are 50 for `faktura` and 500 for `uwagi`. Omitted
fields use `CPC_INSERT_DEFAULTS` (the zero/empty values shared by legacy rows)
or their database defaults. Null/blank optional create fields are omitted.

`PATCH /cpc-settlement/{id_cpc_table}` changes supplied fields only and returns `200`.
Nullable fields can be cleared with null; blank text becomes an empty string.
Year/month must retain valid values, and `idvat` cannot be null. Client, machine,
agreement and generated record IDs cannot change: the legacy update trigger
refreshes only the NEW parents, so moving a settlement would leave old totals
stale. An empty patch returns `400`. Unknown fields, invalid values and attempts
to change parent links return `422`.

`DELETE /cpc-settlement/{id_cpc_table}` returns an empty `204`. Missing records on GET,
PATCH or DELETE return `404`. Writes require `KS_ALLOW_WRITES=true` and the
configured API key; reads need only the configured API key.

These routes store supplied readings, counts and financial amounts. They do
not infer copy counts or calculate charges, VAT, or profit from meter readings.
Existing database triggers recalculate machine/agreement aggregate costs,
revenue and profit after CPC insertion, update and deletion, within the same
transaction. Empty aggregates follow the database's existing NULL behavior.

```http
POST /api/v1/cpc-settlement
Content-Type: application/json

{"id_klient": 42, "id_maszyna": 4, "id_umowacpc": 3, "rok": 2026, "miesiac": 11, "licznik_mono_start": 1000, "licznik_mono_end": 1500}
```

```http
PATCH /api/v1/cpc-settlement/5
Content-Type: application/json

{"kopie_mono": 500, "oplata_suma": "25.0000", "uwagi": "Updated settlement"}
```

`POST /machines` takes the lower-cased column names of the `GET /machines`
projection (`marka`, `model`, `serial`, `instalacja`, `oplata`, ...) and inserts
one `MASZYNA` row. All fields are optional, so `{}` is valid. An omitted,
`null` or zero `id_klient` means unassigned and is stored as `0`, because
`MASZYNA.ID_KLIENT` cannot be NULL. Negative client IDs are rejected.
`INS_MASZYNA_RECORD` assigns `ID_MASZYNA_TABLE` and `ID_MASZYNA`.
`MACHINE_INSERT_DEFAULTS` reproduces the native row profile: branch/company/VAT
and sync flags `0`, printer group `grupa = "Druk"`, `aktywna = "TAK"`,
`kolorowa = "NIE"`, billing type
`rodzaj_us = "Płatne"`, and expected empty text fields (including internal
`MKOD`, `OPCJE`, `DETAL20`). The branch default is intentionally `0`, matching
recent legacy-created rows, rather than the raw column default `1`. Explicit
caller values override these defaults, including branch and business flags.
Omitted/null/blank optional strings use that profile. Counters, dates, optional
links and financial aggregates retain their database defaults. Strings are
trimmed; unknown fields return `422`. Application-maintained fields
(`licznik_total`, `last_m`, `last_w`, `next_w`, `koszty`, `przychody`, `wynik`,
`synwp`) cannot be supplied directly.

`POST /machines/{id_klient}` creates a machine with its owner taken from the
URL. It uses the same validation and legacy defaults as `POST /machines`, with
an optional body of machine details (or no body). A body `id_klient` may be
omitted, null, or match the URL; a conflicting value returns `400`. URL client
ID `0` creates an unassigned machine. The response is the stored machine with
`201`; writes enabled and the configured API key are required.

```http
POST /api/v1/machines/42
Content-Type: application/json

{"marka": "KONICA", "model": "C224", "serial": "SN-0001"}
```

`PATCH /machines/{id_maszyna}` updates an existing machine by `ID_MASZYNA`
(the business identifier returned by `GET /machines`). It accepts the same
writable fields as `POST /machines`, all optional. Only supplied fields change;
omitted fields and defaults remain untouched. Strings are trimmed; `""` clears
text and `null` clears nullable fields. Set `id_klient` to `0` to unassign the
machine; null is rejected for ownership and other non-nullable columns.
Generated keys and derived fields remain read-only. Empty updates return `400`,
unknown or invalid fields `422`, missing machines `404`, and ambiguous business
IDs `409` (the database does not enforce uniqueness of `ID_MASZYNA`). Successful
updates return the stored `Machine` projection with `200`. Existing database
update triggers run normally, including propagation of machine details to
related orders. Requires writes enabled and the configured API key.

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/machines/4 -H 'Content-Type: application/json' -d '{"model": "C224", "serial": "SN-0002"}'
```

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
`409` ambiguous machine identifier, `403` writes disabled (`api.allow_writes` off), `404` unknown table or client record, `422`
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
