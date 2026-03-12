"""
Service for managing admin and signal configs.
Extensible design: add new config types without changing the DB schema.
"""

import json
from typing import Any, Optional
from sqlalchemy import select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SignalConfig, AdminConfig


class SignalConfigService:
    """Manage signal routing (which signals go to telegram, etc.)"""

    @staticmethod
    async def get_or_create_default(db: AsyncSession) -> None:
        """Initialize default signal configs if empty."""
        count = (await db.execute(select(SignalConfig))).scalars().all()
        if count:
            return

        # Default configs: only high-severity to telegram
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

    @staticmethod
    async def get_all(db: AsyncSession) -> list[SignalConfig]:
        """Fetch all signal configs."""
        result = await db.execute(select(SignalConfig).order_by(SignalConfig.kind, SignalConfig.severity))
        return result.scalars().all()

    @staticmethod
    async def get_by_kind_severity(db: AsyncSession, kind: str, severity: str) -> Optional[SignalConfig]:
        """Fetch specific config."""
        result = await db.execute(
            select(SignalConfig).where(
                (SignalConfig.kind == kind) & (SignalConfig.severity == severity)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def should_send_telegram(db: AsyncSession, kind: str, severity: str) -> bool:
        """Check if this signal should go to telegram."""
        cfg = await SignalConfigService.get_by_kind_severity(db, kind, severity)
        if not cfg:
            return False
        return cfg.enabled and cfg.send_telegram

    @staticmethod
    async def update(
        db: AsyncSession, 
        kind: str, 
        severity: str,
        enabled: bool = None,
        send_telegram: bool = None,
        description: str = None,
        config_json: dict = None,
    ) -> Optional[SignalConfig]:
        """Update signal config."""
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
        return cfg


class AdminConfigService:
    """Manage global admin settings (polling intervals, thresholds, etc.)"""

    @staticmethod
    async def get_or_create_defaults(db: AsyncSession) -> None:
        """Initialize default admin configs if empty."""
        count = (await db.execute(select(AdminConfig))).scalars().all()
        if count:
            return

        # Defaults matching app/core/config.py Settings
        defaults = [
            AdminConfig(
                key="poll_interval_seconds",
                value=60,
                category="polling",
                description="How often to poll odds (seconds)",
            ),
            AdminConfig(
                key="arbitrage_min_profit_pct",
                value=0.5,
                category="analysis",
                description="Minimum arbitrage profit to report (%)",
            ),
            AdminConfig(
                key="anomaly_drop_pct",
                value=3.0,
                category="analysis",
                description="Odds drop threshold for steam detection (%)",
            ),
            AdminConfig(
                key="suspicious_drop_pct",
                value=10.0,
                category="analysis",
                description="Threshold for critical steam alerts (%)",
            ),
            AdminConfig(
                key="suspicious_books_moved",
                value=5,
                category="analysis",
                description="Number of books needed for 'suspicious' alert",
            ),
            AdminConfig(
                key="value_bet_threshold_pct",
                value=3.0,
                category="analysis",
                description="Min soft-book premium to report as value (%)",
            ),
            AdminConfig(
                key="odds_retention_days",
                value=7,
                category="retention",
                description="Keep odds snapshots for N days",
            ),
            AdminConfig(
                key="log_retention_days_info",
                value=7,
                category="retention",
                description="Keep INFO/WARNING logs for N days",
            ),
            AdminConfig(
                key="log_retention_days_error",
                value=30,
                category="retention",
                description="Keep ERROR logs for N days",
            ),
        ]
        db.add_all(defaults)
        await db.commit()

    @staticmethod
    async def get(db: AsyncSession, key: str) -> Optional[AdminConfig]:
        """Fetch single config."""
        result = await db.execute(select(AdminConfig).where(AdminConfig.key == key))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_category(db: AsyncSession, category: str) -> list[AdminConfig]:
        """Fetch configs by category."""
        result = await db.execute(
            select(AdminConfig).where(AdminConfig.category == category).order_by(AdminConfig.key)
        )
        return result.scalars().all()

    @staticmethod
    async def get_all(db: AsyncSession) -> list[AdminConfig]:
        """Fetch all configs."""
        result = await db.execute(select(AdminConfig).order_by(AdminConfig.category, AdminConfig.key))
        return result.scalars().all()

    @staticmethod
    async def set(db: AsyncSession, key: str, value: Any, category: str = "general", description: str = None) -> AdminConfig:
        """Set or update config value."""
        cfg = await AdminConfigService.get(db, key)
        if cfg:
            cfg.value = value
            if description:
                cfg.description = description
        else:
            cfg = AdminConfig(key=key, value=value, category=category, description=description)
            db.add(cfg)
        await db.commit()
        return cfg

    @staticmethod
    async def get_value(db: AsyncSession, key: str, default: Any = None) -> Any:
        """Quick fetch of config value."""
        cfg = await AdminConfigService.get(db, key)
        return cfg.value if cfg else default
