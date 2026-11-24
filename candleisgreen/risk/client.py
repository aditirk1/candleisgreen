"""Client for the risk service. Any failure to reach it blocks the order."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime

from ..core.schemas import OrderIntent, RiskContext, RiskDecision, RiskVerdict


class RiskClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body, default=str).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def evaluate(self, intent: OrderIntent, ctx: RiskContext) -> RiskDecision:
        try:
            out = self._call("POST", "/evaluate", {"intent": intent.model_dump(mode="json"),
                                                   "context": ctx.model_dump(mode="json")})
            return RiskDecision.model_validate(out["decision"])
        except Exception as exc:
            return RiskDecision(client_order_id=intent.client_order_id, verdict=RiskVerdict.BLOCKED,
                                reasons=(f"risk_service: unreachable or invalid response ({type(exc).__name__})",),
                                checks_run=(), limits_hash="unknown", decided_at=ctx.now)

    def health(self) -> dict:
        return self._call("GET", "/health")

    def set_kill_switch(self, engaged: bool, actor: str) -> bool:
        return bool(self._call("POST", "/kill-switch", {"engaged": engaged, "actor": actor})["kill_switch"])

    def evaluate_book(self, weights: dict, clusters: dict, sectors: dict | None = None,
                      sector_cap: float | None = None) -> list[str]:
        try:
            return self._call("POST", "/evaluate-book", {"weights": weights, "clusters": clusters,
                                                         "sectors": sectors, "sector_cap": sector_cap})["reasons"]
        except Exception as exc:
            return [f"risk_service: unreachable ({type(exc).__name__})"]
