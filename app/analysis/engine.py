"""
Unified analysis engine.

Consumes a list of OddsSnapshot rows for a match and produces Signal dicts.
Each detector is a pure function: (snapshots, config) -> list[signal_dict].

The 28 user-requested features are grouped into ~10 detectors below.
Many features share identical data (e.g. odds comparison, line shopping,
market spread, best odds alert are all projections of the *same* snapshot set).
"""

import json
import statistics
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings


# ─── helpers ──────────────────────────────────────────────────────────

def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def _implied_prob(odds: float) -> float:
    return 1.0 / odds if odds > 0 else 0.0


# ─── 1. Odds Comparison / Line Shopping / Best Odds ──────────────────

def compare_odds(snapshots: list[dict]) -> dict:
    """
    Given latest snapshot per bookmaker, return structured comparison.
    Covers: odds_comparison, line_shopping, best_odds_alert, market_spread.
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


# ─── 2. Arbitrage Scanner ────────────────────────────────────────────

def detect_arbitrage(snapshots: list[dict], cfg: Settings) -> list[dict]:
    """Covers: arbitrage_scanner."""
    signals = []
    if len(snapshots) < 2:
        return signals

    t1 = {s["bookmaker"]: s["team1_odds"] for s in snapshots}
    t2 = {s["bookmaker"]: s["team2_odds"] for s in snapshots}

    best_t1_bk = max(t1, key=t1.get)
    best_t2_bk = max(t2, key=t2.get)

    arb_sum = _implied_prob(t1[best_t1_bk]) + _implied_prob(t2[best_t2_bk])
    if arb_sum < 1.0:
        profit = ((1 / arb_sum) - 1) * 100
        if profit >= cfg.arbitrage_min_profit_pct:
            total = 100.0
            stake1 = total * _implied_prob(t1[best_t1_bk]) / arb_sum
            stake2 = total * _implied_prob(t2[best_t2_bk]) / arb_sum
            signals.append({
                "kind": "arbitrage",
                "severity": "critical" if profit > 3 else "warning",
                "title": f"Arbitrage {profit:.2f}%: {best_t1_bk} vs {best_t2_bk}",
                "meta": {
                    "profit_pct": round(profit, 3),
                    "bk1": best_t1_bk, "odds1": t1[best_t1_bk], "stake1": round(stake1, 2),
                    "bk2": best_t2_bk, "odds2": t2[best_t2_bk], "stake2": round(stake2, 2),
                },
            })
    return signals


# ─── 3. Steam Move / Odds Drop-Spike / Odds Change Alert ────────────

def detect_steam_moves(
    current: list[dict], previous: list[dict], cfg: Settings,
) -> list[dict]:
    """
    Covers: steam_move_detector, odds_drop_spike, odds_change_alerts,
    underdog_movement_tracker.
    """
    signals = []
    prev_map = {s["bookmaker"]: s for s in previous}

    for cur in current:
        bk = cur["bookmaker"]
        if bk not in prev_map:
            continue
        prev = prev_map[bk]

        for team_key, team_label in [("team1_odds", "Team 1"), ("team2_odds", "Team 2")]:
            old_val, new_val = prev[team_key], cur[team_key]
            if old_val == 0:
                continue
            pct = _pct_change(old_val, new_val)

            # Generic odds change alert
            if abs(pct) >= cfg.anomaly_drop_pct:
                sev = "critical" if abs(pct) >= cfg.suspicious_drop_pct else "warning"
                signals.append({
                    "kind": "steam_move",
                    "severity": sev,
                    "title": f"Steam {team_label} @ {bk}: {old_val:.3f}→{new_val:.3f} ({pct:+.1f}%)",
                    "meta": {"bookmaker": bk, "team": team_key, "old": old_val, "new": new_val, "pct": round(pct, 2)},
                })

            # Underdog tracker (odds > 2.5 dropping)
            if old_val > 2.5 and pct < -cfg.anomaly_drop_pct:
                signals.append({
                    "kind": "underdog_drop",
                    "severity": "warning",
                    "title": f"Underdog drop {team_label} @ {bk}: {old_val:.3f}→{new_val:.3f}",
                    "meta": {"bookmaker": bk, "team": team_key, "old": old_val, "new": new_val, "pct": round(pct, 2)},
                })
    return signals


# ─── 4. Value Bet / Sharp vs Soft ────────────────────────────────────

# Sharp books: no/high limits, react fast to insider money, market-makers
# These detect real action first before soft books adjust
SHARP_BOOKS = {
    "pinnacle",      # no limits, hedges through action
    "betfair",       # exchange, true market price
    "singbet",       # asian sharp
    "sbobet",        # asian sharp
    "matchbook",     # exchange
    "inbet",         # known sharp for esports
    "asianodds",     # asian sharp
    "bookmaker.eu",  # professional market
}

# Soft books: mainstream, follow the market, adjust slower
# These are the "herd" that we compare against sharp books
SOFT_BOOKS = {
    "vave", "vbet", "betika", "dafabet",
    "betway", "betway.es",  # mid-tier, soft for niche sports like CS2
    "unibet", "unibet.dk", "unibet.ie", "unibet.ro", "unibet.se", "unibet.com.au",
    "casumo", "leovegas", "leovegas.es",
    "betplay", "betrivers", "tabtouch", "sportybet",
    "scooore.be", "bingoal.be", "rushbet.co", "stake.bet.br",
    "betmgm.co.uk", "svenskaspel",
    "polymarket",  # retail-heavy betting
    "lottoland",   # retail
}

def detect_value_bets(snapshots: list[dict], cfg: Settings) -> list[dict]:
    """
    Covers: value_bet_calculator, sharp_vs_soft_comparison,
    bookmaker_odds_difference_analyzer.
    """
    signals = []
    if len(snapshots) < 3:
        return signals

    for team_key, label in [("team1_odds", "Team 1"), ("team2_odds", "Team 2")]:
        vals = [s[team_key] for s in snapshots if s[team_key] > 0]
        if not vals:
            continue
        market_avg = statistics.mean(vals)

        # sharp average
        sharp_vals = [s[team_key] for s in snapshots if s["bookmaker"] in SHARP_BOOKS and s[team_key] > 0]
        sharp_avg = statistics.mean(sharp_vals) if sharp_vals else market_avg

        # soft books offering more than sharp → value
        for s in snapshots:
            if s["bookmaker"] in SHARP_BOOKS:
                continue
            diff_pct = _pct_change(sharp_avg, s[team_key])
            if diff_pct > cfg.value_bet_threshold_pct:
                signals.append({
                    "kind": "value_bet",
                    "severity": "info",
                    "title": f"Value {label} @ {s['bookmaker']}: {s[team_key]:.3f} vs sharp {sharp_avg:.3f} (+{diff_pct:.1f}%)",
                    "meta": {
                        "bookmaker": s["bookmaker"], "team": team_key,
                        "odds": s[team_key], "sharp_avg": round(sharp_avg, 3),
                        "market_avg": round(market_avg, 3), "diff_pct": round(diff_pct, 2),
                    },
                })
    return signals


# ─── 5. Consensus / Soft-vs-Outlier Divergence ──────────────────────

def detect_consensus(
    current: list[dict],
    previous: list[dict],
    cfg: Settings,
) -> list[dict]:
    """
    Two-mode consensus detection:

    Mode A — Snapshot divergence (no previous needed):
        Compare soft books avg vs outlier books avg for SAME snapshot.
        If outlier books systematically disagree with soft consensus by a
        large margin, this indicates insider money or match-fixing pressure.
        Example: soft books Team1 @ 1.4, but inbet/betway/lottoland @ 5.0+
        → "Outlier books diverge from market on Team1"

    Mode B — Multi-book temporal drop (requires previous):
        If 3+ books all dropped odds on same team between cycles,
        that's a coordinated move (steam / consensus shift).
    """
    signals = []

    # ── Mode A: Snapshot-level soft vs outlier divergence ──────────────
    # Works even on first polling cycle with no previous data.
    if len(current) >= 4:
        for team_key, team_label, opponent_label in [
            ("team1_odds", "Team 1", "Team 2"),
            ("team2_odds", "Team 2", "Team 1"),
        ]:
            soft_odds = [
                s[team_key] for s in current
                if s["bookmaker"] in SOFT_BOOKS and s[team_key] > 0
            ]
            outlier_odds_map = {
                s["bookmaker"]: s[team_key]
                for s in current
                if s["bookmaker"] not in SOFT_BOOKS and s[team_key] > 0
            }

            if len(soft_odds) < 2 or len(outlier_odds_map) < 2:
                continue

            avg_soft = statistics.mean(soft_odds)
            if avg_soft == 0:
                continue

            # Find outlier books that diverge heavily from soft consensus
            # A book is an "outlier" if its odds are > 2x the soft average
            # (meaning soft books think Team1 is likely winner @ ~1.4,
            #  but this book says Team1 is big underdog @ 5.0+)
            divergent_books = {
                bk: odds for bk, odds in outlier_odds_map.items()
                if odds > avg_soft * 2.0
            }

            if len(divergent_books) >= cfg.suspicious_books_moved:
                # Predict: team with LOW odds from outliers wins
                # (outlier books are confident the other team wins)
                divergent_avg = statistics.mean(divergent_books.values())
                signals.append({
                    "kind": "suspicious",
                    "severity": "critical",
                    "title": (
                        f"Suspicious: {len(divergent_books)} books diverge on {team_label} "
                        f"(soft avg {avg_soft:.2f} vs outliers avg {divergent_avg:.2f})"
                    ),
                    "meta": {
                        "team": team_key,
                        "prediction": opponent_label,
                        "soft_avg": round(avg_soft, 3),
                        "outlier_avg": round(divergent_avg, 3),
                        "divergent_books": {bk: round(odds, 3) for bk, odds in divergent_books.items()},
                        "soft_book_count": len(soft_odds),
                    },
                })
            elif len(divergent_books) >= 2:
                divergent_avg = statistics.mean(divergent_books.values())
                signals.append({
                    "kind": "consensus_move",
                    "severity": "warning",
                    "title": (
                        f"Divergence: {len(divergent_books)} books disagree on {team_label} "
                        f"(soft avg {avg_soft:.2f} vs outliers avg {divergent_avg:.2f})"
                    ),
                    "meta": {
                        "team": team_key,
                        "prediction": opponent_label,
                        "soft_avg": round(avg_soft, 3),
                        "outlier_avg": round(divergent_avg, 3),
                        "divergent_books": {bk: round(odds, 3) for bk, odds in divergent_books.items()},
                        "soft_book_count": len(soft_odds),
                    },
                })

    # ── Mode B: Temporal multi-book drop (requires previous data) ──────
    if previous:
        prev_map = {s["bookmaker"]: s for s in previous}
        for team_key, label in [("team1_odds", "Team 1"), ("team2_odds", "Team 2")]:
            books_dropped = []
            for cur in current:
                bk = cur["bookmaker"]
                if bk not in prev_map:
                    continue
                pct = _pct_change(prev_map[bk][team_key], cur[team_key])
                if pct < -5:  # >5% drop since last cycle
                    books_dropped.append(bk)

            if len(books_dropped) >= cfg.suspicious_books_moved:
                signals.append({
                    "kind": "suspicious",
                    "severity": "critical",
                    "title": f"Steam: {len(books_dropped)} books dropped {label} this cycle",
                    "meta": {"team": team_key, "books": books_dropped, "mode": "temporal"},
                })
            elif len(books_dropped) >= 3:
                signals.append({
                    "kind": "consensus_move",
                    "severity": "warning",
                    "title": f"Consensus move: {len(books_dropped)} books dropped {label}",
                    "meta": {"team": team_key, "books": books_dropped, "mode": "temporal"},
                })

    return signals


# ─── 6. Odds Volatility ─────────────────────────────────────────────

def calc_volatility(history: list[dict]) -> dict:
    """Covers: odds_volatility_tracker, market_efficiency."""
    result = {}
    for team_key in ("team1_odds", "team2_odds"):
        vals = [h[team_key] for h in history if h[team_key] > 0]
        if len(vals) >= 2:
            result[team_key] = {
                "stdev": round(statistics.stdev(vals), 4),
                "variance": round(statistics.variance(vals), 6),
                "mean": round(statistics.mean(vals), 4),
                "min": min(vals),
                "max": max(vals),
                "samples": len(vals),
            }
    return result


# ─── 7. Opening vs Closing / CLV / Pre-match drift ──────────────────

def calc_line_movement(opening: dict, closing: dict) -> dict:
    """Covers: opening_vs_closing, CLV, pre_match_drift."""
    result = {}
    for team_key in ("team1_odds", "team2_odds"):
        o, c = opening.get(team_key, 0), closing.get(team_key, 0)
        if o > 0 and c > 0:
            result[team_key] = {
                "opening": o, "closing": c,
                "movement": round(c - o, 4),
                "movement_pct": round(_pct_change(o, c), 2),
            }
    return result


# ─── 8. Run all detectors ────────────────────────────────────────────

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

    signals.extend(detect_arbitrage(current_snapshots, cfg))
    signals.extend(detect_value_bets(current_snapshots, cfg))
    signals.extend(detect_steam_moves(current_snapshots, previous_snapshots, cfg))
    # detect_consensus runs always: Mode A works without previous data,
    # Mode B activates automatically when previous_snapshots are available
    signals.extend(detect_consensus(current_snapshots, previous_snapshots, cfg))

    return signals
