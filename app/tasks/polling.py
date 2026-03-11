"""
Celery tasks: periodic polling, analysis, notification.
"""

import asyncio
import json
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.tasks.celery_app import celery
from app.db.session import get_engine, get_session_factory
from app.db.models import Match, OddsSnapshot, Signal
from app.providers.oddspapi import OddsPapiClient
from app.analysis.engine import run_all, compare_odds
from app.bot.telegram import send_signal_alert
from app.core.config import get_settings

log = structlog.get_logger()


def _run_async(coro):
    """Run an async function from sync celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="app.tasks.polling.poll_all_matches")
def poll_all_matches():
    """Main periodic task: fetch fixtures → fetch odds → analyse → alert."""
    _run_async(_poll_all_matches_async())


async def _poll_all_matches_async():
    settings = get_settings()
    client = OddsPapiClient()
    factory = get_session_factory()

    try:
        fixtures = await client.fetch_fixtures(sport="cs2", has_odds=True)
        log.info("poll_start", fixtures=len(fixtures))

        async with factory() as session:
            for fix in fixtures:
                try:
                    await _process_fixture(fix, client, session, settings)
                except Exception:
                    log.exception("fixture_error", fixture_id=fix.get("fixtureId"))
            await session.commit()

    finally:
        await client.close()


async def _process_fixture(fix: dict, client: OddsPapiClient, session, settings):
    fixture_id = fix["fixtureId"]

    # 1. Upsert match
    stmt = pg_insert(Match).values(
        external_id=fixture_id,
        sport="cs2",
        tournament=fix.get("tournamentName", "Unknown"),
        team1_name=fix.get("participant1Name", "TBD"),
        team2_name=fix.get("participant2Name", "TBD"),
        start_time=fix["startTime"],
        source="oddspapi",
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={"tournament": fix.get("tournamentName"), "updated_at": datetime.utcnow()},
    ).returning(Match.id)
    result = await session.execute(stmt)
    match_id = result.scalar_one()

    # 2. Fetch odds
    odds_data = await client.fetch_odds(fixture_id)
    bookmaker_odds = odds_data.get("bookmakerOdds", {})
    now = datetime.utcnow()

    current_snapshots = []
    for bk_slug, bk_data in bookmaker_odds.items():
        markets = bk_data.get("markets", {})
        mw = markets.get("171", {}).get("outcomes", {})
        t1 = mw.get("171", {}).get("players", {}).get("0", {}).get("price")
        t2 = mw.get("172", {}).get("players", {}).get("0", {}).get("price")
        if not t1 or not t2:
            continue

        snap = OddsSnapshot(
            match_id=match_id, bookmaker=bk_slug,
            team1_odds=float(t1), team2_odds=float(t2), timestamp=now,
        )
        session.add(snap)
        current_snapshots.append({"bookmaker": bk_slug, "team1_odds": float(t1), "team2_odds": float(t2)})

    # 3. Load previous snapshots (last poll cycle)
    cutoff = now - timedelta(seconds=settings.poll_interval_seconds + 60)
    prev_q = await session.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.match_id == match_id, OddsSnapshot.timestamp < cutoff)
        .order_by(OddsSnapshot.timestamp.desc())
        .limit(50)
    )
    prev_rows = prev_q.scalars().all()
    # dedupe: keep latest per bookmaker
    seen = set()
    previous_snapshots = []
    for row in prev_rows:
        if row.bookmaker not in seen:
            seen.add(row.bookmaker)
            previous_snapshots.append({
                "bookmaker": row.bookmaker,
                "team1_odds": row.team1_odds,
                "team2_odds": row.team2_odds,
            })

    # 4. Run analysis
    signals = run_all(current_snapshots, previous_snapshots, settings)

    # 5. Persist signals + send alerts
    for sig in signals:
        db_signal = Signal(
            match_id=match_id,
            kind=sig["kind"],
            severity=sig.get("severity", "info"),
            title=sig["title"],
            meta_json=json.dumps(sig.get("meta", {})),
        )
        session.add(db_signal)

        # Telegram alert for warning/critical
        if sig.get("severity") in ("warning", "critical"):
            match_label = f"{fix.get('participant1Name')} vs {fix.get('participant2Name')}"
            await send_signal_alert(sig, match_label, fix.get("tournamentName", ""))

    if signals:
        log.info("signals_detected", fixture=fixture_id, count=len(signals))


@celery.task(name="app.tasks.polling.cleanup_old_data")
def cleanup_old_data():
    """Remove snapshots older than 30 days."""
    _run_async(_cleanup_async())


async def _cleanup_async():
    factory = get_session_factory()
    async with factory() as session:
        cutoff = datetime.utcnow() - timedelta(days=30)
        await session.execute(
            text("DELETE FROM odds_snapshots WHERE timestamp < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
        log.info("cleanup_done", cutoff=cutoff.isoformat())
