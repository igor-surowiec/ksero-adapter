# Configuration

Everything lives in `config/config.yaml`; values may use `${VAR}` (required) or
`${VAR:-default}` (fallback) placeholders, so most settings can be overridden
without touching the file:

| Variable | Setting |
| --- | --- |
| `KS_CONFIG` | path to the YAML file (default `config/config.yaml`) |
| `KS_DB_PATH`, `KS_DB_USER`, `KS_DB_PASSWORD`, `KS_DB_CHARSET` | database and credentials |
| `KS_DB_HOST`, `KS_DB_PORT`, `KS_FB_CLIENT` | remote server, native library |
| `KS_SERVER_HOST`, `KS_SERVER_PORT`, `KS_LOG_LEVEL` | server |
| `KS_API_KEY` | require `X-API-Key` on resource requests |
| `KS_ALLOW_WRITES` | enable the write endpoints (`POST /clients`, `POST /cpc-agreements/{id_klient}`, `PATCH /clients/{id_klient}`, `DELETE /clients/{id_klient}`, `POST /machines/{id_klient}`, `PATCH /machines/{id_maszyna}`, `DELETE /machines/{id_maszyna}`, `PATCH /cpc-agreements/{id_umowacpc}`, `DELETE /cpc-agreements/{id_umowacpc}`, `POST/PATCH/DELETE /cpc-settlement`) |
| `KS_DEFAULT_LIMIT`, `KS_MAX_LIMIT` | API page caps |

Unknown keys are rejected, the password is meant to come from the environment,
and a relative `database.path` is resolved against the project root (so
`BAZAMS.FDB` works from any working directory). The remaining settings
(`pool_size`, `check_path`, `schema_cache_ttl`, `decimal_as_string`,
`cors_origins`, ...) are documented inline in the YAML file.


`api.max_query_rows` / `KS_MAX_QUERY_ROWS` caps local Python diagnostic queries;
it is not used by an HTTP query route.

## macOS Firebird client

Use a native Firebird client matching the Python process architecture. If the
framework client fails to load with ``@rpath/lib/libtommath.dylib`` and
``no LC_RPATH's found``, start the adapter with its dependency directory:

```bash
export DYLD_LIBRARY_PATH=/Library/Frameworks/Firebird.framework/Versions/A/Resources/lib
uv run --locked --no-dev adapter --check
uv run --locked --no-dev adapter
```

``KS_FB_CLIENT`` selects the client library itself; it does not configure the
loader's dependency search path. The adapter applies a transaction-binding
compatibility fix for ``fdb`` on Apple Silicon automatically.

For embedded local access, the process also needs access to Firebird's runtime
directory (typically ``/tmp/firebird``) and read/write access to the database
file. After adding a user to the ``firebird`` group, log out and back in, and
restart the adapter so it inherits the updated groups.
