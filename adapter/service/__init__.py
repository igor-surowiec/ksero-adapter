"""Database service facade and compatible resource-constant exports."""

from __future__ import annotations

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
):
    """Resource operations sharing one connection pool and schema cache."""


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
