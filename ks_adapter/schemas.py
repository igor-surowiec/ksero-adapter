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


class ClientCreate(BaseModel):
    """Payload of ``POST /clients``.

    The name is the only value the caller has to supply: Firebird assigns the
    surrogate and business keys from their generators and the ``ID_FIRMA`` /
    ``ID_ODDZIAL`` defaults (or the ``INS_KLIENT_RECORD`` trigger), so no other
    column of ``KLIENT`` is required.
    """

    name: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Full contractor name, stored in KLIENT.NAZWA; surrounding "
            "whitespace is trimmed"
        ),
    )


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


class Machine(BaseModel):
    """A machine (installed device) stored in the ``MASZYNA`` table."""

    id: int | None = Field(
        default=None, description="Surrogate key (MASZYNA.ID_MASZYNA_TABLE)"
    )
    machine_id: int | None = Field(
        default=None, description="Business identifier (MASZYNA.ID_MASZYNA)"
    )
    client_id: int | None = Field(default=None, description="Owner (ID_KLIENT)")
    branch_id: int | None = Field(default=None, description="Branch (ID_ODDZIAL)")
    company_id: int | None = Field(default=None, description="Company (ID_FIRMA)")
    model_id: int | None = Field(
        default=None, description="Model dictionary (ID_MODEL)"
    )
    agreement_id: int | None = Field(
        default=None, description="Servicing agreement (ID_UMOWACPC)"
    )
    brand: str | None = Field(default=None, description="Manufacturer (MARKA)")
    model: str | None = Field(default=None, description="Model name (MODEL)")
    group: str | None = Field(default=None, description="Device group (GRUPA)")
    type: str | None = Field(default=None, description="Device type (TYP)")
    service_type: str | None = Field(
        default=None, description="Billing model (RODZAJ_US)"
    )
    serial: str | None = Field(default=None, description="Serial number (SERIAL)")
    serial_alt: str | None = Field(
        default=None, description="Secondary serial (SERIAL2)"
    )
    inventory_no: str | None = Field(
        default=None, description="Asset record number (EWIDENCJA)"
    )
    location: str | None = Field(
        default=None, description="Placement inside the site (STOI)"
    )
    address: str | None = Field(default=None, description="Site address (ADRES)")
    city: str | None = Field(default=None, description="Site city (MIEJSCOWOSC)")
    email: str | None = Field(
        default=None, description="Notification e-mail (EMAIL)"
    )
    install_date: str | None = Field(
        default=None, description="ISO installation date (INSTALACJA)"
    )
    warranty_months: int | None = Field(
        default=None, description="Warranty length in months (GWARANCJA)"
    )
    warranty_until: str | None = Field(
        default=None, description="ISO warranty end date (GWARANCJA_DO)"
    )
    last_reading_date: str | None = Field(
        default=None, description="ISO date of the last meter reading (LAST_M)"
    )
    counter: int | None = Field(default=None, description="Meter value (LICZNIK)")
    counter_a3: int | None = Field(default=None, description="A3 meter (LICZNIKA3)")
    counter_total: int | None = Field(
        default=None, description="Lifetime counter (LICZNIK_TOTAL)"
    )
    meterless: int | None = Field(
        default=None, description="Raw 'no meter' flag (BEZLICZ)"
    )
    last_service_date: str | None = Field(
        default=None, description="ISO date of the last service (LAST_W)"
    )
    next_service_date: str | None = Field(
        default=None, description="ISO date of the next service (NEXT_W)"
    )
    maintenance_date: str | None = Field(
        default=None, description="ISO date of the next maintenance (KONSERWACJA)"
    )
    service_count: int | None = Field(
        default=None, description="Number of performed services (PRZEGLADY)"
    )
    technician: str | None = Field(default=None, description="Technician (TECHNIK)")
    recommendations: str | None = Field(
        default=None, description="Service recommendations (ZALECENIA)"
    )
    notes: str | None = Field(default=None, description="Notes (UWAGI)")
    fee: DecimalValue | None = Field(default=None, description="Unit fee (OPLATA)")
    costs: DecimalValue | None = Field(default=None, description="KOSZTY")
    revenue: DecimalValue | None = Field(default=None, description="PRZYCHODY")
    profit: DecimalValue | None = Field(default=None, description="WYNIK")
    active: str | None = Field(default=None, description="Raw AKTYWNA flag")
    color: str | None = Field(default=None, description="Raw KOLOROWA flag")


class MachinePage(BaseModel):
    """A page of machines returned by ``/machines``."""

    total: int = Field(description="Total number of machines matching 'search'")
    count: int = Field(description="Number of machines in this page")
    limit: int
    offset: int
    machines: list[Machine]


class Order(BaseModel):
    """A service order (job) stored in the ``ZLECENIE`` table."""

    id: int | None = Field(
        default=None, description="Surrogate key (ZLECENIE.ID_ZLECENIE_TABLE)"
    )
    order_id: int | None = Field(
        default=None, description="Business identifier (ZLECENIE.ID_ZLECENIE)"
    )
    year: int | None = Field(default=None, description="Order year (ROK)")
    status: str | None = Field(default=None, description="Raw status code (STAN)")
    company_id: int | None = Field(default=None, description="Company (ID_FIRMA)")
    branch_id: int | None = Field(default=None, description="Branch (ID_ODDZIAL)")
    client_id: int | None = Field(default=None, description="Contractor (ID_KLIENT)")
    machine_id: int | None = Field(default=None, description="Device (ID_MASZYNA)")
    client_name: str | None = Field(
        default=None, description="Client name copied onto the order (NAZWA)"
    )
    address: str | None = Field(default=None, description="ADRES")
    postcode: str | None = Field(default=None, description="KOD")
    city: str | None = Field(default=None, description="POCZTA")
    phone: str | None = Field(default=None, description="TELEFON")
    email: str | None = Field(default=None, description="E_MAIL")
    location: str | None = Field(
        default=None, description="Placement inside the site (STOI)"
    )
    brand: str | None = Field(default=None, description="Device brand (MARKA)")
    model: str | None = Field(default=None, description="Device model (MODEL)")
    serial: str | None = Field(default=None, description="Serial number (SERIAL)")
    inventory_no: str | None = Field(
        default=None, description="Asset number (EWIDENCJA)"
    )
    order_date: str | None = Field(
        default=None, description="ISO date the order was created (DATA)"
    )
    due_date: str | None = Field(
        default=None, description="ISO deadline (TERMIN)"
    )
    scheduled_date: str | None = Field(
        default=None, description="ISO planned visit date (DATA_Z)"
    )
    planned_time: str | None = Field(
        default=None, description="Planned visit time (GODZINA_PLAN)"
    )
    accepted_on: str | None = Field(
        default=None, description="ISO date the device was accepted (DATA_PRZY)"
    )
    issued_on: str | None = Field(
        default=None, description="ISO date the device was released (DATA_WYDA)"
    )
    started_on: str | None = Field(
        default=None, description="ISO date work started (DATA_START)"
    )
    finished_on: str | None = Field(
        default=None, description="ISO date work finished (DATA_STOP)"
    )
    service_type: str | None = Field(
        default=None, description="Service type (RODZAJ_US)"
    )
    damage: str | None = Field(default=None, description="Reported damage (USZKODZENIE)")
    problem: str | None = Field(
        default=None, description="Reported problem (PROBLEM)"
    )
    diagnosis: str | None = Field(default=None, description="Diagnosis (DIAGNOZA)")
    work_done: str | None = Field(
        default=None, description="Work performed (WYKONANIE)"
    )
    recommendations: str | None = Field(
        default=None, description="Service recommendations (ZALECENIA)"
    )
    notes: str | None = Field(default=None, description="Notes (UWAGI)")
    technician: str | None = Field(default=None, description="Technician (TECHNIK)")
    reported_by: str | None = Field(
        default=None, description="Person who reported the fault (ZGLASZA)"
    )
    operator: str | None = Field(
        default=None, description="Audit string of the author (OPERATOR)"
    )
    signed_by: str | None = Field(
        default=None, description="Person accepting the job (SIGNWHO)"
    )
    signed_at: str | None = Field(
        default=None, description="ISO timestamp of the acceptance (SIGNWHEN)"
    )
    counter: int | None = Field(default=None, description="Meter value (LICZNIK)")
    counter_a3: int | None = Field(default=None, description="A3 meter (LICZNIKA3)")
    counter_total: int | None = Field(
        default=None, description="Lifetime counter (LICZNIK_TOTAL)"
    )
    labour: DecimalValue | None = Field(
        default=None, description="Labour cost (ROBOCIZNA)"
    )
    travel: DecimalValue | None = Field(default=None, description="Travel cost (DOJAZD)")
    parts: DecimalValue | None = Field(default=None, description="Parts cost (CZESCI)")
    materials: DecimalValue | None = Field(
        default=None, description="Materials cost (MATERIALY)"
    )
    net: DecimalValue | None = Field(default=None, description="Net total (NETTO)")
    vat: DecimalValue | None = Field(default=None, description="VAT amount (VAT)")
    gross: DecimalValue | None = Field(default=None, description="Gross total (BRUTTO)")
    prepayment: DecimalValue | None = Field(
        default=None, description="Prepayment (ZALICZKA)"
    )
    payment_method: str | None = Field(
        default=None, description="Payment method (PLATNOSC)"
    )
    invoice_number: str | None = Field(
        default=None, description="Linked invoice number (FAKTURA)"
    )
    file: str | None = Field(default=None, description="Linked document (PLIK)")


class OrderPage(BaseModel):
    """A page of service orders returned by ``/orders``."""

    total: int = Field(description="Total number of orders matching 'search'")
    count: int = Field(description="Number of orders in this page")
    limit: int
    offset: int
    orders: list[Order]


class Invoice(BaseModel):
    """An invoice (sales document header) stored in the ``FAKTURA`` table."""

    id: int | None = Field(
        default=None, description="Surrogate key (FAKTURA.ID_FAKTURA_TABLE)"
    )
    branch_id: int | None = Field(default=None, description="Branch (ID_ODDZIAL)")
    company_id: int | None = Field(default=None, description="Company (ID_FIRMA)")
    warehouse_id: int | None = Field(default=None, description="Warehouse (ID_MAGAZYN)")
    client_id: int | None = Field(default=None, description="Contractor (ID_KLIENT)")
    recipient_id: int | None = Field(
        default=None, description="Goods recipient (ID_ODBIORCA)"
    )
    machine_id: int | None = Field(default=None, description="Device (ID_MASZYNA)")
    service_order_id: int | None = Field(
        default=None, description="Linked service order (ID_ZLECENIE)"
    )
    service_order_year: int | None = Field(
        default=None, description="Year of the linked service order (ROK_ZLECENIA)"
    )
    estimate_id: int | None = Field(
        default=None, description="Linked estimate (ID_KOSZTORYS)"
    )
    wz_id: int | None = Field(
        default=None, description="Linked goods issue document (ID_WZ)"
    )
    contract_id: int | None = Field(
        default=None, description="Linked contract (ID_UMOWA)"
    )
    agreement_id: int | None = Field(
        default=None, description="Linked service agreement (ID_UMOWACPC)"
    )
    purchase_order_id: int | None = Field(
        default=None, description="Linked purchase order (ID_ZAMOWIENIE)"
    )
    parcel_id: int | None = Field(default=None, description="Linked parcel (ID_PACZKA)")
    account_id: int | None = Field(
        default=None, description="Bank account used for payment (ID_ACCOUNT)"
    )
    currency_id: int | None = Field(
        default=None, description="Currency dictionary entry (ID_CURR)"
    )
    client_name: str | None = Field(
        default=None, description="Contractor name copied onto the document (NAZWA)"
    )
    address: str | None = Field(default=None, description="ADRES")
    postcode: str | None = Field(default=None, description="KOD")
    city: str | None = Field(default=None, description="POCZTA")
    nip: str | None = Field(default=None, description="Tax identifier (NIP)")
    country_code: str | None = Field(default=None, description="KOD_KRAJU")
    document_type: str | None = Field(
        default=None,
        description="Document kind, e.g. invoice or correction (RODZAJ_DOK)",
    )
    number: str | None = Field(default=None, description="Document number (NUMER)")
    corrected_number: str | None = Field(
        default=None, description="Number of the corrected document (NR_KORY)"
    )
    correction_number: str | None = Field(
        default=None, description="Correction document number (KOREKTA)"
    )
    receipt_number: str | None = Field(
        default=None, description="Linked receipt number (NR_PAR)"
    )
    currency_code: str | None = Field(
        default=None, description="Currency code, e.g. PLN/EUR (CCODE)"
    )
    issue_place: str | None = Field(
        default=None, description="Place of issue (MIEJSCE_WYST)"
    )
    issued_by: str | None = Field(default=None, description="Issued by (WYSTAWIL)")
    received_by: str | None = Field(default=None, description="Received by (ODEBRAL)")
    sale_date: str | None = Field(
        default=None, description="ISO date of sale (DATA_SPRZ)"
    )
    issue_date: str | None = Field(
        default=None, description="ISO issue date (DATA_WYST)"
    )
    due_date: str | None = Field(default=None, description="ISO due date (DATA_PLAT)")
    paid_date: str | None = Field(default=None, description="ISO paid date (DATA_ZAPL)")
    correction_date: str | None = Field(
        default=None, description="ISO correction date (DATA_KORY)"
    )
    purchase_order_date: str | None = Field(
        default=None, description="ISO date of the linked order (DATA_ZAM)"
    )
    payment_days: int | None = Field(
        default=None, description="Payment term in days (DNI_PLAT)"
    )
    payment_method: str | None = Field(
        default=None, description="Payment method (PLATNOSC)"
    )
    exchange_rate: DecimalValue | None = Field(
        default=None, description="Foreign-currency rate (WAL_KURS)"
    )
    net: DecimalValue | None = Field(default=None, description="Net total (SUMA_NETTO)")
    vat: DecimalValue | None = Field(default=None, description="VAT total (SUMA_VAT)")
    gross: DecimalValue | None = Field(
        default=None, description="Gross total (SUMA_BRUTTO)"
    )
    paid: DecimalValue | None = Field(
        default=None, description="Amount paid (ZAPLACONO)"
    )
    prepayment: DecimalValue | None = Field(
        default=None, description="Prepayment deducted (ZALICZKA)"
    )
    amount_due: DecimalValue | None = Field(
        default=None, description="Outstanding amount (DO_ZAPLATY)"
    )
    corrected_net: DecimalValue | None = Field(
        default=None, description="Net total after the correction (POKOR_NETTO)"
    )
    corrected_vat: DecimalValue | None = Field(
        default=None, description="VAT total after the correction (POKOR_VAT)"
    )
    corrected_gross: DecimalValue | None = Field(
        default=None, description="Gross total after the correction (POKOR_BRUTTO)"
    )
    net_currency: DecimalValue | None = Field(
        default=None, description="Net total in the foreign currency (WAL_NETTO)"
    )
    vat_currency: DecimalValue | None = Field(
        default=None, description="VAT total in the foreign currency (WAL_VAT)"
    )
    gross_currency: DecimalValue | None = Field(
        default=None, description="Gross total in the foreign currency (WAL_BRUTTO)"
    )
    paid_currency: DecimalValue | None = Field(
        default=None, description="Amount paid in the foreign currency (WAL_ZAPLACONO)"
    )
    amount_due_currency: DecimalValue | None = Field(
        default=None, description="Outstanding amount in the currency (WAL_DO_ZAPLATY)"
    )
    status: str | None = Field(default=None, description="Raw status code (STAN)")
    notes: str | None = Field(default=None, description="Notes (UWAGI)")
    purchase_order_number: str | None = Field(
        default=None, description="Linked order number (ZAMOWIENIE)"
    )
    contract_number: str | None = Field(
        default=None, description="Linked contract number (DOUMOWY)"
    )


class InvoicePage(BaseModel):
    """A page of invoices returned by ``/invoices``."""

    total: int = Field(description="Total number of invoices matching 'search'")
    count: int = Field(description="Number of invoices in this page")
    limit: int
    offset: int
    invoices: list[Invoice]


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
