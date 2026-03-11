"""
Telegram notifications via aiogram.
"""

import structlog
from aiogram import Bot
from app.core.config import get_settings

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
    """Send a formatted alert to Telegram."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        log.warning("telegram_not_configured")
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

    try:
        bot = _get_bot()
        await bot.send_message(chat_id=s.telegram_chat_id, text=text, parse_mode="HTML")
        log.info("telegram_sent", kind=signal["kind"])
    except Exception:
        log.exception("telegram_send_error")


async def send_message(text: str):
    """Send raw message."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return
    try:
        bot = _get_bot()
        await bot.send_message(chat_id=s.telegram_chat_id, text=text, parse_mode="HTML")
    except Exception:
        log.exception("telegram_send_error")
