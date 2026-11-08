"""Invoices request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import DecimalValue


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
