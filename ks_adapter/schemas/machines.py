"""Machines request and response models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..service.machines import MACHINE_TEXT_LENGTHS
from .common import DecimalValue


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
    """Machine details for ``POST /machines/{id_klient}``; marka is required.

    The required positive client ID comes from the URL. An optional body owner
    must match it. The ``INS_MASZYNA_RECORD`` trigger assigns
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
        default=None, ge=1, strict=True,
        description="Optional body owner; if provided, must match the URL client ID",
    )
    id_oddzial: int | None = Field(
        default=None, description="Branch (legacy insert default 0)"
    )
    id_firma: int | None = Field(default=None, description="Company (column default 0)")
    id_model: int | None = Field(default=None, description="Model dictionary id")
    id_umowacpc: int | None = Field(
        default=None, description="Servicing agreement (UMOWACPC)"
    )
    marka: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(
        min_length=1,
        max_length=MACHINE_TEXT_LENGTHS["MARKA"],
        description="Required manufacturer; surrounding whitespace is trimmed",
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
    marka: str | None = Field(
        default=None,
        max_length=MACHINE_TEXT_LENGTHS["MARKA"],
        description="Manufacturer",
    )
