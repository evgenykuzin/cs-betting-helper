"""
Telegram notifications — rich signal cards with i18n (en/ru).
Sends alerts to all authorized users.
"""

import statistics
from datetime import datetime, timezone

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


# ─── i18n ─────────────────────────────────────────────────────────────

LANG = {
    "en": {
        "steam_move": "🚨 STEAM MOVE",
        "sharp_vs_soft": "⚠️ SHARP VS SOFT",
        "consensus_move": "⚠️ CONSENSUS MOVE",
        "divergence": "⚠️ DIVERGENCE",
        "start": "Start",
        "prematch": "Prematch",
        "books_dropped": "{n} of {total} bookmakers dropped odds\non <b>{team}</b>",
        "books_diverge": "{n} bookmakers diverge from market\non <b>{team}</b>",
        "was": "Was",
        "now": "Now",
        "avg_drop": "Avg drop",
        "soft_avg": "Market avg ({n} books)",
        "divergent_avg": "Divergent avg ({n} books)",
        "conclusion_steam": (
            "⚡ <b>Conclusion:</b> Massive synchronized odds drop "
            "on the underdog. Sharp money entered on <b>{team}</b>."
        ),
        "conclusion_divergence": (
            "⚡ <b>Conclusion:</b> Sharp bookmakers already lowered "
            "odds on <b>{team}</b>. Soft books haven't caught up yet. "
            "Expect further line movement."
        ),
        "conclusion_consensus": (
            "⚡ <b>Conclusion:</b> Several bookmakers are moving "
            "in the same direction on <b>{team}</b>. Worth monitoring."
        ),
        "more_books": "... +{n} more",
    },
    "ru": {
        "steam_move": "🚨 STEAM MOVE",
        "sharp_vs_soft": "⚠️ SHARP VS SOFT",
        "consensus_move": "⚠️ ДВИЖЕНИЕ ЛИНИИ",
        "divergence": "⚠️ РАСХОЖДЕНИЕ",
        "start": "Старт",
        "prematch": "Прематч",
        "books_dropped": "{n} из {total} букмекеров дропнули кэф\nна <b>{team}</b>",
        "books_diverge": "{n} букмекеров расходятся с рынком\nна <b>{team}</b>",
        "was": "Было",
        "now": "Стало",
        "avg_drop": "Средний дроп",
        "soft_avg": "Средний рынок ({n} буков)",
        "divergent_avg": "Средний расхождение ({n} буков)",
        "conclusion_steam": (
            "⚡ <b>Вывод:</b> Массовое синхронное снижение кэфа "
            "на андердога. Профессиональные деньги зашли на <b>{team}</b>."
        ),
        "conclusion_divergence": (
            "⚡ <b>Вывод:</b> Шарп-букмекеры уже снизили кэф "
            "на <b>{team}</b>. Софты ещё не догнали. "
            "Ожидается дальнейшее падение линии."
        ),
        "conclusion_consensus": (
            "⚡ <b>Вывод:</b> Несколько букмекеров двигаются "
            "в одном направлении на <b>{team}</b>. Стоит отслеживать."
        ),
        "more_books": "... ещё {n}",
    },
}

DEFAULT_LANG = "en"


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Translate a key with optional format args."""
    text = LANG.get(lang, LANG[DEFAULT_LANG]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


# ─── Card Formatters ─────────────────────────────────────────────────

def _format_time_utc(dt: datetime) -> str:
    """Format datetime as 'DD Mon, HH:MM UTC'."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{dt.day} {months[dt.month - 1]}, {dt.strftime('%H:%M')} UTC"


def _get_market_avg(current_odds: list[dict], team_key: str) -> float:
    """Calculate market average for a team from current snapshots."""
    vals = [s[team_key] for s in current_odds if s.get(team_key, 0) > 0]
    return round(statistics.mean(vals), 2) if vals else 0


def format_mode_b_card(signal: dict, match_ctx: dict, lang: str = DEFAULT_LANG) -> str:
    """
    Format Mode B (Temporal Drop / Steam Move) card.

    🚨 STEAM MOVE │ CCT European Series
    ⚔️  Sangal eSports vs Ex-Zero Tenacity
    ⏰  Start: 13 Mar, 19:00 UTC
    📊  Prematch: 1.45 : 2.70
    🔻  19 of 26 bookmakers dropped odds on Ex-Zero Tenacity
        Was     Now      Δ
        2.95 →  2.70   -8.5%  │ unibet
        ...
    ⚡  Conclusion: ...
    """
    meta = signal.get("meta", {})
    team1 = match_ctx.get("team1", "Team 1")
    team2 = match_ctx.get("team2", "Team 2")
    tournament = match_ctx.get("tournament", "")
    start_time = match_ctx.get("start_time")
    current_odds = match_ctx.get("current_odds", [])

    # Determine which team is affected
    team_label = meta.get("team_label", "Team 1")
    affected_team = team1 if team_label == "Team 1" else team2
    prediction = team1 if meta.get("prediction") == "Team 1" else team2

    # Market averages
    avg_t1 = _get_market_avg(current_odds, "team1_odds")
    avg_t2 = _get_market_avg(current_odds, "team2_odds")

    # Header
    is_critical = signal.get("severity") == "critical"
    header = t("steam_move", lang) if is_critical else t("consensus_move", lang)

    lines = [
        f"{header} │ {tournament}",
        "",
        f"⚔️  <b>{team1}</b> vs <b>{team2}</b>",
        f"⏰  {t('start', lang)}: {_format_time_utc(start_time)}",
        f"📊  {t('prematch', lang)}: <b>{avg_t1}</b> : <b>{avg_t2}</b>",
        "",
        f"🔻 {t('books_dropped', lang, n=meta.get('books_dropped', 0), total=meta.get('total_compared', 0), team=affected_team)}",
        "",
    ]

    # Per-book breakdown table
    book_details = meta.get("book_details", [])
    lines.append(f"<pre>  {t('was', lang):>6}  →  {t('now', lang):<6}    Δ")
    lines.append(f"  {'─' * 32}")

    shown = 0
    for bd in book_details[:8]:
        bk = bd["bookmaker"]
        old = bd["old_odds"]
        new = bd["new_odds"]
        drop = bd["drop_pct"]
        lines.append(f"  {old:>6.2f}  →  {new:<6.2f}  {drop:>+5.1f}%  │ {bk}")
        shown += 1

    remaining = len(meta.get("all_books", [])) - shown
    if remaining > 0:
        lines.append(f"  {t('more_books', lang, n=remaining)}")

    lines.append("</pre>")

    # Average drop
    avg_drop = meta.get("avg_drop_pct", 0)
    lines.append(f"\n📉 {t('avg_drop', lang)}: <b>{avg_drop:+.1f}%</b>")

    # Conclusion
    if is_critical:
        conclusion = t("conclusion_steam", lang, team=prediction)
    else:
        conclusion = t("conclusion_consensus", lang, team=affected_team)
    lines.append(f"\n{conclusion}")

    return "\n".join(lines)


def format_mode_a_card(signal: dict, match_ctx: dict, lang: str = DEFAULT_LANG) -> str:
    """
    Format Mode A (Sharp vs Soft Divergence) card.

    ⚠️ SHARP VS SOFT │ Exort Series
    ⚔️  MOUZ NXT vs Apogee
    ⏰  Start: 14 Mar, 15:00 UTC
    📊  Prematch: 1.72 : 2.15
    🔍  3 bookmakers diverge from market on MOUZ NXT
        Book          Odds    vs Market
        pinnacle      1.55    │ -9.9%
        ...
    ⚡  Conclusion: ...
    """
    meta = signal.get("meta", {})
    team1 = match_ctx.get("team1", "Team 1")
    team2 = match_ctx.get("team2", "Team 2")
    tournament = match_ctx.get("tournament", "")
    start_time = match_ctx.get("start_time")
    current_odds = match_ctx.get("current_odds", [])

    # Determine which team
    team_label = meta.get("team_label", "Team 1")
    affected_team = team1 if team_label == "Team 1" else team2
    prediction = team1 if meta.get("prediction") == "Team 1" else team2

    # Market averages
    avg_t1 = _get_market_avg(current_odds, "team1_odds")
    avg_t2 = _get_market_avg(current_odds, "team2_odds")

    # Header
    is_critical = signal.get("severity") == "critical"
    header = t("sharp_vs_soft", lang) if is_critical else t("divergence", lang)

    lines = [
        f"{header} │ {tournament}",
        "",
        f"⚔️  <b>{team1}</b> vs <b>{team2}</b>",
        f"⏰  {t('start', lang)}: {_format_time_utc(start_time)}",
        f"📊  {t('prematch', lang)}: <b>{avg_t1}</b> : <b>{avg_t2}</b>",
        "",
        f"🔍 {t('books_diverge', lang, n=meta.get('divergent_count', 0), team=affected_team)}",
        "",
    ]

    # Per-book breakdown
    book_details = meta.get("book_details", [])
    soft_avg = meta.get("soft_avg", 0)

    lines.append("<pre>  Book              Odds   vs Market")
    lines.append(f"  {'─' * 34}")

    shown = 0
    for bd in book_details[:8]:
        bk = bd["bookmaker"]
        odds = bd["odds"]
        diff = bd["diff_pct"]
        lines.append(f"  {bk:<16}  {odds:<6.2f}  │ {diff:>+5.1f}%")
        shown += 1

    remaining = len(book_details) - shown
    if remaining > 0:
        lines.append(f"  {t('more_books', lang, n=remaining)}")

    lines.append("</pre>")

    # Market context
    lines.append(f"\n📊 {t('soft_avg', lang, n=meta.get('soft_count', 0))}: <b>{soft_avg:.2f}</b>")
    divergent_avg = meta.get("divergent_avg", 0)
    lines.append(f"📊 {t('divergent_avg', lang, n=meta.get('divergent_count', 0))}: <b>{divergent_avg:.2f}</b>")

    # Conclusion
    if is_critical:
        conclusion = t("conclusion_divergence", lang, team=prediction)
    else:
        conclusion = t("conclusion_consensus", lang, team=affected_team)
    lines.append(f"\n{conclusion}")

    return "\n".join(lines)


def format_signal_card(signal: dict, match_ctx: dict, lang: str = DEFAULT_LANG) -> str:
    """Route to the correct card formatter based on signal mode."""
    mode = signal.get("mode") or signal.get("meta", {}).get("mode", "B")

    if mode == "A":
        return format_mode_a_card(signal, match_ctx, lang)
    else:
        return format_mode_b_card(signal, match_ctx, lang)


# ─── Send to All Users ──────────────────────────────────────────────

async def send_signal_alert(signal: dict, match_ctx: dict):
    """Send a formatted signal card to all authorized Telegram users."""
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("telegram_bot_token_not_configured")
        return

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
            # Use user's language preference (default: en)
            lang = getattr(user, "language", None) or DEFAULT_LANG
            text = format_signal_card(signal, match_ctx, lang)

            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
                sent_count += 1
                log.debug("alert_sent_to_user", telegram_id=user.telegram_id, kind=signal.get("kind"))
            except Exception as e:
                failed_count += 1
                log.warning("alert_send_failed", telegram_id=user.telegram_id, error=str(e))

        log.info(
            "telegram_alerts_sent",
            total=len(authorized_users),
            sent=sent_count,
            failed=failed_count,
            kind=signal.get("kind"),
        )


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
                parse_mode="HTML",
            )
        except Exception:
            log.exception("telegram_send_error", telegram_id=user.telegram_id)
