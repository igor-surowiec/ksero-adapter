"""Machines database operations and curated fields."""

from __future__ import annotations

from typing import Any, Mapping

from ..errors import (
    ColumnNotFound, DatabaseUnavailable, InvalidRequest, RecordConflict, RecordNotFound,
)
from ..sql import build_insert, build_update, quote_identifier
from .base import BaseDatabaseService, _insert_plan
from .clients import CLIENTS_TABLE


#: Table holding machines (installed devices) in the BAZAMS schema.
MACHINES_TABLE = "MASZYNA"

#: Columns exposed by ``GET /machines`` (keys: lower-cased column names).
MACHINE_COLUMNS: tuple[str, ...] = (
    "ID_MASZYNA_TABLE",
    "ID_MASZYNA",
    "ID_KLIENT",
    "ID_ODDZIAL",
    "ID_FIRMA",
    "ID_MODEL",
    "ID_UMOWACPC",
    "MARKA",
    "MODEL",
    "GRUPA",
    "TYP",
    "RODZAJ_US",
    "SERIAL",
    "SERIAL2",
    "EWIDENCJA",
    "STOI",
    "ADRES",
    "MIEJSCOWOSC",
    "EMAIL",
    "INSTALACJA",
    "GWARANCJA",
    "GWARANCJA_DO",
    "LAST_M",
    "LICZNIK",
    "LICZNIKA3",
    "LICZNIK_TOTAL",
    "BEZLICZ",
    "LAST_W",
    "NEXT_W",
    "KONSERWACJA",
    "PRZEGLADY",
    "TECHNIK",
    "ZALECENIA",
    "UWAGI",
    "OPLATA",
    "KOSZTY",
    "PRZYCHODY",
    "WYNIK",
    "AKTYWNA",
    "KOLOROWA",
)

#: Columns matched by the ``search`` parameter of ``GET /machines``.
MACHINE_SEARCH_COLUMNS: tuple[str, ...] = (
    "MARKA",
    "MODEL",
    "GRUPA",
    "TYP",
    "RODZAJ_US",
    "SERIAL",
    "SERIAL2",
    "EWIDENCJA",
    "MIEJSCOWOSC",
    "TECHNIK",
)

#: Columns ``POST /machines/{id_klient}`` accepts, in insertion order. Every
#: one of them is part of :data:`MACHINE_COLUMNS` as well, so the created row is
#: served exactly as ``GET /machines`` would return it.  The columns the
#: application derives from other data stay out of reach: ``LICZNIK_TOTAL`` (the
#: lifetime counter), ``LAST_M``/``LAST_W``/``NEXT_W`` (meter readings and
#: service orders), the ``KOSZTY``/``PRZYCHODY``/``WYNIK`` aggregates and the
#: ``SYNWP`` synchronisation flag.
MACHINE_WRITE_COLUMNS: tuple[str, ...] = (
    "ID_KLIENT",
    "ID_ODDZIAL",
    "ID_FIRMA",
    "ID_MODEL",
    "ID_UMOWACPC",
    "MARKA",
    "MODEL",
    "GRUPA",
    "TYP",
    "RODZAJ_US",
    "SERIAL",
    "SERIAL2",
    "EWIDENCJA",
    "STOI",
    "ADRES",
    "MIEJSCOWOSC",
    "EMAIL",
    "TECHNIK",
    "INSTALACJA",
    "GWARANCJA",
    "GWARANCJA_DO",
    "LICZNIK",
    "LICZNIKA3",
    "PRZEGLADY",
    "KONSERWACJA",
    "OPLATA",
    "UWAGI",
    "ZALECENIA",
    "AKTYWNA",
    "KOLOROWA",
)

#: Row profile of newly entered legacy machines. The active/billing/colour flags
#: and empty strings are application defaults that Firebird does not supply.
#: Recent native rows use branch 0 despite the column default of 1. Preserve
#: NULL counters, dates, optional links and aggregates; never copy device data.
MACHINE_INSERT_DEFAULTS: dict[str, Any] = {
    "ID_ODDZIAL": 0,
    "ID_FIRMA": 0,
    "IDVAT": 0,
    "AKTYWNA": "TAK",
    "KOLOROWA": "NIE",
    "RODZAJ_US": "P\u0142atne",
    "SYNWP": 0,
    "MARKA": "",
    "MODEL": "",
    "GRUPA": "Druk",
    "SERIAL": "",
    "EWIDENCJA": "",
    "MKOD": "",
    "OPCJE": "",
    "STOI": "",
    "ADRES": "",
    "MIEJSCOWOSC": "",
    "EMAIL": "",
    "ZALECENIA": "",
    "UWAGI": "",
    "TYP": "",
    "TECHNIK": "",
    "DETAL20": "",
}

#: Widths of the ``MASZYNA`` text columns.  Longer values are rejected up front,
#: otherwise Firebird answers with a string-truncation error instead of a clear
#: message. The machine-create payload model reuses this mapping, so every
#: limit is declared in one place.
MACHINE_TEXT_LENGTHS: dict[str, int] = {
    "MARKA": 100,
    "MODEL": 100,
    "GRUPA": 50,
    "TYP": 50,
    "RODZAJ_US": 50,
    "SERIAL": 100,
    "SERIAL2": 200,
    "EWIDENCJA": 100,
    "STOI": 1000,
    "ADRES": 250,
    "MIEJSCOWOSC": 150,
    "EMAIL": 150,
    "TECHNIK": 100,
    "UWAGI": 2000,
    "ZALECENIA": 2000,
    "AKTYWNA": 3,
    "KOLOROWA": 3,
}


class MachinesService(BaseDatabaseService):
    """Machines operations sharing the database service state."""

    def fetch_machines(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of machines (installed devices) from ``MASZYNA``.

        The third curated projection (:data:`MACHINE_COLUMNS`) of a wide
        physical table: the generic ``DETAL*`` slots, the per-copy price
        matrix (``KOPIA_*``, ``A3_*``, ``WYDRUK_*``, ``SKAN_*``, ``TRYB_*``,
        ``TK``/``TC``/``TM``/``TY``), the ``KOSZTY_STALE*`` variants and the
        ``FAV*``/``V_2010A``/``SYNWP`` bookkeeping columns stay out of the
        payload unless the endpoint is extended explicitly.
        """
        page = self._projection_page(
            MACHINES_TABLE,
            MACHINE_COLUMNS,
            MACHINE_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("ID_MASZYNA", "ID_MASZYNA_TABLE"),
            label="machine",
        )
        page["machines"] = page.pop("rows")
        return page

    def create_machine(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a machine into ``MASZYNA`` and return the stored row.

        ``values`` is keyed by the lower-cased column names of the curated
        projection (``{"id_klient": 7, "marka": "KONICA"}``); only the fields of
        :data:`MACHINE_WRITE_COLUMNS` are accepted and only the ones the caller
        supplies override :data:`MACHINE_INSERT_DEFAULTS`, the legacy row profile.
        ``ID_KLIENT`` must identify an existing client. The
        ``BEFORE INSERT`` trigger ``INS_MASZYNA_RECORD`` fills
        ``ID_MASZYNA_TABLE`` and ``ID_MASZYNA`` from their generators,
        branch/company/VAT and synchronisation flags are explicitly zeroed,
        so nothing is queued for synchronisation.
        ``RETURNING`` hands the generated keys back inside the same transaction
        and the response is the projection ``GET /machines`` serves.

        Raises :class:`errors.WritesDisabled` when ``api.allow_writes`` is off.
        """
        self._require_writes()
        prepared = self._prepared_write_values(
            values, MACHINE_WRITE_COLUMNS, MACHINE_TEXT_LENGTHS
        )
        owner = prepared.get("ID_KLIENT")
        self._check_client_id(owner)
        if not isinstance(prepared.get("MARKA"), str) or not prepared["MARKA"]:
            raise InvalidRequest("'marka' must be a nonblank string")

        info = self.schema.get(MACHINES_TABLE)
        if "ID_KLIENT" not in info.column_map:
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the expected machine columns"
            )
        columns, params = _insert_plan(
            prepared, MACHINE_INSERT_DEFAULTS, info.column_map
        )
        selected = [
            column for column in MACHINE_COLUMNS if column in info.column_map
        ]
        statement = build_insert(info.name, columns, returning=selected)
        client_info = self.schema.get(CLIENTS_TABLE)
        client_key = client_info.column_map.get("ID_KLIENT")
        if client_key is None:
            raise InvalidRequest("Client table has no ID_KLIENT key")
        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT FIRST 2 {quote_identifier(client_key)} "
                    f"FROM {quote_identifier(client_info.name)} "
                    f"WHERE {quote_identifier(client_key)} = ?", [owner],
                )
                matches = cursor.fetchall()
                if not matches:
                    raise RecordNotFound(f"Client with id_klient {owner} not found")
                if len(matches) > 1:
                    raise RecordConflict(f"Multiple clients have id_klient {owner}")
                cursor.execute(statement, params)
                row = cursor.fetchone()
                if row is None:
                    raise DatabaseUnavailable("Firebird did not return the machine")
                return self._serialize_row([c.lower() for c in selected], row)
            finally:
                cursor.close()

    def update_machine(
        self, id_maszyna: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update supplied machine fields by business ID; reject ambiguous IDs."""
        self._require_writes()
        if (
            not isinstance(id_maszyna, int)
            or isinstance(id_maszyna, bool)
            or id_maszyna < 1
        ):
            raise InvalidRequest("'id_maszyna' must be a positive integer")
        prepared = self._prepared_write_values(
            values, MACHINE_WRITE_COLUMNS, MACHINE_TEXT_LENGTHS, preserve_empty=True
        )
        if not prepared:
            raise InvalidRequest("Supply at least one machine field to update")
        if "ID_KLIENT" in prepared:
            owner = prepared["ID_KLIENT"]
            if not isinstance(owner, int) or isinstance(owner, bool) or owner < 0:
                raise InvalidRequest("'id_klient' must be a non-negative integer")
        info = self.schema.get(MACHINES_TABLE)
        key = info.column_map.get("ID_MASZYNA")
        if key is None:
            raise InvalidRequest("Machine table has no ID_MASZYNA key")
        for column, value in prepared.items():
            if column not in info.column_map:
                raise ColumnNotFound(f"Column '{column}' does not exist")
            if value is None and not next(
                c.nullable for c in info.columns if c.name == info.column_map[column]
            ):
                raise InvalidRequest(f"'{column.lower()}' must not be null")
        selected = [c for c in MACHINE_COLUMNS if c in info.column_map]
        statement = build_update(
            info.name, [info.column_map[c] for c in prepared], key=key,
            returning=[info.column_map[c] for c in selected],
        )
        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT FIRST 2 1 FROM {quote_identifier(info.name)} "
                    f"WHERE {quote_identifier(key)} = ?", [id_maszyna],
                )
                if len(cursor.fetchall()) > 1:
                    raise RecordConflict(
                        f"Multiple machines have id_maszyna {id_maszyna}"
                    )
                cursor.execute(statement, [*prepared.values(), id_maszyna])
                row = cursor.fetchone()
                if row is None or all(value is None for value in row):
                    raise RecordNotFound(
                        f"Machine with id_maszyna {id_maszyna} not found"
                    )
                return self._serialize_row([c.lower() for c in selected], row)
            finally:
                cursor.close()
