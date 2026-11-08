"""Orders request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import DecimalValue


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
