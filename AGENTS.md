# AGENTS.md

Guidance for AI agents (and new contributors) working on **ks-adapter**, a
FastAPI bridge in front of a Firebird database (Firebird 2.5, `WIN1250` Polish
data; the `ZLECENIE` table alone has 154 columns). It is read-only by default;
`POST /clients` and `POST /machines` are the two opt-in write routes.

User documentation is [`README.md`](README.md), the flow and file-by-file
reference is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Read both before
changing behaviour - this file only adds the rules and recipes that are easy to
get wrong.

## Non-negotiable invariants

1. **Reads are read-only.** Every read statement passes `sql.ensure_read_only()`
   and must stay a single `SELECT`/`WITH`. The only exceptions are the curated
   inserts (`POST /clients`, `POST /machines`): they are gated behind
   `api.allow_writes` (`errors.WritesDisabled` → 403), their statements come
   from `sql.build_insert()`, and they run **only** inside
   `pool.write_session()` - never `pool.session()`, which always rolls back. Do
   not add another write path without the same switch, the same builder and
   explicit tests.
2. **Values are always parameters, never strings.** Emit `?` placeholders and
   pass the values separately; identifiers go through `sql.quote_identifier()`.
   Anything else is an injection bug.
3. **All database work goes through `DatabaseService`** (`service.py`) and
   `pool.session()`/`pool.write_session()`. Never call `fdb.connect()` from a
   route, service method or test - `pool.connect()` is the only place that opens
   connections.
4. **Respect Firebird's 64 KB statement-message limit.** More than
   `sql.MAX_SEARCH_COLUMNS` (63) `CAST(? AS VARCHAR(1024))` parameters in one
   statement make the server answer `-204 Implementation limit exceeded`. That
   is why the curated endpoints use hand-picked `*_COLUMNS` /
   `*_SEARCH_COLUMNS` instead of `SELECT *` on wide tables.
5. **Settings are whitelisted.** A new key needs `config._ALLOWED_KEYS`, a
   dataclass field, parsing in `_build_settings` (plus `_ENV_OVERRIDES` if it
   should be overridable) and `config/config.yaml`. Unknown keys are an error.
6. **Never commit the database or credentials.** `*.fdb` is git-ignored and
   holds customer data: do not copy rows into tests, docs, logs or fixtures.

## Environment and commands

The project targets Python 3.10 and ships a virtualenv at `.venv`. Prefer the
explicit interpreter path - on Windows `python` may resolve elsewhere.

```bash
.venv/Scripts/python.exe -m pytest           # Windows (Git Bash or cmd)
.venv/bin/python -m pytest                   # Linux / macOS
pip install -r requirements-dev.txt          # runtime deps + pytest + httpx
```

```bash
.venv/Scripts/python.exe -m ks_adapter --check   # config + DB smoke test
.venv/Scripts/python.exe -m ks_adapter           # serve :8000, docs at /docs
.venv/Scripts/python.exe -m pytest -q            # offline suite, no database
KS_TEST_DB_PATH=BAZAMS.FDB .venv/Scripts/python.exe -m pytest -q  # + live DB
KS_TEST_DB_PATH=BAZAMS.FDB KS_TEST_DB_WRITABLE=1 .venv/Scripts/python.exe -m pytest -q
                                                 # + the create-client tests
.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k orders  # one test
```

Runtime dependencies are `fastapi`, `uvicorn`, `fdb` and `PyYAML` only; the
suite adds `pytest` and `httpx`. Do not add a dependency without being asked.
`pytest.ini` limits collection to `tests/` and registers the `integration`
marker.

## Layout

- `ks_adapter/api.py` - routes (`create_router`), `get_service`,
  `require_api_key`.
- `ks_adapter/service.py` - `DatabaseService`, curated tables/fields, paging,
  `create_client()` and `create_machine()` (the only writes).
- `ks_adapter/sql.py` - read-only guard, `build_insert()`, filters, ordering,
  `LIKE` search.
- `ks_adapter/schema.py` - TTL schema cache (`SchemaCache`), table/column info.
- `ks_adapter/pool.py` - thread-safe connection pool (`session()`,
  `write_session()`, `ping()`).
- `ks_adapter/serialization.py` - Firebird to JSON types, `row_to_dict()`.
- `ks_adapter/schemas.py` - Pydantic wire models, i.e. the OpenAPI contract.
- `ks_adapter/config.py` - YAML + `${VAR}` + `KS_*` settings, validation.
- `ks_adapter/errors.py` - `AdapterError` subclasses carrying HTTP statuses.
- `ks_adapter/app.py` - app factory, exception handlers, CORS, lifespan.
- `tests/` - `conftest.py` (`FakeService`, `client`), unit, API, integration.

## Recipes

### Add a field to a curated endpoint (`/clients`, `/agreements`, ...)

1. Append the column name to the matching `*_COLUMNS` constant in `service.py`
   and, if it must be searchable, the column to `*_SEARCH_COLUMNS` **within
   budget** - the suite asserts the budget.
2. Add the optional field to the Pydantic model in `schemas.py`, named after
   the column in lower case (`NAZWA` -> `nazwa`): the JSON key *is* the column
   name, there is no alias table to update.
3. Extend the stub `TableInfo` in the tests if the assertions need values.
4. Leave the docstrings alone unless the documented meaning changed.

### Add a curated endpoint

1. Constants in `service.py`: `X_TABLE`, `X_COLUMNS`, `X_SEARCH_COLUMNS`.
2. `fetch_x()` that calls `_projection_page(...)` and renames `rows` to the
   plural key.
3. Models in `schemas.py` and a route in `api.create_router` with
   `dependencies=protected`.
4. `FakeService.fetch_x` in `tests/conftest.py`, tests in `test_api.py` /
   `test_service.py`, and live coverage in `test_integration.py` when it helps.
5. A row in the README endpoint table; `/docs` documents the fields.

### Add a setting

`config.py` (`_ALLOWED_KEYS`, dataclass field, `_build_settings`,
`_ENV_OVERRIDES`), then `config/config.yaml`, then the README env table when
the variable is public.

### Add a write

1. Gate it: raise `errors.WritesDisabled` when `settings.api.allow_writes` is
   off - never write while the switch is off.
2. Declare the writable subset as a `*_WRITE_COLUMNS` constant and the text
   widths as `*_TEXT_LENGTHS`, then normalise the payload with
   `DatabaseService._prepared_insert_values()` (key matching, trimming, blank
   and unknown-field rejection) instead of validating by hand.
3. Reproduce the row profile the legacy program writes: collect every column
   value that program puts into new rows (see `CLIENT_INSERT_DEFAULTS`) in a
   `*_INSERT_DEFAULTS` constant and merge it with `_insert_plan()`. A write that
   leaves the Firebird `NULL`s behind produces a row the program does not show,
   even though SQL accepts it.
4. Build the statement with `sql.build_insert(table, columns, returning=...)`
   and bind every value; never format a value into the SQL.
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
- Documented module constants get a `#:` comment above them (`service.py`).
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

1. `python -m pytest -q` green; the live suite green when a database is
   available.
2. `python -m ks_adapter --check` still passes after config/service changes.
3. README / ARCHITECTURE updated when endpoints, settings or flow changed.
4. No scratch files left behind (`.tmp_*` is git-ignored but must not be
   committed) and no `.fdb` in the diff.
