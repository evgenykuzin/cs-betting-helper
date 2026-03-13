"""
Telegram notifications via aiogram.
Sends alerts to all authorized users.
"""

import structlog
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.authorized_users_service import AuthorizedUsersService

log = structlog.get_logger()

_bot: Bot | None = None


def _get_bot() -> Bot:
    global _bot
    if _bot is None:
        s = get_settings()
        _bot = Bot(token=s.telegram_bot_token)
    return _bot


SEVERITY_EMOJI = {
    "critical": "🚨",
    "warning": "⚠️",
    "info": "ℹ️",
}


async def send_signal_alert(signal: dict, match_label: str, tournament: str):
    """Send a formatted alert to all authorized Telegram users."""
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("telegram_bot_token_not_configured")
        return

    emoji = SEVERITY_EMOJI.get(signal.get("severity", "info"), "📌")
    kind = signal["kind"].replace("_", " ").title()
    meta = signal.get("meta", {})

    lines = [
        f"{emoji} <b>{kind}</b>",
        f"🎮 {match_label}",
        f"🏆 {tournament}",
        "",
        signal["title"],
    ]

    if "profit_pct" in meta:
        lines.append(f"\n💰 Profit: <b>{meta['profit_pct']:.2f}%</b>")
        lines.append(f"📊 {meta.get('bk1','')} @ {meta.get('odds1','')} (stake ${meta.get('stake1','')})")
        lines.append(f"📊 {meta.get('bk2','')} @ {meta.get('odds2','')} (stake ${meta.get('stake2','')})")

    if "pct" in meta:
        lines.append(f"\n📉 Change: <b>{meta['pct']:+.1f}%</b>")
        lines.append(f"📊 {meta.get('bookmaker','')}: {meta.get('old','')} → {meta.get('new','')}")

    if "books" in meta:
        lines.append(f"\n📚 Books moved: {', '.join(meta['books'])}")

    text = "\n".join(lines)

    # Get all authorized users from DB
    factory = get_session_factory()
    async with factory() as session:
        authorized_users = await AuthorizedUsersService.get_all_active(session)
        
        if not authorized_users:
            log.warning("no_authorized_users_for_alerts")
            return

        bot = _get_bot()
        sent_count = 0
        failed_count = 0

        for user in authorized_users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML"
                )
                sent_count += 1
                log.debug("alert_sent_to_user", telegram_id=user.telegram_id, kind=signal["kind"])
            except Exception as e:
                failed_count += 1
                log.warning("alert_send_failed", telegram_id=user.telegram_id, error=str(e))

        log.info("telegram_alerts_sent", total=len(authorized_users), sent=sent_count, failed=failed_count, kind=signal["kind"])


async def send_message(text: str):
    """Send raw message to all authorized users."""
    s = get_settings()
    if not s.telegram_bot_token:
        return

    factory = get_session_factory()
    async with factory() as session:
        authorized_users = await AuthorizedUsersService.get_all_active(session)

    if not authorized_users:
        return

    bot = _get_bot()
    for user in authorized_users:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception:
            log.exception("telegram_send_error", telegram_id=user.telegram_id)
