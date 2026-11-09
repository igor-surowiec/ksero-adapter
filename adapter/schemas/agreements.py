"""Agreements request and response models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..service.agreements import AGREEMENT_TEXT_LENGTHS, MAX_AGREEMENT_MACHINES
from .common import DecimalValue


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
    """A page of agreements returned by ``/cpc-agreements``."""

    total: int = Field(description="Total number of agreements matching 'search'")
    count: int = Field(description="Number of agreements in this page")
    limit: int
    offset: int
    agreements: list[Agreement]


class AgreementCreate(BaseModel):
    """Required machine list and optional details; client ID comes from the URL.

    The business ID is the lowest unused positive integer; Firebird generates
    the table key. Omitted fields receive the shared
    legacy profile or column defaults; unknown fields are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    machines: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(
        max_length=MAX_AGREEMENT_MACHINES,
        description="Required ID_MASZYNA list; [] creates an agreement without machines",
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

    machines: list[Annotated[int, Field(strict=True, ge=1, le=2147483647)]] = Field(
        default_factory=list, max_length=MAX_AGREEMENT_MACHINES,
        description="Complete ID_MASZYNA list; omitted preserves, empty clears links",
    )
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
