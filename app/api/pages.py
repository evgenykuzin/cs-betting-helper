"""
Server-side rendered pages (Jinja2 + HTMX).
"""

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from app.db.session import get_db
from app.db.models import Match, Signal

router = APIRouter()
templates = Jinja2Templates(directory="app/frontend/templates")


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    # Recent matches
    q = await db.execute(
        select(Match).order_by(Match.start_time.desc()).limit(20)
    )
    matches = q.scalars().all()

    # Recent signals
    sq = await db.execute(
        select(Signal).order_by(Signal.detected_at.desc()).limit(20)
    )
    signals = sq.scalars().all()

    # Stats
    total_matches = (await db.execute(select(func.count(Match.id)))).scalar() or 0
    total_signals = (await db.execute(select(func.count(Signal.id)))).scalar() or 0
    critical_signals = (await db.execute(
        select(func.count(Signal.id)).where(Signal.severity == "critical")
    )).scalar() or 0

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "matches": matches,
        "signals": signals,
        "stats": {
            "total_matches": total_matches,
            "total_signals": total_signals,
            "critical_signals": critical_signals,
        },
    })


@router.get("/match/{match_id}")
async def match_detail(request: Request, match_id: int, db: AsyncSession = Depends(get_db)):
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    signals = (await db.execute(
        select(Signal).where(Signal.match_id == match_id).order_by(Signal.detected_at.desc())
    )).scalars().all()

    return templates.TemplateResponse("match.html", {
        "request": request, "match": match, "signals": signals,
    })


@router.get("/logs")
async def logs_page(request: Request):
    """Live logs page."""
    return templates.TemplateResponse("logs.html", {"request": request})


@router.get("/admin")
async def admin_page(request: Request):
    """Admin configuration panel."""
    return templates.TemplateResponse("admin.html", {"request": request})
