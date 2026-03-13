"""
SQLAlchemy ORM models with proper PostgreSQL types and server-side timestamps.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, func,
    ForeignKey, Index, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True, nullable=False, index=True)
    sport = Column(String(50), nullable=False, server_default="cs2")
    tournament = Column(String(255))
    team1_name = Column(String(255), nullable=False)
    team2_name = Column(String(255), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String(50), nullable=False, server_default="oddspapi")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    odds_snapshots = relationship("OddsSnapshot", back_populates="match", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="match", cascade="all, delete-orphan")


class OddsSnapshot(Base):
    """One row = one bookmaker's odds at one point in time (timeseries)."""
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    bookmaker = Column(String(100), nullable=False)
    team1_odds = Column(Float, nullable=False)
    team2_odds = Column(Float, nullable=False)
    map1_team1_odds = Column(Float)
    map1_team2_odds = Column(Float)
    total_maps_over = Column(Float)
    total_maps_under = Column(Float)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    match = relationship("Match", back_populates="odds_snapshots")

    __table_args__ = (
        Index("ix_odds_match_bk_ts", "match_id", "bookmaker", "timestamp"),
    )


class Signal(Base):
    """
    Unified signal table for all detection types:
    arbitrage, steam_move, value_bet, suspicious, etc.
    """
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, server_default="info")
    title = Column(String(512), nullable=False)
    detail = Column(Text)
    meta_json = Column(JSONB, nullable=True)  # Native PostgreSQL JSON type
    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    notified = Column(Boolean, nullable=False, server_default="false")

    match = relationship("Match", back_populates="signals")

    __table_args__ = (
        Index("ix_signals_kind_detected", "kind", "detected_at"),
    )


class Log(Base):
    """Activity logs for debugging and monitoring."""
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    level = Column(String(20), nullable=False)
    source = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    meta_json = Column(JSONB, nullable=True)  # Native PostgreSQL JSON type

    __table_args__ = (
        Index("ix_logs_timestamp_level", "timestamp", "level"),
    )


class SignalConfig(Base):
    """
    Configuration for signal filtering and routing.
    Extensible: kind + severity combo determines behavior.
    Can add new columns (channels, webhooks, etc.) later.
    """
    __tablename__ = "signal_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(50), nullable=False)  # arbitrage, steam_move, value_bet, etc.
    severity = Column(String(20), nullable=False)  # info, warning, critical
    enabled = Column(Boolean, nullable=False, server_default="true")
    send_telegram = Column(Boolean, nullable=False, server_default="false")
    description = Column(String(512))
    config_json = Column(JSONB, nullable=True)  # Future: webhooks, filters, thresholds, etc.
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_signal_config_kind_severity", "kind", "severity"),
    )


class AdminConfig(Base):
    """
    Global admin settings (expandable key-value store).
    Use for poll_interval, retention_days, thresholds, etc.
    """
    __tablename__ = "admin_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSONB, nullable=False)  # Stores any JSON (int, bool, string, object)
    description = Column(String(512))
    category = Column(String(50))  # polling, analysis, alerts, etc.
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class TournamentConfig(Base):
    """
    Tournament whitelist / configuration.
    Allows Amy to manage which tournaments to analyze.
    Supports tier-based filtering (e.g., exclude Tier 1 majors).
    """
    __tablename__ = "tournament_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, unique=True, nullable=False, index=True)
    tournament_name = Column(String(255), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default="true", index=True)
    tier = Column(String(20), nullable=False, server_default="tier2")  # tier1, tier2, tier3, tier4, other
    description = Column(String(512))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tournament_enabled_tier", "enabled", "tier"),
    )
