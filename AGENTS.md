# AGENTS.md

Guidance for AI agents (and new contributors) working on **ks-adapter**, a
FastAPI bridge in front of a Firebird database (Firebird 2.5, `WIN1250` Polish
data; the `ZLECENIE` table alone has 154 columns). It is read-only by default;
`POST /clients`, `POST /machines/{id_klient}`, `POST /cpc-agreements/{id_klient}`, `PATCH /clients/{id_klient}` and
`DELETE /clients/{id_klient}`, `PATCH /machines/{id_maszyna}`,
`DELETE /machines/{id_maszyna}` and
`PATCH /cpc-agreements/{id_umowacpc}`, `DELETE /cpc-agreements/{id_umowacpc}`
and CPC POST/PATCH/DELETE are opt-in write routes.

Quick setup is in [`README.md`](README.md). Detailed references are
[`docs/ROUTES.md`](docs/ROUTES.md),
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Read the relevant references
before changing behaviour; this file adds rules and recipes that are easy to
get wrong.

## Non-negotiable invariants

1. **Reads are read-only.** Every read statement passes `sql.ensure_read_only()`
   and must stay a single `SELECT`/`WITH`. The only exceptions are the curated
   writes (including CPC CRUD), gated behind
   `api.allow_writes` (`errors.WritesDisabled` → 403), their statements come
   from curated SQL builders (`build_insert`, `build_update`, `build_delete`)
   and run **only** inside
   `pool.write_session()` - never `pool.session()`, which always rolls back. Do
   not add another write path without the same switch, the same builder and
   explicit tests.
2. **Values are always parameters, never strings.** Emit `?` placeholders and
   pass the values separately; identifiers go through `sql.quote_identifier()`.
   Anything else is an injection bug.
3. **All database work goes through `DatabaseService`** (`service/`) and
   `pool.session()`/`pool.write_session()`. Never call `fdb.connect()` from a
   route, service method or test - `pool.connect()` is the only place that opens
   connections.
4. **Respect Firebird's 64 KB statement-message limit.** More than
   `sql.MAX_SEARCH_COLUMNS` (63) `CAST(? AS VARCHAR(1024))` parameters in one
   statement make the server answer `-204 Implementation limit exceeded`. That
   is why the curated endpoints use hand-picked `*_COLUMNS` /
   `*_SEARCH_COLUMNS` instead of `SELECT *` on wide tables.
5. **Settings are whitelisted.** `_ALLOWED_KEYS` comes from the settings
   dataclasses. A new key needs a dataclass field and parsing in
   `_build_settings` (plus `_ENV_OVERRIDES` for environment overrides) and
   `config/config.yaml`. Unknown keys are an error.
6. **Never commit the database or credentials.** `*.fdb` is git-ignored and
   holds customer data: do not copy rows into tests, docs, logs or fixtures.

## Environment and commands

The project targets Python 3.10+ and uses uv to manage `.venv` and the locked
dependencies. Run commands from the project directory; no activation is needed.

```bash
uv sync --locked                             # runtime deps + pytest + httpx
uv run --locked adapter --check  # config + DB smoke test
uv run --locked adapter          # serve :8000, docs at /docs
uv run --locked python -m pytest -q           # offline suite, no database
KS_TEST_DB_PATH=BAZAMS.FDB uv run --locked python -m pytest -q  # + live DB
KS_TEST_DB_PATH=BAZAMS.FDB KS_TEST_DB_WRITABLE=1 uv run --locked python -m pytest -q
                                             # + the create-client tests
uv run --locked python -m pytest tests/test_api.py -q -k orders  # one test
```

`pyproject.toml` declares dependency ranges and the `dev` group; `uv.lock` pins
resolved versions. Commit both when changing dependencies. Use
`uv sync --locked --no-dev` and `uv run --locked --no-dev adapter`
for runtime-only installations.

Runtime dependencies are `fastapi`, `uvicorn`, `fdb` and `PyYAML` only; the
suite adds `pytest` and `httpx`. Do not add a dependency without being asked.
`pytest.ini` limits collection to `tests/` and registers the `integration`
marker.

## Layout

- `adapter/api.py` - router composition and shared API-key enforcement.
- `adapter/static/api_tester.html` - buildless API tester at the exact API
  prefix; inputs come from OpenAPI and requests run only on submission.
- `adapter/routes/` - resource routers (`clients.py`, `agreements.py`,
  `machines.py`, `cpc_settlement.py`, `orders.py`, `invoices.py`,
  public `meta.py`); `common.py` holds shared dependencies.
- `adapter/service/` - `DatabaseService` facade in `__init__.py`; resource
  operations and constants in `clients.py`, `agreements.py`, `machines.py`,
  `cpc_settlement.py`, `orders.py`, `invoices.py`; shared pool/cache/query/write
  helpers in `base.py`. Every resource shares the facade's pool and cache.
- `adapter/sql.py` - read-only guard, `build_insert()` / `build_update()`,
  filters, ordering, `LIKE` search.
- `adapter/schema.py` - TTL schema cache (`SchemaCache`), table/column info.
- `adapter/pool.py` - thread-safe connection pool (`session()`,
  `write_session()`, `ping()`).
- `adapter/serialization.py` - Firebird to JSON types, `row_to_dict()`.
- `adapter/schemas/` - Pydantic wire models by matching resource, plus
  `meta.py` and shared `common.py`. `__init__.py` re-exports the
  existing model names to preserve public imports.
- `adapter/config.py` - YAML + `${VAR}` + `KS_*` settings, validation.
- `adapter/errors.py` - `AdapterError` subclasses carrying HTTP statuses.
- `adapter/app.py` - app factory, exception handlers, CORS, lifespan.
- `tests/` - `conftest.py` (`FakeService`, `client`), unit, API, integration.

## Recipes

### Add a field to a curated endpoint (`/clients`, `/cpc-agreements`, ...)

1. Append the column name to the matching `*_COLUMNS` constant in its `service/<resource>.py` module
   and, if it must be searchable, the column to `*_SEARCH_COLUMNS` **within
   budget** - the suite asserts the budget.
2. Add the optional field to the Pydantic model in `schemas/<resource>.py`, named after
   the column in lower case (`NAZWA` -> `nazwa`): the JSON key *is* the column
   name, there is no alias table to update.
3. Extend the stub `TableInfo` in the tests if the assertions need values.
4. Leave the docstrings alone unless the documented meaning changed.

### Add a curated endpoint

1. Constants in the resource's `service/` module: `X_TABLE`, `X_COLUMNS`, `X_SEARCH_COLUMNS`.
2. `fetch_x()` that calls `_projection_page(...)` and renames `rows` to the
   plural key.
3. Models in the resource's `schemas/` module and a route in the appropriate `routes/` module.
   Resource routers are protected centrally by `api.create_router`; only
   `routes/meta.py` is public. Register any new resource module in `api.py`.
4. `FakeService.fetch_x` in `tests/conftest.py`, tests in `test_api.py` /
   `test_service.py`, and live coverage in `test_integration.py` when it helps.
5. A row in the `docs/ROUTES.md` endpoint table; `/docs` documents the fields.

### Add a setting

`config.py` (dataclass field, `_build_settings`,
`_ENV_OVERRIDES`), then `config/config.yaml`, then the `docs/CONFIGURATION.md` env table when
the variable is public.

### Add a write

1. Gate it: raise `errors.WritesDisabled` when `settings.api.allow_writes` is
   off - never write while the switch is off.
2. Declare the writable subset as a `*_WRITE_COLUMNS` constant and the text
   widths as `*_TEXT_LENGTHS`, then normalise the payload with
   `DatabaseService._prepared_write_values()` (key matching, trimming, blank
   and unknown-field rejection) instead of validating by hand.
3. For inserts, reproduce the row profile the legacy program writes: collect
   every column value that program puts into new rows (see
   `CLIENT_INSERT_DEFAULTS`) in a
   `*_INSERT_DEFAULTS` constant and merge it with `_insert_plan()`. A write that
   leaves the Firebird `NULL`s behind produces a row the program does not show,
   even though SQL accepts it.
4. Build the statement with `sql.build_insert(table, columns, returning=...)`
   and bind every value; never format a value into the SQL.
   For updates use `sql.build_update()` with a unique key predicate, preserve
   omitted fields, and never merge insert defaults into the existing row.
   For deletions use `sql.build_delete()` with a unique key predicate.
   `DEL_KLIENT_RECORD` also deletes the client's machines and contacts.
   `DEL_MASZYNA_DELETE` deletes the machine's service orders; reject ambiguous
   machine business IDs before deleting anything.
   Agreement creation allocates the lowest unused positive `ID_UMOWACPC`
   inside `write_session(reserve_table="UMOWACPC")`; keep allocation and insert
   in that same reserved transaction to prevent races across processes.
   Agreement creation requires a machine list; updates may omit it. Machine
   links must use the same cursor/transaction;
   missing or ambiguous machine IDs must roll back the complete request.
   CPC parent IDs remain fixed on update: its legacy trigger only recomputes
   NEW parent totals. Allow legacy ID_CPC_TABLE=0 in record URLs.
   CPC creation derives ID_KLIENT from the unique agreement in the insert
   transaction; reject conflicting caller-supplied client IDs.
5. Execute it inside `self.pool.write_session()` and only there: it commits on
   success and rolls back on any exception.
6. Give the offline suite a `_Pool.write_session()` case (`committed` /
   `rolled_back`) plus an integration test behind `KS_TEST_DB_WRITABLE=1` that
   deletes what it created.

## Testing rules

- The default suite must pass **without a database**: `FakeService` for HTTP
  tests, the scripted `_Pool`/`_StubSchema` in `test_service.py` for service
  tests. Never mock `fdb` directly.
- Live tests live in `tests/test_integration.py` behind the `integration`
  marker and `KS_TEST_DB_PATH`; run them after touching SQL, the pool or a
  curated view.
- Write tests additionally need `KS_TEST_DB_WRITABLE=1` and must delete the row
  they created (`delete_client()` in `test_integration.py`); never leave data in
  the database the tests point at.
- When behaviour depends on the generated statement, assert the SQL text and
  parameters (`pool.executed`); when touching search lists, assert the budget
  constants. For writes also assert `pool.committed` / `pool.rolled_back`.
- Keep `conftest.FakeService` in sync with new service methods - a missing
  method breaks unrelated tests.

## Conventions

- `from __future__ import annotations` first in every module, full type hints;
  `fdb` connections and cursors are typed `Any`.
- Import order: stdlib, third-party, relative. Logging through
  `logging.getLogger(__name__)`; no `print()` outside the CLI.
- Python lines stay within 88 columns; Markdown prose wraps at 80. Long table
  rows, code fences and the ASCII diagrams in `docs/ARCHITECTURE.md` are the
  exceptions.
- Docstrings: one-line module docstring, public API documented, reST
  cross-references (`:data:`, `:class:`, `:meth:`) and ``double backticks`` for
  code. **Keep them count-free** - no hard-coded column or test counts.
- Documented module constants get a `#:` comment above them (`service/`).
- Errors: raise `errors.AdapterError` subclasses (`InvalidRequest` 400,
  `AuthenticationError` 401, `WritesDisabled` 403, `TableNotFound` 404,
  `DatabaseUnavailable` 503).
  Handlers return plain dicts; `app.py` renders
  `{"detail": <message>, "error": <exception class>}`.
- Comments explain *why* (Firebird quirks), never restate the code.
- Backslashes in SQL literals (`ESCAPE '\\'` in `sql.py`) are easy to mangle
  through editors and JSON layers - re-read the file after such an edit.
- Routes are sync `def` and run in the threadpool; do not make them `async`
  unless the database layer becomes async too.

## Definition of done

1. `uv run --locked python -m pytest -q` green; the live suite green when a
   database is available.
2. `uv run --locked adapter --check` still passes after
   config/service changes.
3. Routes, configuration and architecture docs updated when their contracts change.
4. No scratch files left behind (`.tmp_*` is git-ignored but must not be
   committed) and no `.fdb` in the diff.
