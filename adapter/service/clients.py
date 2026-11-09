"""Clients database operations and curated fields."""

from __future__ import annotations

from typing import Any, Mapping

from ..errors import ColumnNotFound, InvalidRequest, RecordNotFound
from ..sql import build_delete, build_insert, build_update
from .base import BaseDatabaseService, _insert_plan


#: Table holding contractors/clients in the BAZAMS schema.
CLIENTS_TABLE = "KLIENT"

#: Columns exposed by ``GET /clients``.  The curated endpoints speak the
#: database's own vocabulary: every row is keyed by the lower-cased column name
#: (``NAZWA`` -> ``nazwa``), so no separate field mapping has to be maintained.
CLIENT_COLUMNS: tuple[str, ...] = (
    "ID_KLIENT_TABLE",
    "ID_KLIENT",
    "NAZWA",
    "NAZWA_S",
    "NIP",
    "REGON",
    "ADRES",
    "KOD",
    "POCZTA",
    "WOJEWODZTWO",
    "TELEFON",
    "E_MAIL",
    "WWW",
    "TYP",
    "AKTYWNY",
    "PLATNOSC",
    "TERMIN",
    "RABAT",
    "OSTATNIO",
)

#: Columns matched by the ``search`` parameter of ``GET /clients``.
CLIENT_SEARCH_COLUMNS: tuple[str, ...] = (
    "NAZWA",
    "NAZWA_S",
    "NIP",
    "REGON",
    "E_MAIL",
    "TELEFON",
    "KOD",
    "POCZTA",
)

#: Width of ``KLIENT.NAZWA``.  Longer names are rejected up front, otherwise
#: Firebird answers with a string-truncation error instead of a clear message.
CLIENT_NAME_MAX_LENGTH = 500

#: Columns ``POST /clients`` accepts, in the order they are inserted.  Every one
#: of them belongs to :data:`CLIENT_COLUMNS`, so the created row is served
#: exactly as ``GET /clients`` would return it, and ``NAZWA`` is the only value
#: the caller has to supply.  The keys stay out of reach (``ID_KLIENT_TABLE`` and
#: ``ID_KLIENT`` come from their generators, ``ID_FIRMA`` is one of the
#: :data:`CLIENT_INSERT_DEFAULTS`) and so does ``OSTATNIO``, which the
#: application maintains itself.
CLIENT_WRITE_COLUMNS: tuple[str, ...] = (
    "NAZWA",
    "NAZWA_S",
    "NIP",
    "REGON",
    "ADRES",
    "KOD",
    "POCZTA",
    "WOJEWODZTWO",
    "TELEFON",
    "E_MAIL",
    "WWW",
    "TYP",
    "AKTYWNY",
    "PLATNOSC",
    "TERMIN",
    "RABAT",
)

#: Widths of the ``KLIENT`` text columns.  Longer values are rejected up front,
#: otherwise Firebird answers with a string-truncation error instead of a clear
#: message.  The ``POST /clients`` payload model reuses this mapping, so every
#: limit is declared in one place.
CLIENT_TEXT_LENGTHS: dict[str, int] = {
    "NAZWA": CLIENT_NAME_MAX_LENGTH,
    "NAZWA_S": 50,
    "NIP": 20,
    "REGON": 30,
    "ADRES": 250,
    "KOD": 6,
    "POCZTA": 150,
    "TELEFON": 100,
    "E_MAIL": 200,
    "WWW": 200,
    "TYP": 50,
    "AKTYWNY": 3,
    "PLATNOSC": 50,
}

#: The values the legacy application itself writes into a new ``KLIENT`` row.
#: They are read off the clients that program created: every one of them carries
#: these exact values, while a row that lets Firebird fill the columns with
#: ``NULL`` (and ``ID_FIRMA`` with the ``INS_KLIENT_RECORD`` fallback of ``1``)
#: never shows up in the program.  ``POST /clients`` therefore inserts them for
#: every column the caller did not supply, which keeps a bridged client
#: indistinguishable from a hand-entered one.
#:
#: ``ID_FIRMA`` is the important one: the program works with ``0`` even though
#: ``FIRMA`` holds ``1``, and it filters its client list by that number.
#: ``OSTATNIO`` (activity stamp) and ``GUSDATA`` (version date of the GUS data
#: the program ships) are deliberately absent - the first is the program's own
#: clock, the second a build constant, and neither decides whether a client is
#: listed.
CLIENT_INSERT_DEFAULTS: dict[str, Any] = {
    "ID_FIRMA": 0,
    "ID_ODBIORCA": 0,
    "ID_GRUPACEN": 0,
    "ID_US": 0,
    "ODDZIAL": 0,
    "NAZWA_S": "",
    "ADRES": "",
    "KOD": "",
    "POCZTA": "",
    "IDW": -1,
    "POWIAT": "",
    "GMINA": "",
    "NIP": "",
    "KOD_KRAJU": "PL",
    "REGON": "",
    "TELEFON": "",
    "WWW": "",
    "E_MAIL": "",
    "E_FAKTURA": "",
    "SENDXML": 0,
    "NAFRE": 0,
    "KONTAKT": "",
    "KLIENT": "",
    "BANK": "",
    "KONTO": "",
    "TYP": "Odbiorca",
    "RODZAJ": 0,
    "INNE": "",
    "UWAGI": "",
    "RABAT": 0,
    "PLATNOSC": "Gotówka",
    "TERMIN": 0,
    "ROBOCIZNA": 0,
    "DOJAZDY": 0,
    "POZIOM": 0,
    "STATUS": 0,
    "OSTZAPIS": 0,
    "SYNDEV": 0,
    "SYNTAS": 0,
    "SYNCHA": 0,
    "AKTYWNY": "",
    "KTO": "",
    "ALIEN_CODE": "",
}


class ClientsService(BaseDatabaseService):
    """Clients operations sharing the database service state."""

    def fetch_clients(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of contractors from the ``KLIENT`` table.

        Only :data:`CLIENT_COLUMNS` are selected, so the response shape stays
        stable even though the physical table is much wider.  Columns missing
        from the database are skipped instead of failing the request.
        """
        page = self._projection_page(
            CLIENTS_TABLE,
            CLIENT_COLUMNS,
            CLIENT_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("NAZWA", "ID_KLIENT_TABLE"),
            label="client",
        )
        page["clients"] = page.pop("rows")
        return page

    def create_client(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a contractor into ``KLIENT`` and return the stored row.

        ``values`` is keyed by the lower-cased column names of the curated
        projection (``{"nazwa": "ACME", "nip": "1234567890"}``); only the fields
        of :data:`CLIENT_WRITE_COLUMNS` are accepted and ``NAZWA`` is the single
        mandatory value.  Every column the caller leaves out is filled with the
        values :data:`CLIENT_INSERT_DEFAULTS` records from the legacy
        application, because a row that keeps the Firebird defaults is invisible
        to that program.  The ``BEFORE INSERT`` trigger ``INS_KLIENT_RECORD``
        fills ``ID_KLIENT_TABLE`` and ``ID_KLIENT`` from their generators and
        ``ID_ODDZIAL`` falls back to its column default, so every NOT NULL
        constraint is satisfied.  ``RETURNING`` hands the generated keys back
        inside the same transaction and the response is the same projection
        ``GET /clients`` serves, keyed by the lower-cased column names.

        Raises :class:`errors.WritesDisabled` when ``api.allow_writes`` is off.
        """
        self._require_writes()
        prepared = self._prepared_write_values(
            values, CLIENT_WRITE_COLUMNS, CLIENT_TEXT_LENGTHS
        )
        if "NAZWA" not in prepared:
            raise InvalidRequest("'nazwa' must not be empty")

        info = self.schema.get(CLIENTS_TABLE)
        if "NAZWA" not in info.column_map:
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the expected client columns"
            )
        columns, params = _insert_plan(
            prepared, CLIENT_INSERT_DEFAULTS, info.column_map
        )
        selected = [
            column for column in CLIENT_COLUMNS if column in info.column_map
        ]
        statement = build_insert(info.name, columns, returning=selected)

        return self._write_row(info.name, selected, statement, params)

    def update_client(
        self, id_klient: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update supplied client fields by unique business identifier.

        Existing legacy defaults, generated keys and omitted fields are preserved.
        Null and blank optional values explicitly clear the stored field.
        """
        self._require_writes()
        self._check_client_id(id_klient)
        prepared = self._prepared_write_values(
            values, CLIENT_WRITE_COLUMNS, CLIENT_TEXT_LENGTHS,
            preserve_empty=True,
        )
        if not prepared:
            raise InvalidRequest("Supply at least one client field to update")
        if "NAZWA" in prepared and not prepared["NAZWA"]:
            raise InvalidRequest("'nazwa' must not be empty")
        info = self.schema.get(CLIENTS_TABLE)
        if "ID_KLIENT" not in info.column_map:
            raise InvalidRequest("Client table has no unique ID_KLIENT key")
        for column in prepared:
            if column not in info.column_map:
                raise ColumnNotFound(f"Column '{column}' does not exist")
        selected = [c for c in CLIENT_COLUMNS if c in info.column_map]
        statement = build_update(
            info.name,
            [info.column_map[c] for c in prepared],
            key=info.column_map["ID_KLIENT"],
            returning=[info.column_map[c] for c in selected],
        )
        return self._write_row(
            info.name, selected, statement, [*prepared.values(), id_klient],
            not_found=RecordNotFound(f"Client with id_klient {id_klient} not found"),
        )

    def delete_client(self, id_klient: int) -> None:
        """Delete a client by ID_KLIENT, including trigger-managed dependents.

        DEL_KLIENT_RECORD also deletes the client's machines and contacts.
        Missing clients raise RecordNotFound and roll back the transaction.
        """
        self._require_writes()
        self._check_client_id(id_klient)
        info = self.schema.get(CLIENTS_TABLE)
        key = info.column_map.get("ID_KLIENT")
        if key is None:
            raise InvalidRequest("Client table has no unique ID_KLIENT key")
        self._write_row(
            info.name, [key], build_delete(info.name, key=key), [id_klient],
            not_found=RecordNotFound(f"Client with id_klient {id_klient} not found"),
        )
