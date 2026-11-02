"""Settle logged combos from NHL box scores."""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from . import nhl

Fetcher = Callable[[str], dict]


def evaluate_legs(boxscore: dict, legs: list[sqlite3.Row], team: str | None) -> list[dict]:
    results = []
    for leg in legs:
        pts = nhl.points_for(boxscore, leg["player"], team)
        outcome = "missing" if pts is None else "win" if pts >= leg["threshold"] else "loss"
        results.append(
            {
                "player": leg["player"],
                "threshold": leg["threshold"],
                "points": pts,
                "outcome": outcome,
            }
        )
    return results


def combo_result(leg_results: list[dict]) -> str | None:
    """'win', 'loss', or None when it cannot be called.

    Any leg that missed is a loss no matter what. A leg whose player is not in
    the box score (scratched, wrong name) leaves the combo open for a human.
    """
    if any(r["outcome"] == "loss" for r in leg_results):
        return "loss"
    if any(r["outcome"] == "missing" for r in leg_results):
        return None
    return "win"


def settle_combo(conn: sqlite3.Connection, combo_id: int, fetch: Fetcher, base: str) -> str:
    """Returns a one-line status. Writes a settlement row only on a clear result."""
    combo = conn.execute("SELECT * FROM combos WHERE id = ?", (combo_id,)).fetchone()
    if combo is None:
        return f"combo {combo_id}: not found"
    if conn.execute("SELECT 1 FROM settlements WHERE combo_id = ?", (combo_id,)).fetchone():
        return f"combo {combo_id}: already settled"

    game_id = combo["nhl_game_id"]
    if game_id is None:
        away, home = nhl.parse_game_ref(combo["game"])
        schedule = fetch(f"{base}/schedule/{combo['game_date']}")
        game_id = nhl.find_game_id(schedule, combo["game_date"], away, home)
        if game_id is None:
            return f"combo {combo_id}: no {away}@{home} game found on {combo['game_date']}"
        conn.execute("UPDATE combos SET nhl_game_id = ? WHERE id = ?", (game_id, combo_id))

    box = fetch(f"{base}/gamecenter/{game_id}/boxscore")
    if not nhl.is_final(box):
        return f"combo {combo_id}: game {game_id} not final ({box.get('gameState')})"

    legs = conn.execute("SELECT * FROM legs WHERE combo_id = ? ORDER BY id", (combo_id,)).fetchall()
    try:
        leg_results = evaluate_legs(box, legs, combo["team"])
    except ValueError as exc:
        return f"combo {combo_id}: {exc}"
    result = combo_result(leg_results)
    if result is None:
        missing = [r["player"] for r in leg_results if r["outcome"] == "missing"]
        return f"combo {combo_id}: not in box score: {', '.join(missing)}; left open"

    contracts = conn.execute(
        "SELECT COALESCE(SUM(contracts), 0) FROM buys WHERE combo_id = ?", (combo_id,)
    ).fetchone()[0]
    payout = float(contracts) if result == "win" else 0.0
    conn.execute(
        "INSERT INTO settlements (combo_id, settled_at, result, payout_usd, leg_results)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            combo_id,
            datetime.now(UTC).isoformat(timespec="seconds"),
            result,
            payout,
            json.dumps(leg_results),
        ),
    )
    conn.commit()
    return f"combo {combo_id}: {result}"


def unsettled_ids(conn: sqlite3.Connection, today: str) -> list[int]:
    rows = conn.execute(
        "SELECT c.id FROM combos c LEFT JOIN settlements s ON s.combo_id = c.id"
        " WHERE s.id IS NULL AND c.status IN ('priced', 'bought') AND c.game_date <= ?"
        " ORDER BY c.id",
        (today,),
    ).fetchall()
    return [r["id"] for r in rows]
