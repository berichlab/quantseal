"""SQLAlchemy 2.0 storage models for QuantSeal."""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CampaignIndex(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="running")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")
    cost_preset: Mapped[str] = mapped_column(String(32), nullable=False, default="us_equities")
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    data_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    prior_campaign_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validation_evaluated_once: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_contaminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dev_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qualified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )


class ShadowStrategy(Base):
    __tablename__ = "shadow_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_key: Mapped[str] = mapped_column(String(96), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_campaign_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    spec_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="shadow")
    observations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evalue: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    peak_evalue: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    cumulative_return_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cumulative_excess_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reason: Mapped[str] = mapped_column(Text, nullable=False, default="Enrolled in forward shadow tracking.")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )

    observations: Mapped[list[ShadowObservation]] = relationship(
        "ShadowObservation",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="ShadowObservation.obs_date.asc()",
    )


class ShadowObservation(Base):
    __tablename__ = "shadow_observations"
    __table_args__ = (UniqueConstraint("strategy_id", "obs_date", name="uq_shadow_obs_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("shadow_strategies.id", ondelete="CASCADE"), index=True)
    obs_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    strategy_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_return_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    excess_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    strategy: Mapped[ShadowStrategy] = relationship("ShadowStrategy", back_populates="observations")


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )


class MCPServerRecord(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    headers_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    command: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    args_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_in_discovery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discovery_tools_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    discovered_tools_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    last_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
