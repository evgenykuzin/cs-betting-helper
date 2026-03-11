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

SHARP_BOOKS = {"pinnacle", "singbet", "sbobet"}

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


# ─── 5. Consensus / Multi-book movement ─────────────────────────────

def detect_consensus(
    current: list[dict], previous: list[dict], cfg: Settings,
) -> list[dict]:
    """Covers: multi_book_consensus, suspicious_match."""
    signals = []
    prev_map = {s["bookmaker"]: s for s in previous}

    for team_key, label in [("team1_odds", "Team 1"), ("team2_odds", "Team 2")]:
        books_dropped = []
        for cur in current:
            bk = cur["bookmaker"]
            if bk not in prev_map:
                continue
            pct = _pct_change(prev_map[bk][team_key], cur[team_key])
            if pct < -5:  # >5% drop
                books_dropped.append(bk)

        if len(books_dropped) >= cfg.suspicious_books_moved:
            signals.append({
                "kind": "suspicious",
                "severity": "critical",
                "title": f"Suspicious: {len(books_dropped)} books dropped {label}",
                "meta": {"team": team_key, "books": books_dropped},
            })
        elif len(books_dropped) >= 3:
            signals.append({
                "kind": "consensus_move",
                "severity": "warning",
                "title": f"Consensus: {len(books_dropped)} books moved {label}",
                "meta": {"team": team_key, "books": books_dropped},
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

    if previous_snapshots:
        signals.extend(detect_steam_moves(current_snapshots, previous_snapshots, cfg))
        signals.extend(detect_consensus(current_snapshots, previous_snapshots, cfg))

    return signals
