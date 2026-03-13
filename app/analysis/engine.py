"""
Unified analysis engine.

Focuses on detecting suspicious odds movements (steam moves).
Two detection modes:
  Mode A — Cross-bookmaker divergence (sharp vs soft books disagree)
  Mode B — Temporal multi-book drop (many books drop odds between polling cycles)
"""

import statistics
from typing import Any

from app.core.config import Settings


# ─── helpers ──────────────────────────────────────────────────────────

def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def _implied_prob(odds: float) -> float:
    return 1.0 / odds if odds > 0 else 0.0


# ─── Odds Comparison (utility, used by UI) ───────────────────────────

def compare_odds(snapshots: list[dict]) -> dict:
    """
    Given latest snapshot per bookmaker, return structured comparison.
    Used by API/UI for display.
    """
    if not snapshots:
        return {}

    t1_odds = {s["bookmaker"]: s["team1_odds"] for s in snapshots}
    t2_odds = {s["bookmaker"]: s["team2_odds"] for s in snapshots}

    best_t1_bk = max(t1_odds, key=t1_odds.get)
    best_t2_bk = max(t2_odds, key=t2_odds.get)

    all_t1 = list(t1_odds.values())
    all_t2 = list(t2_odds.values())

    return {
        "team1_odds": t1_odds,
        "team2_odds": t2_odds,
        "best_team1": {"bookmaker": best_t1_bk, "odds": t1_odds[best_t1_bk]},
        "best_team2": {"bookmaker": best_t2_bk, "odds": t2_odds[best_t2_bk]},
        "market_avg_team1": statistics.mean(all_t1) if all_t1 else 0,
        "market_avg_team2": statistics.mean(all_t2) if all_t2 else 0,
        "spread_team1": max(all_t1) - min(all_t1) if all_t1 else 0,
        "spread_team2": max(all_t2) - min(all_t2) if all_t2 else 0,
        "bookmaker_count": len(snapshots),
    }


# ─── Bookmaker Classification ───────────────────────────────────────

# Sharp books: no/high limits, react fast to insider money
SHARP_BOOKS = {
    "pinnacle", "betfair", "singbet", "sbobet",
    "matchbook", "inbet", "asianodds", "bookmaker.eu",
}

# Soft books: mainstream, follow the market, adjust slower
SOFT_BOOKS = {
    "vave", "vbet", "betika", "dafabet",
    "betway", "betway.es",
    "unibet", "unibet.dk", "unibet.ie", "unibet.ro", "unibet.se", "unibet.com.au",
    "casumo", "leovegas", "leovegas.es",
    "betplay", "betrivers", "tabtouch", "sportybet",
    "scooore.be", "bingoal.be", "rushbet.co", "stake.bet.br",
    "betmgm.co.uk", "svenskaspel",
    "polymarket", "lottoland", "paddypower",
}


# ─── Main Detector: Suspicious Consensus ────────────────────────────

def detect_consensus(
    current: list[dict],
    previous: list[dict],
    cfg: Settings,
) -> list[dict]:
    """
    Two-mode consensus detection:

    Mode A — Snapshot divergence (no previous needed):
        Sharp books give significantly different odds than soft books.
        Indicates sharp money has already moved the line.

    Mode B — Temporal multi-book drop (requires previous):
        Multiple bookmakers dropped odds on same team between cycles.
        Indicates coordinated steam move.
    """
    signals = []

    # ── Mode A: Sharp vs Soft divergence ──────────────────────────────
    if len(current) >= 4:
        for team_key, team_label, opponent_label in [
            ("team1_odds", "Team 1", "Team 2"),
            ("team2_odds", "Team 2", "Team 1"),
        ]:
            soft_odds = {
                s["bookmaker"]: s[team_key]
                for s in current
                if s["bookmaker"] in SOFT_BOOKS and s[team_key] > 0
            }
            sharp_odds = {
                s["bookmaker"]: s[team_key]
                for s in current
                if s["bookmaker"] in SHARP_BOOKS and s[team_key] > 0
            }
            # Also check non-classified books for outliers
            other_odds = {
                s["bookmaker"]: s[team_key]
                for s in current
                if s["bookmaker"] not in SOFT_BOOKS
                and s["bookmaker"] not in SHARP_BOOKS
                and s[team_key] > 0
            }

            if len(soft_odds) < 2:
                continue

            avg_soft = statistics.mean(soft_odds.values())
            if avg_soft == 0:
                continue

            # Find ALL books that diverge heavily from soft consensus
            # (odds > 2x soft average = massive divergence)
            all_non_soft = {**sharp_odds, **other_odds}
            divergent_books = {
                bk: odds for bk, odds in all_non_soft.items()
                if odds > avg_soft * 2.0
            }

            if len(divergent_books) >= cfg.suspicious_books_moved:
                divergent_avg = statistics.mean(divergent_books.values())

                # Build detailed per-book breakdown
                book_details = []
                for bk, odds in sorted(divergent_books.items(), key=lambda x: -x[1]):
                    diff = _pct_change(avg_soft, odds)
                    book_details.append({
                        "bookmaker": bk,
                        "odds": round(odds, 3),
                        "diff_pct": round(diff, 1),
                    })

                signals.append({
                    "kind": "suspicious",
                    "severity": "critical",
                    "mode": "A",
                    "title": (
                        f"Sharp vs Soft divergence on {team_label}: "
                        f"{len(divergent_books)} books @ avg {divergent_avg:.2f} "
                        f"vs market {avg_soft:.2f}"
                    ),
                    "meta": {
                        "team": team_key,
                        "team_label": team_label,
                        "prediction": opponent_label,
                        "soft_avg": round(avg_soft, 3),
                        "divergent_avg": round(divergent_avg, 3),
                        "divergent_count": len(divergent_books),
                        "soft_count": len(soft_odds),
                        "total_books": len(current),
                        "book_details": book_details,
                        "mode": "A",
                    },
                })

            elif len(divergent_books) >= 2:
                divergent_avg = statistics.mean(divergent_books.values())

                book_details = []
                for bk, odds in sorted(divergent_books.items(), key=lambda x: -x[1]):
                    diff = _pct_change(avg_soft, odds)
                    book_details.append({
                        "bookmaker": bk,
                        "odds": round(odds, 3),
                        "diff_pct": round(diff, 1),
                    })

                signals.append({
                    "kind": "consensus_move",
                    "severity": "warning",
                    "mode": "A",
                    "title": (
                        f"Divergence on {team_label}: "
                        f"{len(divergent_books)} books @ avg {divergent_avg:.2f} "
                        f"vs market {avg_soft:.2f}"
                    ),
                    "meta": {
                        "team": team_key,
                        "team_label": team_label,
                        "prediction": opponent_label,
                        "soft_avg": round(avg_soft, 3),
                        "divergent_avg": round(divergent_avg, 3),
                        "divergent_count": len(divergent_books),
                        "soft_count": len(soft_odds),
                        "total_books": len(current),
                        "book_details": book_details,
                        "mode": "A",
                    },
                })

    # ── Mode B: Temporal multi-book drop ──────────────────────────────
    if previous:
        prev_map = {s["bookmaker"]: s for s in previous}
        cur_map = {s["bookmaker"]: s for s in current}

        for team_key, team_label in [("team1_odds", "Team 1"), ("team2_odds", "Team 2")]:
            opposite_team = "Team 2" if team_label == "Team 1" else "Team 1"

            # Collect per-book drop details
            book_drops = []
            total_compared = 0

            for cur in current:
                bk = cur["bookmaker"]
                if bk not in prev_map:
                    continue
                total_compared += 1
                old_val = prev_map[bk][team_key]
                new_val = cur[team_key]
                pct = _pct_change(old_val, new_val)

                if pct < -5:  # >5% drop since last cycle
                    book_drops.append({
                        "bookmaker": bk,
                        "old_odds": round(old_val, 3),
                        "new_odds": round(new_val, 3),
                        "drop_pct": round(pct, 1),
                    })

            if not book_drops:
                continue

            # Sort by biggest drop first
            book_drops.sort(key=lambda x: x["drop_pct"])
            avg_drop = statistics.mean([d["drop_pct"] for d in book_drops])

            # Calculate current market average for this team
            all_current_odds = [s[team_key] for s in current if s[team_key] > 0]
            market_avg = statistics.mean(all_current_odds) if all_current_odds else 0

            if len(book_drops) >= cfg.suspicious_books_moved:
                signals.append({
                    "kind": "suspicious",
                    "severity": "critical",
                    "mode": "B",
                    "title": (
                        f"Steam Move: {len(book_drops)} of {total_compared} books "
                        f"dropped on {team_label} (avg {avg_drop:+.1f}%)"
                    ),
                    "meta": {
                        "team": team_key,
                        "team_label": team_label,
                        "prediction": opposite_team,
                        "books_dropped": len(book_drops),
                        "total_compared": total_compared,
                        "total_books": len(current),
                        "avg_drop_pct": round(avg_drop, 1),
                        "market_avg": round(market_avg, 3),
                        "book_details": book_drops[:10],  # Top 10 biggest drops
                        "all_books": [d["bookmaker"] for d in book_drops],
                        "mode": "B",
                    },
                })

            elif len(book_drops) >= 3:
                signals.append({
                    "kind": "consensus_move",
                    "severity": "warning",
                    "mode": "B",
                    "title": (
                        f"Consensus Move: {len(book_drops)} of {total_compared} books "
                        f"dropped on {team_label} (avg {avg_drop:+.1f}%)"
                    ),
                    "meta": {
                        "team": team_key,
                        "team_label": team_label,
                        "prediction": opposite_team,
                        "books_dropped": len(book_drops),
                        "total_compared": total_compared,
                        "total_books": len(current),
                        "avg_drop_pct": round(avg_drop, 1),
                        "market_avg": round(market_avg, 3),
                        "book_details": book_drops[:10],
                        "all_books": [d["bookmaker"] for d in book_drops],
                        "mode": "B",
                    },
                })

    return signals


# ─── Run all detectors ────────────────────────────────────────────────

def run_all(
    current_snapshots: list[dict],
    previous_snapshots: list[dict] | None = None,
    cfg: Settings | None = None,
) -> list[dict]:
    """Run every detector and return flat list of signals."""
    from app.core.config import get_settings
    cfg = cfg or get_settings()
    previous_snapshots = previous_snapshots or []
    signals: list[dict] = []

    # Only suspicious/consensus detection — focused on steam moves
    signals.extend(detect_consensus(current_snapshots, previous_snapshots, cfg))

    return signals
