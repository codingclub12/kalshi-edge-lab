import csv

import pytest

from conftest import add_combo
from kalshi_edge_lab import export


def test_export_rows_and_repo_guard(conn, tmp_path):
    add_combo(conn, [("A B", 2), ("C D", 2)])
    path = export.write_csv(conn, tmp_path / "out.csv")
    rows = list(csv.DictReader(path.open()))
    assert rows[0]["legs"] == "A B:2; C D:2"
    assert rows[0]["status"] == "priced"
    with pytest.raises(ValueError):
        export.write_csv(conn, export.REPO / "oops.csv")


def test_settle_csv_offline(conn, tmp_path, box, schedule):
    src = tmp_path / "in.csv"
    with open(src, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(export.HEADER)
        row = dict.fromkeys(export.HEADER, "")
        row |= {
            "id": 1, "game_date": "2026-11-01", "game": "TOR@BOS", "team": "TOR",
            "status": "priced", "legs": "Auston Matthews:2; Mitch Marner:2",
        }  # fmt: skip
        w.writerow([row[h] for h in export.HEADER])

    def fetch(url):
        return schedule if "schedule" in url else box

    out = tmp_path / "out.csv"
    lines = export.settle_csv(src, out, fetch, "https://x")
    assert len(lines) == 1
    assert list(csv.DictReader(out.open()))[0]["result"] in ("win", "loss", "")
