"""
Celery tasks: periodic polling, analysis, notification.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import get_engine, get_session_factory
from app.db.models import Match, OddsSnapshot, Signal, Log
from app.providers.oddspapi import OddsPapiClient
from app.analysis.engine import run_all, compare_odds
from app.bot.telegram import send_signal_alert
from app.core.config import get_settings
from app.services.config_service import SignalConfigService
from app.services.tournament_service import TournamentConfigService

log = structlog.get_logger()

# Import celery AFTER other modules to avoid circular imports
from app.tasks.celery_app import celery  # noqa: E402


def _run_async(coro):
    """
    Run an async function from sync celery task.
    Properly handles event loop lifecycle to avoid "attached to a different loop" errors.
    """
    try:
        # Try to get existing loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create new one for this task
            loop = asyncio.new_event_loop()
    except RuntimeError:
        # No loop in current thread, create new one
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        log.debug("async_start", task=coro.__name__ if hasattr(coro, '__name__') else 'coro')
        result = loop.run_until_complete(coro)
        log.debug("async_complete", task=coro.__name__ if hasattr(coro, '__name__') else 'coro')
        return result
    except Exception as e:
        log.error("async_error", error=str(e), exc_info=True)
        raise
    finally:
        # Don't close the loop here in case Celery reuses threads
        pass


async def _write_log(level: str, source: str, message: str, meta: dict | None = None):
    """Write log entry to database (timestamp handled by server default)."""
    factory = get_session_factory()
    async with factory() as session:
        log_entry = Log(
            level=level,
            source=source,
            message=message,
            meta_json=meta,  # JSONB column, pass dict directly
        )
        session.add(log_entry)
        await session.commit()


async def _count_signals(session) -> int:
    """Count total signals in DB."""
    result = await session.execute(select(Signal))
    return len(result.scalars().all())


@celery.task(name="app.tasks.polling.poll_all_matches", bind=True)
def poll_all_matches(self):
    """Main periodic task: fetch PREMATCH fixtures → fetch odds → analyse → alert."""
    log.info("poll_task_start", task_id=self.request.id)
    try:
        _run_async(_poll_all_matches_async())
        log.info("poll_task_complete", task_id=self.request.id)
    except Exception as e:
        log.error("poll_task_failed", task_id=self.request.id, error=str(e), exc_info=True)
        raise


async def _poll_all_matches_async():
    settings = get_settings()
    client = OddsPapiClient()
    factory = get_session_factory()

    log.info("poll_async_init", poll_interval=settings.poll_interval_seconds)

    async with factory() as session:
        try:
            log.debug("initializing_tournament_defaults")
            # Initialize tournament configs on first run
            await TournamentConfigService.initialize_defaults(session)
            log.debug("tournament_defaults_initialized")

            # Get enabled tournaments (exclude Tier1)
            log.debug("fetching_enabled_tournaments")
            tournament_ids_str = await TournamentConfigService.get_tournament_ids_string(
                session, exclude_tier="tier1"
            )
            log.info("enabled_tournaments_fetched", tournament_ids=tournament_ids_str[:50] if tournament_ids_str else "NONE")

            if not tournament_ids_str:
                log.warning("no_enabled_tournaments")
                await _write_log("WARNING", "polling", "No enabled tournaments configured")
                return

            try:
                log.debug("fetching_prematch_fixtures")
                # Fetch ONLY prematch fixtures from enabled tournaments
                # This ensures detect_consensus works on pure prematch data
                fixtures = await client.fetch_prematch_fixtures(sport="cs2", window_hours=48)
                log.info("prematch_fixtures_fetched", total_count=len(fixtures))

                # Filter by tournament
                enabled_ids = set(int(t) for t in tournament_ids_str.split(","))
                fixtures = [f for f in fixtures if f.get("tournamentId") in enabled_ids]
                log.info("fixtures_filtered_by_tournament", filtered_count=len(fixtures), enabled_tournaments=len(enabled_ids))

            except Exception as e:
                log.error("fetch_prematch_fixtures_failed", error=str(e), exc_info=True)
                await _write_log("ERROR", "polling", f"fetch_prematch_fixtures failed: {e}")
                return

            log.info("poll_prematch_start", prematch_fixtures=len(fixtures), tournaments=len(enabled_ids))
            await _write_log("INFO", "polling", f"Prematch poll started, {len(fixtures)} fixtures from {len(enabled_ids)} tournaments")

            processed_count = 0
            signal_count = 0

            for fix in fixtures:
                try:
                    signals_count_before = await _count_signals(session)
                    await _process_fixture(fix, client, session, settings)
                    signals_count_after = await _count_signals(session)
                    new_signals = signals_count_after - signals_count_before
                    processed_count += 1
                    signal_count += new_signals
                    if new_signals > 0:
                        log.info("fixture_processed_with_signals", fixture_id=fix.get("fixtureId"), signals=new_signals)
                except Exception as e:
                    log.exception("fixture_error", fixture_id=fix.get("fixtureId"), error=str(e), exc_info=True)
                    await _write_log("ERROR", "polling", f"Fixture error {fix.get('fixtureId')}: {e}")

            await session.commit()
            log.info("poll_async_complete", fixtures_processed=processed_count, signals_detected=signal_count)
            await _write_log("INFO", "polling", f"Poll complete: {processed_count} fixtures processed, {signal_count} signals detected")

        except Exception as e:
            log.error("poll_async_failed", error=str(e), exc_info=True)
            await _write_log("ERROR", "polling", f"Poll failed: {e}")
            raise
        finally:
            await client.close()
            log.debug("oddspapi_client_closed")


async def _process_fixture(fix: dict, client: OddsPapiClient, session, settings):
    fixture_id = fix["fixtureId"]
    team1 = fix.get("participant1Name", "TBD")
    team2 = fix.get("participant2Name", "TBD")
    tournament = fix.get("tournamentName", "Unknown")
    
    log.debug("processing_fixture", fixture_id=fixture_id, team1=team1, team2=team2, tournament=tournament)
    
    # Parse start_time from ISO string to datetime
    start_time_str = fix.get("startTime")
    if isinstance(start_time_str, str):
        # Handle ISO 8601 format: "2026-03-11T18:00:00.000Z"
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            start_time = datetime.now(timezone.utc)
            log.warning("start_time_parse_failed", fixture_id=fixture_id, raw_value=start_time_str)
    else:
        start_time = start_time_str or datetime.now(timezone.utc)

    # 1. Upsert match (let DB handle timestamps via server defaults)
    log.debug("upserting_match", fixture_id=fixture_id)
    stmt = pg_insert(Match).values(
        external_id=fixture_id,
        sport="cs2",
        tournament=tournament,
        team1_name=team1,
        team2_name=team2,
        start_time=start_time,
        source="oddspapi",
    ).on_conflict_do_update(
        index_elements=["external_id"],
        set_={"tournament": tournament},  # Let DB update timestamps
    ).returning(Match.id)
    result = await session.execute(stmt)
    match_id = result.scalar_one()
    log.debug("match_upserted", match_id=match_id, fixture_id=fixture_id)

    # 2. Fetch odds (skip fixture on rate limit / error)
    log.debug("fetching_odds", fixture_id=fixture_id)
    try:
        odds_data = await client.fetch_odds(fixture_id)
        log.debug("odds_fetched", fixture_id=fixture_id)
    except Exception as e:
        log.warning("fetch_odds_failed", fixture_id=fixture_id, error=str(e), exc_info=True)
        await _write_log("WARNING", "polling", f"fetch_odds skipped {fixture_id}: {e}")
        return
    
    bookmaker_odds = odds_data.get("bookmakerOdds", {})
    log.debug("parsing_bookmaker_odds", fixture_id=fixture_id, bookmakers_count=len(bookmaker_odds))

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
            team1_odds=float(t1), team2_odds=float(t2),
            # timestamp handled by server default
        )
        session.add(snap)
        current_snapshots.append({"bookmaker": bk_slug, "team1_odds": float(t1), "team2_odds": float(t2)})

    # 3. Load previous snapshots (last poll cycle)
    now = datetime.now(timezone.utc)
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
    log.debug("running_analysis", fixture_id=fixture_id, current_snapshots=len(current_snapshots), previous_snapshots=len(previous_snapshots))
    signals = run_all(current_snapshots, previous_snapshots, settings)
    log.info("analysis_complete", fixture_id=fixture_id, signals_count=len(signals))

    # 5. Persist signals + send alerts
    for sig in signals:
        log.debug("persisting_signal", fixture_id=fixture_id, signal_kind=sig["kind"], severity=sig.get("severity"))
        db_signal = Signal(
            match_id=match_id,
            kind=sig["kind"],
            severity=sig.get("severity", "info"),
            title=sig["title"],
            meta_json=json.dumps(sig.get("meta", {})),
        )
        session.add(db_signal)

        # Check if this signal should go to telegram based on config
        kind = sig["kind"]
        severity = sig.get("severity", "info")
        should_send = await SignalConfigService.should_send_telegram(session, kind, severity)
        log.debug("telegram_check", fixture_id=fixture_id, kind=kind, severity=severity, should_send=should_send)
        
        if should_send:
            match_label = f"{team1} vs {team2}"
            log.info("sending_telegram_alert", fixture_id=fixture_id, signal_kind=sig["kind"])
            await send_signal_alert(sig, match_label, tournament)
            await _write_log("INFO", "telegram", f"Alert sent: {sig['kind']}", {
                "match": match_label, "title": sig["title"],
            })

    if signals:
        log.info("signals_detected", fixture=fixture_id, count=len(signals), signal_kinds=[s["kind"] for s in signals])
        await _write_log("INFO", "analysis", f"{len(signals)} signals detected", {
            "fixture_id": fixture_id, "signals": [s["kind"] for s in signals],
        })
    else:
        log.debug("no_signals_detected", fixture_id=fixture_id)


@celery.task(name="app.tasks.polling.cleanup_old_data")
def cleanup_old_data():
    """Remove snapshots older than retention days."""
    _run_async(_cleanup_async())


async def _cleanup_async():
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=settings.odds_retention_days)
        await session.execute(
            text("DELETE FROM odds_snapshots WHERE timestamp < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
        log.info("cleanup_done", cutoff=cutoff.isoformat())
        await _write_log("INFO", "cleanup", f"Odds cleanup completed, cutoff {cutoff.date()}")


@celery.task(name="app.tasks.polling.cleanup_old_logs")
def cleanup_old_logs():
    """Remove old logs based on retention policy."""
    _run_async(_cleanup_logs_async())


async def _cleanup_logs_async():
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        now = datetime.now(timezone.utc)
        # Delete INFO/WARNING older than N days
        info_cutoff = now - timedelta(days=settings.log_retention_days_info)
        await session.execute(
            text("DELETE FROM logs WHERE level IN ('INFO', 'WARNING') AND timestamp < :cutoff"),
            {"cutoff": info_cutoff},
        )
        # Delete ERROR older than M days
        error_cutoff = now - timedelta(days=settings.log_retention_days_error)
        await session.execute(
            text("DELETE FROM logs WHERE level = 'ERROR' AND timestamp < :cutoff"),
            {"cutoff": error_cutoff},
        )
        await session.commit()
        log.info("logs_cleanup_done", info_cutoff=info_cutoff.isoformat(), error_cutoff=error_cutoff.isoformat())
        await _write_log("INFO", "cleanup", "Log cleanup completed", {
            "info_retention_days": settings.log_retention_days_info,
            "error_retention_days": settings.log_retention_days_error,
        })
