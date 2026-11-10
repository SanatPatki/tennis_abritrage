"""Kalshi REST client: RSA-PSS signing, retries, rate limit. See AGENTS.md §4.2–4.5."""

from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

PROD_REST = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_REST = "https://demo-api.kalshi.co/trade-api/v2"


def load_key(path: str | Path) -> RSAPrivateKey:
    with open(path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    assert isinstance(key, RSAPrivateKey)
    return key


def signed_headers(key: RSAPrivateKey, key_id: str, method: str, path: str) -> dict[str, str]:
    """Sign a request per AGENTS.md §4.2.

    `path` must start with /trade-api/v2/... with NO host and NO query string.
    Timestamp is unix milliseconds as a string.
    """
    ts = str(int(time.time() * 1000))
    sig = key.sign(
        f"{ts}{method.upper()}{path.split('?')[0]}".encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }


def kalshi_fee(price: float, contracts: int, maker: bool, maker_fee_series: bool) -> float:
    """Kalshi fee per AGENTS.md §6.2/§4.7. Returns dollars."""
    import math

    if maker and not maker_fee_series:
        return 0.0
    rate = 0.0175 if maker else 0.07
    return math.ceil(rate * contracts * price * (1 - price) * 100) / 100


class KalshiClient:
    """Async REST client. TODO: rate limiter (1 req / 100 ms), 429/5xx backoff per §4.3."""

    def __init__(self, base_url: str, key: RSAPrivateKey, key_id: str):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.key_id = key_id
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = signed_headers(self.key, self.key_id, method, path)
        return await self._client.request(method, path, headers=headers, **kwargs)

    # TODO: implement endpoints from AGENTS.md §4.4
    #   GET /markets?series_ticker=..., GET /markets/{ticker}, GET /markets/{ticker}/orderbook,
    #   GET /portfolio/balance, /positions, /fills,
    #   POST /portfolio/orders, /orders/batched, /orders/{id}/amend, /orders/{id}/decrease,
    #   DELETE /portfolio/orders/{id}

    async def aclose(self) -> None:
        await self._client.aclose()
