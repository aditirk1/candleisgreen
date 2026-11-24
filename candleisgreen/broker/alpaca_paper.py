"""Alpaca paper trading adapter. Paper host only, limit orders only.

Duplicate safety: every order carries the stable client order ID from the intent. Before
submitting, the adapter asks the broker whether that ID already exists. After an uncertain
response it queries again before any retry, and it never resubmits blind. Order and
position shapes follow Alpaca's documentation and have not been checked against a live
response (DECISIONS D-033).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from ..core.config import AlpacaSourceConfig
from ..core.schemas import BrokerAck, Fill, OrderIntent, Quote, RiskDecision, Side, Venue
from ..core.timeutil import ensure_utc
from ..sources.alpaca import (BrokerRejectedError, DuplicateClientOrderError, UncertainResponseError)
from .base import BrokerAdapter, LiveTradingDisabledError, assert_approved, assert_paper_endpoint

STATUS_MAP = {
    "new": "accepted", "accepted": "accepted", "pending_new": "accepted", "accepted_for_bidding": "accepted",
    "partially_filled": "partially_filled", "filled": "filled",
    "canceled": "rejected", "expired": "rejected", "rejected": "rejected", "done_for_day": "rejected",
}


class AlpacaPaperBroker(BrokerAdapter):
    venue = Venue.PAPER

    def __init__(self, transport: Any, cfg: AlpacaSourceConfig, symbol_for: Callable[[str], Optional[str]],
                 instrument_for: Callable[[str], Optional[str]]):
        assert_paper_endpoint(cfg.trading_base_url + "/")
        self.t = transport
        self.base = cfg.trading_base_url
        self.symbol_for = symbol_for
        self.instrument_for = instrument_for

    # Queries -------------------------------------------------------------------------------

    def find_order(self, client_order_id: str) -> Optional[dict]:
        try:
            return self.t.get(self.base, "/v2/orders:by_client_order_id", {"client_order_id": client_order_id})
        except Exception as exc:
            if "404" in str(exc) or isinstance(exc, KeyError):
                return None
            raise

    def open_orders(self) -> tuple[str, ...]:
        return tuple(o["client_order_id"] for o in self.t.get(self.base, "/v2/orders", {"status": "open"}))

    def positions(self) -> dict[str, float]:
        out = {}
        for p in self.t.get(self.base, "/v2/positions", {}):
            iid = self.instrument_for(p["symbol"])
            out[iid or f"unmapped:{p['symbol']}"] = float(p["qty"])
        return out

    def fills_for(self, order: dict, intent: OrderIntent, quote: Quote) -> tuple[Fill, ...]:
        acts = self.t.get(self.base, "/v2/account/activities/FILL", {"direction": "asc"})
        mine = [a for a in acts if a.get("order_id") == order["id"]]
        return tuple(Fill(
            client_order_id=intent.client_order_id, asset_id=intent.asset_id, side=Side(a["side"]),
            quantity=float(a["qty"]), price=float(a["price"]), venue=Venue.PAPER,
            filled_at=ensure_utc(datetime.fromisoformat(a["transaction_time"].replace("Z", "+00:00"))),
            fill_seq=i, arrival_mid=quote.mid) for i, a in enumerate(mine))

    def _ack(self, order: dict, intent: OrderIntent, quote: Quote, note: str = "") -> BrokerAck:
        status = STATUS_MAP.get(order.get("status", ""), "unknown")
        return BrokerAck(client_order_id=intent.client_order_id, status=status, venue=Venue.PAPER,
                         fills=self.fills_for(order, intent, quote), message=note or f"broker status {order.get('status')}")

    # Submission ----------------------------------------------------------------------------

    def submit(self, intent: OrderIntent, decision: RiskDecision, quote: Quote) -> BrokerAck:
        if intent.venue is not Venue.PAPER:
            raise LiveTradingDisabledError("the Alpaca paper adapter only accepts PAPER orders")
        assert_approved(intent, decision)
        symbol = self.symbol_for(intent.asset_id)
        if not symbol:
            return BrokerAck(client_order_id=intent.client_order_id, status="rejected", venue=Venue.PAPER,
                             message="no symbol for this instrument")
        existing = self.find_order(intent.client_order_id)
        if existing:
            return self._ack(existing, intent, quote, "order already at the broker, not resubmitted")
        body = {"symbol": symbol, "qty": str(int(intent.quantity)) if float(intent.quantity).is_integer() else str(intent.quantity),
                "side": intent.side.value, "type": "limit", "time_in_force": "day",
                "limit_price": f"{intent.limit_price:.2f}", "client_order_id": intent.client_order_id}
        for attempt in range(2):
            try:
                return self._ack(self.t.send("POST", self.base, "/v2/orders", body), intent, quote)
            except DuplicateClientOrderError:
                found = self.find_order(intent.client_order_id)
                if found:
                    return self._ack(found, intent, quote, "broker reported a duplicate, existing order used")
                return BrokerAck(client_order_id=intent.client_order_id, status="unknown", venue=Venue.PAPER,
                                 message="broker reported a duplicate but the order could not be found")
            except UncertainResponseError:
                found = self.find_order(intent.client_order_id)  # query before any retry
                if found:
                    return self._ack(found, intent, quote, "response was lost, order found at the broker")
                if attempt == 1:
                    return BrokerAck(client_order_id=intent.client_order_id, status="unknown", venue=Venue.PAPER,
                                     message="broker response uncertain twice, order state unknown")
            except BrokerRejectedError as exc:
                return BrokerAck(client_order_id=intent.client_order_id, status="rejected", venue=Venue.PAPER,
                                 message=str(exc)[:300])
        raise RuntimeError("unreachable")
