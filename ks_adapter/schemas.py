"""Pydantic models describing the HTTP API payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

#: ``NUMERIC``/``DECIMAL`` columns are serialised as floats, or as strings when
#: ``api.decimal_as_string`` is enabled (see ``serialization.to_jsonable``), so
#: both variants have to be accepted by the response models.
DecimalValue = float | str


class ColumnModel(BaseModel):
    """A column of a table or view."""

    name: str
    position: int
    type: str = Field(description="Firebird SQL type, e.g. VARCHAR(50) or NUMERIC(15,2)")
    nullable: bool
    default: str | None = None
    charset: str | None = None
    length: int | None = Field(default=None, description="Length in bytes")
    precision: int | None = None
    scale: int | None = None


class TableSummary(BaseModel):
    """Short description of a table or view."""

    name: str
    kind: str = Field(description="Either 'table' or 'view'")
    column_count: int
    description: str | None = None


class TableListResponse(BaseModel):
    count: int
    tables: list[TableSummary]


class TableDetail(TableSummary):
    columns: list[ColumnModel] = Field(default_factory=list)


class RowPage(BaseModel):
    """A page of rows returned by ``/tables/{table}/rows``."""

    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    total: int = Field(description="Total number of rows matching the filters")
    limit: int
    offset: int


class Client(BaseModel):
    """A contractor (client) stored in the ``KLIENT`` table."""

    id: int | None = Field(
        default=None, description="Surrogate key (KLIENT.ID_KLIENT_TABLE)"
    )
    client_id: int | None = Field(
        default=None, description="Business identifier (KLIENT.ID_KLIENT)"
    )
    name: str | None = Field(default=None, description="Full name (NAZWA)")
    short_name: str | None = Field(default=None, description="Short name (NAZWA_S)")
    nip: str | None = None
    regon: str | None = None
    address: str | None = None
    postcode: str | None = None
    city: str | None = None
    province: int | None = Field(
        default=None, description="Province dictionary id (WOJEWODZTWO)"
    )
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    type: str | None = Field(default=None, description="Client type (TYP)")
    active: str | None = Field(default=None, description="Raw AKTYWNY flag")
    payment_method: str | None = Field(default=None, description="PLATNOSC")
    payment_days: int | None = Field(
        default=None, description="Payment term in days (TERMIN)"
    )
    discount: int | None = Field(default=None, description="Discount (RABAT)")
    last_contact: str | None = Field(
        default=None, description="ISO date of the last activity (OSTATNIO)"
    )


class ClientPage(BaseModel):
    """A page of clients returned by ``/clients``."""

    total: int = Field(description="Total number of clients matching 'search'")
    count: int = Field(description="Number of clients in this page")
    limit: int
    offset: int
    clients: list[Client]


class Agreement(BaseModel):
    """A service agreement (contract) stored in the ``UMOWACPC`` table."""

    id: int | None = Field(
        default=None, description="Surrogate key (UMOWACPC.ID_UMOWACPC_TABLE)"
    )
    agreement_id: int | None = Field(
        default=None, description="Business identifier (UMOWACPC.ID_UMOWACPC)"
    )
    branch_id: int | None = Field(default=None, description="Branch (ID_ODDZIAL)")
    client_id: int | None = Field(default=None, description="Client (ID_KLIENT)")
    recipient_id: int | None = Field(
        default=None, description="Recipient (ID_ODBIORCA)"
    )
    company_id: int | None = Field(default=None, description="Company (ID_FIRMA)")
    number: str | None = Field(default=None, description="Agreement number (UMOWA)")
    type: str | None = Field(default=None, description="Agreement type (TYP)")
    salesperson: str | None = Field(default=None, description="HANDLOWIEC")
    supervisor: str | None = Field(default=None, description="OPIEKUN")
    supervisor_email: str | None = Field(default=None, description="OPIEKUNMAIL")
    supervisor_phone: str | None = Field(default=None, description="OPIEKUNTEL")
    start_date: str | None = Field(
        default=None, description="ISO start date (U_START)"
    )
    end_date: str | None = Field(default=None, description="ISO end date (U_STOP)")
    terms: str | None = Field(default=None, description="Contract terms (WARUNKI)")
    notes: str | None = Field(default=None, description="Notes (UWAGI)")
    costs: DecimalValue | None = Field(default=None, description="KOSZTY")
    revenue: DecimalValue | None = Field(default=None, description="PRZYCHODY")
    profit: DecimalValue | None = Field(default=None, description="WYNIK")
    discount: DecimalValue | None = Field(default=None, description="RABAT")
    payment_method: str | None = Field(default=None, description="PLATNOSC")
    payment_days: int | None = Field(
        default=None, description="Payment term in days (TERMIN)"
    )
    active: str | None = Field(default=None, description="Raw AKTYWNA flag")
    pages_mono: int | None = Field(default=None, description="STRONY_MONO")
    pages_color: int | None = Field(default=None, description="STRONY_KOLOR")
    scans: int | None = Field(default=None, description="SKANY")
    invoice_email: str | None = Field(default=None, description="FRAEMAIL")
    file: str | None = Field(default=None, description="Linked file (PLIK)")


class AgreementPage(BaseModel):
    """A page of agreements returned by ``/agreements``."""

    total: int = Field(description="Total number of agreements matching 'search'")
    count: int = Field(description="Number of agreements in this page")
    limit: int
    offset: int
    agreements: list[Agreement]


class QueryRequest(BaseModel):
    sql: str = Field(
        min_length=1,
        description="A single read-only SELECT or WITH statement",
        examples=["SELECT FIRST 10 * FROM APPUSER"],
    )
    limit: int | None = Field(
        default=None, ge=1, description="Maximum number of rows to return"
    )
    parameters: list[Any] | None = Field(
        default=None, description="Optional positional parameters for '?' placeholders"
    )


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = Field(description="True when more rows matched than 'limit'")


class DatabaseInfo(BaseModel):
    dsn: str
    charset: str
    server_version: str


class PoolInfo(BaseModel):
    created: int
    idle: int
    capacity: int


class HealthResponse(BaseModel):
    status: str
    database: DatabaseInfo
    pool: PoolInfo
    latency_ms: float


class SchemaRefreshResponse(BaseModel):
    refreshed: bool
    table_count: int


class ServiceInfo(BaseModel):
    name: str
    version: str
    api_prefix: str
    docs_url: str


class ErrorResponse(BaseModel):
    detail: str
    error: str = Field(description="Exception class name")
