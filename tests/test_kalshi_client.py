import base64
import re
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from kalshi_edge_lab import collector, kalshi_client
from kalshi_edge_lab.kalshi_client import (
    KalshiClient,
    KalshiError,
    NotAllowedError,
    Response,
    is_allowed,
)

SRC = Path(__file__).resolve().parents[1] / "src"
P = "/trade-api/v2"


def ed_pem() -> str:
    key = ed25519.Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


class Fake:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    def __call__(self, method, url, headers, params, body):
        self.calls.append((method, url, headers, params, body))
        return self.replies.pop(0) if self.replies else Response(200, {})


def client(fake):
    return KalshiClient("key-id", ed_pem(), fake)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", f"{P}/markets"),
        ("GET", f"{P}/markets/KXNHLPTS-26NOV02VGKBOS-BOSJHAGENS44-2"),
        ("GET", f"{P}/events/KXNHLPTS-26NOV02VGKBOS"),
        ("POST", f"{P}/multivariate_event_collections/KXMVECROSSCATEGORY-R"),
        ("POST", f"{P}/communications/rfqs"),
        ("GET", f"{P}/communications/quotes"),
        ("DELETE", f"{P}/communications/rfqs/abc-123"),
    ],
)
def test_allowlisted(method, path):
    assert is_allowed(method, path)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", f"{P}/portfolio/orders"),
        ("GET", f"{P}/portfolio/balance"),
        ("DELETE", f"{P}/portfolio/orders/x"),
        ("PUT", f"{P}/communications/quotes/x/accept"),
        ("POST", f"{P}/communications/quotes"),
        ("POST", f"{P}/communications/quotes/x/confirm"),
        ("POST", f"{P}/markets"),
        ("DELETE", f"{P}/markets/X"),
        ("DELETE", f"{P}/communications/quotes/x"),
        ("POST", f"{P}/communications/rfqs/x"),
        ("GET", "/other/path"),
    ],
)
def test_rejected_without_traffic(method, path):
    fake = Fake()
    with pytest.raises(NotAllowedError):
        client(fake)._request(method, path)
    assert fake.calls == []


def test_signature_headers_and_message():
    fake = Fake()
    client(fake)._request("GET", f"{P}/markets", {"limit": 1})
    method, url, headers, _, _ = fake.calls[0]
    assert url == "https://external-api.kalshi.com" + f"{P}/markets"
    assert set(headers) >= {
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-TIMESTAMP",
        "KALSHI-ACCESS-SIGNATURE",
    }


def test_both_key_types_sign_and_load():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pem = rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    assert kalshi_client.sign(kalshi_client.load_private_key(rsa_pem), "m")
    ed = ed25519.Ed25519PrivateKey.generate()
    der = ed.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    loaded = kalshi_client.load_private_key(base64.b64encode(der).decode())
    assert kalshi_client.sign(loaded, "m")
    escaped = ed_pem().strip().replace("\n", "\\n")
    assert kalshi_client.load_private_key(escaped)


def test_rfq_size_cap_and_flags():
    fake = Fake([Response(200, {"id": "r1"})])
    c = client(fake)
    with pytest.raises(ValueError):
        c.create_rfq("M", 100, 5.0)
    assert fake.calls == []
    assert c.create_rfq("M", 6, 0.9) == "r1"
    body = fake.calls[0][4]
    assert body == {
        "market_ticker": "M",
        "contracts_fp": "6.00",
        "rest_remainder": False,
        "obscure_creator_id": True,
    }


def test_no_accept_or_order_endpoints_anywhere_in_src():
    text = "\n".join(p.read_text() for p in SRC.rglob("*.py"))
    for banned in ("/accept", "/confirm", "portfolio", "/orders"):
        assert banned not in text
    assert not re.search(r"def\s+\w*(accept|order)\w*\s*\(", text)


def test_best_quote_and_fee():
    best = collector.best_yes_from_quotes(
        [{"no_bid_dollars": "0.80"}, {"no_bid_dollars": "0.9"}, {"no_bid_dollars": "0.00"}]
    )
    assert best["yes"] == 0.1
    assert best["multiple"] == 10.0
    assert best["fee"] == pytest.approx(0.07 * 0.1 * 0.9, abs=1e-5)
    assert collector.best_yes_from_quotes([]) is None


def test_sizing_stays_under_cap():
    for est in (0.002, 0.03, 0.15, 0.4, 0.9):
        n = collector.size_contracts(est)
        assert n >= 1
        assert n * est <= 1.5


def test_price_combo_retries_then_deletes_rfq():
    mk = {
        collector.norm(p): {"ticker": f"T-{p}", "event_ticker": "E", "yes_ask_dollars": "0.5"}
        for p in ("A B", "C D", "E F")
    }
    plan = {"players": ["A B", "C D", "E F"]}
    busy = Response(400, {"error": "Trading is not currently allowed on markets in Sports"})
    fake = Fake(
        [
            busy,  # first combo creation fails, retried
            Response(200, {"market_ticker": "CMB"}),
            Response(200, {"id": "r9"}),
            Response(200, {"quotes": [{"no_bid_dollars": "0.9"}]}),
            Response(200, {}),  # delete
        ]
    )
    res = collector.price_combo(client(fake), plan, mk, sleep=lambda s: None)
    assert res["status"] == "priced" and res["yes"] == 0.1
    assert fake.calls[-1][0] == "DELETE"
    methods = [c[0] for c in fake.calls]
    assert methods == ["POST", "POST", "POST", "GET", "DELETE"]


def test_price_combo_gives_up_after_three_with_error():
    mk = {
        collector.norm(p): {"ticker": p, "event_ticker": "E", "yes_ask_dollars": "0.5"}
        for p in ("A B", "C D", "E F")
    }
    busy = Response(400, {"error": "Trading is not currently allowed on markets in Sports"})
    fake = Fake([busy, busy, busy])
    res = collector.price_combo(client(fake), {"players": ["A B", "C D", "E F"]}, mk, lambda s: 0)
    assert res["status"] == "error" and "not currently allowed" in res["message"]
    assert len(fake.calls) == 3
    with pytest.raises(KalshiError):
        client(Fake([Response(500, {})]))._request("GET", f"{P}/markets")


def test_plans_hold_flagged_and_missing_and_no_defense():
    lineups = {
        "teams": {
            "AAA": {
                "game": "AAA@BBB",
                "F": [["A One", "A Two", "A Three"], ["B One", "B Two", "B Three"]],
                "D": ["D One"],
                "PP1": ["A One", "A Two", "A Three", "B One", "B Two"],
                "out": ["B Two"],
            }
        }
    }
    names = ["A One", "A Two", "A Three", "B One", "B Two", "B Three", "D One"]
    mk = {collector.norm(n): {"yes_ask_dollars": "0.3"} for n in names if n != "A Three"}
    plans = collector.build_plans(lineups, {"AAA@BBB": mk})
    reasons = [p["reason"] for p in plans]
    assert "no Kalshi 2+ market: A Three" in reasons[0]
    assert "flagged out/injured: B Two" in reasons[1]
    assert "0 defensemen" in reasons[2]
