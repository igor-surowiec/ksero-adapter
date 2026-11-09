# ks-adapter

A FastAPI server connecting clients, machines, CPC agreements and settlements
with a Firebird database.

## Structure

- `adapter/routes/` — HTTP endpoints.
- `adapter/service/` — database operations.
- `adapter/schemas/` — request and response models.
- `adapter/app.py` — app setup; `api.py` composes the routes.
- `config/config.yaml` — server and database settings.
- `tests/` — automated tests.
- `docs/` — [routes](docs/ROUTES.md), [configuration](docs/CONFIGURATION.md),
  [development](docs/DEVELOPMENT.md) and [architecture](docs/ARCHITECTURE.md).

## Install and run

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), Python
3.10+ and the native Firebird client (`fbclient.dll` on Windows). From the
project directory, in PowerShell (the same commands work on macOS/Linux):

```powershell
uv sync --locked --no-dev
```

Set your database connection in `config/config.yaml` or through the documented
`KS_*` environment variables, then start the server:

```powershell
uv run adapter
```

For a locked runtime-only environment, use `uv run --locked --no-dev adapter`.
The module form `uv run python -m adapter` also works.

The server runs at `http://127.0.0.1:8000`; open `/api/v1` for the API tester.

uv manages `.venv` automatically; no activation is needed. Dependencies are
declared in `pyproject.toml` and pinned in `uv.lock`. See
[development](docs/DEVELOPMENT.md) for test dependencies and commands.
