from kalshi_edge_lab import cli
from kalshi_edge_lab.db import connect


def run(db, *argv):
    return cli.main(["--db", str(db), *argv])


LOG = [
    "log",
    "--date",
    "2026-11-01",
    "--game",
    "TOR@BOS",
    "--team",
    "TOR",
    "--leg",
    "Auston Matthews:2",
    "--leg",
    "Mitch Marner:2",
    "--leg",
    "John Tavares:2",
    "--builder-payout",
    "32.5",
    "--rfq-yes",
    "0.034",
    "--rfq-no-bid",
    "0.95",
    "--fanduel-american",
    "+3500",
    "--other-book",
    "dk:Auston Matthews:2:+250",
    "--notes",
    "test row",
]


def test_log_and_list(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    assert run(db, *LOG) == 0
    out = capsys.readouterr().out
    assert "logged combo 1" in out
    conn = connect(db)
    row = conn.execute("SELECT * FROM combos").fetchone()
    assert row["status"] == "priced"
    assert abs(row["taker_fee_per_contract"] - 0.07 * 0.034 * 0.966) < 1e-9
    assert conn.execute("SELECT COUNT(*) FROM legs").fetchone()[0] == 3
    assert conn.execute("SELECT american FROM other_book_prices").fetchone()[0] == 250
    conn.close()
    assert run(db, "list") == 0
    assert "TOR@BOS" in capsys.readouterr().out


def test_other_book_for_unknown_leg_rejected(tmp_path):
    bad = [*LOG, "--other-book", "dk:Someone Else:2:+100"]
    assert run(tmp_path / "t.sqlite", *bad) == 2


def test_bad_game_ref_rejected(tmp_path):
    import pytest

    bad = [a if a != "TOR@BOS" else "Toronto vs Boston" for a in LOG]
    with pytest.raises(ValueError):
        run(tmp_path / "t.sqlite", *bad)


def test_record_buy_enforces_stake_cap(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    run(db, *LOG)
    assert (
        run(
            db,
            "record-buy",
            "--combo",
            "1",
            "--stake",
            "2",
            "--fill-price",
            "0.04",
            "--contracts",
            "50",
        )
        == 2
    )
    assert (
        run(
            db,
            "record-buy",
            "--combo",
            "1",
            "--stake",
            "1",
            "--fill-price",
            "0.04",
            "--contracts",
            "100",
        )
        == 2
    )
    assert (
        run(
            db,
            "record-buy",
            "--combo",
            "1",
            "--stake",
            "1",
            "--fill-price",
            "0.04",
            "--contracts",
            "25",
        )
        == 0
    )
    conn = connect(db)
    assert conn.execute("SELECT status FROM combos").fetchone()[0] == "bought"
    assert conn.execute("SELECT fee_usd FROM buys").fetchone()[0] > 0


def test_status_and_report(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    run(db, *LOG)
    assert run(db, "status", "1", "expired") == 0
    assert run(db, "status", "9", "expired") == 2
    assert run(db, "report") == 0
    assert "No settled combos" in capsys.readouterr().out
