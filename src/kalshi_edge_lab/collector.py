"""Phase 0b quote collector. Reads quotes only; there is no way to act on one."""

import json
import math
import time
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime

from . import db as dbmod
from .fees import taker_fee
from .kalshi_client import KalshiClient, KalshiError
from .safety import DRY_RUN, MAX_STAKE_USD

MAX_RFQS = 40
MAX_NOTIONAL_USD = 1.5
RETRIES = 3
RETRYABLE = "Trading is not currently allowed"


def norm(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().replace(".", "").replace("-", " ").split())


def index_markets(markets: list[dict]) -> dict[str, dict]:
    """Map normalized player name to the open '2+' points market."""
    out = {}
    for m in markets:
        sub = m.get("yes_sub_title", "")
        if sub.endswith(": 2+") and m.get("status") in ("active", "open"):
            out[norm(sub[: -len(": 2+")])] = m
    return out


def best_yes_from_quotes(quotes: list[dict]) -> dict | None:
    """Best executable Yes: highest no_bid, yes = 1 - no_bid, multiple = 1 / yes."""
    bids = []
    for q in quotes:
        raw = q.get("no_bid_dollars", q.get("no_bid"))
        try:
            bid = float(raw)
        except (TypeError, ValueError):
            continue
        if 0 < bid < 1:
            bids.append(bid)
    if not bids:
        return None
    no_bid = max(bids)
    yes = round(1 - no_bid, 4)
    return {
        "no_bid": no_bid,
        "yes": yes,
        "multiple": round(1 / yes, 2),
        "fee": round(taker_fee(yes), 5),
        "n_quotes": len(bids),
    }


def size_contracts(est_yes: float) -> int:
    """Contracts so that the estimated max cost is at most MAX_STAKE_USD (never over 1.50)."""
    n = max(1, math.floor(MAX_STAKE_USD / est_yes))
    if n * est_yes > MAX_NOTIONAL_USD:
        n = max(1, math.floor(MAX_NOTIONAL_USD / est_yes))
    return n


def build_plans(lineups: dict, markets_by_game: dict[str, dict[str, dict]]) -> list[dict]:
    """Return combo plans. Each has legs, a status ('plan' or 'held') and a reason."""
    plans = []
    for team, t in lineups["teams"].items():
        mk = markets_by_game[t["game"]]
        out = {norm(p) for p in t.get("out", [])}
        fwds = {norm(p) for line in t["F"] for p in line}
        defs = {norm(p) for p in t["D"]}

        def add(kind, players, team=team, t=t, mk=mk, out=out):
            plan = {"team": team, "game": t["game"], "kind": kind, "players": players}
            flagged = [p for p in players if norm(p) in out]
            missing = [p for p in players if norm(p) not in mk]
            if flagged:
                plan |= {"status": "held", "reason": f"flagged out/injured: {', '.join(flagged)}"}
            elif missing:
                plan |= {"status": "held", "reason": f"no Kalshi 2+ market: {', '.join(missing)}"}
            else:
                plan["status"] = "plan"
            plans.append(plan)

        add("ES line 1", list(t["F"][0]))
        add("ES line 2", list(t["F"][1]))
        pp = t["PP1"]
        pf = [p for p in pp if norm(p) in fwds]
        pd_ = [p for p in pp if norm(p) in defs]
        if len(pf) < 2 or not pd_:
            plans.append(
                {
                    "team": team,
                    "game": t["game"],
                    "kind": "PP1 2F+1D",
                    "players": pf + pd_,
                    "status": "held",
                    "reason": f"PP1 has {len(pf)} forwards and {len(pd_)} defensemen listed",
                }
            )
        else:

            def ask(p, mk=mk):
                m = mk.get(norm(p))
                return float(m["yes_ask_dollars"]) if m else -1.0

            top_f = sorted(pf, key=ask, reverse=True)[:2]
            add("PP1 2F+1D", top_f + [max(pd_, key=ask)])
    return plans


def est_price(players: list[str], mk: dict[str, dict]) -> float:
    """Independent product of leg asks, floored. Correlated combos cost more than this."""
    prod = 1.0
    for p in players:
        prod *= max(float(mk[norm(p)]["yes_ask_dollars"]), 0.01)
    return max(prod, 0.002)


def price_combo(client: KalshiClient, plan: dict, mk: dict, sleep: Callable = time.sleep) -> dict:
    """Create the combo market, ask for quotes, read them, delete the RFQ."""
    legs = [mk[norm(p)] for p in plan["players"]]
    selected = [
        {"market_ticker": m["ticker"], "event_ticker": m["event_ticker"], "side": "yes"}
        for m in legs
    ]
    result: dict = {"status": "error", "message": ""}
    for _ in range(RETRIES):
        rfq_id = None
        try:
            created = client.create_combo_market(selected)
            combo_ticker = created.get("market_ticker") or created["market"]["ticker"]
            result["combo_market_ticker"] = combo_ticker
            cm = created.get("market") or {}
            try:
                est = float(cm.get("yes_ask_dollars") or 0) or est_price(plan["players"], mk)
            except ValueError:
                est = est_price(plan["players"], mk)
            est = max(est, est_price(plan["players"], mk))
            n = size_contracts(est)
            if client.rfqs_created >= MAX_RFQS:
                result["message"] = "RFQ cap reached"
                return result
            rfq_id = client.create_rfq(combo_ticker, n, n * est)
            quotes: list[dict] = []
            for _ in range(5):
                sleep(2)
                quotes = client.get_quotes(rfq_id)
                if quotes:
                    break
            best = best_yes_from_quotes(quotes)
            result["contracts"] = n
            if best is None:
                result |= {"status": "error", "message": "no quotes received"}
            else:
                result |= {"status": "priced", "message": "", **best}
            return result
        except KalshiError as exc:
            result["message"] = str(exc)
            if RETRYABLE not in str(exc):
                return result
            sleep(3)
        finally:
            if rfq_id:
                try:
                    client.delete_rfq(rfq_id)
                except KalshiError as exc:
                    result["message"] += f" [delete failed: {exc}]"
    return result


def record(conn, plan: dict, res: dict | None, meta: dict) -> int:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    status = "held" if res is None else res["status"]
    detail = plan.get("reason") if res is None else res.get("message")
    note = f"{plan['kind']}: {detail}" if detail else plan["kind"]
    cur = conn.execute(
        "INSERT INTO combos (logged_at, source_ts, game_date, game, team, rfq_yes_price,"
        " rfq_no_bid, taker_fee_per_contract, status, notes, puck_time_ct, lineup_source,"
        " lineup_fetched_at, combo_market_ticker, exec_payout_multiple)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now,
            now,
            meta["date"],
            plan["game"],
            plan["team"],
            (res or {}).get("yes"),
            (res or {}).get("no_bid"),
            (res or {}).get("fee"),
            status,
            note,
            meta["puck"][plan["game"]],
            meta["lineup_source"],
            meta["fetched_at"],
            (res or {}).get("combo_market_ticker"),
            (res or {}).get("multiple"),
        ),
    )
    for p in plan["players"]:
        conn.execute(
            "INSERT INTO legs (combo_id, player, threshold) VALUES (?,?,2)", (cur.lastrowid, p)
        )
    conn.commit()
    return cur.lastrowid


def run(client, lineups, meta, db_path, fetch_markets, sleep=time.sleep) -> list[dict]:
    assert DRY_RUN is True
    conn = dbmod.connect(db_path)
    markets_by_game = {
        t["game"]: index_markets(fetch_markets(t["event"])) for t in lineups["teams"].values()
    }
    summary = []
    for plan in build_plans(lineups, markets_by_game):
        res = None
        if plan["status"] == "plan":
            if client.rfqs_created >= MAX_RFQS:
                plan |= {"status": "held", "reason": "RFQ cap reached"}
            else:
                res = price_combo(client, plan, markets_by_game[plan["game"]], sleep)
                sleep(1.5)
        cid = record(conn, plan, res, meta)
        summary.append({"id": cid, **plan, "res": res})
    conn.close()
    return summary


def load_lineups(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
