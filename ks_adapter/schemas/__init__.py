"""Compatible imports for the resource-specific request and response models."""

from __future__ import annotations

from .common import DecimalValue as DecimalValue
from .clients import (
    Client,
    ClientPage,
    ClientCreate,
    ClientUpdate,
)
from .agreements import (
    Agreement,
    AgreementPage,
    AgreementCreate,
    AgreementUpdate,
)
from .machines import (
    Machine,
    MachinePage,
    MachineCreate,
    MachineUpdate,
)
from .cpc_settlement import (
    CpcValues,
    CpcCreate,
    CpcUpdate,
    Cpc,
    CpcPage,
)
from .orders import (
    Order,
    OrderPage,
)
from .invoices import (
    Invoice,
    InvoicePage,
)
from .database import (
    ColumnModel,
    TableSummary,
    TableListResponse,
    TableDetail,
    RowPage,
    QueryRequest,
    QueryResponse,
    SchemaRefreshResponse,
)
from .meta import (
    DatabaseInfo,
    PoolInfo,
    HealthResponse,
    ServiceInfo,
)

__all__ = [
    "DecimalValue",
    "Client",
    "ClientPage",
    "ClientCreate",
    "ClientUpdate",
    "Agreement",
    "AgreementPage",
    "AgreementCreate",
    "AgreementUpdate",
    "Machine",
    "MachinePage",
    "MachineCreate",
    "MachineUpdate",
    "CpcValues",
    "CpcCreate",
    "CpcUpdate",
    "Cpc",
    "CpcPage",
    "Order",
    "OrderPage",
    "Invoice",
    "InvoicePage",
    "ColumnModel",
    "TableSummary",
    "TableListResponse",
    "TableDetail",
    "RowPage",
    "QueryRequest",
    "QueryResponse",
    "SchemaRefreshResponse",
    "DatabaseInfo",
    "PoolInfo",
    "HealthResponse",
    "ServiceInfo",
]
