"""Read-only Kalshi client.

Only the calls in ALLOWED are possible. Everything else raises NotAllowedError before any
network traffic or signing happens. The list covers public market data, creating the combo
market from a collection, and the request-for-quote flow (create, read quotes, delete). There
is deliberately nothing here that could commit money.
"""

import base64
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from .safety import DRY_RUN, MAX_STAKE_USD

HOST = "https://external-api.kalshi.com"
PREFIX = "/trade-api/v2"
COLLECTION = "KXMVECROSSCATEGORY-R"
_T = r"[A-Za-z0-9_.-]+"

ALLOWED: tuple[tuple[str, re.Pattern], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("GET", rf"{PREFIX}/exchange/status"),
        ("GET", rf"{PREFIX}/series(/{_T})?"),
        ("GET", rf"{PREFIX}/events(/{_T})?"),
        ("GET", rf"{PREFIX}/markets(/{_T})?"),
        ("GET", rf"{PREFIX}/multivariate_event_collections(/{_T})?"),
        ("POST", rf"{PREFIX}/multivariate_event_collections/{_T}"),
        ("POST", rf"{PREFIX}/communications/rfqs"),
        ("GET", rf"{PREFIX}/communications/quotes"),
        ("DELETE", rf"{PREFIX}/communications/rfqs/{_T}"),
    )
)


class NotAllowedError(Exception):
    """Raised for any method and path outside ALLOWED."""


class KalshiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def is_allowed(method: str, path: str) -> bool:
    path = path.split("?", 1)[0]
    return any(m == method.upper() and p.fullmatch(path) for m, p in ALLOWED)


def load_private_key(pem: str):
    """Parse a key from an env var: PEM (literal backslash-n tolerated) or bare base64 DER."""
    text = pem.strip()
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")
    if "-----BEGIN" in text:
        return serialization.load_pem_private_key(text.encode(), password=None)
    raw = base64.b64decode(text)  # bare base64: PKCS#8 DER, or a raw 32-byte Ed25519 seed
    if len(raw) == 32:
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    return serialization.load_der_private_key(raw, password=None)


def sign(key, message: str) -> str:
    data = message.encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(data)
    elif isinstance(key, rsa.RSAPrivateKey):
        sig = key.sign(
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    else:
        raise ValueError("unsupported key type")
    return base64.b64encode(sig).decode()


@dataclass
class Response:
    status: int
    data: dict


Transport = Callable[[str, str, dict, dict | None, dict | None], Response]


def _requests_transport(method, url, headers, params, body) -> Response:
    r = requests.request(method, url, headers=headers, params=params, json=body, timeout=20)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:300]}
    return Response(r.status_code, data)


class KalshiClient:
    def __init__(self, key_id: str, private_key_pem: str, transport: Transport | None = None):
        self._key_id = key_id
        self._key = load_private_key(private_key_pem)
        self._transport = transport or _requests_transport
        self.rfqs_created = 0

    @classmethod
    def from_env(cls, transport: Transport | None = None) -> "KalshiClient":
        return cls(os.environ["KALSHI_API_KEY_ID"], os.environ["KALSHI_PRIVATE_KEY"], transport)

    def _request(self, method: str, path: str, params=None, body=None) -> dict:
        if not is_allowed(method, path):
            raise NotAllowedError(f"{method} {path} is not on the read-only allowlist")
        ts = str(int(time.time() * 1000))
        headers = {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sign(self._key, ts + method.upper() + path),
            "Content-Type": "application/json",
        }
        resp = self._transport(method.upper(), HOST + path, headers, params, body)
        if resp.status >= 400:
            raise KalshiError(resp.status, str(resp.data))
        return resp.data

    # Public data -------------------------------------------------------------
    def get_markets(self, **params) -> dict:
        return self._request("GET", f"{PREFIX}/markets", params)

    def get_event(self, event_ticker: str) -> dict:
        return self._request("GET", f"{PREFIX}/events/{event_ticker}")

    # Combo market creation (creates a market only, never a position) ---------
    def create_combo_market(self, selected: list[dict]) -> dict:
        body = {"selected_markets": selected, "with_market_payload": True}
        path = f"{PREFIX}/multivariate_event_collections/{COLLECTION}"
        return self._request("POST", path, None, body)

    # Request for quote -------------------------------------------------------
    def create_rfq(self, market_ticker: str, contracts: int, max_cost_usd: float) -> str:
        if not DRY_RUN or max_cost_usd > MAX_STAKE_USD * 1.5:
            raise ValueError("RFQ size is over the notional cap")
        body = {
            "market_ticker": market_ticker,
            "contracts_fp": f"{contracts}.00",
            "rest_remainder": False,
            "obscure_creator_id": True,
        }
        self.rfqs_created += 1
        data = self._request("POST", f"{PREFIX}/communications/rfqs", None, body)
        return data.get("id") or data["rfq"]["id"]

    def get_quotes(self, rfq_id: str) -> list[dict]:
        params = {"rfq_id": rfq_id, "rfq_user_filter": "self"}
        return self._request("GET", f"{PREFIX}/communications/quotes", params).get("quotes", [])

    def delete_rfq(self, rfq_id: str) -> None:
        self._request("DELETE", f"{PREFIX}/communications/rfqs/{rfq_id}")
