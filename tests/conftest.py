import json
from pathlib import Path

import pytest

from kalshi_edge_lab.db import connect

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def box():
    return load_fixture("boxscore_tor_bos.json")


@pytest.fixture
def schedule():
    return load_fixture("schedule_2026_11_01.json")


def add_combo(
    conn,
    legs,
    *,
    price=0.05,
    fee=0.0033,
    game="TOR@BOS",
    date="2026-11-01",
    team="TOR",
    status="priced",
    builder_x=25.0,
):
    cur = conn.execute(
        "INSERT INTO combos (logged_at, source_ts, game_date, game, team, builder_payout_multiple,"
        " rfq_yes_price, taker_fee_per_contract, status) VALUES ('t','t',?,?,?,?,?,?,?)",
        (date, game, team, builder_x, price, fee, status),
    )
    for player, thr in legs:
        conn.execute(
            "INSERT INTO legs (combo_id, player, threshold) VALUES (?,?,?)",
            (cur.lastrowid, player, thr),
        )
    conn.commit()
    return cur.lastrowid
