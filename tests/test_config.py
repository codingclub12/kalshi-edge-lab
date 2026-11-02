from pathlib import Path

import pytest
import yaml

from kalshi_edge_lab.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_example_config_loads_and_has_no_secrets():
    cfg = load_config(ROOT / "config.example.yaml")
    assert cfg["db_path"].startswith("data/")
    keys = {k.lower() for k in yaml.safe_load((ROOT / "config.example.yaml").read_text())}
    assert not any(w in k for k in keys for w in ("key", "secret", "token", "password"))


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config()["db_path"] == "data/edge_lab.sqlite"


def test_missing_explicit_file_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
