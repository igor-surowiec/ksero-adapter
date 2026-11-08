"""Business logic for curated reads and writes.

Curated writes require ``api.allow_writes`` and use ``pool.write_session()``.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from .config import AppSettings
from .errors import (
    ColumnNotFound,
    DatabaseUnavailable,
    InvalidRequest,
    RecordConflict,
    RecordNotFound,
    WritesDisabled,
)
from .pool import ConnectionPool
from .schema import SchemaCache, TableInfo
from .serialization import row_to_dict, serialize_rows
from .sql import (
    build_delete,
    build_insert,
    build_next_available_id,
    build_search,
    build_update,
    build_where,
    ensure_read_only,
    parse_filters,
    quote_identifier,
)

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

#: Table holding service agreements (contracts) in the BAZAMS schema.
AGREEMENTS_TABLE = "UMOWACPC"

#: Columns exposed by ``GET /agreements`` (keys: lower-cased column names).
AGREEMENT_COLUMNS: tuple[str, ...] = (
    "ID_UMOWACPC_TABLE",
    "ID_UMOWACPC",
    "ID_ODDZIAL",
    "ID_KLIENT",
    "ID_ODBIORCA",
    "ID_FIRMA",
    "UMOWA",
    "TYP",
    "HANDLOWIEC",
    "OPIEKUN",
    "OPIEKUNMAIL",
    "OPIEKUNTEL",
    "U_START",
    "U_STOP",
    "WARUNKI",
    "UWAGI",
    "KOSZTY",
    "PRZYCHODY",
    "WYNIK",
    "RABAT",
    "PLATNOSC",
    "TERMIN",
    "AKTYWNA",
    "STRONY_MONO",
    "STRONY_KOLOR",
    "SKANY",
    "FRAEMAIL",
    "PLIK",
)

#: Columns matched by the ``search`` parameter of ``GET /agreements``.
AGREEMENT_SEARCH_COLUMNS: tuple[str, ...] = (
    "UMOWA",
    "TYP",
    "HANDLOWIEC",
    "OPIEKUN",
    "OPIEKUNMAIL",
    "FRAEMAIL",
    "PLIK",
)

#: Writable agreement details; generated table keys and financial totals stay out.
AGREEMENT_WRITE_COLUMNS: tuple[str, ...] = (
    "ID_KLIENT", "ID_ODDZIAL", "ID_ODBIORCA", "ID_FIRMA",
    "UMOWA", "TYP", "HANDLOWIEC", "OPIEKUN", "OPIEKUNMAIL", "OPIEKUNTEL",
    "U_START", "U_STOP", "WARUNKI", "UWAGI", "RABAT", "PLATNOSC", "TERMIN",
    "AKTYWNA", "STRONY_MONO", "STRONY_KOLOR", "SKANY", "FRAEMAIL", "PLIK",
)

#: Text widths from the connected UMOWACPC catalog, reused by the wire model.
AGREEMENT_TEXT_LENGTHS: dict[str, int] = {
    "UMOWA": 100, "TYP": 100, "HANDLOWIEC": 100, "OPIEKUN": 100,
    "OPIEKUNMAIL": 100, "OPIEKUNTEL": 100, "WARUNKI": 1000, "UWAGI": 1000,
    "PLATNOSC": 250, "AKTYWNA": 20, "FRAEMAIL": 100, "PLIK": 250,
}

#: Defaults matching the legacy agreement with ID_UMOWACPC=1, including its
#: active flag and payment sentinel. The start date is filled with CURRENT_DATE
#: at insertion; record-specific details such as number/type are not copied.
AGREEMENT_INSERT_DEFAULTS: dict[str, Any] = {
    "ID_ODBIORCA": 0, "AUTOCPC": 0, "NOCPCSEND": 0, "AUTOFRA": 0,
    "HANDLOWIEC": "", "OPIEKUN": "", "OPIEKUNMAIL": "", "OPIEKUNTEL": "",
    "WARUNKI": "", "UWAGI": "", "PLIK": "", "FRAEMAIL": "",
    "PLATNOSC": "$_$", "TERMIN": 0, "AKTYWNA": "TAK",
    "IDVAT": 0, "ROZLICZ": 0,
    "UOPLATA1": 0, "UOPLATA2": 0, "UOPLATA3": 0,
    "OPLATA_MONO": 0, "OPLATA_KOLOR": 0, "UOEURO": 0,
    "STRONY_MONO": 0, "STRONY_KOLOR": 0,
    **{f"FRAPAR{i}": 0 for i in range(1, 9)},
    **{f"FRANAZ{i}": "" for i in range(1, 8)},
}

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

#: Columns ``POST /machines`` accepts, in the order they are inserted.  Every
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

#: ID_KLIENT is NOT NULL; legacy unassigned machines use 0 instead of NULL.
MACHINE_INSERT_DEFAULTS: dict[str, Any] = {"ID_KLIENT": 0}

#: Widths of the ``MASZYNA`` text columns.  Longer values are rejected up front,
#: otherwise Firebird answers with a string-truncation error instead of a clear
#: message.  The ``POST /machines`` payload model reuses this mapping, so every
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

#: Table holding service orders (jobs) in the BAZAMS schema.
ORDERS_TABLE = "ZLECENIE"

#: Columns exposed by ``GET /orders`` (keys: lower-cased column names).
#:
#: ``ZLECENIE`` is the widest table of the schema, so this is a hand-picked
#: projection rather than ``SELECT *``: it keeps the response shape stable and
#: the fetch message small (Firebird caps a statement message at 64 KB, which a
#: ``SELECT *`` of a very wide table would eventually blow).
ORDER_COLUMNS: tuple[str, ...] = (
    "ID_ZLECENIE_TABLE",
    "ID_ZLECENIE",
    "ROK",
    "STAN",
    "ID_FIRMA",
    "ID_ODDZIAL",
    "ID_KLIENT",
    "ID_MASZYNA",
    "NAZWA",
    "ADRES",
    "KOD",
    "POCZTA",
    "TELEFON",
    "E_MAIL",
    "STOI",
    "MARKA",
    "MODEL",
    "SERIAL",
    "EWIDENCJA",
    "DATA",
    "TERMIN",
    "DATA_Z",
    "GODZINA_PLAN",
    "DATA_PRZY",
    "DATA_WYDA",
    "DATA_START",
    "DATA_STOP",
    "RODZAJ_US",
    "USZKODZENIE",
    "PROBLEM",
    "DIAGNOZA",
    "WYKONANIE",
    "ZALECENIA",
    "UWAGI",
    "TECHNIK",
    "ZGLASZA",
    "OPERATOR",
    "SIGNWHO",
    "SIGNWHEN",
    "LICZNIK",
    "LICZNIKA3",
    "LICZNIK_TOTAL",
    "ROBOCIZNA",
    "DOJAZD",
    "CZESCI",
    "MATERIALY",
    "NETTO",
    "VAT",
    "BRUTTO",
    "ZALICZKA",
    "PLATNOSC",
    "FAKTURA",
    "PLIK",
)

#: Columns matched by the ``search`` parameter of ``GET /orders``.
#:
#: Deliberately a subset: Firebird sizes the parameter message from the number
#: of ``LIKE`` predicates and rejects more than
#: :data:`ks_adapter.sql.MAX_SEARCH_COLUMNS` of them, so "every text column"
#: (which ``ZLECENIE`` has plenty of) could never be searched in one statement.
ORDER_SEARCH_COLUMNS: tuple[str, ...] = (
    "NAZWA",
    "ADRES",
    "POCZTA",
    "TELEFON",
    "E_MAIL",
    "STOI",
    "MARKA",
    "MODEL",
    "SERIAL",
    "EWIDENCJA",
    "RODZAJ_US",
    "USZKODZENIE",
    "PROBLEM",
    "DIAGNOZA",
    "WYKONANIE",
    "ZALECENIA",
    "UWAGI",
    "TECHNIK",
    "ZGLASZA",
    "STAN",
    "FAKTURA",
    "PLIK",
)

#: Table holding invoices (sales documents) in the BAZAMS schema.
INVOICES_TABLE = "FAKTURA"

#: Columns exposed by ``GET /invoices`` (keys: lower-cased column names).
#:
#: The invoice header of ``FAKTURA`` is wide and mostly bookkeeping, so the
#: projection keeps document identity, links, the contractor snapshot, dates,
#: the PLN and foreign-currency totals and the correction amounts; the
#: per-VAT-rate matrix (``NETTO1``-``NETTO8``, ``VAT1``-``VAT5``,
#: ``BRUTTO1``-``BRUTTO8``), the pre-correction block (``PRKOR_*``, ``ZALICZKA_*``
#: variants), the ``F_*`` marker flags and the ``ALIENSYNCH*``/``WERSJA``/
#: ``EDITCNT``/``TEMP`` bookkeeping columns stay out of the payload.  The
#: invoice lines live in the separate ``FPOZYCJA`` table and are not exposed.
INVOICE_COLUMNS: tuple[str, ...] = (
    "ID_FAKTURA_TABLE",
    "ID_ODDZIAL",
    "ID_FIRMA",
    "ID_MAGAZYN",
    "ID_KLIENT",
    "ID_ODBIORCA",
    "ID_MASZYNA",
    "ID_ZLECENIE",
    "ROK_ZLECENIA",
    "ID_KOSZTORYS",
    "ID_WZ",
    "ID_UMOWA",
    "ID_UMOWACPC",
    "ID_ZAMOWIENIE",
    "ID_PACZKA",
    "ID_ACCOUNT",
    "ID_CURR",
    "NAZWA",
    "ADRES",
    "KOD",
    "POCZTA",
    "NIP",
    "KOD_KRAJU",
    "RODZAJ_DOK",
    "NUMER",
    "NR_KORY",
    "KOREKTA",
    "NR_PAR",
    "CCODE",
    "MIEJSCE_WYST",
    "WYSTAWIL",
    "ODEBRAL",
    "DATA_SPRZ",
    "DATA_WYST",
    "DATA_PLAT",
    "DATA_ZAPL",
    "DATA_KORY",
    "DATA_ZAM",
    "DNI_PLAT",
    "PLATNOSC",
    "WAL_KURS",
    "SUMA_NETTO",
    "SUMA_VAT",
    "SUMA_BRUTTO",
    "ZAPLACONO",
    "ZALICZKA",
    "DO_ZAPLATY",
    "POKOR_NETTO",
    "POKOR_VAT",
    "POKOR_BRUTTO",
    "WAL_NETTO",
    "WAL_VAT",
    "WAL_BRUTTO",
    "WAL_ZAPLACONO",
    "WAL_DO_ZAPLATY",
    "STAN",
    "UWAGI",
    "ZAMOWIENIE",
    "DOUMOWY",
)

#: Columns matched by the ``search`` parameter of ``GET /invoices``.
INVOICE_SEARCH_COLUMNS: tuple[str, ...] = (
    "NUMER",
    "NR_KORY",
    "KOREKTA",
    "NR_PAR",
    "RODZAJ_DOK",
    "CCODE",
    "NAZWA",
    "NIP",
    "ADRES",
    "KOD",
    "POCZTA",
    "PLATNOSC",
    "WYSTAWIL",
    "MIEJSCE_WYST",
    "UWAGI",
    "ZAMOWIENIE",
    "DOUMOWY",
    "STAN",
)


def _insert_plan(
    prepared: Mapping[str, Any],
    defaults: Mapping[str, Any],
    column_map: Mapping[str, Any],
) -> tuple[list[str], list[Any]]:
    """Merge a prepared write payload with the legacy default profile.

    The caller's columns come first, in the order
    :meth:`DatabaseService._prepared_write_values` produced them, followed by
    the default columns the payload did not touch.  Columns the connected
    database does not have are dropped, so a snapshot of an older catalog still
    produces a valid statement.  Returns the column names and the matching
    parameter values, both in statement order.
    """
    merged = {**defaults, **prepared}
    ordered = dict.fromkeys((*prepared, *defaults))
    columns = [column for column in ordered if column in column_map]
    return columns, [merged[column] for column in columns]


class DatabaseService:
    """Facade over a Firebird database: read models plus the curated writes."""

    def __init__(
        self, settings: AppSettings, pool: ConnectionPool | None = None
    ) -> None:
        self.settings = settings
        self.pool = pool if pool is not None else ConnectionPool(settings.database)
        self.schema = SchemaCache(self.pool, settings.api.schema_cache_ttl)

    def close(self) -> None:
        self.pool.close()

    # -- metadata ---------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Ping the database and report pool statistics."""
        started = time.perf_counter()
        version = self.pool.ping()
        return {
            "status": "ok",
            "database": {
                "dsn": self.settings.database.dsn,
                "charset": self.settings.database.charset,
                "server_version": version,
            },
            "pool": self.pool.stats,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def list_tables(self) -> list[dict[str, Any]]:
        tables = self.schema.tables()
        return [tables[name].to_dict() for name in sorted(tables, key=str.upper)]

    def describe_table(self, table: str) -> dict[str, Any]:
        return self.schema.get(table).to_dict(include_columns=True)

    def refresh_schema(self) -> int:
        """Drop the cached metadata and reload it, returning the table count."""
        self.schema.invalidate()
        return len(self.schema.tables())

    # -- data -------------------------------------------------------------
    def fetch_rows(
        self,
        table: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        filters: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of rows with optional ordering and JSON filters."""
        info = self.schema.get(table)
        limit = self.check_limit(limit)
        if offset < 0:
            raise InvalidRequest("'offset' must not be negative")

        where_sql, params = build_where(parse_filters(filters), info.column_map)
        order_sql = self._order_clause(order_by, info)
        table_sql = quote_identifier(info.name)
        count_sql = f"SELECT COUNT(*) FROM {table_sql}{where_sql}"
        page_sql = (
            f"SELECT * FROM {table_sql}{where_sql}{order_sql} "
            f"ROWS {offset + 1} TO {offset + limit}"
        )

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(count_sql, params or None)
                row = cursor.fetchone()
                total = int(row[0]) if row and row[0] is not None else 0
                cursor.execute(page_sql, params or None)
                columns, rows = serialize_rows(
                    cursor.description,
                    cursor.fetchall(),
                    decimal_as_string=self.settings.api.decimal_as_string,
                    blob_encoding=self.settings.api.blob_encoding,
                )
            finally:
                cursor.close()

        return {
            "table": info.name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

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

    def fetch_agreements(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of agreements from the ``UMOWACPC`` table.

        Like :meth:`fetch_clients` this is a hand-picked projection
        (:data:`AGREEMENT_COLUMNS`) of the physical table, so the printing
        parameters (``FRAPAR*``, ``FRANAZ*``/``IDMAG*``) and per-item prices stay
        out of the payload unless the endpoint is extended explicitly.
        """
        page = self._projection_page(
            AGREEMENTS_TABLE,
            AGREEMENT_COLUMNS,
            AGREEMENT_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("UMOWA", "ID_UMOWACPC_TABLE"),
            label="agreement",
        )
        page["agreements"] = page.pop("rows")
        return page

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

    def fetch_orders(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of service orders (jobs) from the ``ZLECENIE`` table.

        ``ZLECENIE`` is the widest table of the schema and Firebird caps a
        statement message at 64 KB, so this endpoint avoids both traps:

        * :data:`ORDER_COLUMNS` is a hand-picked projection instead of
          ``SELECT *``, which keeps the fetch message small;
        * :data:`ORDER_SEARCH_COLUMNS` holds fewer columns than
          :data:`ks_adapter.sql.MAX_SEARCH_COLUMNS`, because every ``search``
          predicate is bound as a ``VARCHAR(1024)`` parameter and Firebird
          rejects a wider parameter message with "Implementation limit
          exceeded".

        The budgets are asserted in the test-suite, so extending either list
        too far fails the build instead of the request.
        """
        page = self._projection_page(
            ORDERS_TABLE,
            ORDER_COLUMNS,
            ORDER_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("DATA", "ID_ZLECENIE_TABLE"),
            label="order",
        )
        page["orders"] = page.pop("rows")
        return page

    def fetch_invoices(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of invoices (sales documents) from ``FAKTURA``.

        ``FAKTURA`` is the invoice header, not the document: the positions live
        in ``FPOZYCJA`` and are not exposed.  :data:`INVOICE_COLUMNS` therefore
        keeps document identity, links, the contractor snapshot, dates and the
        PLN/foreign-currency totals, while the per-VAT-rate matrix and the
        bookkeeping columns are skipped.

        Ordering is by issue date and surrogate key, so paging stays stable
        when several invoices share a date.
        """
        page = self._projection_page(
            INVOICES_TABLE,
            INVOICE_COLUMNS,
            INVOICE_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("DATA_WYST", "ID_FAKTURA_TABLE"),
            label="invoice",
        )
        page["invoices"] = page.pop("rows")
        return page

    def _projection_page(
        self,
        table: str,
        columns: Sequence[str],
        search_columns: Sequence[str],
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        order_columns: Sequence[str],
        label: str,
    ) -> dict[str, Any]:
        """Page through a stable projection of ``table``.

        Shared implementation of ``/clients``, ``/agreements``,
        ``/machines``, ``/orders`` and ``/invoices``: selects only the
        ``columns`` that exist in the database,
        applies the optional ``search`` substring, orders by ``order_columns``
        (first available wins) and returns ``total``/``count``/``limit``/
        ``offset`` plus ``rows`` keyed by the lower-cased column names, so the
        JSON speaks the same Polish vocabulary as the database.
        """
        info = self.schema.get(table)
        limit = self.check_limit(limit)
        if offset < 0:
            raise InvalidRequest("'offset' must not be negative")

        selected = [column for column in columns if column.upper() in info.column_map]
        if not selected:
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the expected {label} columns"
            )

        where_sql, params = build_search(search, info.column_map, search_columns)
        select_sql = ", ".join(quote_identifier(column) for column in selected)
        table_sql = quote_identifier(info.name)
        order_sql = self._default_order_clause(info, order_columns)
        count_sql = f"SELECT COUNT(*) FROM {table_sql}{where_sql}"
        page_sql = (
            f"SELECT {select_sql} FROM {table_sql}{where_sql}{order_sql} "
            f"ROWS {offset + 1} TO {offset + limit}"
        )

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(count_sql, params or None)
                row = cursor.fetchone()
                total = int(row[0]) if row and row[0] is not None else 0
                cursor.execute(page_sql, params or None)
                raw_rows = cursor.fetchall()
            finally:
                cursor.close()

        keys = [column.lower() for column in selected]
        rows = [self._serialize_row(keys, row) for row in raw_rows]
        return {
            "total": total,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "rows": rows,
        }

    def run_query(
        self,
        sql: str,
        *,
        limit: int | None = None,
        parameters: Sequence[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a single read-only statement and return at most ``limit`` rows."""
        statement = ensure_read_only(sql)
        limit = self.check_limit(
            limit,
            maximum=self.settings.api.max_query_rows,
            default=self.settings.api.max_query_rows,
        )
        params = self._check_parameters(parameters)

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                if cursor.description is None:
                    return {
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "truncated": False,
                    }
                fetched = cursor.fetchmany(limit + 1)
                truncated = len(fetched) > limit
                if truncated:
                    fetched = fetched[:limit]
                columns, rows = serialize_rows(
                    cursor.description,
                    fetched,
                    decimal_as_string=self.settings.api.decimal_as_string,
                    blob_encoding=self.settings.api.blob_encoding,
                )
            finally:
                cursor.close()

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    # -- writes -----------------------------------------------------------
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

    def create_agreement(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Create an agreement with the lowest unused positive business ID.

        A protected table reservation serialises allocation and insertion across
        connections. The surrogate table key remains generated by the trigger.
        """
        self._require_writes()
        prepared = self._prepared_write_values(
            values, AGREEMENT_WRITE_COLUMNS, AGREEMENT_TEXT_LENGTHS
        )
        self._check_client_id(prepared.get("ID_KLIENT"))
        info = self.schema.get(AGREEMENTS_TABLE)
        if not {"ID_UMOWACPC", "ID_KLIENT"} <= info.column_map.keys():
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the required agreement columns"
            )
        key = info.column_map["ID_UMOWACPC"]
        selected = [c for c in AGREEMENT_COLUMNS if c in info.column_map]
        with self.pool.write_session(reserve_table=info.name) as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(build_next_available_id(info.name, key))
                row = cursor.fetchone()
                if row is None or row[0] is None:
                    raise InvalidRequest("No positive agreement identifiers available")
                business_id = int(row[0])
                defaults = dict(AGREEMENT_INSERT_DEFAULTS)
                if "U_START" not in prepared and "U_START" in info.column_map:
                    cursor.execute("SELECT CURRENT_DATE FROM RDB$DATABASE")
                    today = cursor.fetchone()
                    if today is None or today[0] is None:
                        raise DatabaseUnavailable(
                            "Firebird did not return current date"
                        )
                    defaults["U_START"] = today[0]
                columns, params = _insert_plan(prepared, defaults, info.column_map)
                statement = build_insert(
                    info.name, [key, *columns], returning=selected
                )
                cursor.execute(statement, [business_id, *params])
                raw_row = cursor.fetchone()
                if raw_row is None:
                    raise DatabaseUnavailable("Firebird did not return the agreement")
                return self._serialize_row([c.lower() for c in selected], raw_row)
            finally:
                cursor.close()

    def create_machine(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a machine into ``MASZYNA`` and return the stored row.

        ``values`` is keyed by the lower-cased column names of the curated
        projection (``{"id_klient": 7, "marka": "KONICA"}``); only the fields of
        :data:`MACHINE_WRITE_COLUMNS` are accepted and only the ones the caller
        supplies are inserted, with ``ID_KLIENT`` defaulting to ``0`` (unassigned).
        The
        ``BEFORE INSERT`` trigger ``INS_MASZYNA_RECORD`` fills
        ``ID_MASZYNA_TABLE`` and ``ID_MASZYNA`` from their generators,
        ``ID_ODDZIAL``/``ID_FIRMA``/``IDVAT`` fall back to their column defaults
        and ``SYNWP`` stays untouched, so nothing is queued for synchronisation.
        ``RETURNING`` hands the generated keys back inside the same transaction
        and the response is the projection ``GET /machines`` serves.

        Raises :class:`errors.WritesDisabled` when ``api.allow_writes`` is off.
        """
        self._require_writes()
        prepared = self._prepared_write_values(
            values, MACHINE_WRITE_COLUMNS, MACHINE_TEXT_LENGTHS
        )
        owner = prepared.get("ID_KLIENT", 0)
        if not isinstance(owner, int) or isinstance(owner, bool) or owner < 0:
            raise InvalidRequest("'id_klient' must be a non-negative integer")

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

        return self._write_row(
            info.name, selected, statement, params
        )

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

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _check_client_id(id_klient: int) -> None:
        if (
            not isinstance(id_klient, int)
            or isinstance(id_klient, bool)
            or id_klient < 1
        ):
            raise InvalidRequest("'id_klient' must be a positive integer")

    def _require_writes(self) -> None:
        if not self.settings.api.allow_writes:
            raise WritesDisabled(
                "Writes are disabled; enable 'api.allow_writes' (KS_ALLOW_WRITES)"
            )

    def _write_row(
        self,
        table: str,
        selected: Sequence[str],
        statement: str,
        params: Sequence[Any],
        *,
        not_found: RecordNotFound | None = None,
    ) -> dict[str, Any]:
        """Execute a curated write and serialise RETURNING before committing."""
        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                raw_row = cursor.fetchone()
                # Firebird 2.5 returns a NULL-filled RETURNING row for no match.
                if not_found is not None and (
                    raw_row is None or all(value is None for value in raw_row)
                ):
                    raise not_found
                if raw_row is None:
                    raise DatabaseUnavailable(
                        f"Firebird did not return the row written to '{table}'"
                    )
                return self._serialize_row([c.lower() for c in selected], raw_row)
            finally:
                cursor.close()

    def _serialize_row(
        self, names: Sequence[str], row: Sequence[Any]
    ) -> dict[str, Any]:
        return row_to_dict(
            row, names,
            decimal_as_string=self.settings.api.decimal_as_string,
            blob_encoding=self.settings.api.blob_encoding,
        )

    @staticmethod
    def _prepared_write_values(
        values: Mapping[str, Any],
        allowed: Sequence[str],
        lengths: Mapping[str, int],
        *,
        preserve_empty: bool = False,
    ) -> dict[str, Any]:
        """Validate and normalise the fields of a curated write payload.

        Keys are matched case-insensitively against ``allowed``, strings are
        trimmed and a blank string counts as "not supplied", so the calling write
        falls back to its own default for that column (the legacy profile of
        :data:`CLIENT_INSERT_DEFAULTS`, or the database default).  The result
        follows the order of ``allowed``, which keeps the generated statement
        stable, and a field outside that list is refused instead of being dropped
        silently. With ``preserve_empty``, explicit nulls and blanks are kept
        for partial updates instead of invoking insert defaults.
        """
        if not isinstance(values, Mapping):
            raise InvalidRequest("Fields must be a JSON object")

        supplied: dict[str, Any] = {}
        for key, value in values.items():
            column = str(key).strip().upper()
            if column not in allowed:
                raise InvalidRequest(f"Unknown field '{key}'")
            supplied[column] = value

        prepared: dict[str, Any] = {}
        for column in allowed:
            if column not in supplied:
                continue
            value = supplied[column]
            if value is None and not preserve_empty:
                continue
            if isinstance(value, str):
                value = value.strip()
                maximum = lengths.get(column)
                if maximum is not None and len(value) > maximum:
                    raise InvalidRequest(
                        f"'{column.lower()}' must not be longer than "
                        f"{maximum} characters"
                    )
                if not value and not preserve_empty:
                    continue
            prepared[column] = value
        return prepared

    def check_limit(
        self, limit: int | None, *, maximum: int | None = None, default: int | None = None
    ) -> int:
        """Validate a requested page size against the configured limits."""
        api = self.settings.api
        bound = api.max_limit if maximum is None else maximum
        fallback = api.default_limit if default is None else default
        value = fallback if limit is None else int(limit)
        if value < 1:
            raise InvalidRequest("'limit' must be at least 1")
        if value > bound:
            raise InvalidRequest(f"'limit' must not exceed {bound}")
        return value

    @staticmethod
    def _default_order_clause(info: TableInfo, columns: Sequence[str]) -> str:
        """Order by the first available of ``columns``, so pages stay stable."""
        parts = [
            quote_identifier(info.column_map[column])
            for column in columns
            if column in info.column_map
        ]
        return f" ORDER BY {', '.join(parts)}" if parts else ""

    def _order_clause(self, order_by: str | None, info: TableInfo) -> str:
        if not order_by or not order_by.strip():
            return ""
        parts: list[str] = []
        for token in order_by.split(","):
            token = token.strip()
            if not token:
                continue
            pieces = token.split()
            if len(pieces) > 2:
                raise InvalidRequest(
                    f"Invalid 'order_by' entry '{token}', expected 'COLUMN [ASC|DESC]'"
                )
            direction = "ASC"
            if len(pieces) == 2:
                direction = pieces[1].upper()
                if direction not in {"ASC", "DESC"}:
                    raise InvalidRequest(
                        f"Invalid sort direction '{pieces[1]}' in 'order_by'"
                    )
            canonical = info.column_map.get(pieces[0].upper())
            if canonical is None:
                raise ColumnNotFound(f"Unknown column '{pieces[0]}' in 'order_by'")
            parts.append(f"{quote_identifier(canonical)} {direction}")
        return f" ORDER BY {', '.join(parts)}" if parts else ""

    @staticmethod
    def _check_parameters(parameters: Sequence[Any] | None) -> list[Any] | None:
        if parameters is None:
            return None
        if not isinstance(parameters, (list, tuple)):
            raise InvalidRequest("'parameters' must be a JSON array")
        for index, value in enumerate(parameters):
            if value is None or isinstance(value, (str, bool, int, float)):
                continue
            raise InvalidRequest(
                f"Parameter {index} must be a string, number, boolean or null"
            )
        return list(parameters) or None


