"""Run the Phase 0b quote collector. Reads credentials from the environment only.

    python scripts/run_collector.py LINEUPS.json DB_PATH [--limit N]

Both paths must be outside the repo. Nothing here can accept a quote or place an order.
"""

import sys
from pathlib import Path

from kalshi_edge_lab import collector
from kalshi_edge_lab.kalshi_client import KalshiClient

REPO = Path(__file__).resolve().parents[1]


def main(argv):
    lineups_path, db_path = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    for p in (lineups_path, db_path):
        if REPO in p.parents:
            sys.exit(f"{p} is inside the repo; data must live outside it")
    lineups = collector.load_lineups(str(lineups_path))
    client = KalshiClient.from_env()

    def fetch_markets(event):
        return client.get_markets(event_ticker=event, limit=300).get("markets", [])

    meta = {k: lineups[k] for k in ("date", "puck", "lineup_source", "fetched_at")}
    if "--limit" in argv:
        n = int(argv[argv.index("--limit") + 1])
        lineups["teams"] = dict(list(lineups["teams"].items())[:n])
    summary = collector.run(client, lineups, meta, str(db_path), fetch_markets)
    for s in summary:
        r = s["res"] or {}
        print(
            s["id"],
            s["game"],
            s["team"],
            s["kind"],
            s["status"] if not r else r["status"],
            r.get("yes"),
            r.get("multiple"),
            r.get("message") or s.get("reason", ""),
        )
    print(f"rfqs created: {client.rfqs_created}")


if __name__ == "__main__":
    main(sys.argv[1:])
