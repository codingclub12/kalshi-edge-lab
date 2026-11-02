"""NHL box score helpers. Parsing is pure; only fetch_json touches the network."""

import json
import re
import unicodedata
import urllib.request

FINAL_STATES = {"FINAL", "OFF"}
SKATER_GROUPS = ("forwards", "defense")


def fetch_json(url: str, user_agent: str = "kalshi-edge-lab-research/0.1") -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (fixed https hosts)
        return json.load(resp)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", " ", text.lower().replace("-", " "))


def name_key(name: str) -> tuple[str, str]:
    """(first initial, last token). Handles 'A. Matthews' and 'Auston Matthews'."""
    tokens = _norm(name).split()
    if len(tokens) < 2:
        raise ValueError(f"need first and last name, got {name!r}")
    return tokens[0][0], tokens[-1]


def parse_game_ref(game: str) -> tuple[str, str]:
    """'TOR@BOS' -> ('TOR', 'BOS') as (away, home)."""
    m = re.fullmatch(r"\s*([A-Za-z]{2,4})\s*(?:@|at|vs\.?|-)\s*([A-Za-z]{2,4})\s*", game)
    if not m:
        raise ValueError(f"game must look like AWAY@HOME, got {game!r}")
    return m.group(1).upper(), m.group(2).upper()


def find_game_id(schedule: dict, game_date: str, away: str, home: str) -> int | None:
    for day in schedule.get("gameWeek", []):
        if day.get("date") != game_date:
            continue
        for g in day.get("games", []):
            if g["awayTeam"]["abbrev"] == away and g["homeTeam"]["abbrev"] == home:
                return g["id"]
    return None


def is_final(boxscore: dict) -> bool:
    return boxscore.get("gameState") in FINAL_STATES


def skater_points(boxscore: dict) -> list[dict]:
    """Flat list of skaters: name, team abbrev, points."""
    out = []
    stats = boxscore.get("playerByGameStats", {})
    for side in ("awayTeam", "homeTeam"):
        abbrev = boxscore[side]["abbrev"]
        for group in SKATER_GROUPS:
            for p in stats.get(side, {}).get(group, []):
                pts = p.get("points")
                if pts is None:
                    pts = p.get("goals", 0) + p.get("assists", 0)
                out.append({"name": p["name"]["default"], "team": abbrev, "points": pts})
    return out


def points_for(boxscore: dict, player: str, team: str | None = None) -> int | None:
    """Points for a player, or None if not in the box score.

    Raises ValueError if the name matches more than one skater and `team` does
    not settle it.
    """
    key = name_key(player)
    hits = [s for s in skater_points(boxscore) if name_key(s["name"]) == key]
    if len(hits) > 1 and team:
        hits = [s for s in hits if s["team"] == team.upper()]
    if not hits:
        return None
    if len(hits) > 1:
        raise ValueError(f"ambiguous player {player!r}: {[h['name'] for h in hits]}")
    return hits[0]["points"]
