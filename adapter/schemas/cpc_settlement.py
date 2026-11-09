"""Cpc settlement request and response models."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ..service.cpc_settlement import CPC_TEXT_LENGTHS
from .common import DecimalValue


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

    id_klient: int | None = Field(
        default=None, ge=1,
        description="Derived from the agreement; if supplied, must match its client ID",
    )
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
