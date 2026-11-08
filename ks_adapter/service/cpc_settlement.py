"""Cpc settlement database operations and curated fields."""

from __future__ import annotations

from typing import Any, Mapping

from ..errors import (
    ColumnNotFound, DatabaseUnavailable, InvalidRequest, RecordConflict, RecordNotFound,
)
from ..sql import (
    build_delete,
    build_insert,
    build_update,
    ensure_read_only,
    quote_identifier,
)
from .base import BaseDatabaseService, _insert_plan
from .agreements import AGREEMENTS_TABLE


#: CPC settlement records, keyed only by the generated ID_CPC_TABLE.
CPC_TABLE = "CPC"

#: Explicit settlement projection; internal version bookkeeping is omitted.
CPC_COLUMNS: tuple[str, ...] = (
    "ID_CPC_TABLE",
    "ID_KLIENT",
    "ID_MASZYNA",
    "ID_UMOWACPC",
    "ID_FAKTURA",
    "LICZNIK_MONO_START",
    "LICZNIK_MONOA3_START",
    "LICZNIK_KOLOR_START",
    "LICZNIK_KOLORA3_START",
    "LICZNIK_SKAN_START",
    "LICZNIK_MONO_END",
    "LICZNIK_MONOA3_END",
    "LICZNIK_KOLOR_END",
    "LICZNIK_KOLORA3_END",
    "LICZNIK_SKAN_END",
    "KOPIE_MONO",
    "KOPIE_KOLOR",
    "KOPIE_MONOA3",
    "KOPIE_KOLORA3",
    "SKANY",
    "STRONY_MONO_NW",
    "STRONY_KOLOR_NW",
    "STRONY_MONOA3_NW",
    "STRONY_KOLORA3_NW",
    "SKANY_NW",
    "ROK",
    "MIESIAC",
    "IDVAT",
    "OPLATA_MIN",
    "OPLATA_STALA",
    "DOPLATA",
    "OPLATA_MONO",
    "OPLATA_KOLOR",
    "OPLATA_MONOA3",
    "OPLATA_KOLORA3",
    "OPLATA_SKAN",
    "OPLATA_SUMA",
    "OPLATA_VAT",
    "OPLATA_BRUTTO",
    "ROBOCIZNA",
    "DOJAZDY",
    "CZESCI",
    "MATERIALY",
    "KOSZTY",
    "KOSZTY_STALE",
    "KOSZTY_STALE2",
    "KOSZTY_STALE3",
    "WYNIK",
    "KOSZTY_N",
    "WYNIK_N",
    "KEURO",
    "FAKTURA",
    "UWAGI",
)

#: Writable settlement inputs; generated record keys remain read-only.
CPC_WRITE_COLUMNS = tuple(c for c in CPC_COLUMNS if c != "ID_CPC_TABLE")

#: Parent links cannot change: the legacy trigger only refreshes NEW parents.
CPC_UPDATE_COLUMNS = tuple(
    c for c in CPC_WRITE_COLUMNS if c not in {"ID_KLIENT", "ID_MASZYNA", "ID_UMOWACPC"}
)

#: Text widths from the CPC catalog, shared with payload validation.
CPC_TEXT_LENGTHS = {"FAKTURA": 50, "UWAGI": 500}

#: Empty and zero values shared by legacy CPC rows; other fields keep NULL.
CPC_INSERT_DEFAULTS: dict[str, Any] = {
    "LICZNIK_MONOA3_START": 0,
    "LICZNIK_KOLOR_START": 0,
    "LICZNIK_KOLORA3_START": 0,
    "LICZNIK_SKAN_START": 0,
    "IDVAT": 0,
    "OPLATA_MIN": 0,
    "OPLATA_STALA": 0,
    "OPLATA_MONO": 0,
    "OPLATA_KOLOR": 0,
    "OPLATA_MONOA3": 0,
    "OPLATA_KOLORA3": 0,
    "OPLATA_SKAN": 0,
    "OPLATA_SUMA": 0,
    "ROBOCIZNA": 0,
    "DOJAZDY": 0,
    "CZESCI": 0,
    "MATERIALY": 0,
    "KOSZTY": 0,
    "KOSZTY_STALE": 0,
    "KOSZTY_STALE2": 0,
    "WYNIK": 0,
    "KEURO": 0,
    "UWAGI": "",
}


class CpcSettlementService(BaseDatabaseService):
    """Cpc settlement operations sharing the database service state."""

    def fetch_cpc(
        self, *, limit: int | None = None, offset: int = 0,
        search: str | None = None, filters: str | None = None,
    ) -> dict[str, Any]:
        """Return settlement records with optional search and column filters."""
        page = self._projection_page(
            CPC_TABLE, CPC_COLUMNS, ("FAKTURA", "UWAGI"), limit=limit,
            offset=offset, search=search, order_columns=("ID_CPC_TABLE",),
            label="CPC", filters=filters,
        )
        page["cpc"] = page.pop("rows")
        return page

    def get_cpc(self, id_cpc_table: int) -> dict[str, Any]:
        """Return one settlement by its generated record key."""
        self._check_cpc_id(id_cpc_table)
        info = self.schema.get(CPC_TABLE)
        selected = [c for c in CPC_COLUMNS if c in info.column_map]
        key = info.column_map.get("ID_CPC_TABLE")
        if key is None:
            raise InvalidRequest("CPC table has no ID_CPC_TABLE key")
        names = ", ".join(quote_identifier(info.column_map[c]) for c in selected)
        statement = (
            f"SELECT {names} FROM {quote_identifier(info.name)} "
            f"WHERE {quote_identifier(key)} = ?"
        )
        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(ensure_read_only(statement), [id_cpc_table])
                row = cursor.fetchone()
            finally:
                cursor.close()
        if row is None:
            raise RecordNotFound(f"CPC record {id_cpc_table} not found")
        return self._serialize_row([c.lower() for c in selected], row)

    def create_cpc(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a settlement using the client stored on its agreement."""
        self._require_writes()
        prepared = self._prepared_write_values(
            values, CPC_WRITE_COLUMNS, CPC_TEXT_LENGTHS
        )
        for column in ("ID_MASZYNA", "ID_UMOWACPC"):
            value = prepared.get(column)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise InvalidRequest(f"'{column.lower()}' must be a positive integer")
        if "ID_KLIENT" in prepared:
            self._check_client_id(prepared["ID_KLIENT"])
        self._check_cpc_period(prepared)
        info = self.schema.get(CPC_TABLE)
        required = {"ID_CPC_TABLE", "ID_KLIENT", "ID_MASZYNA", "ID_UMOWACPC",
                    "ROK", "MIESIAC"}
        if not required <= info.column_map.keys():
            raise InvalidRequest("CPC table lacks required settlement columns")
        selected = [c for c in CPC_COLUMNS if c in info.column_map]
        agreement_info = self.schema.get(AGREEMENTS_TABLE)
        if not {"ID_UMOWACPC", "ID_KLIENT"} <= agreement_info.column_map.keys():
            raise InvalidRequest("Agreement table lacks client reference columns")
        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT FIRST 2 "
                    f"{quote_identifier(agreement_info.column_map['ID_KLIENT'])} "
                    f"FROM {quote_identifier(agreement_info.name)} "
                    f"WHERE {quote_identifier(agreement_info.column_map['ID_UMOWACPC'])} "
                    "= ?", [prepared["ID_UMOWACPC"]],
                )
                agreements = cursor.fetchall()
                if not agreements:
                    raise RecordNotFound(
                        f"Agreement {prepared['ID_UMOWACPC']} not found"
                    )
                if len(agreements) > 1:
                    raise RecordConflict(
                        f"Multiple agreements have ID {prepared['ID_UMOWACPC']}"
                    )
                owner = agreements[0][0]
                self._check_client_id(owner)
                if "ID_KLIENT" in prepared and prepared["ID_KLIENT"] != owner:
                    raise InvalidRequest("'id_klient' must match the agreement's client")
                prepared = {"ID_KLIENT": owner, **prepared}
                defaults = dict(CPC_INSERT_DEFAULTS)
                if "ROK" not in prepared or "MIESIAC" not in prepared:
                    cursor.execute("SELECT CURRENT_DATE FROM RDB$DATABASE")
                    today = cursor.fetchone()
                    if today is None or today[0] is None:
                        raise DatabaseUnavailable(
                            "Firebird did not return current date"
                        )
                    defaults.update(ROK=today[0].year, MIESIAC=today[0].month)
                columns, params = _insert_plan(prepared, defaults, info.column_map)
                statement = build_insert(info.name, columns, returning=selected)
                cursor.execute(statement, params)
                row = cursor.fetchone()
                if row is None:
                    raise DatabaseUnavailable("Firebird did not return the CPC record")
                return self._serialize_row([c.lower() for c in selected], row)
            finally:
                cursor.close()

    def update_cpc(
        self, id_cpc_table: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Patch settlement values while preserving parent links and omitted fields."""
        self._require_writes()
        self._check_cpc_id(id_cpc_table)
        prepared = self._prepared_write_values(
            values, CPC_UPDATE_COLUMNS, CPC_TEXT_LENGTHS, preserve_empty=True
        )
        if not prepared:
            raise InvalidRequest("Supply at least one CPC field to update")
        self._check_cpc_period(prepared)
        info = self.schema.get(CPC_TABLE)
        key = info.column_map.get("ID_CPC_TABLE")
        if key is None:
            raise InvalidRequest("CPC table has no ID_CPC_TABLE key")
        for column, value in prepared.items():
            if column not in info.column_map:
                raise ColumnNotFound(f"Column '{column}' does not exist")
            if value is None and not next(
                c.nullable for c in info.columns if c.name == info.column_map[column]
            ):
                raise InvalidRequest(f"'{column.lower()}' must not be null")
        selected = [c for c in CPC_COLUMNS if c in info.column_map]
        return self._write_row(
            info.name, selected,
            build_update(info.name, [info.column_map[c] for c in prepared],
                         key=key, returning=selected),
            [*prepared.values(), id_cpc_table],
            not_found=RecordNotFound(f"CPC record {id_cpc_table} not found"),
        )

    def delete_cpc(self, id_cpc_table: int) -> None:
        """Delete one settlement; database triggers refresh its parent totals."""
        self._require_writes()
        self._check_cpc_id(id_cpc_table)
        info = self.schema.get(CPC_TABLE)
        key = info.column_map.get("ID_CPC_TABLE")
        if key is None:
            raise InvalidRequest("CPC table has no ID_CPC_TABLE key")
        self._write_row(
            info.name, [key], build_delete(info.name, key=key), [id_cpc_table],
            not_found=RecordNotFound(f"CPC record {id_cpc_table} not found"),
        )

    @staticmethod
    def _check_cpc_id(value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidRequest("'id_cpc_table' must be a non-negative integer")

    @staticmethod
    def _check_cpc_period(values: Mapping[str, Any]) -> None:
        for column, maximum in (("ROK", 9999), ("MIESIAC", 12)):
            if column in values:
                value = values[column]
                if (not isinstance(value, int) or isinstance(value, bool)
                        or not 1 <= value <= maximum):
                    raise InvalidRequest(
                        f"'{column.lower()}' must be between 1 and {maximum}"
                    )
