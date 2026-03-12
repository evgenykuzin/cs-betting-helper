"""
Service for managing admin and signal configs.
Refactored for production: type-safe, Pydantic-friendly, async-consistent.
"""

from typing import Any, Optional, List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SignalConfig, AdminConfig


class SignalConfigService:
    """Manage signal routing configurations (Telegram, etc.)"""

    @staticmethod
    async def get_or_create_default(db: AsyncSession) -> List[SignalConfig]:
        """Initialize default signal configs if empty."""
        existing = await db.execute(select(SignalConfig))
        existing_configs = existing.scalars().all()
        if existing_configs:
            return existing_configs

        defaults = [
            SignalConfig(kind="arbitrage", severity="warning", enabled=True, send_telegram=True, description="Low-profit arbitrage"),
            SignalConfig(kind="arbitrage", severity="critical", enabled=True, send_telegram=True, description="High-profit arbitrage (>3%)"),
            SignalConfig(kind="steam_move", severity="warning", enabled=True, send_telegram=True, description="Odds drop/spike"),
            SignalConfig(kind="steam_move", severity="critical", enabled=True, send_telegram=True, description="Extreme odds movement"),
            SignalConfig(kind="suspicious", severity="critical", enabled=True, send_telegram=True, description="Multi-book consensus drop"),
            SignalConfig(kind="consensus_move", severity="warning", enabled=True, send_telegram=False, description="3+ books moved odds"),
            SignalConfig(kind="value_bet", severity="info", enabled=True, send_telegram=False, description="Soft book premium"),
            SignalConfig(kind="underdog_drop", severity="warning", enabled=True, send_telegram=True, description="Underdog odds collapsing"),
        ]
        db.add_all(defaults)
        await db.commit()
        for cfg in defaults:
            await db.refresh(cfg)
        return defaults

    @staticmethod
    async def get_all(db: AsyncSession) -> List[SignalConfig]:
        result = await db.execute(select(SignalConfig).order_by(SignalConfig.kind, SignalConfig.severity))
        return result.scalars().all()

    @staticmethod
    async def get_by_kind_severity(db: AsyncSession, kind: str, severity: str) -> Optional[SignalConfig]:
        result = await db.execute(
            select(SignalConfig).where(SignalConfig.kind == kind, SignalConfig.severity == severity)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def should_send_telegram(db: AsyncSession, kind: str, severity: str) -> bool:
        cfg = await SignalConfigService.get_by_kind_severity(db, kind, severity)
        return bool(cfg and cfg.enabled and cfg.send_telegram)

    @staticmethod
    async def update(
        db: AsyncSession,
        kind: str,
        severity: str,
        enabled: Optional[bool] = None,
        send_telegram: Optional[bool] = None,
        description: Optional[str] = None,
        config_json: Optional[Dict] = None,
    ) -> Optional[SignalConfig]:
        """Update signal config and return the updated object."""
        cfg = await SignalConfigService.get_by_kind_severity(db, kind, severity)
        if not cfg:
            return None

        if enabled is not None:
            cfg.enabled = enabled
        if send_telegram is not None:
            cfg.send_telegram = send_telegram
        if description is not None:
            cfg.description = description
        if config_json is not None:
            cfg.config_json = config_json

        await db.commit()
        await db.refresh(cfg)
        return cfg


class AdminConfigService:
    """Manage global admin settings (polling intervals, thresholds, retention, etc.)"""

    @staticmethod
    async def get_or_create_defaults(db: AsyncSession) -> List[AdminConfig]:
        """Initialize default admin configs if empty."""
        existing = await db.execute(select(AdminConfig))
        existing_configs = existing.scalars().all()
        if existing_configs:
            return existing_configs

        defaults = [
            AdminConfig(key="poll_interval_seconds", value=60, category="polling", description="How often to poll odds (seconds)"),
            AdminConfig(key="arbitrage_min_profit_pct", value=0.5, category="analysis", description="Minimum arbitrage profit to report (%)"),
            AdminConfig(key="anomaly_drop_pct", value=3.0, category="analysis", description="Odds drop threshold for steam detection (%)"),
            AdminConfig(key="suspicious_drop_pct", value=10.0, category="analysis", description="Threshold for critical steam alerts (%)"),
            AdminConfig(key="suspicious_books_moved", value=5, category="analysis", description="Number of books needed for 'suspicious' alert"),
            AdminConfig(key="value_bet_threshold_pct", value=3.0, category="analysis", description="Min soft-book premium to report as value (%)"),
            AdminConfig(key="odds_retention_days", value=7, category="retention", description="Keep odds snapshots for N days"),
            AdminConfig(key="log_retention_days_info", value=7, category="retention", description="Keep INFO/WARNING logs for N days"),
            AdminConfig(key="log_retention_days_error", value=30, category="retention", description="Keep ERROR logs for N days"),
        ]

        db.add_all(defaults)
        await db.commit()
        for cfg in defaults:
            await db.refresh(cfg)
        return defaults

    @staticmethod
    async def get(db: AsyncSession, key: str) -> Optional[AdminConfig]:
        result = await db.execute(select(AdminConfig).where(AdminConfig.key == key))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_category(db: AsyncSession, category: str) -> List[AdminConfig]:
        result = await db.execute(
            select(AdminConfig).where(AdminConfig.category == category).order_by(AdminConfig.key)
        )
        return result.scalars().all()

    @staticmethod
    async def get_all(db: AsyncSession) -> List[AdminConfig]:
        result = await db.execute(select(AdminConfig).order_by(AdminConfig.category, AdminConfig.key))
        return result.scalars().all()

    @staticmethod
    async def set(
        db: AsyncSession,
        key: str,
        value: Any,
        category: str = "general",
        description: Optional[str] = None,
    ) -> AdminConfig:
        """Set or update a config and return the object."""
        cfg = await AdminConfigService.get(db, key)
        if cfg:
            cfg.value = value
            if description:
                cfg.description = description
        else:
            cfg = AdminConfig(key=key, value=value, category=category, description=description)
            db.add(cfg)

        await db.commit()
        await db.refresh(cfg)
        return cfg

    @staticmethod
    async def get_value(db: AsyncSession, key: str, default: Any = None) -> Any:
        cfg = await AdminConfigService.get(db, key)
        return cfg.value if cfg else default