from conftest import add_combo
from kalshi_edge_lab import settle

BASE = "https://example.invalid/v1"


def make_fetch(box, schedule, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if "/schedule/" in url:
            return schedule
        if url.endswith("/boxscore"):
            return box
        raise AssertionError(f"unexpected url {url}")

    return fetch


def test_win_when_every_leg_hits(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2), ("Mitch Marner", 2)])
    msg = settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE)
    assert msg.endswith("win")
    row = conn.execute("SELECT * FROM settlements WHERE combo_id = ?", (cid,)).fetchone()
    assert row["result"] == "win"
    assert conn.execute("SELECT nhl_game_id FROM combos").fetchone()[0] == 2026020100


def test_loss_when_one_leg_misses(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2), ("John Tavares", 2)])
    assert settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE).endswith("loss")


def test_threshold_is_n_or_more(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 1), ("John Tavares", 1)])
    assert settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE).endswith("win")


def test_missing_player_with_no_miss_stays_open(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2), ("Ghost Player", 2)])
    msg = settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE)
    assert "left open" in msg
    assert conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0] == 0


def test_missing_player_with_a_miss_is_still_a_loss(conn, box, schedule):
    cid = add_combo(conn, [("Tim Stutzle", 2), ("Ghost Player", 2)])
    assert settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE).endswith("loss")


def test_not_final_is_skipped(conn, box, schedule):
    box["gameState"] = "LIVE"
    cid = add_combo(conn, [("Auston Matthews", 2)])
    assert "not final" in settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE)
    assert conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0] == 0


def test_settled_once_and_no_refetch(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2)])
    calls = []
    fetch = make_fetch(box, schedule, calls)
    settle.settle_combo(conn, cid, fetch, BASE)
    n = len(calls)
    assert "already settled" in settle.settle_combo(conn, cid, fetch, BASE)
    assert len(calls) == n


def test_payout_uses_recorded_buys(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2)])
    conn.execute(
        "INSERT INTO buys (combo_id, bought_at, stake_usd, fill_price, contracts, fee_usd)"
        " VALUES (?, 't', 1, 0.05, 20, 0.07)",
        (cid,),
    )
    settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE)
    assert conn.execute("SELECT payout_usd FROM settlements").fetchone()[0] == 20.0


def test_unknown_game(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2)], game="TOR@MTL")
    assert "no TOR@MTL game" in settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE)


def test_unsettled_ids_skips_future_expired_and_done(conn, box, schedule):
    a = add_combo(conn, [("Auston Matthews", 2)])
    add_combo(conn, [("Auston Matthews", 2)], date="2026-11-09")
    add_combo(conn, [("Auston Matthews", 2)], status="expired")
    done = add_combo(conn, [("Auston Matthews", 2)])
    settle.settle_combo(conn, done, make_fetch(box, schedule), BASE)
    assert settle.unsettled_ids(conn, "2026-11-02") == [a]


def test_ungateable_combos_are_settled_too(conn, box, schedule):
    cid = add_combo(conn, [("Auston Matthews", 2)], status="ungateable")
    assert settle.unsettled_ids(conn, "2026-11-02") == [cid]
    assert settle.settle_combo(conn, cid, make_fetch(box, schedule), BASE).endswith("win")
