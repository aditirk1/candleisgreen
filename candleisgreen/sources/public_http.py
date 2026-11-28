"""Read-only HTTP for public market data endpoints, with an allowlist of hosts.

Used where a source serves data without an account (Alpaca crypto data, Kraken public data,
the CFTC reporting site). Keys are added only when a caller passes headers. No method here
can write. A host outside the allowlist is refused before any request leaves.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional
from urllib.parse import urlparse

READ_ONLY_HOSTS = frozenset({"data.alpaca.markets", "api.kraken.com", "publicreporting.cftc.gov", "api-fxpractice.oanda.com"})
USER_AGENT = "CandleIsGreen research client admin@example.com"


class HostNotAllowedError(RuntimeError):
    pass


class PublicTransport:
    def __init__(self, timeout: float = 30, retries: int = 3, headers: Optional[dict[str, str]] = None):
        self.timeout, self.retries, self.headers = timeout, retries, dict(headers or {})

    def get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        host = (urlparse(base_url).hostname or "").lower()
        if host not in READ_ONLY_HOSTS:
            raise HostNotAllowedError(f"'{host}' is not an allowed read-only data host")
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{base_url}{path}?{query}" if query else f"{base_url}{path}"
        delay = 1.0
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **self.headers})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except urllib.error.URLError:
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")
