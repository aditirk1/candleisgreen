"""Offline stand-in for the Alpaca paper trading API, for tests and demos only.

It mimics the documented paper behavior: a marketable limit order fills at the quote, a
resting one waits. It can lose a response after accepting an order, or fail before
accepting one, so duplicate safety can be tested.
"""
from __future__ import annotations

import itertools
from datetime import datetime
from typing import Any, Optional

from ..sources.alpaca import DuplicateClientOrderError, UncertainResponseError


class FakeAlpacaPaper:
    def __init__(self, now: Optional[datetime] = None):
        self.orders: dict[str, dict] = {}
        self.activities: list[dict] = []
        self.quotes: dict[str, tuple[float, float]] = {}
        self.now = now or datetime(2026, 11, 20, 14, 40)
        self.lose_response_after_accept = 0
        self.fail_before_accept = 0
        self.post_calls = 0
        self.partial_fraction: Optional[float] = None
        self._ids = itertools.count(1)

    def set_quote(self, symbol: str, bid: float, ask: float) -> None:
        self.quotes[symbol] = (bid, ask)

    def get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        if path == "/v2/orders:by_client_order_id":
            order = self.orders.get(params["client_order_id"])
            if order is None:
                raise KeyError("404 order not found")
            return dict(order)
        if path == "/v2/orders":
            return [dict(o) for o in self.orders.values() if o["status"] in ("new", "accepted", "partially_filled")]
        if path == "/v2/positions":
            pos: dict[str, float] = {}
            for a in self.activities:
                q = float(a["qty"]) * (1 if a["side"] == "buy" else -1)
                pos[a["symbol"]] = pos.get(a["symbol"], 0.0) + q
            return [{"symbol": s, "qty": str(q)} for s, q in pos.items() if abs(q) > 1e-9]
        if path == "/v2/account/activities/FILL":
            return [dict(a) for a in self.activities]
        raise KeyError(f"fake paper API has no route {path}")

    def send(self, method: str, base_url: str, path: str, body: Optional[dict] = None) -> Any:
        if method != "POST" or path != "/v2/orders":
            raise KeyError(f"fake paper API has no route {method} {path}")
        self.post_calls += 1
        if self.fail_before_accept:
            self.fail_before_accept -= 1
            raise UncertainResponseError("timeout before the order reached the broker")
        cid = body["client_order_id"]
        if cid in self.orders:
            raise DuplicateClientOrderError("client_order_id must be unique")
        oid = f"order-{next(self._ids)}"
        order = {"id": oid, "client_order_id": cid, "symbol": body["symbol"], "qty": body["qty"], "side": body["side"],
                 "type": body["type"], "limit_price": body["limit_price"], "status": "new", "filled_qty": "0"}
        bid, ask = self.quotes.get(body["symbol"], (None, None))
        limit = float(body["limit_price"])
        price = ask if body["side"] == "buy" else bid
        if price is not None and ((body["side"] == "buy" and limit >= price) or (body["side"] == "sell" and limit <= price)):
            qty = float(body["qty"])
            fill_qty = qty if self.partial_fraction is None else max(1.0, round(qty * self.partial_fraction))
            self.activities.append({"id": f"act-{oid}", "activity_type": "FILL", "order_id": oid, "symbol": body["symbol"],
                                    "side": body["side"], "qty": str(fill_qty), "price": str(price),
                                    "transaction_time": self.now.strftime("%Y-%m-%dT%H:%M:%SZ")})
            order["filled_qty"] = str(fill_qty)
            order["status"] = "filled" if fill_qty >= qty else "partially_filled"
        self.orders[cid] = order
        if self.lose_response_after_accept:
            self.lose_response_after_accept -= 1
            raise UncertainResponseError("connection dropped after the broker accepted the order")
        return dict(order)
