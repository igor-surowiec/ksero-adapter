# Development and testing

Install runtime and development packages with `uv sync --locked` from the
project directory. uv creates and manages `.venv` automatically.

Check configuration and database connectivity:

```bash
uv run --locked adapter --check
```

```bash
uv run --locked python -m pytest             # unit + API, no database
KS_TEST_DB_PATH=BAZAMS.FDB uv run --locked python -m pytest  # live tests
KS_TEST_DB_PATH=BAZAMS.FDB KS_TEST_DB_WRITABLE=1 uv run --locked python -m pytest
                                            # + the create-client tests
```

The write tests insert a disposable contractor and delete it again, which is why
they need the extra opt-in variable.

Test the secondary database endpoint independently of primary database access:

```bash
KS_TEST_DB_PATH=BAZAMS.fdb KS_TEST_MACHINES_DB_PATH=BAZA_CPC_FB5.FDB uv run --locked python -m pytest tests/test_integration.py -q -k secondary_machines_database_endpoint
```

`KS_TEST_DB_PATH` enables the integration module; this selected test opens only
`KS_TEST_MACHINES_DB_PATH`. Credentials and client library use the same
`KS_TEST_DB_USER`, `KS_TEST_DB_PASSWORD`, `KS_TEST_DB_CHARSET`, and
`KS_TEST_DB_CLIENT` variables as the other live tests.

The CPC synchronization integration test inserts synthetic records into both
test databases and removes them on exit. It additionally requires
`KS_TEST_MACHINES_DB_WRITABLE=1` as well as `KS_TEST_DB_WRITABLE=1` and both
database paths. Use disposable copies when enabling both write flags.

Dependency ranges live in `pyproject.toml`; `uv.lock` pins resolved versions
across supported Python versions and platforms. Use `uv add PACKAGE` for
runtime dependencies, `uv add --dev PACKAGE` for test dependencies, and
`uv lock --upgrade` to refresh locked versions. Commit both files when changing
dependencies. The development group is installed by default; use
`uv sync --locked --no-dev` for a runtime-only environment.

Run write tests against a disposable database copy. See
[AGENTS.md](../AGENTS.md) for the transaction and cleanup rules, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the implementation reference.

## Migrating a local Firebird 2.5 database to Firebird 5

Stop the application/server using the source file before copying it. Run:

```bash
scripts/migrate-firebird-2.5-to-5.sh BAZA_CPC.FDB BAZA_CPC_FB5.FDB
```

The script prompts for the database password, or accepts `ISC_PASSWORD` from
the environment; `ISC_USER` defaults to `SYSDBA`. Avoid putting passwords in
shell command arguments or shell history.

On macOS, it downloads the official Intel Firebird 2.5.9 Classic package and
extracts it temporarily, without running its installer. Apple Silicon needs
Rosetta available. Firebird 5 must already be installed. On Linux, provide
`FB25_ROOT` and `FB5_BIN` for existing installations. Run with `--help` for
library-path overrides and installation directory conventions. The source and
destination must be local file paths, with an existing destination directory.

The script backs up a temporary source copy, restores with Firebird 5, checks
ODS 13.1, runs full validation without repairs, and verifies the source's
SHA-256. It publishes the destination only after those checks and refuses to
overwrite an existing file. Temporary copies, tools, backups and logs are
removed on exit. Database credentials are passed through the environment.
The script does not change adapter configuration or test application writes.

The legacy macOS tool may abort during shutdown after reporting a completed
backup. The script accepts that specific case only when the backup completion
marker is present and no backup error is reported; restore and validation must
still pass. Other backup failures stop the migration.

After migration, set `KS_MACHINES_DB_PATH` to the new file to select it in the
optional machine database configuration. See Firebird's
[backup and restore documentation](https://www.firebirdsql.org/file/documentation/html/en/firebirddocs/gbak/firebird-gbak.html).
