"""Broker adapter interface and the guards that keep every route paper-only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from ..core.schemas import BrokerAck, OrderIntent, Quote, RiskDecision, RiskVerdict, Venue

# The only broker hosts an adapter may talk to. Live hosts are never added here.
PAPER_HOSTS = frozenset({"paper-api.alpaca.markets"})


class LiveTradingDisabledError(RuntimeError):
    """Raised by any route that could reach real money. Live trading is not built."""


class RiskApprovalRequiredError(RuntimeError):
    """Raised when an order reaches a broker without a matching risk approval."""


def assert_paper_endpoint(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in PAPER_HOSTS:
        raise LiveTradingDisabledError(f"endpoint host '{host}' is not a paper trading host")


def assert_approved(intent: OrderIntent, decision: RiskDecision) -> None:
    if decision.client_order_id != intent.client_order_id:
        raise RiskApprovalRequiredError("risk decision is for a different order")
    if decision.verdict is not RiskVerdict.APPROVED:
        raise RiskApprovalRequiredError("order was blocked by the risk service")


class BrokerAdapter(ABC):
    """One interface, paper implementations only."""

    venue: Venue

    @abstractmethod
    def submit(self, intent: OrderIntent, decision: RiskDecision, quote: Quote) -> BrokerAck: ...

    @abstractmethod
    def open_orders(self) -> tuple[str, ...]: ...

    @abstractmethod
    def positions(self) -> dict[str, float]: ...


class LiveBroker(BrokerAdapter):
    """Placeholder that exists only to prove every live route rejects orders."""

    venue = None  # type: ignore[assignment]

    def submit(self, intent, decision, quote):
        raise LiveTradingDisabledError("live trading is not built in this project")

    def open_orders(self):
        raise LiveTradingDisabledError("live trading is not built in this project")

    def positions(self):
        raise LiveTradingDisabledError("live trading is not built in this project")
