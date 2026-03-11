"""
SQLAlchemy ORM models.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), unique=True, nullable=False, index=True)
    sport = Column(String(50), nullable=False, default="cs2")
    tournament = Column(String(255))
    team1_name = Column(String(255), nullable=False)
    team2_name = Column(String(255), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String(50), nullable=False, default="oddspapi")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    odds_snapshots = relationship("OddsSnapshot", back_populates="match", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="match", cascade="all, delete-orphan")


class OddsSnapshot(Base):
    """One row = one bookmaker's odds at one point in time."""
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    bookmaker = Column(String(100), nullable=False)
    team1_odds = Column(Float, nullable=False)
    team2_odds = Column(Float, nullable=False)
    # additional markets
    map1_team1_odds = Column(Float)
    map1_team2_odds = Column(Float)
    total_maps_over = Column(Float)
    total_maps_under = Column(Float)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    match = relationship("Match", back_populates="odds_snapshots")

    __table_args__ = (
        Index("ix_odds_match_bk_ts", "match_id", "bookmaker", "timestamp"),
    )


class Signal(Base):
    """
    Unified signal table.  'kind' discriminates the type:
        arbitrage, steam_move, value_bet, suspicious, reverse_line,
        odds_spike, consensus, middle, etc.
    """
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="info")  # info / warning / critical
    title = Column(String(512), nullable=False)
    detail = Column(Text)
    meta_json = Column(Text)  # free-form JSON payload
    detected_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    notified = Column(Boolean, default=False)

    match = relationship("Match", back_populates="signals")

    __table_args__ = (
        Index("ix_signals_kind_detected", "kind", "detected_at"),
    )
