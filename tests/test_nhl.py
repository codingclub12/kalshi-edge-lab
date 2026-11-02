import pytest

from kalshi_edge_lab import nhl


def test_name_key_handles_initials_accents_and_full_names():
    assert nhl.name_key("Auston Matthews") == nhl.name_key("A. Matthews")
    assert nhl.name_key("Tim Stützle") == nhl.name_key("T. Stutzle")


def test_name_key_needs_two_parts():
    with pytest.raises(ValueError):
        nhl.name_key("Matthews")


def test_parse_game_ref():
    assert nhl.parse_game_ref("tor@bos") == ("TOR", "BOS")
    with pytest.raises(ValueError):
        nhl.parse_game_ref("Toronto Boston")


def test_find_game_id(schedule):
    assert nhl.find_game_id(schedule, "2026-11-01", "TOR", "BOS") == 2026020100
    assert nhl.find_game_id(schedule, "2026-11-01", "TOR", "MTL") is None
    assert nhl.find_game_id(schedule, "2026-10-31", "TOR", "MTL") == 2026020090


def test_points_for(box):
    assert nhl.is_final(box)
    assert nhl.points_for(box, "Auston Matthews") == 2
    assert nhl.points_for(box, "Tim Stutzle") == 0
    assert nhl.points_for(box, "Charlie McAvoy", team="BOS") == 2
    assert nhl.points_for(box, "Nobody Here") is None


def test_goalies_are_not_skaters(box):
    assert nhl.points_for(box, "Joseph Woll") is None


def test_ambiguous_name_needs_team(box):
    box["playerByGameStats"]["homeTeam"]["forwards"].append(
        {"playerId": 99, "name": {"default": "A. Matthews"}, "goals": 0, "assists": 0, "points": 0}
    )
    with pytest.raises(ValueError):
        nhl.points_for(box, "Auston Matthews")
    assert nhl.points_for(box, "Auston Matthews", team="TOR") == 2
    assert nhl.points_for(box, "Auston Matthews", team="BOS") == 0
