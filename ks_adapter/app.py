"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import fdb
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import create_router
from .config import AppSettings, load_config
from .errors import AdapterError
from .service import DatabaseService

logger = logging.getLogger(__name__)

DESCRIPTION = """
HTTP access to a Firebird database.

* **Schema** - list tables/views, inspect their columns.
* **Rows** - paginated access with ordering and JSON based filters.
* **Query** - run your own single read-only `SELECT`/`WITH` statement.
* **Clients** - create a contractor (opt-in via `api.allow_writes`).
* **Machines** - create a machine of a contractor (opt-in as well).

Identifiers are quoted and values are always bound parameters. Read requests can
never modify the database; the writing routes are `POST /clients`, `POST /machines` and
`PATCH /clients/{id_klient}` and `DELETE /clients/{id_klient}`, all rejected with `403`
unless `api.allow_writes` is enabled.
"""


def create_app(
    settings: AppSettings | None = None, service: DatabaseService | None = None
) -> FastAPI:
    """Build the FastAPI application.

    ``service`` can be injected (handy in tests); otherwise a service bound to
    the configured database is created and closed on shutdown.
    """
    settings = settings or load_config()
    owns_service = service is None
    database = service if service is not None else DatabaseService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "ks-adapter %s started (database=%s)", __version__, settings.database.dsn
        )
        try:
            yield
        finally:
            if owns_service:
                database.close()
            logger.info("ks-adapter stopped")

    app = FastAPI(
        title="KS Adapter",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.service = database

    if settings.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.api.cors_origins),
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["*"],
        )

    app.include_router(create_router(settings))
    app.add_exception_handler(AdapterError, _adapter_error_handler)
    app.add_exception_handler(fdb.Error, _firebird_error_handler)

    @app.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {
            "service": "ks-adapter",
            "version": __version__,
            "api": settings.api.prefix,
            "docs": "/docs",
        }

    return app


async def _adapter_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, AdapterError) else AdapterError(str(exc))
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message, "error": type(exc).__name__},
    )


async def _firebird_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Firebird error while handling %s %s", request.method, request.url.path
    )
    message = str(exc).strip().splitlines()
    detail = message[0] if message else type(exc).__name__
    return JSONResponse(
        status_code=500,
        content={"detail": f"Firebird error: {detail}", "error": type(exc).__name__},
    )
