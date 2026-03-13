"""
Reanalysis task: reprocess existing matches from database.
Does NOT fetch new odds from OddsPapi, just re-runs analysis engine.
"""

import json
import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_engine, get_session_factory
from app.db.models import Match, OddsSnapshot, Signal
from app.analysis.engine import run_all
from app.bot.telegram import send_signal_alert
from app.core.config import get_settings
from app.services.config_service import SignalConfigService

log = structlog.get_logger()


async def reanalyze_all_matches():
    """
    Reprocess all matches in DB:
    1. Load match
    2. Load its odds snapshots
    3. Run analysis engine
    4. Generate signals (only new ones)
    5. Send alerts
    """
    settings = get_settings()
    factory = get_session_factory()

    async with factory() as session:
        log.info("reanalysis_start")

        # Get all matches with odds
        result = await session.execute(
            select(Match).order_by(Match.created_at.desc())
        )
        matches = result.scalars().all()
        log.info("reanalysis_matches_loaded", count=len(matches))

        processed = 0
        signals_generated = 0

        for match in matches:
            try:
                # Load snapshots for this match
                snap_result = await session.execute(
                    select(OddsSnapshot)
                    .where(OddsSnapshot.match_id == match.id)
                    .order_by(OddsSnapshot.timestamp.desc())
                )
                snapshots = snap_result.scalars().all()

                if len(snapshots) < 2:
                    log.debug("reanalysis_skip_match", match_id=match.id, reason="not_enough_snapshots")
                    continue

                # Build current + previous snapshots
                # Current = latest snapshot per bookmaker
                current_map = {}
                for snap in snapshots:
                    if snap.bookmaker not in current_map:
                        current_map[snap.bookmaker] = {
                            "bookmaker": snap.bookmaker,
                            "team1_odds": snap.team1_odds,
                            "team2_odds": snap.team2_odds,
                        }

                current_snapshots = list(current_map.values())

                # Previous = snapshots from 5+ minutes ago (or all if less than 5 min of history)
                now = datetime.now(timezone.utc)
                cutoff = now - timedelta(seconds=settings.poll_interval_seconds + 60)
                
                previous_map = {}
                for snap in snapshots:
                    if snap.timestamp < cutoff:
                        if snap.bookmaker not in previous_map:
                            previous_map[snap.bookmaker] = {
                                "bookmaker": snap.bookmaker,
                                "team1_odds": snap.team1_odds,
                                "team2_odds": snap.team2_odds,
                            }

                previous_snapshots = list(previous_map.values()) if previous_map else []

                # Run analysis
                signals = run_all(current_snapshots, previous_snapshots, settings)
                log.debug("reanalysis_signals_generated", match_id=match.id, count=len(signals))

                # Check which signals should be persisted + sent
                for sig in signals:
                    kind = sig["kind"]
                    severity = sig.get("severity", "info")
                    should_send = await SignalConfigService.should_send_telegram(session, kind, severity)

                    if should_send:
                        # Check if signal already exists (avoid duplicates)
                        existing = await session.execute(
                            select(Signal).where(
                                Signal.match_id == match.id,
                                Signal.kind == sig["kind"],
                                Signal.severity == sig.get("severity", "info"),
                            )
                        )
                        if existing.scalars().first():
                            log.debug("reanalysis_signal_skip_duplicate", match_id=match.id, kind=kind)
                            continue

                        # Build match context for card
                        match_context = {
                            "team1": match.team1_name,
                            "team2": match.team2_name,
                            "tournament": match.tournament,
                            "start_time": match.start_time,
                            "current_odds": current_snapshots,
                        }

                        # Send alert
                        log.info("reanalysis_sending_alert", match_id=match.id, kind=kind)
                        await send_signal_alert(sig, match_context)

                        # Persist signal
                        db_signal = Signal(
                            match_id=match.id,
                            kind=sig["kind"],
                            severity=sig.get("severity", "info"),
                            title=sig["title"],
                            meta_json=json.dumps(sig.get("meta", {})),
                        )
                        session.add(db_signal)
                        signals_generated += 1

                processed += 1

            except Exception as e:
                log.exception("reanalysis_match_error", match_id=match.id, error=str(e))
                continue

        # Commit all new signals
        if signals_generated > 0:
            await session.commit()

        log.info(
            "reanalysis_complete",
            matches_processed=processed,
            signals_generated=signals_generated,
        )

        return {
            "matches_processed": processed,
            "signals_generated": signals_generated,
        }
