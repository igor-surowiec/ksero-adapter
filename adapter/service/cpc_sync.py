"""Synchronize settlement readings from the independent machine database."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Mapping

from ..errors import DatabaseUnavailable, InvalidRequest, RecordConflict, RecordNotFound
from ..schema import TableInfo
from ..sql import ensure_read_only, quote_identifier
from .agreements import AGREEMENTS_TABLE
from .cpc_settlement import (
    CPC_TABLE, CPC_TEXT_LENGTHS, CPC_UPDATE_COLUMNS, _insert_cpc_on_cursor,
)
from .machines import MACHINES_TABLE
from .machines_database import MachinesDatabaseService


#: Equivalent readings and notes copied into a new settlement with legacy defaults.
CPC_MACHINE_FIELD_MAP = {
    "licz_m_ostatn_rozl": "LICZNIK_MONO_START",
    "licz_k_ostatn_rozl": "LICZNIK_KOLOR_START",
    "licznik_mono": "LICZNIK_MONO_END",
    "licznik_kolor": "LICZNIK_KOLOR_END",
    "licznik_skan": "LICZNIK_SKAN_END",
    "uwagi": "UWAGI",
}


class CpcSyncService(MachinesDatabaseService):
    """Create a settlement from matched readings and the machine's agreement."""

    def sync_cpc_from_machine(
        self, id_maszyna: int, *, start_date: date, end_date: date,
    ) -> dict[str, Any]:
        """Create a settlement from a unique source reading in one write session."""
        self._require_writes()
        if type(start_date) is not date or type(end_date) is not date:
            raise InvalidRequest("'start_date' and 'end_date' must be dates")
        if start_date > end_date:
            raise InvalidRequest("'start_date' must not be after 'end_date'")
        if (not isinstance(id_maszyna, int) or isinstance(id_maszyna, bool)
                or id_maszyna < 1):
            raise InvalidRequest("'id_maszyna' must be a positive integer")
        if self._machines_database_service is None:
            raise DatabaseUnavailable("machines_database is not configured")
        machine = self.schema.get(MACHINES_TABLE)
        cpc = self.schema.get(CPC_TABLE)
        identity_columns = {"ID_MASZYNA", "MODEL", "SERIAL", "ID_UMOWACPC"}
        if not identity_columns <= machine.column_map.keys():
            raise InvalidRequest("Machine table lacks model/serial identity columns")
        required = {"ID_CPC_TABLE", "ID_MASZYNA", "ID_KLIENT", "ID_UMOWACPC",
                    "ROK", "MIESIAC"}
        if not required <= cpc.column_map.keys():
            raise InvalidRequest("CPC table lacks required settlement columns")
        agreement = self.schema.get(AGREEMENTS_TABLE)
        if not {"ID_UMOWACPC", "ID_KLIENT"} <= agreement.column_map.keys():
            raise InvalidRequest("Agreement table lacks client reference columns")

        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(ensure_read_only(
                    f"SELECT FIRST 2 {quote_identifier(machine.column_map['MODEL'])}, "
                    f"{quote_identifier(machine.column_map['SERIAL'])}, "
                    f"{quote_identifier(machine.column_map['ID_UMOWACPC'])} "
                    f"FROM {quote_identifier(machine.name)} "
                    f"WHERE {quote_identifier(machine.column_map['ID_MASZYNA'])} = ?"
                ), [id_maszyna])
                matches = cursor.fetchall()
                if not matches:
                    raise RecordNotFound(f"Machine {id_maszyna} not found")
                if len(matches) > 1:
                    raise RecordConflict(f"Multiple machines have ID {id_maszyna}")
                model, serial, agreement_id = matches[0]
                if any(
                    not isinstance(v, str) or not v.strip() for v in (model, serial)
                ):
                    raise InvalidRequest("Machine model and serial must be nonblank")

                if (not isinstance(agreement_id, int) or isinstance(agreement_id, bool)
                        or agreement_id < 1):
                    raise InvalidRequest("Machine must have a linked CPC agreement")

                # Use the same filtered query as GET /machines-database, without
                # a loopback HTTP request or assuming matching IDs across databases.
                page = self.fetch_database_machines(limit=1, filters=json.dumps({
                    "model": model.strip(), "id_nr_seryjny": serial.strip(),
                }))
                if page["total"] == 0:
                    raise RecordNotFound("No matching machine in machines_database")
                if page["total"] > 1:
                    raise RecordConflict(
                        "Multiple matching machines in machines_database"
                    )
                if not page["machines"]:
                    raise DatabaseUnavailable(
                        "Matching machine record was not returned"
                    )
                source = page["machines"][0]
                try:
                    reading_date = date.fromisoformat(source.get("data_licznika"))
                except (TypeError, ValueError):
                    raise InvalidRequest(
                        "Source 'data_licznika' must contain a valid date"
                    ) from None
                if not start_date <= reading_date <= end_date:
                    raise InvalidRequest(
                        "Source 'data_licznika' is outside the requested date range"
                    )
                prepared = self._cpc_machine_values(source, cpc)
                prepared.update(ID_MASZYNA=id_maszyna, ID_UMOWACPC=agreement_id)
                return _insert_cpc_on_cursor(self, cursor, prepared, cpc, agreement)
            finally:
                cursor.close()

    def _cpc_machine_values(
        self, source: Mapping[str, Any], cpc: TableInfo,
    ) -> dict[str, Any]:
        """Validate mapped non-null source values before building the insert."""
        values: dict[str, Any] = {}
        for source_name, target in CPC_MACHINE_FIELD_MAP.items():
            value = source.get(source_name)
            if value is None or target not in cpc.column_map:
                continue
            if target == "UWAGI":
                if not isinstance(value, str):
                    raise InvalidRequest("Source 'uwagi' must be a string")
                if not value.strip():
                    continue
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InvalidRequest(
                    f"Source '{source_name}' must be a non-negative integer"
                )
            values[target] = value
        prepared = self._prepared_write_values(
            values, CPC_UPDATE_COLUMNS, CPC_TEXT_LENGTHS
        )
        if not prepared:
            raise InvalidRequest("Matching machine has no transferable CPC values")
        return prepared
