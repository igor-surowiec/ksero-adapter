"""Clients request and response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..service.clients import CLIENT_TEXT_LENGTHS


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
