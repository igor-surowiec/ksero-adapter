"""Meta request and response models."""

from __future__ import annotations

from pydantic import BaseModel



class DatabaseInfo(BaseModel):
    dsn: str
    charset: str
    server_version: str


class PoolInfo(BaseModel):
    created: int
    idle: int
    capacity: int


class HealthResponse(BaseModel):
    status: str
    database: DatabaseInfo
    pool: PoolInfo
    latency_ms: float


class ServiceInfo(BaseModel):
    name: str
    version: str
    api_prefix: str
    docs_url: str
