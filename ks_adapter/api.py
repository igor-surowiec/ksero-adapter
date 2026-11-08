"""FastAPI routes exposing the Firebird data."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status

from .config import AppSettings
from .errors import AuthenticationError
from .schemas import (
    Agreement,
    AgreementCreate,
    AgreementPage,
    AgreementUpdate,
    Client,
    ClientCreate,
    ClientPage,
    ClientUpdate,
    HealthResponse,
    InvoicePage,
    Machine,
    MachineCreate,
    MachinePage,
    MachineUpdate,
    OrderPage,
    QueryRequest,
    QueryResponse,
    RowPage,
    SchemaRefreshResponse,
    ServiceInfo,
    TableDetail,
    TableListResponse,
)
from .service import DatabaseService

FILTERS_DESCRIPTION = (
    "JSON object with column filters, e.g. "
    '{"nazwa": "Kowalski", "typ": {"op": "in", "value": [1, 2]}}. '
    "Column names are matched case-insensitively, so the lower-cased Polish "
    "names of the responses work here too. "
    "Supported operators: eq, ne, gt, ge, lt, le, like, contains, startswith, "
    "endswith, in, isnull, notnull."
)


def get_service(request: Request) -> DatabaseService:
    """Return the service instance stored on the application state."""
    service = getattr(request.app.state, "service", None)
    if service is None:  # pragma: no cover - only possible on misconfiguration
        raise RuntimeError("DatabaseService is not attached to the application")
    return service


def require_api_key(settings: AppSettings) -> Any:
    """Build a dependency that enforces the ``X-API-Key`` header when configured."""
    expected = settings.api.api_key

    def check_api_key(
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if expected is None:
            return
        if x_api_key is None:
            raise AuthenticationError("Missing X-API-Key header")
        if not hmac.compare_digest(
            x_api_key.encode("utf-8"), expected.encode("utf-8")
        ):
            raise AuthenticationError("Invalid X-API-Key header")

    return check_api_key


def create_router(settings: AppSettings) -> APIRouter:
    """Create the API router for ``settings``."""
    api = settings.api
    protected = [Depends(require_api_key(settings))]
    router = APIRouter(prefix=api.prefix)

    def page_limit(label: str) -> Any:
        return Query(
            default=None, ge=1, le=api.max_limit,
            description=(
                f"{label} per page (default {api.default_limit}, "
                f"max {api.max_limit})"
            ),
        )

    @router.get(
        "/",
        response_model=ServiceInfo,
        tags=["meta"],
        summary="Service information",
    )
    def service_info() -> ServiceInfo:
        from . import __version__

        return ServiceInfo(
            name="ks-adapter",
            version=__version__,
            api_prefix=api.prefix,
            docs_url="/docs",
        )

    @router.get(
        "/health",
        response_model=HealthResponse,
        tags=["meta"],
        summary="Check database connectivity",
    )
    def health(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.health()

    @router.get(
        "/tables",
        response_model=TableListResponse,
        tags=["schema"],
        summary="List tables and views",
        dependencies=protected,
    )
    def list_tables(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        tables = service.list_tables()
        return {"count": len(tables), "tables": tables}

    @router.get(
        "/tables/{table}",
        response_model=TableDetail,
        tags=["schema"],
        summary="Describe a table or view",
        dependencies=protected,
    )
    def describe_table(
        table: str,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.describe_table(table)

    @router.post(
        "/schema/refresh",
        response_model=SchemaRefreshResponse,
        tags=["schema"],
        summary="Reload cached table metadata",
        dependencies=protected,
    )
    def refresh_schema(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return {"refreshed": True, "table_count": service.refresh_schema()}

    @router.get(
        "/tables/{table}/rows",
        response_model=RowPage,
        tags=["data"],
        summary="Read a page of rows from a table or view",
        dependencies=protected,
    )
    def read_rows(
        table: str,
        limit: int | None = page_limit("Rows"),
        offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
        order_by: str | None = Query(
            default=None,
            description="Comma separated sort keys, e.g. 'NAZWA ASC, ID DESC'",
        ),
        filters: str | None = Query(default=None, description=FILTERS_DESCRIPTION),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_rows(
            table, limit=limit, offset=offset, order_by=order_by, filters=filters
        )

    @router.get(
        "/clients",
        response_model=ClientPage,
        tags=["data"],
        summary="List contractors (clients)",
        description=(
            "Returns a page of contractors from the KLIENT table, keyed by the "
            "lower-cased column names (nazwa, id_klient, nip, regon, adres, "
            "kod, poczta, telefon, e_mail, ...). 'search' matches nazwa, "
            "nazwa_s, nip, regon, e_mail, telefon, kod and poczta (case "
            "sensitive substring)."
        ),
        dependencies=protected,
    )
    def list_clients(
        limit: int | None = page_limit("Clients"),
        offset: int = Query(default=0, ge=0, description="Number of clients to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against nazwa, nip, e_mail, telefon, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_clients(limit=limit, offset=offset, search=search)

    @router.post(
        "/clients",
        response_model=Client,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a contractor (client)",
        description=(
            "Inserts one row into the KLIENT table and returns the stored row "
            "in the same shape as GET /clients (keys are the lower-cased "
            "column names). 'nazwa' (NAZWA) is the only required value; every "
            "other field is optional. Columns the payload omits get the "
            "defaults the legacy application itself writes (ID_FIRMA 0, TYP "
            "'Odbiorca', PLATNOSC 'Gotowka', KOD_KRAJU 'PL', IDW -1, empty "
            "strings instead of null, zeroed flags), because a row that keeps "
            "the raw Firebird defaults never shows up in that program. The "
            "INS_KLIENT_RECORD trigger fills ID_KLIENT_TABLE and ID_KLIENT "
            "from their generators and ID_ODDZIAL falls back to its column "
            "default. Unknown fields are rejected with 422 instead of being "
            "ignored. Requires 'api.allow_writes' (otherwise 403) and, when "
            "configured, the X-API-Key header."
        ),
        dependencies=protected,
    )
    def create_client(
        payload: ClientCreate,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.create_client(payload.model_dump(exclude_none=True))

    @router.patch(
        "/clients/{id_klient}",
        response_model=Client,
        tags=["data"],
        summary="Update a contractor (client)",
        description=(
            "Updates only supplied fields, identified by the unique "
            "id_klient from GET /clients. Omitted fields stay unchanged. "
            "Null clears optional fields; blank strings clear text fields. "
            "The name cannot be cleared. Returns 404 for an unknown record. "
            "Requires api.allow_writes and the configured X-API-Key."
        ),
        dependencies=protected,
    )
    def update_client(
        payload: ClientUpdate,
        id_klient: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_client(
            id_klient, payload.model_dump(exclude_unset=True)
        )

    @router.delete(
        "/clients/{id_klient}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
        tags=["data"],
        summary="Delete a contractor (client)",
        description=(
            "Permanently deletes the client identified by ID_KLIENT. "
            "The database DEL_KLIENT_RECORD trigger also deletes the client's "
            "machines and contacts. Returns 204 with no body on success, or "
            "404 when the client does not exist. Requires api.allow_writes "
            "and the configured X-API-Key."
        ),
        dependencies=protected,
    )
    def delete_client(
        id_klient: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> Response:
        service.delete_client(id_klient)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/agreements",
        response_model=AgreementPage,
        tags=["data"],
        summary="List service agreements (contracts)",
        description=(
            "Returns a page of service agreements from the UMOWACPC table, "
            "keyed by the lower-cased column names (id_umowacpc, umowa, typ, "
            "id_klient, ...). 'search' matches umowa, typ, handlowiec, "
            "opiekun, opiekunmail, fraemail and plik (case sensitive "
            "substring)."
        ),
        dependencies=protected,
    )
    def list_agreements(
        limit: int | None = page_limit("Agreements"),
        offset: int = Query(default=0, ge=0, description="Number of agreements to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against umowa, typ, handlowiec, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_agreements(limit=limit, offset=offset, search=search)

    @router.post(
        "/agreements/{id_klient}",
        response_model=Agreement,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a service agreement (UMOWACPC)",
        description=(
            "Creates an agreement for id_klient from the URL path. The optional "
            "body contains agreement details. The adapter "
            "assigns id_umowacpc as the lowest unused positive integer, "
            "reusing gaps. The database generates id_umowacpc_table. "
            "Both identifiers are read-only. Optional fields "
            "use legacy defaults, including aktywna=TAK and u_start set to the "
            "database current date; supplied values override them. "
            "An optional machines array links those ID_MASZYNA records to "
            "the new agreement in the same transaction. Missing or ambiguous "
            "machine IDs roll back everything. Omitted preserves links; empty clears. "
            "Returns the same projection as GET /agreements. Generated table "
            "keys and financial totals cannot be supplied. Requires "
            "api.allow_writes and the configured X-API-Key."
        ),
        dependencies=protected,
    )
    def create_agreement(
        id_klient: int = Path(ge=1),
        payload: AgreementCreate | None = None,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        values = (
            payload.model_dump(exclude_unset=True, exclude_none=True) if payload else {}
        )
        return service.create_agreement({"id_klient": id_klient, **values})

    @router.patch(
        "/agreements/{id_umowacpc}",
        response_model=Agreement,
        tags=["data"],
        summary="Update a service agreement and optionally link machines",
        description=(
            "Updates only supplied agreement fields, identified by ID_UMOWACPC. "
            "The optional machines array contains ID_MASZYNA values to link. "
            "Omitted arrays preserve links. Supplied arrays replace the complete "
            "list: empty clears all links, removed machines are unassigned. "
            "Existing links on listed machines are reassigned. "
            "Agreement updates and links commit together; missing records "
            "return 404 and ambiguous IDs 409 with rollback. Requires "
            "api.allow_writes and the configured X-API-Key."
        ),
        dependencies=protected,
    )
    def update_agreement(
        payload: AgreementUpdate,
        id_umowacpc: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_agreement(
            id_umowacpc, payload.model_dump(exclude_unset=True)
        )

    @router.get(
        "/machines",
        response_model=MachinePage,
        tags=["data"],
        summary="List machines (installed devices)",
        description=(
            "Returns a page of machines from the MASZYNA table, keyed by the "
            "lower-cased column names (id_maszyna, marka, model, serial, "
            "licznik, ...). 'search' matches marka, model, grupa, typ, "
            "rodzaj_us, serial, serial2, ewidencja, miejscowosc and technik "
            "(case sensitive substring)."
        ),
        dependencies=protected,
    )
    def list_machines(
        limit: int | None = page_limit("Machines"),
        offset: int = Query(default=0, ge=0, description="Number of machines to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against marka, model, serial, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_machines(limit=limit, offset=offset, search=search)

    @router.post(
        "/machines",
        response_model=Machine,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a machine (installed device)",
        description=(
            "Inserts one row into the MASZYNA table and returns the stored row "
            "in the same shape as GET /machines (keys are the lower-cased "
            "column names). All fields are optional; an omitted or null "
            "id_klient is stored as 0 (unassigned). The "
            "INS_MASZYNA_RECORD trigger fills ID_MASZYNA_TABLE and ID_MASZYNA "
            "from their generators, ID_ODDZIAL, ID_FIRMA and IDVAT fall back to "
            "their column defaults, so the new row carries only the fields that "
            "were sent with a non-blank value. Unknown fields are rejected with "
            "422. Requires 'api.allow_writes' (otherwise 403) and, when "
            "configured, the X-API-Key header."
        ),
        dependencies=protected,
    )
    def create_machine(
        payload: MachineCreate,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.create_machine(payload.model_dump(exclude_none=True))

    @router.patch(
        "/machines/{id_maszyna}",
        response_model=Machine,
        tags=["data"],
        summary="Update a machine (installed device)",
        description=(
            "Updates only supplied fields, identified by ID_MASZYNA. "
            "Omitted fields stay unchanged. Null clears nullable fields; "
            "blank strings clear text fields. Set id_klient to 0 to unassign "
            "the owner; null is invalid for non-nullable columns. "
            "Generated keys and derived fields cannot be changed. Returns "
            "404 if missing, 409 if the business ID matches multiple records. "
            "Requires api.allow_writes and the configured X-API-Key."
        ),
        dependencies=protected,
    )
    def update_machine(
        payload: MachineUpdate,
        id_maszyna: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_machine(
            id_maszyna, payload.model_dump(exclude_unset=True)
        )

    @router.get(
        "/orders",
        response_model=OrderPage,
        tags=["data"],
        summary="List service orders (jobs)",
        description=(
            "Returns a page of service orders from the ZLECENIE table, keyed "
            "by the lower-cased column names (id_zlecenie, nazwa, stan, "
            "marka, model, ...). ZLECENIE is the widest table of the schema, "
            "so the columns are a curated subset: Firebird caps a statement "
            "message at 64 KB, which a full-width SELECT or a LIKE over every "
            "text column would exceed. 'search' matches nazwa, adres, poczta, "
            "telefon, e_mail, stoi, marka, model, serial, ewidencja, "
            "rodzaj_us, uszkodzenie, problem, diagnoza, wykonanie, zalecenia, "
            "uwagi, technik, zglasza, stan, faktura and plik (case sensitive "
            "substring)."
        ),
        dependencies=protected,
    )
    def list_orders(
        limit: int | None = page_limit("Orders"),
        offset: int = Query(default=0, ge=0, description="Number of orders to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against nazwa, marka, uszkodzenie, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_orders(limit=limit, offset=offset, search=search)

    @router.get(
        "/invoices",
        response_model=InvoicePage,
        tags=["data"],
        summary="List invoices (sales documents)",
        description=(
            "Returns a page of invoice headers from the FAKTURA table, keyed "
            "by the lower-cased column names (id_faktura_table, numer, nazwa, "
            "suma_brutto, ...): document links, the contractor snapshot, "
            "type/number and corrections, sale/issue/due/paid dates, payment "
            "terms, issuer, PLN totals with paid and outstanding amounts and "
            "the foreign-currency totals. The positions live in FPOZYCJA and "
            "are not included. 'search' matches numer, nr_kory, korekta, "
            "nr_par, rodzaj_dok, ccode, nazwa, nip, adres, kod, poczta, "
            "platnosc, wystawil, miejsce_wyst, uwagi, zamowienie, doumowy and "
            "stan (case sensitive substring)."
        ),
        dependencies=protected,
    )
    def list_invoices(
        limit: int | None = page_limit("Invoices"),
        offset: int = Query(default=0, ge=0, description="Number of invoices to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against numer, nazwa, uwagi, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_invoices(limit=limit, offset=offset, search=search)

    @router.post(
        "/query",
        response_model=QueryResponse,
        tags=["data"],
        summary="Run a read-only SQL query",
        dependencies=protected,
    )
    def run_query(
        payload: QueryRequest,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.run_query(
            payload.sql, limit=payload.limit, parameters=payload.parameters
        )

    return router
