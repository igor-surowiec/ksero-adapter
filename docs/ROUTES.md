# API routes

Resource routes live under `api.prefix` (default `/api/v1`). Paths in the table
below are relative to that prefix. Outside it, `GET /` returns public liveness
information, `GET /docs` serves Swagger UI, `GET /redoc` serves ReDoc, and `GET
/openapi.json` returns the OpenAPI schema.

Open `GET /api/v1` in a browser for a simple API tester. It lists all API routes
from OpenAPI in resource sections (clients, agreements, machines, etc.) and
provides inputs for path IDs, query parameters and request fields, plus an
editable JSON body for arrays or explicit `null`. Enter the configured API key
once; it stays in memory for the open page. Only clicking Send runs a request,
and the page shows its status and response. Write requests use the normal
write-enable setting. Custom API prefixes work the same way. The existing `GET
/api/v1/` still returns JSON service information.

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | exact prefix (no trailing slash) | HTML API tester (no API key) |
| `GET` | `/` | JSON service information (no API key) |
| `GET` | `/health` | database ping and pool statistics (no API key) |
| `GET` | `/clients` | contractors (`KLIENT`) |
| `POST` | `/clients` | create a contractor (`KLIENT`), `nazwa` plus optional fields |
| `PATCH` | `/clients/{id_klient}` | update supplied contractor fields by client identifier |
| `DELETE` | `/clients/{id_klient}` | delete a contractor and trigger-managed machines/contacts (`204`) |
| `GET` | `/cpc-agreements` | service agreements (`UMOWACPC`) |
| `POST` | `/cpc-agreements/{id_klient}` | create an agreement (`UMOWACPC`); `id_klient` in URL and `machines` array required |
| `PATCH` | `/cpc-agreements/{id_umowacpc}` | update agreement details and optionally link machines |
| `DELETE` | `/cpc-agreements/{id_umowacpc}` | delete an unreferenced agreement (`204`) |
| `GET` | `/machines` | machines and devices (`MASZYNA`) |
| `POST` | `/machines/{id_klient}` | create a machine; client ID from the URL and nonblank `marka` required |
| `PATCH` | `/machines/{id_maszyna}` | update supplied machine fields by business identifier |
| `DELETE` | `/machines/{id_maszyna}` | delete a machine and trigger-managed service orders (`204`) |
| `GET` | `/cpc-settlement` | paginated CPC settlement records, search and JSON filters |
| `GET` | `/cpc-settlement/{id_cpc_table}` | one CPC settlement |
| `POST` | `/cpc-settlement` | create a CPC settlement |
| `PATCH` | `/cpc-settlement/{id_cpc_table}` | update settlement readings, counts, charges and notes |
| `DELETE` | `/cpc-settlement/{id_cpc_table}` | delete a settlement (`204`) |
| `GET` | `/orders` | service orders (`ZLECENIE`) |
| `GET` | `/invoices` | invoices (`FAKTURA`, header only) |

List endpoints take `limit` (default `api.default_limit`, max `api.max_limit`)
and `offset`. The curated ones (`/clients`, `/cpc-agreements`, `/machines`,
`/orders`, `/invoices`) also take `search`, a case-sensitive substring with
escaped wildcards, and return a hand-picked column subset that stays inside
Firebird's 64 KB statement-message limit - the reason `ZLECENIE` is never
`SELECT *`ed. `/invoices` returns invoice headers only; the positions live in
`FPOZYCJA` and are not exposed. The curated endpoints keep the **original Polish
column names**: every row is keyed by the lower-cased database column (`nazwa`,
`nazwa_s`, `id_klient`, `kod`, `poczta`, `suma_brutto`, ...), so client code
needs no name translation. Only the envelope keys (`total`, `count`, `limit`,
`offset`, `clients`, `agreements`, ...) stay English. Every response field is
documented in the OpenAPI schema (`/docs` or `/openapi.json`).

Insert and update routes return the stored row (`201` and `200` respectively);
deletion returns `204` with no body. All write routes use the same `X-API-Key`
as the read routes and answer `403` unless `api.allow_writes` /
`KS_ALLOW_WRITES=true` is set.

## Clients

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

`PATCH /clients/{id_klient}` updates an existing contractor using the unique
`id_klient` returned by `GET /clients`, also used by machines and related
records. It accepts the same writable fields as `POST /clients`, all optional.
Only supplied fields change: omitted fields and the stored legacy profile stay
untouched. Strings are trimmed; `""` clears a text field and `null` clears an
optional field. A supplied `nazwa` cannot be null or blank. An empty update
returns `400`; unknown or overlong fields return `422`; an unknown record
returns `404`. Generated keys and `ostatnio` cannot be changed. The response is
the updated `Client` projection with `200`.

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

## CPC agreements

`POST /cpc-agreements/{id_klient}` inserts a service agreement into `UMOWACPC`.
The positive `id_klient` (contractor) comes from the URL path. The request body
must include `machines`; send `{"machines": []}` for an agreement without linked
machines using default details. Do not include `id_klient` in the body.
The adapter assigns `id_umowacpc` as the lowest unused positive
integer, starting at `1` and reusing gaps (existing IDs `1, 2, 4` produce `3`).
The trigger generates `id_umowacpc_table`. Both IDs are read-only and rejected
if included in the request.

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
`CURRENT_DATE` at insertion (the database server's date). Explicit `u_start` and
`aktywna` values override these defaults. If `umowa` is omitted, null or blank,
it defaults to `{generated ID_UMOWACPC}/{current database year}`, e.g. `4/2026`.
A supplied nonblank number is preserved; an explicit start date does not change
the numbering year. Type, end date and company are left to the caller;
reference-specific values are not copied. The response is the stored `Agreement`
projection with `201`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/cpc-agreements/42 -H 'Content-Type: application/json' -d '{"machines": [], "umowa": "CPC/2026/001", "u_start": "2026-11-08", "aktywna": "TAK"}'
```

Agreement creation requires a `machines` array of positive `ID_MASZYNA`
values; it is optional on update. Omitted or null arrays on POST return `422`.
An empty array is valid. On creation, each listed machine gets the generated agreement ID in
`MASZYNA.ID_UMOWACPC`. On update, it gets the agreement ID from the URL.
Existing agreement links on listed machines are reassigned; machine ownership
(`ID_KLIENT`) stays unchanged. Omitting `machines` on PATCH preserves current links. A
supplied array is the complete desired list: machines previously linked to this
agreement but absent from it have `ID_UMOWACPC` cleared to NULL. Sending `[]`
clears all of this agreement's links. Other agreements' machine links are
untouched. Repeated list entries are processed once. Arrays accept up to 1000
integer IDs; null, strings, booleans and nonpositive values are rejected with
`422`.

`PATCH /cpc-agreements/{id_umowacpc}` updates supplied agreement fields only and
returns the stored agreement with `200`. Its URL identifies an agreement; the
POST URL identifies a client. The optional array can accompany agreement details
or be the only field. Omitted fields retain their values; null clears nullable
columns. Creation defaults are never reapplied. An empty object `{}` returns
`400`; `{"machines": []}` is a valid request to clear all links. Generated
agreement IDs and calculated totals remain read-only. `id_klient` may be
supplied as a positive integer to change the agreement's client.

Agreement changes and all listed machine links commit in one transaction. A
missing agreement or machine returns `404`; duplicate business IDs matching
multiple records return `409`. Any such failure rolls back the agreement and all
links, including machines already processed in that request. Both routes require
writes enabled and the configured API key.

`DELETE /cpc-agreements/{id_umowacpc}` deletes an agreement by its positive
business ID and returns `204` with no body. Missing agreements return `404`;
duplicate IDs or any records referencing the agreement return `409`. This
includes machines, CPC settlements, invoices and lock records. Related records
are preserved, because deleted agreement IDs can be reused by a new agreement.
Clear machine links with `PATCH /cpc-agreements/{id_umowacpc}` and `{"machines":
[]}` before deletion. Requires writes enabled and the configured API key.

```http
POST /api/v1/cpc-agreements/42
Content-Type: application/json

{"umowa": "CPC/2026/001", "machines": [4, 7, 12]}
```

```http
PATCH /api/v1/cpc-agreements/3
Content-Type: application/json

{"uwagi": "Updated agreement", "machines": [15, 18]}
```

## CPC settlements

`GET /cpc-settlement` returns `{total, count, limit, offset, cpc}` with
lower-cased settlement column names. It accepts `limit`, `offset`, `search`
(invoice number and notes), and the JSON `filters` syntax described below. Use
filters for `id_klient`, `id_maszyna`, `id_umowacpc`, `rok` or `miesiac`. `GET
/cpc-settlement/{id_cpc_table}` returns one record or `404`. Record keys are
non-negative: existing legacy key `0` is supported.

`POST /cpc-settlement` requires positive `id_maszyna` and `id_umowacpc`.
The API reads `ID_KLIENT` from that agreement and stores it on the settlement
in the same transaction. Missing agreements return `404`; duplicate agreement
IDs return `409`. `id_klient` may be omitted or null; if supplied, it must match
the agreement's client, otherwise the request returns `400` without insertion.
Optional `rok` (1–9999) and `miesiac` (1–12) default
independently to the database current year/month when omitted or null. Explicit
values are preserved, including when only one period field is supplied. Updates
never reapply these defaults. Firebird generates `id_cpc_table`. Optional fields
include mono/colour/A3/scan start/end readings, copy and page counts, rates,
recorded charges, costs, invoice reference and notes. Monetary values use
`DECIMAL(10,4)`; text widths are 50 for `faktura` and 500 for `uwagi`. Omitted
fields use `CPC_INSERT_DEFAULTS` (the zero/empty values shared by legacy rows)
or their database defaults. Null/blank optional create fields are omitted.

`PATCH /cpc-settlement/{id_cpc_table}` changes supplied fields only and returns
`200`. Nullable fields can be cleared with null; blank text becomes an empty
string. Year/month must retain valid values, and `idvat` cannot be null. Client,
machine, agreement and generated record IDs cannot change: the legacy update
trigger refreshes only the NEW parents, so moving a settlement would leave old
totals stale. An empty patch returns `400`. Unknown fields, invalid values and
attempts to change parent links return `422`.

`DELETE /cpc-settlement/{id_cpc_table}` returns an empty `204`. Missing records
on GET, PATCH or DELETE return `404`. Writes require `KS_ALLOW_WRITES=true` and
the configured API key; reads need only the configured API key.

These routes store supplied readings, counts and financial amounts. They do not
infer copy counts or calculate charges, VAT, or profit from meter readings.
Existing database triggers recalculate machine/agreement aggregate costs,
revenue and profit after CPC insertion, update and deletion, within the same
transaction. Empty aggregates follow the database's existing NULL behavior.

```http
POST /api/v1/cpc-settlement
Content-Type: application/json

{"id_maszyna": 4, "id_umowacpc": 3, "rok": 2026, "miesiac": 11, "licznik_mono_start": 1000, "licznik_mono_end": 1500}
```

```http
PATCH /api/v1/cpc-settlement/5
Content-Type: application/json

{"kopie_mono": 500, "oplata_suma": "25.0000", "uwagi": "Updated settlement"}
```

## Machines

`POST /machines/{id_klient}` takes the lower-cased column names of the `GET /machines`
projection (`marka`, `model`, `serial`, `instalacja`, `oplata`, ...) and inserts
one `MASZYNA` row. The URL `id_klient` must be a positive integer identifying
an existing `KLIENT.ID_KLIENT`. Invalid path IDs return `422`; a missing
client returns `404` and an ambiguous client ID returns `409`. No machine is
inserted on failure. The JSON body must contain a nonblank `marka`
(manufacturer, at most 100 characters). Missing, null, empty and whitespace-only
manufacturer values return `422`. Surrounding whitespace is trimmed. Other
machine details are optional.
`INS_MASZYNA_RECORD` assigns `ID_MASZYNA_TABLE` and `ID_MASZYNA`.
`MACHINE_INSERT_DEFAULTS` reproduces the native row profile: branch/company/VAT
and sync flags `0`, printer group `grupa = "Druk"`, `aktywna = "TAK"`, `kolorowa
= "NIE"`, billing type `rodzaj_us = "Płatne"`, and expected empty text fields
(including internal `MKOD`, `OPCJE`, `DETAL20`). The branch default is
intentionally `0`, matching recent legacy-created rows, rather than the raw
column default `1`. Explicit caller values override these defaults, including
branch and business flags. Omitted/null/blank optional strings use that profile.
Counters, dates, optional links and financial aggregates retain their database
defaults. Strings are trimmed; unknown fields return `422`.
Application-maintained fields (`licznik_total`, `last_m`, `last_w`, `next_w`,
`koszty`, `przychody`, `wynik`, `synwp`) cannot be supplied directly.

`POST /machines/{id_klient}` creates a machine with its owner taken from the
URL, with required `marka` in the JSON body. A body `id_klient` may be
omitted, null, or match the URL; a conflicting value returns `400`. URL client
ID must be positive and identify an existing client; `0` returns `422` and
a missing client returns `404`. The response is the stored machine with
`201`; writes enabled and the configured API key are required.

```http
POST /api/v1/machines/42
Content-Type: application/json

{"marka": "KONICA", "model": "C224", "serial": "SN-0001"}
```

`PATCH /machines/{id_maszyna}` updates an existing machine by `ID_MASZYNA` (the
business identifier returned by `GET /machines`). It accepts the same writable
fields as `POST /machines/{id_klient}`, all optional. Only supplied fields change; omitted
fields and defaults remain untouched. Strings are trimmed; `""` clears text and
`null` clears nullable fields. Set `id_klient` to `0` to unassign the machine;
null is rejected for ownership and other non-nullable columns. Generated keys
and derived fields remain read-only. Empty updates return `400`, unknown or
invalid fields `422`, missing machines `404`, and ambiguous business IDs `409`
(the database does not enforce uniqueness of `ID_MASZYNA`). Successful updates
return the stored `Machine` projection with `200`. Existing database update
triggers run normally, including propagation of machine details to related
orders. Requires writes enabled and the configured API key.

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/machines/4 -H 'Content-Type: application/json' -d '{"model": "C224", "serial": "SN-0002"}'
```

`DELETE /machines/{id_maszyna}` permanently deletes a machine by `ID_MASZYNA`
(the business identifier from `GET /machines`). Returns `204` with no body,
`404` when missing, or `409` when multiple machines share that ID. The database
`DEL_MASZYNA_DELETE` trigger also deletes linked service orders (`ZLECENIE`)
and applies its configured synchronization behavior in the same transaction.
Other related records follow the connected database's constraints and triggers.
Requires writes enabled and the configured API key.

```http
DELETE /api/v1/machines/4
```

## More examples

```bash
curl 'http://127.0.0.1:8000/api/v1/orders?limit=50&search=przeglad'
curl 'http://127.0.0.1:8000/api/v1/invoices?limit=20&search=2026'
curl -X POST http://127.0.0.1:8000/api/v1/clients -H 'Content-Type: application/json' -d '{"nazwa": "ACME Sp. z o.o.", "nip": "1234567890", "poczta": "Warszawa"}'
curl -X POST http://127.0.0.1:8000/api/v1/machines/42 -H 'Content-Type: application/json' -d '{"id_klient": 42, "marka": "KONICA", "model": "C224", "serial": "SN-0001", "instalacja": "2026-01-02"}'
```

## CPC filters

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
operators give `400`.

## Errors and auth

```json
{"detail": "Table or view 'NOPE' does not exist", "error": "TableNotFound"}
```

`400` invalid request, `401` missing/invalid `X-API-Key`, `409` ambiguous
identifier or agreement still referenced, `403` writes disabled
(`api.allow_writes` off), `404` unknown table or client record, `422`
validation, `500`/`503` database failure. When `api.api_key` is set, send it as
`X-API-Key` on every resource route. The tester, service information and health
routes are public.

