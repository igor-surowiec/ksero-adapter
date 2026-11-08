"""Pydantic models describing the HTTP API payloads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from .service import (
    AGREEMENT_TEXT_LENGTHS,
    CLIENT_TEXT_LENGTHS,
    CPC_TEXT_LENGTHS,
    MACHINE_TEXT_LENGTHS,
    MAX_AGREEMENT_MACHINES,
)

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
    """A contractor (client) stored in the ``KLIENT`` table.

    Fields are named after the database columns, lower-cased (``NAZWA`` ->
    ``nazwa``), so the payload needs no translation layer.
    """

    id_klient_table: int | None = Field(default=None, description="Surrogate key")
    id_klient: int | None = Field(default=None, description="Business identifier")
    nazwa: str | None = Field(default=None, description="Full contractor name")
    nazwa_s: str | None = Field(default=None, description="Short (invoice) name")
    nip: str | None = Field(default=None, description="Tax identifier")
    regon: str | None = Field(default=None, description="Statistical number")
    adres: str | None = Field(default=None, description="Street address")
    kod: str | None = Field(default=None, description="Postal code")
    poczta: str | None = Field(default=None, description="City")
    wojewodztwo: int | None = Field(
        default=None, description="Province dictionary id"
    )
    telefon: str | None = Field(default=None, description="Phone number")
    e_mail: str | None = Field(default=None, description="E-mail address")
    www: str | None = Field(default=None, description="Website")
    typ: str | None = Field(default=None, description="Client type")
    aktywny: str | None = Field(default=None, description="Raw active flag")
    platnosc: str | None = Field(default=None, description="Payment method")
    termin: int | None = Field(default=None, description="Payment term in days")
    rabat: int | None = Field(default=None, description="Discount")
    ostatnio: str | None = Field(
        default=None, description="ISO date of the last activity"
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

    Only ``nazwa`` is required: Firebird assigns the surrogate and business keys
    from their generators and the ``INS_KLIENT_RECORD`` trigger fills the ones
    the insert does not supply (``ID_ODDZIAL`` falls back to its column default),
    so every other field is optional.  Columns left out are filled with
    ``service.CLIENT_INSERT_DEFAULTS`` - the values the legacy application
    writes into a new contractor - rather than with ``NULL``, because the
    program does not list a client whose row keeps the raw Firebird defaults.
    The field names are the lower-cased column names of ``KLIENT``, exactly as
    ``GET /clients`` returns them, and an unknown field is refused instead of
    being dropped silently.
    """

    model_config = ConfigDict(extra="forbid")

    nazwa: str = Field(
        min_length=1,
        max_length=CLIENT_TEXT_LENGTHS["NAZWA"],
        description=(
            "Full contractor name, stored in KLIENT.NAZWA; surrounding "
            "whitespace is trimmed"
        ),
    )
    nazwa_s: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["NAZWA_S"],
        description="Short (invoice) name",
    )
    nip: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["NIP"],
        description="Tax identifier",
    )
    regon: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["REGON"],
        description="Statistical number",
    )
    adres: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["ADRES"],
        description="Street address",
    )
    kod: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["KOD"],
        description="Postal code",
    )
    poczta: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["POCZTA"],
        description="City",
    )
    wojewodztwo: int | None = Field(
        default=None, description="Province dictionary id"
    )
    telefon: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["TELEFON"],
        description="Phone number",
    )
    e_mail: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["E_MAIL"],
        description="E-mail address",
    )
    www: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["WWW"],
        description="Website",
    )
    typ: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["TYP"],
        description="Client type",
    )
    aktywny: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["AKTYWNY"],
        description="Raw active flag",
    )
    platnosc: str | None = Field(
        default=None,
        max_length=CLIENT_TEXT_LENGTHS["PLATNOSC"],
        description="Payment method",
    )
    termin: int | None = Field(default=None, description="Payment term in days")
    rabat: int | None = Field(default=None, description="Discount")


class ClientUpdate(ClientCreate):
    """Partial client update; omitted fields retain their stored values.

    Explicit null clears an optional field; empty strings clear text fields.
    A supplied name must be non-null and non-blank (checked by the service).
    """

    nazwa: str | None = Field(
        default=None,
        min_length=1,
        max_length=CLIENT_TEXT_LENGTHS["NAZWA"],
        description="Full contractor name; cannot be cleared",
    )


class Agreement(BaseModel):
    """A service agreement (contract) stored in the ``UMOWACPC`` table."""

    id_umowacpc_table: int | None = Field(default=None, description="Surrogate key")
    id_umowacpc: int | None = Field(default=None, description="Business identifier")
    id_oddzial: int | None = Field(default=None, description="Branch")
    id_klient: int | None = Field(default=None, description="Contractor")
    id_odbiorca: int | None = Field(default=None, description="Recipient")
    id_firma: int | None = Field(default=None, description="Company")
    umowa: str | None = Field(default=None, description="Agreement number")
    typ: str | None = Field(default=None, description="Agreement type")
    handlowiec: str | None = Field(default=None, description="Salesperson")
    opiekun: str | None = Field(default=None, description="Supervisor")
    opiekunmail: str | None = Field(default=None, description="Supervisor e-mail")
    opiekuntel: str | None = Field(default=None, description="Supervisor phone")
    u_start: str | None = Field(default=None, description="ISO start date")
    u_stop: str | None = Field(default=None, description="ISO end date")
    warunki: str | None = Field(default=None, description="Contract terms")
    uwagi: str | None = Field(default=None, description="Notes")
    koszty: DecimalValue | None = Field(default=None, description="Costs")
    przychody: DecimalValue | None = Field(default=None, description="Revenue")
    wynik: DecimalValue | None = Field(default=None, description="Profit")
    rabat: DecimalValue | None = Field(default=None, description="Discount")
    platnosc: str | None = Field(default=None, description="Payment method")
    termin: int | None = Field(default=None, description="Payment term in days")
    aktywna: str | None = Field(default=None, description="Raw active flag")
    strony_mono: int | None = Field(default=None, description="Mono pages")
    strony_kolor: int | None = Field(default=None, description="Colour pages")
    skany: int | None = Field(default=None, description="Scans")
    fraemail: str | None = Field(default=None, description="Invoice e-mail")
    plik: str | None = Field(default=None, description="Linked file")


class AgreementPage(BaseModel):
    """A page of agreements returned by ``/agreements``."""

    total: int = Field(description="Total number of agreements matching 'search'")
    count: int = Field(description="Number of agreements in this page")
    limit: int
    offset: int
    agreements: list[Agreement]


class AgreementCreate(BaseModel):
    """Optional agreement details; the client ID comes from the URL path.

    The business ID is the lowest unused positive integer; Firebird generates
    the table key. Omitted fields receive the shared
    legacy profile or column defaults; unknown fields are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    machines: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(
        default_factory=list, max_length=MAX_AGREEMENT_MACHINES,
        description="Complete ID_MASZYNA list; omitted preserves, empty clears links",
    )

    id_oddzial: int | None = Field(default=None, description="Branch")
    id_odbiorca: int | None = Field(default=None, description="Recipient")
    id_firma: int | None = Field(default=None, description="Company")
    umowa: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["UMOWA"],
        description="Agreement number; defaults to generated ID/current database year",
    )
    typ: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["TYP"],
        description="Agreement type",
    )
    handlowiec: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["HANDLOWIEC"],
        description="Salesperson",
    )
    opiekun: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["OPIEKUN"],
        description="Supervisor",
    )
    opiekunmail: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["OPIEKUNMAIL"],
        description="Supervisor e-mail",
    )
    opiekuntel: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["OPIEKUNTEL"],
        description="Supervisor phone",
    )
    warunki: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["WARUNKI"],
        description="Contract terms",
    )
    uwagi: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["UWAGI"],
        description="Notes",
    )
    platnosc: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["PLATNOSC"],
        description="Payment method; legacy default $_$",
    )
    aktywna: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["AKTYWNA"],
        description="Raw active flag; defaults to TAK",
    )
    fraemail: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["FRAEMAIL"],
        description="Invoice e-mail",
    )
    plik: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["PLIK"],
        description="Linked file",
    )
    u_start: date | None = Field(
        default=None, description="Start date; defaults to the database current date"
    )
    u_stop: date | None = Field(default=None, description="End date")
    rabat: Decimal | None = Field(default=None, description="Discount")
    termin: int | None = Field(default=None, description="Payment term in days")
    strony_mono: int | None = Field(default=None, description="Mono pages")
    strony_kolor: int | None = Field(default=None, description="Colour pages")
    skany: int | None = Field(default=None, description="Scans")


class AgreementUpdate(AgreementCreate):
    """Partial agreement details and optional replacement machine links.

    Omitted columns stay unchanged; defaults apply only to creation.
    """

    umowa: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["UMOWA"],
        description="Agreement number; omitted keeps current value",
    )
    id_klient: int | None = Field(default=None, ge=1, description="Contractor ID")
    u_start: date | None = Field(default=None, description="Start date; null clears")
    aktywna: str | None = Field(
        default=None, max_length=AGREEMENT_TEXT_LENGTHS["AKTYWNA"],
        description="Raw active flag; omitted keeps current value",
    )


class Machine(BaseModel):
    """A machine (installed device) stored in the ``MASZYNA`` table."""

    id_maszyna_table: int | None = Field(default=None, description="Surrogate key")
    id_maszyna: int | None = Field(default=None, description="Business identifier")
    id_klient: int | None = Field(default=None, description="Owner")
    id_oddzial: int | None = Field(default=None, description="Branch")
    id_firma: int | None = Field(default=None, description="Company")
    id_model: int | None = Field(default=None, description="Model dictionary")
    id_umowacpc: int | None = Field(default=None, description="Servicing agreement")
    marka: str | None = Field(default=None, description="Manufacturer")
    model: str | None = Field(default=None, description="Model name")
    grupa: str | None = Field(default=None, description="Device group")
    typ: str | None = Field(default=None, description="Device type")
    rodzaj_us: str | None = Field(default=None, description="Billing model")
    serial: str | None = Field(default=None, description="Serial number")
    serial2: str | None = Field(default=None, description="Secondary serial")
    ewidencja: str | None = Field(default=None, description="Asset record number")
    stoi: str | None = Field(default=None, description="Placement inside the site")
    adres: str | None = Field(default=None, description="Site address")
    miejscowosc: str | None = Field(default=None, description="Site city")
    email: str | None = Field(default=None, description="Notification e-mail")
    instalacja: str | None = Field(default=None, description="ISO installation date")
    gwarancja: int | None = Field(default=None, description="Warranty length in months")
    gwarancja_do: str | None = Field(default=None, description="ISO warranty end date")
    last_m: str | None = Field(
        default=None, description="ISO date of the last meter reading"
    )
    licznik: int | None = Field(default=None, description="Meter value")
    licznika3: int | None = Field(default=None, description="A3 meter")
    licznik_total: int | None = Field(default=None, description="Lifetime counter")
    bezlicz: int | None = Field(default=None, description="Raw 'no meter' flag")
    last_w: str | None = Field(
        default=None, description="ISO date of the last service"
    )
    next_w: str | None = Field(
        default=None, description="ISO date of the next service"
    )
    konserwacja: str | None = Field(
        default=None, description="ISO date of the next maintenance"
    )
    przeglady: int | None = Field(
        default=None, description="Number of performed services"
    )
    technik: str | None = Field(default=None, description="Technician")
    zalecenia: str | None = Field(
        default=None, description="Service recommendations"
    )
    uwagi: str | None = Field(default=None, description="Notes")
    oplata: DecimalValue | None = Field(default=None, description="Unit fee")
    koszty: DecimalValue | None = Field(default=None, description="Costs")
    przychody: DecimalValue | None = Field(default=None, description="Revenue")
    wynik: DecimalValue | None = Field(default=None, description="Profit")
    aktywna: str | None = Field(default=None, description="Raw active flag")
    kolorowa: str | None = Field(default=None, description="Raw colour flag")


class MachinePage(BaseModel):
    """A page of machines returned by ``/machines``."""

    total: int = Field(description="Total number of machines matching 'search'")
    count: int = Field(description="Number of machines in this page")
    limit: int
    offset: int
    machines: list[Machine]


class MachineCreate(BaseModel):
    """Payload of ``POST /machines``.

    All fields are optional. An omitted or null ``id_klient`` is stored as
    ``0`` (unassigned); the ``INS_MASZYNA_RECORD`` trigger assigns
    ``ID_MASZYNA_TABLE`` and ``ID_MASZYNA`` from their generators and
    the legacy row profile supplies branch/company/VAT/sync flags as 0,
    GRUPA=Druk, AKTYWNA=TAK, KOLOROWA=NIE, RODZAJ_US=Platne and empty text. Caller
    values override these defaults. Counters, dates and aggregates retain their
    database defaults. Field names are the
    lower-cased column names and unknown fields are rejected, because a machine
    has many similar columns and a typo would otherwise be dropped silently.
    """

    model_config = ConfigDict(extra="forbid")

    id_klient: int | None = Field(
        default=None, ge=0,
        description="Owner (KLIENT.ID_KLIENT); omitted, null or 0 means unassigned",
    )
    id_oddzial: int | None = Field(
        default=None, description="Branch (legacy insert default 0)"
    )
    id_firma: int | None = Field(default=None, description="Company (column default 0)")
    id_model: int | None = Field(default=None, description="Model dictionary id")
    id_umowacpc: int | None = Field(
        default=None, description="Servicing agreement (UMOWACPC)"
    )
    marka: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["MARKA"],
        description="Manufacturer",
    )
    model: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["MODEL"],
        description="Model name",
    )
    grupa: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["GRUPA"],
        description="Device group",
    )
    typ: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["TYP"],
        description="Device type",
    )
    rodzaj_us: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["RODZAJ_US"],
        description="Billing model, e.g. 'Płatne'",
    )
    serial: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["SERIAL"],
        description="Serial number",
    )
    serial2: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["SERIAL2"],
        description="Secondary serial",
    )
    ewidencja: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["EWIDENCJA"],
        description="Asset record number",
    )
    stoi: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["STOI"],
        description="Placement inside the site",
    )
    adres: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["ADRES"],
        description="Site address",
    )
    miejscowosc: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["MIEJSCOWOSC"],
        description="Site city",
    )
    email: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["EMAIL"],
        description="Notification e-mail",
    )
    technik: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["TECHNIK"],
        description="Technician",
    )
    instalacja: date | None = Field(default=None, description="Installation date")
    gwarancja: int | None = Field(default=None, description="Warranty in months")
    gwarancja_do: date | None = Field(default=None, description="Warranty end date")
    licznik: int | None = Field(default=None, description="Meter value")
    licznika3: int | None = Field(default=None, description="A3 meter")
    przeglady: int | None = Field(default=None, description="Services performed")
    konserwacja: date | None = Field(default=None, description="Next maintenance date")
    oplata: Decimal | None = Field(default=None, description="Unit fee")
    uwagi: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["UWAGI"],
        description="Notes",
    )
    zalecenia: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["ZALECENIA"],
        description="Service recommendations",
    )
    aktywna: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["AKTYWNA"],
        description="Raw active flag; legacy insert default TAK",
    )
    kolorowa: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["KOLOROWA"],
        description="Raw colour flag; legacy insert default NIE",
    )


class MachineUpdate(MachineCreate):
    """Partial machine update; omitted fields keep their stored values.

    Null clears nullable fields; id_klient=0 unassigns the owner. Non-nullable
    ownership/branch fields must have a value when supplied.
    """

    id_klient: int | None = Field(
        default=None, ge=0,
        description="Owner ID; 0 unassigns, null is rejected on update",
    )


class CpcValues(BaseModel):
    """Writable CPC readings, recorded charges and period details."""

    model_config = ConfigDict(extra="forbid")

    id_faktura: int | None = Field(default=None)
    licznik_mono_start: int | None = Field(default=None)
    licznik_monoa3_start: int | None = Field(default=None)
    licznik_kolor_start: int | None = Field(default=None)
    licznik_kolora3_start: int | None = Field(default=None)
    licznik_skan_start: int | None = Field(default=None)
    licznik_mono_end: int | None = Field(default=None)
    licznik_monoa3_end: int | None = Field(default=None)
    licznik_kolor_end: int | None = Field(default=None)
    licznik_kolora3_end: int | None = Field(default=None)
    licznik_skan_end: int | None = Field(default=None)
    kopie_mono: int | None = Field(default=None)
    kopie_kolor: int | None = Field(default=None)
    kopie_monoa3: int | None = Field(default=None)
    kopie_kolora3: int | None = Field(default=None)
    skany: int | None = Field(default=None)
    strony_mono_nw: int | None = Field(default=None)
    strony_kolor_nw: int | None = Field(default=None)
    strony_monoa3_nw: int | None = Field(default=None)
    strony_kolora3_nw: int | None = Field(default=None)
    skany_nw: int | None = Field(default=None)
    rok: int | None = Field(default=None, ge=1, le=9999)
    miesiac: int | None = Field(default=None, ge=1, le=12)
    idvat: int | None = Field(default=None, ge=0)
    oplata_min: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_stala: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    doplata: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_mono: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_kolor: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_monoa3: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_kolora3: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_skan: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_suma: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_vat: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    oplata_brutto: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    robocizna: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    dojazdy: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    czesci: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    materialy: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    koszty: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    koszty_stale: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    koszty_stale2: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    koszty_stale3: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    wynik: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    koszty_n: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    wynik_n: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    keuro: Decimal | None = Field(
        default=None, max_digits=10, decimal_places=4,
    )
    faktura: str | None = Field(
        default=None, max_length=CPC_TEXT_LENGTHS["FAKTURA"]
    )
    uwagi: str | None = Field(
        default=None, max_length=CPC_TEXT_LENGTHS["UWAGI"]
    )


class CpcCreate(CpcValues):
    """Create a settlement; omitted year/month use the database current date."""

    id_klient: int = Field(ge=1)
    id_maszyna: int = Field(ge=1)
    id_umowacpc: int = Field(ge=1)
    rok: int | None = Field(
        default=None, ge=1, le=9999, description="Defaults to current database year"
    )
    miesiac: int | None = Field(
        default=None, ge=1, le=12, description="Defaults to current database month"
    )


class CpcUpdate(CpcValues):
    """Partial settlement update; parent references cannot change."""


class Cpc(BaseModel):
    """A stored CPC settlement with lower-cased database column names."""

    id_cpc_table: int | None = None
    id_klient: int | None = None
    id_maszyna: int | None = None
    id_umowacpc: int | None = None
    id_faktura: int | None = None
    licznik_mono_start: int | None = None
    licznik_monoa3_start: int | None = None
    licznik_kolor_start: int | None = None
    licznik_kolora3_start: int | None = None
    licznik_skan_start: int | None = None
    licznik_mono_end: int | None = None
    licznik_monoa3_end: int | None = None
    licznik_kolor_end: int | None = None
    licznik_kolora3_end: int | None = None
    licznik_skan_end: int | None = None
    kopie_mono: int | None = None
    kopie_kolor: int | None = None
    kopie_monoa3: int | None = None
    kopie_kolora3: int | None = None
    skany: int | None = None
    strony_mono_nw: int | None = None
    strony_kolor_nw: int | None = None
    strony_monoa3_nw: int | None = None
    strony_kolora3_nw: int | None = None
    skany_nw: int | None = None
    rok: int | None = None
    miesiac: int | None = None
    idvat: int | None = None
    oplata_min: DecimalValue | None = None
    oplata_stala: DecimalValue | None = None
    doplata: DecimalValue | None = None
    oplata_mono: DecimalValue | None = None
    oplata_kolor: DecimalValue | None = None
    oplata_monoa3: DecimalValue | None = None
    oplata_kolora3: DecimalValue | None = None
    oplata_skan: DecimalValue | None = None
    oplata_suma: DecimalValue | None = None
    oplata_vat: DecimalValue | None = None
    oplata_brutto: DecimalValue | None = None
    robocizna: DecimalValue | None = None
    dojazdy: DecimalValue | None = None
    czesci: DecimalValue | None = None
    materialy: DecimalValue | None = None
    koszty: DecimalValue | None = None
    koszty_stale: DecimalValue | None = None
    koszty_stale2: DecimalValue | None = None
    koszty_stale3: DecimalValue | None = None
    wynik: DecimalValue | None = None
    koszty_n: DecimalValue | None = None
    wynik_n: DecimalValue | None = None
    keuro: DecimalValue | None = None
    faktura: str | None = None
    uwagi: str | None = None


class CpcPage(BaseModel):
    """A page of CPC settlement records."""

    total: int
    count: int
    limit: int
    offset: int
    cpc: list[Cpc]


class Order(BaseModel):
    """A service order (job) stored in the ``ZLECENIE`` table."""

    id_zlecenie_table: int | None = Field(default=None, description="Surrogate key")
    id_zlecenie: int | None = Field(default=None, description="Business identifier")
    rok: int | None = Field(default=None, description="Order year")
    stan: str | None = Field(default=None, description="Raw status code")
    id_firma: int | None = Field(default=None, description="Company")
    id_oddzial: int | None = Field(default=None, description="Branch")
    id_klient: int | None = Field(default=None, description="Contractor")
    id_maszyna: int | None = Field(default=None, description="Device")
    nazwa: str | None = Field(
        default=None, description="Client name copied onto the order"
    )
    adres: str | None = Field(default=None, description="Address")
    kod: str | None = Field(default=None, description="Postal code")
    poczta: str | None = Field(default=None, description="City")
    telefon: str | None = Field(default=None, description="Phone number")
    e_mail: str | None = Field(default=None, description="E-mail address")
    stoi: str | None = Field(default=None, description="Placement inside the site")
    marka: str | None = Field(default=None, description="Device brand")
    model: str | None = Field(default=None, description="Device model")
    serial: str | None = Field(default=None, description="Serial number")
    ewidencja: str | None = Field(default=None, description="Asset number")
    data: str | None = Field(
        default=None, description="ISO date the order was created"
    )
    termin: str | None = Field(default=None, description="ISO deadline")
    data_z: str | None = Field(default=None, description="ISO planned visit date")
    godzina_plan: str | None = Field(default=None, description="Planned visit time")
    data_przy: str | None = Field(
        default=None, description="ISO date the device was accepted"
    )
    data_wyda: str | None = Field(
        default=None, description="ISO date the device was released"
    )
    data_start: str | None = Field(default=None, description="ISO date work started")
    data_stop: str | None = Field(default=None, description="ISO date work finished")
    rodzaj_us: str | None = Field(default=None, description="Service type")
    uszkodzenie: str | None = Field(default=None, description="Reported damage")
    problem: str | None = Field(default=None, description="Reported problem")
    diagnoza: str | None = Field(default=None, description="Diagnosis")
    wykonanie: str | None = Field(default=None, description="Work performed")
    zalecenia: str | None = Field(
        default=None, description="Service recommendations"
    )
    uwagi: str | None = Field(default=None, description="Notes")
    technik: str | None = Field(default=None, description="Technician")
    zglasza: str | None = Field(
        default=None, description="Person who reported the fault"
    )
    operator: str | None = Field(
        default=None, description="Audit string of the author"
    )
    signwho: str | None = Field(default=None, description="Person accepting the job")
    signwhen: str | None = Field(
        default=None, description="ISO timestamp of the acceptance"
    )
    licznik: int | None = Field(default=None, description="Meter value")
    licznika3: int | None = Field(default=None, description="A3 meter")
    licznik_total: int | None = Field(default=None, description="Lifetime counter")
    robocizna: DecimalValue | None = Field(default=None, description="Labour cost")
    dojazd: DecimalValue | None = Field(default=None, description="Travel cost")
    czesci: DecimalValue | None = Field(default=None, description="Parts cost")
    materialy: DecimalValue | None = Field(default=None, description="Materials cost")
    netto: DecimalValue | None = Field(default=None, description="Net total")
    vat: DecimalValue | None = Field(default=None, description="VAT amount")
    brutto: DecimalValue | None = Field(default=None, description="Gross total")
    zaliczka: DecimalValue | None = Field(default=None, description="Prepayment")
    platnosc: str | None = Field(default=None, description="Payment method")
    faktura: str | None = Field(default=None, description="Linked invoice number")
    plik: str | None = Field(default=None, description="Linked document")


class OrderPage(BaseModel):
    """A page of service orders returned by ``/orders``."""

    total: int = Field(description="Total number of orders matching 'search'")
    count: int = Field(description="Number of orders in this page")
    limit: int
    offset: int
    orders: list[Order]


class Invoice(BaseModel):
    """An invoice (sales document header) stored in the ``FAKTURA`` table."""

    id_faktura_table: int | None = Field(default=None, description="Surrogate key")
    id_oddzial: int | None = Field(default=None, description="Branch")
    id_firma: int | None = Field(default=None, description="Company")
    id_magazyn: int | None = Field(default=None, description="Warehouse")
    id_klient: int | None = Field(default=None, description="Contractor")
    id_odbiorca: int | None = Field(default=None, description="Goods recipient")
    id_maszyna: int | None = Field(default=None, description="Device")
    id_zlecenie: int | None = Field(default=None, description="Linked service order")
    rok_zlecenia: int | None = Field(
        default=None, description="Year of the linked service order"
    )
    id_kosztorys: int | None = Field(default=None, description="Linked estimate")
    id_wz: int | None = Field(default=None, description="Linked goods issue document")
    id_umowa: int | None = Field(default=None, description="Linked contract")
    id_umowacpc: int | None = Field(
        default=None, description="Linked service agreement"
    )
    id_zamowienie: int | None = Field(default=None, description="Linked purchase order")
    id_paczka: int | None = Field(default=None, description="Linked parcel")
    id_account: int | None = Field(
        default=None, description="Bank account used for payment"
    )
    id_curr: int | None = Field(default=None, description="Currency dictionary entry")
    nazwa: str | None = Field(
        default=None, description="Contractor name copied onto the document"
    )
    adres: str | None = Field(default=None, description="Address")
    kod: str | None = Field(default=None, description="Postal code")
    poczta: str | None = Field(default=None, description="City")
    nip: str | None = Field(default=None, description="Tax identifier")
    kod_kraju: str | None = Field(default=None, description="Country code")
    rodzaj_dok: str | None = Field(
        default=None, description="Document kind, e.g. invoice or correction"
    )
    numer: str | None = Field(default=None, description="Document number")
    nr_kory: str | None = Field(
        default=None, description="Number of the corrected document"
    )
    korekta: str | None = Field(default=None, description="Correction number")
    nr_par: str | None = Field(default=None, description="Linked receipt number")
    ccode: str | None = Field(default=None, description="Currency code, e.g. PLN/EUR")
    miejsce_wyst: str | None = Field(default=None, description="Place of issue")
    wystawil: str | None = Field(default=None, description="Issued by")
    odebral: str | None = Field(default=None, description="Received by")
    data_sprz: str | None = Field(default=None, description="ISO date of sale")
    data_wyst: str | None = Field(default=None, description="ISO issue date")
    data_plat: str | None = Field(default=None, description="ISO due date")
    data_zapl: str | None = Field(default=None, description="ISO paid date")
    data_kory: str | None = Field(default=None, description="ISO correction date")
    data_zam: str | None = Field(
        default=None, description="ISO date of the linked order"
    )
    dni_plat: int | None = Field(default=None, description="Payment term in days")
    platnosc: str | None = Field(default=None, description="Payment method")
    wal_kurs: DecimalValue | None = Field(
        default=None, description="Foreign-currency rate"
    )
    suma_netto: DecimalValue | None = Field(default=None, description="Net total")
    suma_vat: DecimalValue | None = Field(default=None, description="VAT total")
    suma_brutto: DecimalValue | None = Field(default=None, description="Gross total")
    zaplacono: DecimalValue | None = Field(default=None, description="Amount paid")
    zaliczka: DecimalValue | None = Field(
        default=None, description="Prepayment deducted"
    )
    do_zaplaty: DecimalValue | None = Field(
        default=None, description="Outstanding amount"
    )
    pokor_netto: DecimalValue | None = Field(
        default=None, description="Net total after the correction"
    )
    pokor_vat: DecimalValue | None = Field(
        default=None, description="VAT total after the correction"
    )
    pokor_brutto: DecimalValue | None = Field(
        default=None, description="Gross total after the correction"
    )
    wal_netto: DecimalValue | None = Field(
        default=None, description="Net total in the foreign currency"
    )
    wal_vat: DecimalValue | None = Field(
        default=None, description="VAT total in the foreign currency"
    )
    wal_brutto: DecimalValue | None = Field(
        default=None, description="Gross total in the foreign currency"
    )
    wal_zaplacono: DecimalValue | None = Field(
        default=None, description="Amount paid in the foreign currency"
    )
    wal_do_zaplaty: DecimalValue | None = Field(
        default=None, description="Outstanding amount in the currency"
    )
    stan: str | None = Field(default=None, description="Raw status code")
    uwagi: str | None = Field(default=None, description="Notes")
    zamowienie: str | None = Field(default=None, description="Linked order number")
    doumowy: str | None = Field(default=None, description="Linked contract number")


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
