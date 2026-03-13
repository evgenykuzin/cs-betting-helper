"""
Admin API endpoints for configuration and management.
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TournamentConfig
from app.db.session import get_db
from app.services.config_service import SignalConfigService, AdminConfigService
from app.services.tournament_service import TournamentConfigService

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Signal Config ────────────────────────────────────────────────────

@router.get("/signal-configs")
async def list_signal_configs(db: AsyncSession = Depends(get_db)):
    """List all signal routing configurations, with defaults if empty."""
    configs: List = await SignalConfigService.get_or_create_default(db)
    return {
        "count": len(configs),
        "configs": [
            {
                "id": c.id,
                "kind": c.kind,
                "severity": c.severity,
                "enabled": c.enabled,
                "send_telegram": c.send_telegram,
                "description": c.description,
                "config_json": c.config_json,
            }
            for c in configs
        ],
    }


@router.patch("/signal-configs/{kind}/{severity}")
async def update_signal_config(
    kind: str,
    severity: str,
    enabled: bool = None,
    send_telegram: bool = None,
    description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Update signal config for a kind/severity combo."""
    cfg = await SignalConfigService.update(
        db, kind, severity, enabled=enabled, send_telegram=send_telegram, description=description
    )
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Config not found: {kind}/{severity}")

    return {
        "id": cfg.id,
        "kind": cfg.kind,
        "severity": cfg.severity,
        "enabled": cfg.enabled,
        "send_telegram": cfg.send_telegram,
        "description": cfg.description,
    }


# ─── Admin Config (Global Settings) ────────────────────────────────────

@router.get("/configs")
async def list_admin_configs(
    category: str = Query(None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
):
    """List all admin configs, optionally filtered by category."""
    # Ensure defaults exist
    await AdminConfigService.get_or_create_defaults(db)

    if category:
        configs = await AdminConfigService.get_by_category(db, category)
    else:
        configs = await AdminConfigService.get_all(db)

    return {
        "count": len(configs),
        "configs": [
            {
                "id": c.id,
                "key": c.key,
                "value": c.value,
                "category": c.category,
                "description": c.description,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in configs
        ],
    }


@router.patch("/configs/{key}")
async def update_admin_config(
    key: str,
    value: Any = None,
    category: str = None,
    description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Update admin config value."""
    if value is None:
        raise HTTPException(status_code=400, detail="value is required")

    cfg = await AdminConfigService.set(db, key, value, category or "general", description)
    return {
        "id": cfg.id,
        "key": cfg.key,
        "value": cfg.value,
        "category": cfg.category,
        "description": cfg.description,
    }


@router.post("/configs/{key}")
async def create_admin_config(
    key: str,
    value: Any = None,
    category: str = "general",
    description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Create new admin config. Fails if key exists."""
    if value is None:
        raise HTTPException(status_code=400, detail="value is required")

    existing = await AdminConfigService.get(db, key)
    if existing:
        raise HTTPException(status_code=409, detail=f"Config key '{key}' already exists")

    cfg = await AdminConfigService.set(db, key, value, category, description)
    return {
        "id": cfg.id,
        "key": cfg.key,
        "value": cfg.value,
        "category": cfg.category,
        "description": cfg.description,
    }


# ─── Tournament Config ────────────────────────────────────────────────

@router.get("/tournaments")
async def list_tournaments(
    enabled: bool = Query(None, description="Filter by enabled status"),
    tier: str = Query(None, description="Filter by tier"),
    db: AsyncSession = Depends(get_db),
):
    """List all tournaments in config, optionally filtered."""
    # Initialize on first run
    await TournamentConfigService.initialize_defaults(db)

    # Get all tournaments
    all_tournaments = await TournamentConfigService.get_enabled_tournaments(db, exclude_tier=None)

    # Apply filters
    result = all_tournaments
    if enabled is not None:
        result = [t for t in result if t.enabled == enabled]
    if tier:
        result = [t for t in result if t.tier == tier]

    return {
        "count": len(result),
        "tournaments": [
            {
                "id": t.id,
                "tournament_id": t.tournament_id,
                "tournament_name": t.tournament_name,
                "enabled": t.enabled,
                "tier": t.tier,
                "description": t.description,
                "updated_at": t.updated_at.isoformat(),
            }
            for t in result
        ],
    }


@router.patch("/tournaments/{tournament_id}")
async def update_tournament(
    tournament_id: int,
    enabled: bool = None,
    tier: str = None,
    description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Update tournament config (enable/disable, tier, description)."""
    try:
        # Fetch current tournament
        from sqlalchemy import select
        result = await db.execute(
            select(TournamentConfig).where(TournamentConfig.tournament_id == tournament_id)
        )
        tournament = result.scalars().first()
        if not tournament:
            raise ValueError(f"Tournament {tournament_id} not found")

        # Update enabled if provided
        if enabled is not None:
            tournament.enabled = bool(enabled)

        # Update tier if provided
        if tier is not None:
            tournament.tier = tier

        # Update description if provided
        if description is not None:
            tournament.description = description

        db.add(tournament)
        await db.commit()
        await db.refresh(tournament)

        return {
            "id": tournament.id,
            "tournament_id": tournament.tournament_id,
            "tournament_name": tournament.tournament_name,
            "enabled": tournament.enabled,
            "tier": tournament.tier,
            "description": tournament.description,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tournaments")
async def create_tournament(
    tournament_id: int,
    tournament_name: str,
    tier: str = "tier2",
    enabled: bool = True,
    description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Add a new tournament to the whitelist."""
    try:
        tournament = await TournamentConfigService.add_tournament(
            db, tournament_id, tournament_name, tier, enabled
        )
        if description:
            tournament.description = description
            db.add(tournament)
            await db.commit()

        return {
            "id": tournament.id,
            "tournament_id": tournament.tournament_id,
            "tournament_name": tournament.tournament_name,
            "enabled": tournament.enabled,
            "tier": tournament.tier,
            "description": tournament.description,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/tournaments/{tournament_id}")
async def delete_tournament(
    tournament_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove a tournament from the whitelist."""
    try:
        await TournamentConfigService.delete_tournament(db, tournament_id)
        return {"status": "deleted", "tournament_id": tournament_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Health ────────────────────────────────────────────────────────

@router.get("/health")
async def admin_health():
    """Admin API health check."""
    return {"status": "ok", "module": "admin"}