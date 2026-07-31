"""Durable and in-memory stores for the singleton operator configuration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from control_plane.types import (
    RuntimeTradingConfiguration,
    TradingConfigurationAudit,
)
from models.control_plane import TradingControlAuditRecord, TradingControlRecord
from storage.time import as_utc


class TradingControlStore(Protocol):
    """Atomic durable boundary for one applied control-plane configuration."""

    async def get_or_create(
        self, default: RuntimeTradingConfiguration
    ) -> RuntimeTradingConfiguration: ...

    async def update(
        self, configuration: RuntimeTradingConfiguration, *, expected_version: int
    ) -> RuntimeTradingConfiguration: ...

    async def list_audit(self, limit: int = 50) -> Sequence[TradingConfigurationAudit]: ...


class InMemoryTradingControlStore:
    """Deterministic store used by isolated application tests."""

    def __init__(self) -> None:
        self._configuration: RuntimeTradingConfiguration | None = None
        self._audit: list[TradingConfigurationAudit] = []

    async def get_or_create(
        self, default: RuntimeTradingConfiguration
    ) -> RuntimeTradingConfiguration:
        if self._configuration is None:
            self._configuration = default
            self._audit.append(
                TradingConfigurationAudit(
                    version=default.version,
                    configuration=default,
                    created_at=default.updated_at,
                )
            )
        return self._configuration

    async def update(
        self, configuration: RuntimeTradingConfiguration, *, expected_version: int
    ) -> RuntimeTradingConfiguration:
        if self._configuration is None:
            raise ValueError("configuration must be initialized before update")
        if self._configuration.version != expected_version:
            raise ValueError("configuration version conflict")
        self._configuration = configuration
        self._audit.append(
            TradingConfigurationAudit(
                version=configuration.version,
                configuration=configuration,
                created_at=configuration.updated_at,
            )
        )
        return configuration

    async def list_audit(self, limit: int = 50) -> Sequence[TradingConfigurationAudit]:
        return tuple(reversed(self._audit[-limit:]))


class SqlAlchemyTradingControlStore:
    """PostgreSQL store with optimistic version checks and append-only audit history."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_or_create(
        self, default: RuntimeTradingConfiguration
    ) -> RuntimeTradingConfiguration:
        async with self._sessions() as session:
            record = await session.get(TradingControlRecord, 1)
            if record is None:
                record = self._record_from_configuration(default)
                session.add(record)
                await session.flush()
                session.add(self._audit_record(default))
                await session.commit()
            return self._to_configuration(record)

    async def update(
        self, configuration: RuntimeTradingConfiguration, *, expected_version: int
    ) -> RuntimeTradingConfiguration:
        async with self._sessions() as session:
            record = await session.scalar(
                select(TradingControlRecord).where(TradingControlRecord.id == 1).with_for_update()
            )
            if record is None:
                raise ValueError("configuration must be initialized before update")
            if record.version != expected_version:
                raise ValueError("configuration version conflict")
            record.mode = configuration.mode.value
            record.place_orders_automatically = configuration.place_orders_automatically
            record.monitoring_enabled = configuration.monitoring_enabled
            record.symbols = list(configuration.symbols)
            record.strategy = configuration.strategy.model_dump(mode="json")
            record.risk_policy = configuration.risk_policy.model_dump(mode="json")
            record.version = configuration.version
            record.updated_at = configuration.updated_at
            session.add(self._audit_record(configuration))
            await session.commit()
        return configuration

    async def list_audit(self, limit: int = 50) -> Sequence[TradingConfigurationAudit]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(TradingControlAuditRecord)
                    .order_by(TradingControlAuditRecord.version.desc())
                    .limit(limit)
                )
            ).all()
        return tuple(
            TradingConfigurationAudit(
                version=record.version,
                configuration=RuntimeTradingConfiguration.model_validate(record.configuration),
                created_at=as_utc(record.created_at),
            )
            for record in records
        )

    @staticmethod
    def _record_from_configuration(configuration: RuntimeTradingConfiguration) -> TradingControlRecord:
        return TradingControlRecord(
            id=1,
            mode=configuration.mode.value,
            place_orders_automatically=configuration.place_orders_automatically,
            monitoring_enabled=configuration.monitoring_enabled,
            symbols=list(configuration.symbols),
            strategy=configuration.strategy.model_dump(mode="json"),
            risk_policy=configuration.risk_policy.model_dump(mode="json"),
            version=configuration.version,
            updated_at=configuration.updated_at,
        )

    @staticmethod
    def _audit_record(configuration: RuntimeTradingConfiguration) -> TradingControlAuditRecord:
        return TradingControlAuditRecord(
            control_id=1,
            version=configuration.version,
            configuration=configuration.model_dump(mode="json"),
            created_at=configuration.updated_at,
        )

    @staticmethod
    def _to_configuration(record: TradingControlRecord) -> RuntimeTradingConfiguration:
        return RuntimeTradingConfiguration(
            mode=record.mode,
            place_orders_automatically=record.place_orders_automatically,
            monitoring_enabled=record.monitoring_enabled,
            symbols=tuple(record.symbols),
            strategy=record.strategy,
            risk_policy=record.risk_policy,
            version=record.version,
            updated_at=as_utc(record.updated_at),
        )
