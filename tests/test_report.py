import pytest

from conftest import add_combo
from kalshi_edge_lab import report


def settle_row(conn, cid, result):
    conn.execute(
        "INSERT INTO settlements (combo_id, settled_at, result, payout_usd) VALUES (?, 't', ?, 0)",
        (cid, result),
    )
    conn.commit()


def test_poisson_binomial_matches_hand_calc():
    upper, lower = report.poisson_binomial_tails([0.5, 0.5], 1)
    assert upper == pytest.approx(0.75)
    assert lower == pytest.approx(0.75)
    assert report.poisson_binomial_tails([0.5, 0.5], 0)[0] == pytest.approx(1.0)


def test_poisson_tails_known_values():
    upper, lower = report.poisson_tails(2.0, 0)
    assert lower == pytest.approx(0.1353353, abs=1e-6)
    assert upper == 1.0
    upper, lower = report.poisson_tails(2.0, 3)
    assert lower == pytest.approx(0.8571235, abs=1e-6)
    assert upper == pytest.approx(1 - 0.6766764, abs=1e-6)


def test_empty_report(conn):
    text = report.build_report(report.load_settled(conn))
    assert "No settled combos" in text
    assert "200" in text


def test_report_numbers(conn):
    for result in ["win", "loss", "loss", "loss"]:
        cid = add_combo(conn, [("Auston Matthews", 2)], price=0.25, fee=0.01)
        settle_row(conn, cid, result)
    rows = report.load_settled(conn)
    text = report.build_report(rows)
    assert "Settled combos:            4" in text
    assert "Actual hits:               1" in text
    assert "Expected hits at price:    1.00" in text
    # cost = 4 * 0.26 = 1.04, returned 1, ROI = -3.8%
    assert "-3.8%" in text
    assert "4 of 200" in text
    assert "Too few to conclude" in text


def test_report_excludes_expired_and_unpriced(conn):
    a = add_combo(conn, [("Auston Matthews", 2)], status="expired")
    b = add_combo(conn, [("Auston Matthews", 2)])
    conn.execute("UPDATE combos SET rfq_yes_price = NULL WHERE id = ?", (b,))
    c = add_combo(conn, [("Auston Matthews", 2)])
    for cid in (a, b, c):
        settle_row(conn, cid, "loss")
    assert [r["id"] for r in report.load_settled(conn)] == [c]


def test_luck_direction_flips_with_result(conn):
    for _ in range(10):
        cid = add_combo(conn, [("Auston Matthews", 2)], price=0.1)
        settle_row(conn, cid, "win")
    text = report.build_report(report.load_settled(conn))
    assert "this many or more hits" in text
    assert "not the probability that an edge exists" in text
