"""
REST API endpoints.
"""

from datetime import datetime, timedelta

from attr.validators import matches_re
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    try:
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

        if not rows:
            return {"snapshots": [], "comparison": {}, "status": "no_data"}

        snapshots = [
            {"bookmaker": r.bookmaker, "team1_odds": r.team1_odds, "team2_odds": r.team2_odds,
             "timestamp": r.timestamp.isoformat()}
            for r in rows
        ]
        comparison = compare_odds(snapshots)
        return {"snapshots": snapshots, "comparison": comparison, "status": "ok"}
    except Exception as e:
        log.exception("odds_fetch_error", match_id=match_id)
        return {"snapshots": [], "comparison": {}, "status": "error", "error": str(e)}


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


# ── Odds List ────────────────────────────────────────

@router.get("/odds")
async def odds_list(
        db: AsyncSession = Depends(get_db),
):
    """
    Возвращает все odds snapshots с информацией о матче внутри каждой ставки.
    """
    result = await db.execute(
        select(OddsSnapshot)
        .options(selectinload(OddsSnapshot.match))  # Загружаем матч вместе со ставкой
        .order_by(OddsSnapshot.timestamp.desc())
    )
    odds_list = result.scalars().all()

    response = []
    for o in odds_list:
        response.append({
            "id": o.id,
            "bookmaker": o.bookmaker,
            "team1_odds": o.team1_odds,
            "team2_odds": o.team2_odds,
            "map1_team1_odds": o.map1_team1_odds,
            "map1_team2_odds": o.map1_team2_odds,
            "total_maps_over": o.total_maps_over,
            "total_maps_under": o.total_maps_under,
            "timestamp": o.timestamp.isoformat(),
            "match": {
                "id": o.match.id,
                "external_id": o.match.external_id,
                "sport": o.match.sport,
                "tournament": o.match.tournament,
                "team1_name": o.match.team1_name,
                "team2_name": o.match.team2_name,
                "start_time": o.match.start_time.isoformat(),
                "source": o.match.source,
                "created_at": o.match.created_at.isoformat(),
                "updated_at": o.match.updated_at.isoformat(),
            },
        })

    return {"count": len(response), "odds": response}


# ── Signals ──────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
        kind: str | None = None,
        severity: str | None = None,
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        db: AsyncSession = Depends(get_db),
):
    """List signals with pagination, filtering, and match context."""
    # Initialize defaults if needed
    from app.services.config_service import SignalConfigService
    await SignalConfigService.get_or_create_default(db)

    offset = (page - 1) * limit
    q = select(Signal).order_by(Signal.detected_at.desc())

    if kind:
        q = q.where(Signal.kind == kind)
    if severity:
        q = q.where(Signal.severity == severity)

    # Get total count
    count_result = await db.execute(select(func.count(Signal.id)).where(
        (Signal.kind == kind if kind else True) and
        (Signal.severity == severity if severity else True)
    ))
    total = count_result.scalar() or 0

    result = await db.execute(q.offset(offset).limit(limit))
    rows = result.scalars().all()

    # Enrich signals with match data
    signals_with_match = []
    for s in rows:
        # Get match info
        match_result = await db.execute(select(Match).where(Match.id == s.match_id))
        match = match_result.scalar_one_or_none()

        signals_with_match.append({
            "id": s.id,
            "match_id": s.match_id,
            "kind": s.kind,
            "severity": s.severity,
            "title": s.title,
            "meta": s.meta_json,
            "detected_at": s.detected_at.isoformat(),
            "match": {
                "team1": match.team1_name if match else "Unknown",
                "team2": match.team2_name if match else "Unknown",
                "tournament": match.tournament if match else "Unknown",
                "start_time": match.start_time.isoformat() if match else None,
            } if match else None,
        })

    return {
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
        },
        "signals": signals_with_match,
    }


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
