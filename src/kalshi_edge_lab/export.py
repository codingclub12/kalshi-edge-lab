"""Export the combos table to CSV or sheet rows. Output paths must be outside the repo."""

import csv
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HEADER = [
    "id", "game_date", "puck_time_ct", "game", "team", "legs", "status", "rfq_yes_price",
    "exec_payout_multiple", "taker_fee_per_contract", "rfq_no_bid", "combo_market_ticker",
    "lineup_source", "lineup_fetched_at", "logged_at", "builder_payout_multiple",
    "fanduel_sgp_american", "notes", "result",
]  # fmt: skip


def rows(conn: sqlite3.Connection) -> list[list]:
    out = []
    for c in conn.execute("SELECT * FROM combos ORDER BY id"):
        legs = [
            f"{r['player']}:{r['threshold']}"
            for r in conn.execute("SELECT * FROM legs WHERE combo_id = ? ORDER BY id", (c["id"],))
        ]
        s = conn.execute("SELECT result FROM settlements WHERE combo_id = ?", (c["id"],)).fetchone()
        rec = dict(c) | {"legs": "; ".join(legs), "result": s["result"] if s else ""}
        out.append(["" if rec.get(h) is None else rec.get(h) for h in HEADER])
    return out


def write_csv(conn: sqlite3.Connection, dest: str | Path) -> Path:
    dest = Path(dest).resolve()
    if dest == REPO or REPO in dest.parents:
        raise ValueError(f"{dest} is inside the repo; export data somewhere else")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows(conn))
    return dest


def settle_csv(src: str | Path, dest: str | Path, fetch, base: str) -> list[str]:
    """Settle rows of a CSV downloaded from the sheet's Combos tab and write a CSV with results.

    Only rows with a status of priced or ungateable and a blank result are settled. Paste the
    `result` column of the output back into the sheet. Both paths must be outside the repo.
    """
    from . import db as dbmod
    from . import settle

    dest = Path(dest).resolve()
    for p in (Path(src).resolve(), dest):
        if p == REPO or REPO in p.parents:
            raise ValueError(f"{p} is inside the repo; keep data files elsewhere")
    with open(src, newline="", encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    conn = dbmod.connect(":memory:")
    lines = []
    for row in table:
        if row["status"] not in ("priced", "ungateable") or row.get("result"):
            continue
        cur = conn.execute(
            "INSERT INTO combos (logged_at, source_ts, game_date, game, team, status)"
            " VALUES ('', '', ?, ?, ?, ?)",
            (row["game_date"], row["game"], row["team"], row["status"]),
        )
        for leg in row["legs"].split("; "):
            player, _, thr = leg.rpartition(":")
            conn.execute(
                "INSERT INTO legs (combo_id, player, threshold) VALUES (?,?,?)",
                (cur.lastrowid, player, int(thr)),
            )
        lines.append(
            f"sheet id {row['id']}: " + settle.settle_combo(conn, cur.lastrowid, fetch, base)
        )
        res = conn.execute(
            "SELECT result FROM settlements WHERE combo_id = ?", (cur.lastrowid,)
        ).fetchone()
        if res:
            row["result"] = res["result"]
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    return lines
