"""SQLite schema and connection helper."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS combos (
    id INTEGER PRIMARY KEY,
    logged_at TEXT NOT NULL,
    source_ts TEXT NOT NULL,
    game_date TEXT NOT NULL,
    sport TEXT NOT NULL DEFAULT 'NHL',
    game TEXT NOT NULL,
    team TEXT,
    nhl_game_id INTEGER,
    -- Total return divided by stake at a $20 stake (32.5 means $20 returns $650).
    builder_payout_multiple REAL,
    -- Executable quote, in dollars per $1 contract.
    rfq_yes_price REAL,
    rfq_no_bid REAL,
    taker_fee_per_contract REAL,
    -- American odds, as displayed.
    fanduel_sgp_american INTEGER,
    status TEXT NOT NULL DEFAULT 'priced'
        CHECK (status IN ('priced', 'bought', 'expired', 'ungateable')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS legs (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    player TEXT NOT NULL,
    stat TEXT NOT NULL DEFAULT 'points',
    threshold INTEGER NOT NULL CHECK (threshold >= 1)
);

CREATE TABLE IF NOT EXISTS other_book_prices (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    leg_id INTEGER REFERENCES legs(id) ON DELETE CASCADE,
    book TEXT NOT NULL,
    american INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS buys (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    bought_at TEXT NOT NULL,
    stake_usd REAL NOT NULL,
    fill_price REAL NOT NULL,
    contracts REAL NOT NULL,
    fee_usd REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL UNIQUE REFERENCES combos(id) ON DELETE CASCADE,
    settled_at TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('win', 'loss')),
    payout_usd REAL NOT NULL,
    leg_results TEXT
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
