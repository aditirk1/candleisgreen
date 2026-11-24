"""Offline demo on the synthetic market. Every number it shows is synthetic.

    python -m candleisgreen.demo --workdir var/demo

Builds two days. On the first, three proposals are approved and filled in the simulator and
the rest are rejected. The second day re-proposes the rejected names, and those wait in the
approval queue for the Execution screen.
"""
from __future__ import annotations

import argparse
import shutil
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .broker.simulator import InternalSimulator
from .core.audit import AuditLog
from .core.config import load_config
from .core.schemas import Quote
from .data.instruments import InstrumentMaster
from .data.pit_store import PointInTimeStore
from .jobs import write_heartbeat
from .journal import Journal
from .risk.client import RiskClient
from .risk.service import serve
from .sources import recorder
from .sources.alpaca import AlpacaData
from .sources.alpaca_fake import FakeAlpacaTransport
from .trading import FixedQuotes, execute_session, run_decision

UTC = timezone.utc


def _quotes(store, master, now):
    out = {}
    for inst in master.instruments():
        closes = store.as_of(now).series(inst["instrument_id"], "close")
        if closes:
            mid = closes[-1].value
            for sym in master.symbols(inst["instrument_id"]):
                out[sym] = Quote(asset_id=inst["instrument_id"], bid=round(mid * 0.9995, 4), ask=round(mid * 1.0005, 4),
                                 quote_time=now - timedelta(seconds=2), feed="fixture_realtime", bid_size=100, ask_size=100)
    return FixedQuotes(out)


def build(workdir: Path) -> None:
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    base = load_config()
    cfg = base.model_copy(update={"execution": base.execution.model_copy(update={"mode": "manual_simulation"})})
    store = PointInTimeStore(workdir / "pit.duckdb")
    master = InstrumentMaster(store.connection)
    audit = AuditLog(workdir / "audit.sqlite")
    journal = Journal(workdir / "journal.sqlite", audit, cfg.execution.simulator_starting_equity_usd,
                      f"config:{cfg.config_version}:{cfg.config_hash}")
    d1, s1, d2, s2 = date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 19), date(2026, 11, 20)
    rec1 = datetime(2026, 11, 18, 21, 20, tzinfo=UTC)
    data = AlpacaData(FakeAlpacaTransport(now=rec1), cfg.sources.alpaca)
    recorder.backfill(date(2025, 6, 2), d1 - timedelta(days=1), data, store, master, rec1, cfg)
    recorder.record_session(d1, data, store, master, rec1, cfg)
    run_decision(d1, s1, store, master, journal, cfg, datetime(2026, 11, 18, 21, 31, tzinfo=UTC))
    server = serve(0, workdir / "risk_demo", cfg)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    risk = RiskClient(f"http://127.0.0.1:{server.server_address[1]}")
    exec1 = datetime(2026, 11, 19, 14, 40, tzinfo=UTC)
    for i, p in enumerate(journal.proposals(s1, "proposed")):
        if i < 3:
            journal.approve(p.proposal_id, "user:aditi", exec1)
        else:
            journal.reject(p.proposal_id, "user:aditi", exec1, "demo: held back on day one")
    execute_session(s1, exec1, journal, _quotes(store, master, exec1), risk,
                    InternalSimulator(journal.cash(), journal.positions()), store, master, cfg)
    server.shutdown()
    rec2 = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    recorder.record_session(d2, AlpacaData(FakeAlpacaTransport(now=rec2), cfg.sources.alpaca), store, master, rec2, cfg)
    run_decision(d2, s2, store, master, journal, cfg, datetime(2026, 11, 19, 21, 31, tzinfo=UTC))
    write_heartbeat(workdir, "record", "ok", rec2, {"sessions": [d2.isoformat()], "synthetic": True})
    store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="var/demo")
    build(Path(parser.parse_args().workdir))
    print("demo built (synthetic data)")
