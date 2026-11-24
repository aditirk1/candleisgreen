"""Shared Phase 1 environment: synthetic market, journal and a real risk-service process."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from candleisgreen.broker.simulator import InternalSimulator
from candleisgreen.core.audit import AuditLog
from candleisgreen.core.config import AppConfig, load_config
from candleisgreen.core.schemas import Quote
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.journal import Journal
from candleisgreen.risk.client import RiskClient
from candleisgreen.sources import recorder
from candleisgreen.sources.alpaca import AlpacaData
from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport, FakeMarket
from candleisgreen.trading import FixedQuotes

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
DECISION_DATE = date(2026, 11, 19)
SESSION_DATE = date(2026, 11, 20)
RECORD_NOW = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)  # 16:20 ET
DECIDE_NOW = datetime(2026, 11, 19, 21, 31, tzinfo=UTC)  # 16:31 ET
EXEC_NOW = datetime(2026, 11, 20, 14, 40, tzinfo=UTC)  # 09:40 ET


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def risk_service(state_dir: Path):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "candleisgreen.risk.service", "--port", str(port),
                             "--state-dir", str(state_dir)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    client = RiskClient(f"http://127.0.0.1:{port}")
    try:
        for _ in range(100):
            try:
                client.health()
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("risk service did not start")
        yield client, proc
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@dataclass
class Env:
    cfg: AppConfig
    store: PointInTimeStore
    master: InstrumentMaster
    journal: Journal
    audit: AuditLog


def build_env(tmp: Path, mode: str) -> Env:
    base = load_config()
    cfg = base.model_copy(update={"execution": base.execution.model_copy(update={"mode": mode})})
    store = PointInTimeStore(tmp / "pit.duckdb")
    master = InstrumentMaster(store.connection)
    data = AlpacaData(FakeAlpacaTransport(now=RECORD_NOW), cfg.sources.alpaca)
    recorder.backfill(date(2025, 6, 2), DECISION_DATE - timedelta(days=1), data, store, master, RECORD_NOW, cfg)
    recorder.record_session(DECISION_DATE, data, store, master, RECORD_NOW, cfg)
    audit = AuditLog(tmp / "audit.sqlite")
    journal = Journal(tmp / "journal.sqlite", audit, cfg.execution.simulator_starting_equity_usd,
                      f"config:{cfg.config_version}:{cfg.config_hash}")
    return Env(cfg, store, master, journal, audit)


def quotes_for(env: Env, now: datetime, age_seconds: float = 2.0, feed: str = "iex_realtime") -> FixedQuotes:
    """Fresh quotes around each name's last synthetic close."""
    market = FakeMarket()
    out = {}
    for inst in env.master.instruments():
        iid = inst["instrument_id"]
        closes = env.store.as_of(now).series(iid, "close")
        if not closes:
            continue
        mid = closes[-1].value
        for symbol in env.master.symbols(iid):
            out[symbol] = Quote(asset_id=iid, bid=round(mid * 0.9995, 4), ask=round(mid * 1.0005, 4),
                                quote_time=now - timedelta(seconds=age_seconds), feed=feed, bid_size=100, ask_size=100)
    return FixedQuotes(out)


def simulator(env: Env) -> InternalSimulator:
    return InternalSimulator(env.cfg.execution.simulator_starting_equity_usd)
