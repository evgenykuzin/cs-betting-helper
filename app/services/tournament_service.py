"""Tournament configuration service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TournamentConfig


class TournamentConfigService:
    """Manage tournament whitelists and tiers."""

    # Default tournaments from Amy's curated list (Tier 2 - analyzed by default)
    DEFAULT_TOURNAMENTS = [
        (23873, "CCT South America", "tier2"),
        (43533, "CCT European Series", "tier2"),
        (43539, "CCT North American Series", "tier2"),
        (44293, "Exort Series", "tier2"),
        (44609, "United21", "tier2"),
        (49568, "NODWIN Clutch Series", "tier2"),
        (13661, "ESEA Premier Division", "tier2"),
        (44751, "Game Zone Masters", "tier2"),
        (43553, "ESL Challenger League Europe", "tier2"),
        (43005, "YaLLa Compass", "tier2"),
        (45693, "Dust2.dk Ligaen", "tier2"),
        (43709, "European Pro League", "tier2"),
        (47277, "The Proving Grounds", "tier2"),
        (47429, "Winline Insight", "tier2"),
        (44607, "Galaxy Battle", "tier2"),
        (44391, "A1 Gaming League", "tier2"),
        (43547, "ESL Challenger League South America", "tier2"),
        (43545, "ESL Challenger League North America", "tier2"),
        (49600, "JB Pro League", "tier2"),
        (44605, "Svenska Cupen", "tier2"),
        (46885, "Y-Games PRO Series", "tier2"),
        (43517, "Hell Cup", "tier2"),
    ]

    # Tier 1 majors to exclude
    TIER1_TOURNAMENTS = [
        (2392, "ESL Pro League", "tier1"),
        (2414, "Intel Extreme Masters", "tier1"),
        (31621, "Blast Premier Series", "tier1"),
        (16634, "PGL Major", "tier1"),
        (43257, "Esports World Cup", "tier1"),
    ]

    @staticmethod
    async def initialize_defaults(session: AsyncSession) -> None:
        """
        Seed default tournaments on first run.
        Idempotent: won't create duplicates (checks before insert).
        Only runs if table is empty — safety check against accidental data loss.
        """
        import structlog
        log = structlog.get_logger()

        # Check if tournaments table already has data
        result = await session.execute(select(TournamentConfig))
        existing_count = len(result.scalars().all())

        if existing_count > 0:
            log.debug("tournament_defaults_already_seeded", existing_count=existing_count)
            return  # Already seeded, skip

        log.info("tournament_defaults_seeding_start")
        all_tournaments = TournamentConfigService.DEFAULT_TOURNAMENTS + TournamentConfigService.TIER1_TOURNAMENTS
        added_count = 0

        for tournament_id, tournament_name, tier in all_tournaments:
            config = TournamentConfig(
                tournament_id=tournament_id,
                tournament_name=tournament_name,
                tier=tier,
                enabled=(tier != "tier1"),  # Tier1 disabled by default
            )
            session.add(config)
            added_count += 1

        try:
            await session.commit()
            log.info("tournament_defaults_seeded", added_count=added_count)
        except Exception as e:
            log.error("tournament_defaults_seed_failed", error=str(e), exc_info=True)
            await session.rollback()
            raise

    @staticmethod
    async def get_enabled_tournaments(
        session: AsyncSession,
        exclude_tier: str | None = None,
    ) -> list[TournamentConfig]:
        """
        Get all enabled tournaments, optionally excluding a tier.

        Args:
            session: DB session
            exclude_tier: if 'tier1', exclude Tier 1 majors

        Returns:
            List of enabled TournamentConfig rows
        """
        query = select(TournamentConfig).where(TournamentConfig.enabled == True)

        if exclude_tier:
            query = query.where(TournamentConfig.tier != exclude_tier)

        result = await session.execute(query.order_by(TournamentConfig.tournament_id))
        return result.scalars().all()

    @staticmethod
    async def toggle_tournament(
        session: AsyncSession,
        tournament_id: int,
        enabled: bool,
    ) -> TournamentConfig:
        """Enable/disable a tournament. Enabled must be bool, not None."""
        if enabled is None:
            raise ValueError("enabled must be True or False, not None")

        result = await session.execute(
            select(TournamentConfig).where(TournamentConfig.tournament_id == tournament_id)
        )
        config = result.scalars().first()
        if not config:
            raise ValueError(f"Tournament {tournament_id} not found")

        config.enabled = bool(enabled)
        session.add(config)
        await session.commit()
        return config

    @staticmethod
    async def add_tournament(
        session: AsyncSession,
        tournament_id: int,
        tournament_name: str,
        tier: str = "tier2",
        enabled: bool = True,
    ) -> TournamentConfig:
        """Add a new tournament to the config."""
        # Check duplicate
        result = await session.execute(
            select(TournamentConfig).where(TournamentConfig.tournament_id == tournament_id)
        )
        if result.scalars().first():
            raise ValueError(f"Tournament {tournament_id} already exists")

        config = TournamentConfig(
            tournament_id=tournament_id,
            tournament_name=tournament_name,
            tier=tier,
            enabled=enabled,
        )
        session.add(config)
        await session.commit()
        return config

    @staticmethod
    async def delete_tournament(
        session: AsyncSession,
        tournament_id: int,
    ) -> None:
        """Delete a tournament from the config."""
        result = await session.execute(
            select(TournamentConfig).where(TournamentConfig.tournament_id == tournament_id)
        )
        config = result.scalars().first()
        if not config:
            raise ValueError(f"Tournament {tournament_id} not found")

        await session.delete(config)
        await session.commit()

    @staticmethod
    async def get_tournament_ids_string(
        session: AsyncSession,
        exclude_tier: str | None = "tier1",
    ) -> str:
        """
        Get enabled tournaments as comma-separated ID string for API calls.
        Default: exclude Tier1 majors.
        """
        tournaments = await TournamentConfigService.get_enabled_tournaments(
            session, exclude_tier=exclude_tier
        )
        return ",".join(str(t.tournament_id) for t in tournaments)
