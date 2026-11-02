"""Tiny config loader. Reads an optional YAML file; falls back to safe defaults."""

from pathlib import Path

import yaml

DEFAULTS = {
    "db_path": "data/edge_lab.sqlite",
    "nhl_api_base": "https://api-web.nhle.com/v1",
    "user_agent": "kalshi-edge-lab-research/0.1",
}


def load_config(path: str | Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    candidate = Path(path) if path else Path("config.yaml")
    if candidate.is_file():
        loaded = yaml.safe_load(candidate.read_text()) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{candidate} must contain a YAML mapping")
        cfg.update(loaded)
    elif path:
        raise FileNotFoundError(path)
    return cfg
