"""Database service facade and compatible resource-constant exports."""

from __future__ import annotations

from dataclasses import replace

from ..config import AppSettings
from ..pool import ConnectionPool
from .machines_database import MachinesDatabaseService
from .base import _insert_plan as _insert_plan
from .clients import (
    ClientsService,
    CLIENTS_TABLE,
    CLIENT_COLUMNS,
    CLIENT_SEARCH_COLUMNS,
    CLIENT_NAME_MAX_LENGTH,
    CLIENT_WRITE_COLUMNS,
    CLIENT_TEXT_LENGTHS,
    CLIENT_INSERT_DEFAULTS,
)
from .agreements import (
    AgreementsService,
    AGREEMENTS_TABLE,
    AGREEMENT_COLUMNS,
    AGREEMENT_SEARCH_COLUMNS,
    AGREEMENT_WRITE_COLUMNS,
    MAX_AGREEMENT_MACHINES,
    AGREEMENT_TEXT_LENGTHS,
    AGREEMENT_INSERT_DEFAULTS,
)
from .machines import (
    MachinesService,
    MACHINES_TABLE,
    MACHINE_COLUMNS,
    MACHINE_SEARCH_COLUMNS,
    MACHINE_WRITE_COLUMNS,
    MACHINE_INSERT_DEFAULTS,
    MACHINE_TEXT_LENGTHS,
)
from .cpc_settlement import (
    CpcSettlementService,
    CPC_TABLE,
    CPC_COLUMNS,
    CPC_WRITE_COLUMNS,
    CPC_UPDATE_COLUMNS,
    CPC_TEXT_LENGTHS,
    CPC_INSERT_DEFAULTS,
)
from .orders import (
    OrdersService,
    ORDERS_TABLE,
    ORDER_COLUMNS,
    ORDER_SEARCH_COLUMNS,
)
from .invoices import (
    InvoicesService,
    INVOICES_TABLE,
    INVOICE_COLUMNS,
    INVOICE_SEARCH_COLUMNS,
)


class DatabaseService(
    ClientsService,
    AgreementsService,
    MachinesService,
    CpcSettlementService,
    OrdersService,
    InvoicesService,
    MachinesDatabaseService,
):
    """Resource operations with isolated primary and machine database state."""

    def __init__(
        self,
        settings: AppSettings,
        pool: ConnectionPool | None = None,
        machines_pool: ConnectionPool | None = None,
    ) -> None:
        super().__init__(settings, pool)
        self._machines_database_service = None
        if settings.machines_database is not None:
            secondary_settings = replace(
                settings,
                database=settings.machines_database,
                machines_database=None,
                api=replace(settings.api, allow_writes=False),
            )
            self._machines_database_service = DatabaseService(
                secondary_settings, pool=machines_pool
            )

    def close(self) -> None:
        """Close both database pools, including on application shutdown."""
        try:
            if self._machines_database_service is not None:
                self._machines_database_service.close()
        finally:
            super().close()


__all__ = [
    "DatabaseService",
    "CLIENTS_TABLE",
    "CLIENT_COLUMNS",
    "CLIENT_SEARCH_COLUMNS",
    "CLIENT_NAME_MAX_LENGTH",
    "CLIENT_WRITE_COLUMNS",
    "CLIENT_TEXT_LENGTHS",
    "CLIENT_INSERT_DEFAULTS",
    "AGREEMENTS_TABLE",
    "AGREEMENT_COLUMNS",
    "AGREEMENT_SEARCH_COLUMNS",
    "AGREEMENT_WRITE_COLUMNS",
    "MAX_AGREEMENT_MACHINES",
    "AGREEMENT_TEXT_LENGTHS",
    "AGREEMENT_INSERT_DEFAULTS",
    "MACHINES_TABLE",
    "MACHINE_COLUMNS",
    "MACHINE_SEARCH_COLUMNS",
    "MACHINE_WRITE_COLUMNS",
    "MACHINE_INSERT_DEFAULTS",
    "MACHINE_TEXT_LENGTHS",
    "CPC_TABLE",
    "CPC_COLUMNS",
    "CPC_WRITE_COLUMNS",
    "CPC_UPDATE_COLUMNS",
    "CPC_TEXT_LENGTHS",
    "CPC_INSERT_DEFAULTS",
    "ORDERS_TABLE",
    "ORDER_COLUMNS",
    "ORDER_SEARCH_COLUMNS",
    "INVOICES_TABLE",
    "INVOICE_COLUMNS",
    "INVOICE_SEARCH_COLUMNS",
]
