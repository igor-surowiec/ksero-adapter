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
and a relative `database.path` is resolved against the project root when no
database host is set. With a host set, the path or alias is resolved by the
Firebird server. The remaining settings
(`pool_size`, `check_path`, `schema_cache_ttl`, `decimal_as_string`,
`cors_origins`, ...) are documented inline in the YAML file.


`api.max_query_rows` / `KS_MAX_QUERY_ROWS` caps local Python diagnostic queries;
it is not used by an HTTP query route.

## Selecting the database file

Set `database.path` directly in `config/config.yaml`. Use an absolute path on
the machine running the Firebird server; the file can live outside this
project. For example, for the local Linux server:

```yaml
database:
  path: /home/igor/Work/BAZAMS.FDB
  host: 127.0.0.1
  port: 3050
```

For a Windows Firebird server, use that server's hostname and Windows path:

```yaml
database:
  path: 'C:\Data\BAZAMS.FDB'
  host: windows-server
  port: 3050
```

Keep the remaining database settings when editing these fields. The existing
`KS_DB_PATH` and `KS_DB_HOST` overrides still take precedence over the YAML.
Restart the adapter after changing its configuration.

Firebird's service account needs read/write access to the database and search
access to its parent directories. System service isolation can also restrict
visible paths. Selecting a path in YAML does not bypass filesystem permissions
or grant access to protected files.

## Native client library

`database.client_library` is empty by default, so the driver discovers the
installed native client. The library must match the operating system and
architecture of the **adapter process**, regardless of where the Firebird
server runs: `fbclient.dll` on Windows, or `libfbclient.so` on Linux. A Linux
adapter connecting to a Windows server still loads the Linux client library.

Use `KS_FB_CLIENT` or `database.client_library` only if automatic discovery
cannot find the correct client. That path belongs to the adapter machine;
`database.path` belongs to the Firebird server. On Linux, register the client
directory with the dynamic loader and run `sudo ldconfig`. On Windows, install
the native Firebird client where the driver can discover it, or provide its
absolute DLL path.

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
