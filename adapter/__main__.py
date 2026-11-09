"""Command line entry point: ``python -m adapter``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Sequence

from .config import CONFIG_ENV_VAR, ConfigError, LOG_LEVELS, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adapter",
        description="Run the read-only Firebird HTTP adapter.",
    )
    parser.add_argument(
        "-c", "--config", help="Path to the YAML configuration file"
    )
    parser.add_argument("--host", help="Override 'server.host'")
    parser.add_argument("--port", type=int, help="Override 'server.port'")
    parser.add_argument(
        "--log-level", choices=LOG_LEVELS, help="Override 'server.log_level'"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server automatically when the code changes",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the configuration and the database connection, then exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    host = args.host or settings.server.host
    port = args.port or settings.server.port
    log_level = args.log_level or settings.server.log_level
    reload = args.reload or settings.server.reload

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    if args.check:
        return _check(settings)

    import uvicorn

    if reload:
        # ``reload=True`` requires an import string, so pass the config via env.
        if settings.config_path is not None:
            os.environ[CONFIG_ENV_VAR] = str(settings.config_path)
        uvicorn.run(
            "adapter.app:create_app",
            factory=True,
            host=host,
            port=port,
            log_level=log_level,
            reload=True,
        )
    else:
        from .app import create_app

        uvicorn.run(create_app(settings), host=host, port=port, log_level=log_level)
    return 0


def _check(settings) -> int:
    from .errors import AdapterError
    from .service import DatabaseService

    service = DatabaseService(settings)
    try:
        health = service.health()
        table_count = len(service.list_tables())
    except AdapterError as exc:
        print(f"Database check failed: {exc.message}", file=sys.stderr)
        return 1
    finally:
        service.close()

    print(f"Configuration OK: {settings.config_path}")
    print(
        "Database: "
        f"{health['database']['dsn']} ({health['database']['server_version']})"
    )
    print(f"Tables/views: {table_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
