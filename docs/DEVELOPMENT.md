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

Dependency ranges live in `pyproject.toml`; `uv.lock` pins resolved versions
across supported Python versions and platforms. Use `uv add PACKAGE` for
runtime dependencies, `uv add --dev PACKAGE` for test dependencies, and
`uv lock --upgrade` to refresh locked versions. Commit both files when changing
dependencies. The development group is installed by default; use
`uv sync --locked --no-dev` for a runtime-only environment.

Run write tests against a disposable database copy. See
[AGENTS.md](../AGENTS.md) for the transaction and cleanup rules, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the implementation reference.
