# ks-adapter

A FastAPI server connecting clients, machines, CPC agreements and settlements
with a Firebird database.

## Structure

- `ks_adapter/routes/` — HTTP endpoints.
- `ks_adapter/service/` — database operations.
- `ks_adapter/schemas/` — request and response models.
- `ks_adapter/app.py` — app setup; `api.py` composes the routes.
- `config/config.yaml` — server and database settings.
- `tests/` — automated tests.
- `docs/` — [routes](docs/ROUTES.md), [configuration](docs/CONFIGURATION.md),
  [development](docs/DEVELOPMENT.md) and [architecture](docs/ARCHITECTURE.md).

## Install and run

Requires Python 3.10+ and the native Firebird client (`fbclient.dll` on Windows).
From the project directory, in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Set your database connection in `config/config.yaml` or through the documented
`KS_*` environment variables, then start the server:

```powershell
.venv/Scripts/python.exe -m ks_adapter
```

The server runs at `http://127.0.0.1:8000`; open `/api/v1` for the API tester.
