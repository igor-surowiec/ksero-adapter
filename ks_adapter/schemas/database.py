"""Database request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field



class ColumnModel(BaseModel):
    """A column of a table or view."""

    name: str
    position: int
    type: str = Field(
        description="Firebird SQL type, e.g. VARCHAR(50) or NUMERIC(15,2)"
    )
    nullable: bool
    default: str | None = None
    charset: str | None = None
    length: int | None = Field(default=None, description="Length in bytes")
    precision: int | None = None
    scale: int | None = None


class TableSummary(BaseModel):
    """Short description of a table or view."""

    name: str
    kind: str = Field(description="Either 'table' or 'view'")
    column_count: int
    description: str | None = None


class TableListResponse(BaseModel):
    count: int
    tables: list[TableSummary]


class TableDetail(TableSummary):
    columns: list[ColumnModel] = Field(default_factory=list)


class RowPage(BaseModel):
    """A page of rows returned by ``/tables/{table}/rows``."""

    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    total: int = Field(description="Total number of rows matching the filters")
    limit: int
    offset: int


class QueryRequest(BaseModel):
    sql: str = Field(
        min_length=1,
        description="A single read-only SELECT or WITH statement",
        examples=["SELECT FIRST 10 * FROM APPUSER"],
    )
    limit: int | None = Field(
        default=None, ge=1, description="Maximum number of rows to return"
    )
    parameters: list[Any] | None = Field(
        default=None, description="Optional positional parameters for '?' placeholders"
    )


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = Field(description="True when more rows matched than 'limit'")


class SchemaRefreshResponse(BaseModel):
    refreshed: bool
    table_count: int
