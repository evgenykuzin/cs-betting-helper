"""
REST API endpoints.
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import Match, OddsSnapshot, Signal, Log
from app.analysis.engine import compare_odds, calc_volatility
from app.providers.oddspapi import OddsPapiClient

router = APIRouter()


# ── Matches ──────────────────────────────────────────────────────────

@router.get("/matches")
async def list_matches(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = await db.execute(
        select(Match)
        .where(Match.start_time >= cutoff)
        .order_by(Match.start_time.desc())
        .limit(100)
    )
    rows = q.scalars().all()
    return [
        {
            "id": m.id, "external_id": m.external_id,
            "team1": m.team1_name, "team2": m.team2_name,
            "tournament": m.tournament, "start_time": m.start_time.isoformat(),
        }
        for m in rows
    ]


# ── Odds Comparison ─────────────────────────────────────────────────

@router.get("/matches/{match_id}/odds")
async def match_odds(match_id: int, db: AsyncSession = Depends(get_db)):
    """Latest odds per bookmaker (line shopping view)."""
    # subquery: latest snapshot per bookmaker
    sq = (
        select(
            OddsSnapshot.bookmaker,
            func.max(OddsSnapshot.id).label("max_id"),
        )
        .where(OddsSnapshot.match_id == match_id)
        .group_by(OddsSnapshot.bookmaker)
        .subquery()
    )
    q = await db.execute(
        select(OddsSnapshot).join(sq, OddsSnapshot.id == sq.c.max_id)
    )
    rows = q.scalars().all()
    snapshots = [
        {"bookmaker": r.bookmaker, "team1_odds": r.team1_odds, "team2_odds": r.team2_odds, "timestamp": r.timestamp.isoformat()}
        for r in rows
    ]
    comparison = compare_odds(snapshots)
    return {"snapshots": snapshots, "comparison": comparison}


# ── Odds History (for charts) ────────────────────────────────────────

@router.get("/matches/{match_id}/history")
async def match_odds_history(
    match_id: int,
    bookmaker: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(OddsSnapshot).where(OddsSnapshot.match_id == match_id)
    if bookmaker:
        q = q.where(OddsSnapshot.bookmaker == bookmaker)
    q = q.order_by(OddsSnapshot.timestamp)
    result = await db.execute(q.limit(2000))
    rows = result.scalars().all()
    return [
        {
            "bookmaker": r.bookmaker,
            "team1_odds": r.team1_odds, "team2_odds": r.team2_odds,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
    ]


# ── Signals ──────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    kind: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(Signal).order_by(Signal.detected_at.desc())
    if kind:
        q = q.where(Signal.kind == kind)
    if severity:
        q = q.where(Signal.severity == severity)
    result = await db.execute(q.limit(limit))
    rows = result.scalars().all()
    return [
        {
            "id": s.id, "match_id": s.match_id, "kind": s.kind,
            "severity": s.severity, "title": s.title,
            "meta": s.meta_json, "detected_at": s.detected_at.isoformat(),
        }
        for s in rows
    ]


# ── Volatility ───────────────────────────────────────────────────────

@router.get("/matches/{match_id}/volatility")
async def match_volatility(match_id: int, db: AsyncSession = Depends(get_db)):
    q = await db.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.match_id == match_id)
        .order_by(OddsSnapshot.timestamp)
    )
    rows = q.scalars().all()
    history = [{"team1_odds": r.team1_odds, "team2_odds": r.team2_odds} for r in rows]
    return calc_volatility(history)


# ── Manual trigger ───────────────────────────────────────────────────

@router.post("/poll")
async def trigger_poll():
    """Manually trigger a poll cycle."""
    from app.tasks.polling import poll_all_matches
    poll_all_matches.delay()
    return {"status": "queued"}


# ── Logs ─────────────────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    level: str | None = None,
    source: str | None = None,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = select(Log).where(Log.timestamp >= cutoff).order_by(Log.timestamp.desc())
    if level:
        q = q.where(Log.level == level.upper())
    if source:
        q = q.where(Log.source == source)
    result = await db.execute(q.limit(limit))
    rows = result.scalars().all()
    return [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat(),
            "level": l.level,
            "source": l.source,
            "message": l.message,
            "meta": l.meta_json,
        }
        for l in rows
    ]