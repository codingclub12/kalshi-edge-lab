"""edge-lab command line. Logging and settling only; nothing here can trade."""

import argparse
import sys
from datetime import UTC, date, datetime

from . import export, report, settle
from .config import load_config
from .db import connect
from .fees import taker_fee
from .nhl import fetch_json, parse_game_ref
from .safety import MAX_STAKE_USD

STATUSES = ("priced", "bought", "expired", "ungateable", "held", "error")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_leg(text: str) -> tuple[str, int]:
    player, _, thr = text.rpartition(":")
    if not player or not thr.isdigit() or int(thr) < 1:
        raise argparse.ArgumentTypeError(f"leg must look like 'Player Name:2', got {text!r}")
    return player.strip(), int(thr)


def _parse_other(text: str) -> tuple[str, str, int, int]:
    parts = text.split(":")
    try:
        book, player, thr, price = parts[0], parts[1], int(parts[2]), int(parts[3])
    except (IndexError, ValueError):
        raise argparse.ArgumentTypeError(
            f"other-book must look like 'book:Player Name:2:-150', got {text!r}"
        ) from None
    return book, player.strip(), thr, price


def _price(text: str) -> float:
    value = float(text)
    if not 0 < value < 1:
        raise argparse.ArgumentTypeError("prices are dollars between 0 and 1, like 0.034")
    return value


def cmd_log(conn, args) -> int:
    parse_game_ref(args.game)
    legs = dict.fromkeys(args.leg)
    other_legs = {(p, t) for _, p, t, _ in args.other_book or []}
    unknown = other_legs - set(legs)
    if unknown:
        print(f"other-book price for a leg not in this combo: {sorted(unknown)}", file=sys.stderr)
        return 2
    fee = taker_fee(args.rfq_yes) if args.rfq_yes is not None else None
    cur = conn.execute(
        "INSERT INTO combos (logged_at, source_ts, game_date, sport, game, team, nhl_game_id,"
        " builder_payout_multiple, rfq_yes_price, rfq_no_bid, taker_fee_per_contract,"
        " fanduel_sgp_american, status, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            _now(),
            args.source_ts or _now(),
            args.date,
            args.sport,
            args.game.upper(),
            args.team,
            args.nhl_game_id,
            args.builder_payout,
            args.rfq_yes,
            args.rfq_no_bid,
            fee,
            args.fanduel_american,
            args.status,
            args.notes,
        ),
    )
    combo_id = cur.lastrowid
    leg_ids = {}
    for player, thr in legs:
        c = conn.execute(
            "INSERT INTO legs (combo_id, player, threshold) VALUES (?,?,?)",
            (combo_id, player, thr),
        )
        leg_ids[(player, thr)] = c.lastrowid
    for book, player, thr, price in args.other_book or []:
        conn.execute(
            "INSERT INTO other_book_prices (combo_id, leg_id, book, american) VALUES (?,?,?,?)",
            (combo_id, leg_ids[(player, thr)], book, price),
        )
    conn.commit()
    fee_txt = f", fee/contract {fee:.4f}" if fee is not None else ""
    print(f"logged combo {combo_id}{fee_txt}")
    return 0


def cmd_record_buy(conn, args) -> int:
    """Records a purchase made by hand elsewhere. This does not place anything."""
    if args.stake > MAX_STAKE_USD:
        print(f"stake {args.stake} is over MAX_STAKE_USD ({MAX_STAKE_USD})", file=sys.stderr)
        return 2
    if args.fill_price * args.contracts > MAX_STAKE_USD + 0.005:
        print("fill_price x contracts is over MAX_STAKE_USD", file=sys.stderr)
        return 2
    if conn.execute("SELECT 1 FROM combos WHERE id = ?", (args.combo,)).fetchone() is None:
        print(f"combo {args.combo} not found", file=sys.stderr)
        return 2
    fee = args.fee if args.fee is not None else taker_fee(args.fill_price, args.contracts)
    conn.execute(
        "INSERT INTO buys (combo_id, bought_at, stake_usd, fill_price, contracts, fee_usd)"
        " VALUES (?,?,?,?,?,?)",
        (args.combo, _now(), args.stake, args.fill_price, args.contracts, fee),
    )
    conn.execute("UPDATE combos SET status = 'bought' WHERE id = ?", (args.combo,))
    conn.commit()
    print(f"recorded buy for combo {args.combo}, fee {fee:.4f}")
    return 0


def cmd_status(conn, args) -> int:
    cur = conn.execute("UPDATE combos SET status = ? WHERE id = ?", (args.status, args.combo))
    conn.commit()
    if cur.rowcount == 0:
        print(f"combo {args.combo} not found", file=sys.stderr)
        return 2
    print(f"combo {args.combo} is now {args.status}")
    return 0


def cmd_list(conn, args) -> int:
    rows = conn.execute(
        "SELECT c.id, c.game_date, c.game, c.status, c.rfq_yes_price, s.result"
        " FROM combos c LEFT JOIN settlements s ON s.combo_id = c.id ORDER BY c.id"
    ).fetchall()
    for r in rows:
        price = f"{r['rfq_yes_price']:.3f}" if r["rfq_yes_price"] is not None else "  -  "
        print(
            f"{r['id']:>4}  {r['game_date']}  {r['game']:<9} {r['status']:<10} "
            f"yes {price}  {r['result'] or 'open'}"
        )
    return 0


def cmd_settle(conn, args, base: str, user_agent: str) -> int:
    today = args.today or date.today().isoformat()
    ids = [args.combo] if args.combo else settle.unsettled_ids(conn, today)

    def fetch(url: str) -> dict:
        return fetch_json(url, user_agent)

    for combo_id in ids:
        try:
            print(settle.settle_combo(conn, combo_id, fetch, base))
        except OSError as exc:
            print(f"combo {combo_id}: network error ({exc}); try again later", file=sys.stderr)
    if not ids:
        print("nothing to settle")
    return 0


def cmd_export_csv(conn, args) -> int:
    print(f"wrote {export.write_csv(conn, args.path)}")
    return 0


def cmd_settle_csv(args, base: str, user_agent: str) -> int:
    def fetch(url: str) -> dict:
        return fetch_json(url, user_agent)

    for line in export.settle_csv(args.input, args.output, fetch, base):
        print(line)
    return 0


def cmd_report(conn, args) -> int:
    print(report.build_report(report.load_settled(conn), report.load_ungateable(conn)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edge-lab", description="Phase 0 paper log. Research only.")
    p.add_argument("--config", help="path to a YAML config (default: ./config.yaml if present)")
    p.add_argument("--db", help="SQLite path (overrides config)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the database file and tables")

    lg = sub.add_parser("log", help="log a priced combo")
    lg.add_argument("--date", required=True, help="game date, YYYY-MM-DD")
    lg.add_argument("--sport", default="NHL")
    lg.add_argument("--game", required=True, help="AWAY@HOME, e.g. TOR@BOS")
    lg.add_argument("--team", help="team the legs belong to, e.g. TOR")
    lg.add_argument(
        "--leg",
        action="append",
        required=True,
        type=_parse_leg,
        help="'Player Name:N' for N+ points; repeat per leg",
    )
    lg.add_argument(
        "--builder-payout", type=float, help="builder payout multiple at $20 (total return / stake)"
    )
    lg.add_argument("--rfq-yes", type=_price, help="executable yes price in dollars")
    lg.add_argument("--rfq-no-bid", type=_price, help="no bid in dollars")
    lg.add_argument("--fanduel-american", type=int, help="FanDuel SGP price, American odds")
    lg.add_argument(
        "--other-book",
        action="append",
        type=_parse_other,
        help="single-leg price as 'book:Player Name:N:american'; repeatable",
    )
    lg.add_argument("--status", choices=STATUSES, default="priced")
    lg.add_argument("--notes")
    lg.add_argument("--source-ts", help="when the prices were seen, ISO 8601 (default: now)")
    lg.add_argument("--nhl-game-id", type=int)

    rb = sub.add_parser("record-buy", help="record a buy you made by hand (places nothing)")
    rb.add_argument("--combo", type=int, required=True)
    rb.add_argument("--stake", type=float, required=True)
    rb.add_argument("--fill-price", type=_price, required=True)
    rb.add_argument("--contracts", type=float, required=True)
    rb.add_argument("--fee", type=float, help="actual fee in dollars (default: computed)")

    st = sub.add_parser("status", help="change a combo's status")
    st.add_argument("combo", type=int)
    st.add_argument("status", choices=STATUSES)

    sub.add_parser("list", help="list logged combos")

    se = sub.add_parser("settle", help="settle finished games from NHL box scores")
    se.add_argument("--combo", type=int, help="settle one combo instead of all due")
    se.add_argument("--today", help="override today's date, YYYY-MM-DD")

    sub.add_parser("report", help="calibration report for settled combos")

    ex = sub.add_parser("export-csv", help="write all combos to a CSV outside the repo")
    ex.add_argument("path")

    sc = sub.add_parser("settle-csv", help="settle a CSV downloaded from the sheet")
    sc.add_argument("input")
    sc.add_argument("output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    if args.command == "settle-csv":
        return cmd_settle_csv(args, cfg["nhl_api_base"], cfg["user_agent"])
    conn = connect(args.db or cfg["db_path"])
    try:
        if args.command == "init-db":
            print(f"database ready at {args.db or cfg['db_path']}")
            return 0
        if args.command == "settle":
            return cmd_settle(conn, args, cfg["nhl_api_base"], cfg["user_agent"])
        handler = {
            "log": cmd_log,
            "record-buy": cmd_record_buy,
            "status": cmd_status,
            "list": cmd_list,
            "report": cmd_report,
            "export-csv": cmd_export_csv,
        }[args.command]
        return handler(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
