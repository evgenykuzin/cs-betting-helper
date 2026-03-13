"""Manage authorized Telegram users for alerts."""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthorizedUser

log = structlog.get_logger()


class AuthorizedUsersService:
    """Manage authorized Telegram users."""

    # Default authorized user IDs (hardcoded for now, can move to config)
    DEFAULT_AUTHORIZED_IDS = [
        (328018558, "jekajops", "Евгений"),  # Евгений
        (343305553, "amywrenfanboy", "Amy"),  # Amy
    ]

    @staticmethod
    async def initialize_defaults(session: AsyncSession) -> None:
        """Seed default authorized users on first run."""
        # Check if we already have users
        result = await session.execute(select(AuthorizedUser))
        existing_count = len(result.scalars().all())

        if existing_count > 0:
            log.debug("authorized_users_already_seeded", existing_count=existing_count)
            return

        log.info("authorized_users_seeding_start")
        added_count = 0

        for telegram_id, username, first_name in AuthorizedUsersService.DEFAULT_AUTHORIZED_IDS:
            user = AuthorizedUser(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                enabled=True,
                receive_alerts=True,
            )
            session.add(user)
            added_count += 1

        try:
            await session.commit()
            log.info("authorized_users_seeded", added_count=added_count)
        except Exception as e:
            log.error("authorized_users_seed_failed", error=str(e), exc_info=True)
            await session.rollback()
            raise

    @staticmethod
    async def add_user(
        session: AsyncSession,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> AuthorizedUser:
        """Add or update an authorized user."""
        result = await session.execute(
            select(AuthorizedUser).where(AuthorizedUser.telegram_id == telegram_id)
        )
        user = result.scalars().first()

        if user:
            user.username = username or user.username
            user.first_name = first_name or user.first_name
            user.enabled = True
            user.receive_alerts = True
            log.debug("user_updated", telegram_id=telegram_id)
        else:
            user = AuthorizedUser(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                enabled=True,
                receive_alerts=True,
            )
            session.add(user)
            log.info("user_added", telegram_id=telegram_id, username=username)

        await session.commit()
        return user

    @staticmethod
    async def get_all_active(session: AsyncSession) -> list[AuthorizedUser]:
        """Get all users enabled and receiving alerts."""
        result = await session.execute(
            select(AuthorizedUser)
            .where(AuthorizedUser.enabled == True, AuthorizedUser.receive_alerts == True)
            .order_by(AuthorizedUser.telegram_id)
        )
        return result.scalars().all()

    @staticmethod
    async def toggle_alerts(session: AsyncSession, telegram_id: int, enabled: bool) -> AuthorizedUser:
        """Enable/disable alerts for a user."""
        result = await session.execute(
            select(AuthorizedUser).where(AuthorizedUser.telegram_id == telegram_id)
        )
        user = result.scalars().first()

        if not user:
            raise ValueError(f"User {telegram_id} not found")

        user.receive_alerts = enabled
        session.add(user)
        await session.commit()
        log.info("alerts_toggled", telegram_id=telegram_id, enabled=enabled)
        return user

    @staticmethod
    async def get_user_count(session: AsyncSession) -> int:
        """Count total active users."""
        result = await session.execute(
            select(AuthorizedUser).where(AuthorizedUser.enabled == True)
        )
        return len(result.scalars().all())
