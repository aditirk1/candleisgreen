"""Internal simulator. Deterministic limit-order fills at the quoted touch.

A buy fills at the ask when its limit is at or above the ask, and a sell fills at the bid
when its limit is at or below the bid. Otherwise the order rests unfilled. There is no
market impact in these fills, so the cost model is applied on top of them in P&L views.
"""
from __future__ import annotations

from ..core.schemas import BrokerAck, Fill, OrderIntent, Quote, RiskDecision, Side, Venue
from .base import BrokerAdapter, LiveTradingDisabledError, assert_approved


class InternalSimulator(BrokerAdapter):
    venue = Venue.SIMULATION

    def __init__(self, starting_cash: float, positions: dict[str, float] | None = None):
        self.cash = float(starting_cash)
        self._positions: dict[str, float] = dict(positions or {})
        self._acks: dict[str, BrokerAck] = {}

    def submit(self, intent: OrderIntent, decision: RiskDecision, quote: Quote) -> BrokerAck:
        if intent.venue is not Venue.SIMULATION:
            raise LiveTradingDisabledError("the simulator only accepts SIMULATION orders")
        assert_approved(intent, decision)
        known = self._acks.get(intent.client_order_id)
        if known is not None:  # a retry with the same client ID is never executed twice
            return known
        if quote.asset_id != intent.asset_id:
            raise ValueError("quote is for a different instrument")
        price = quote.ask if intent.side is Side.BUY else quote.bid
        sign = 1 if intent.side is Side.BUY else -1
        marketable = intent.limit_price >= price if sign > 0 else intent.limit_price <= price
        if not marketable:
            ack = BrokerAck(client_order_id=intent.client_order_id, status="accepted", venue=Venue.SIMULATION,
                            message="limit not marketable, order rests unfilled")
            self._acks[intent.client_order_id] = ack
            return ack
        fill = Fill(
            client_order_id=intent.client_order_id,
            asset_id=intent.asset_id,
            side=intent.side,
            quantity=intent.quantity,
            price=price,
            venue=Venue.SIMULATION,
            filled_at=decision.decided_at,
            fill_seq=0,
            arrival_mid=quote.mid,
        )
        self.cash -= sign * intent.quantity * price
        self._positions[intent.asset_id] = self._positions.get(intent.asset_id, 0.0) + sign * intent.quantity
        ack = BrokerAck(
            client_order_id=intent.client_order_id, status="filled", venue=Venue.SIMULATION, fills=(fill,)
        )
        self._acks[intent.client_order_id] = ack
        return ack

    def open_orders(self) -> tuple[str, ...]:
        return ()

    def positions(self) -> dict[str, float]:
        return dict(self._positions)
