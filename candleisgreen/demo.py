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
    # The synthetic market lists every active name as shortable and easy to borrow, like the fake Alpaca assets.
    return FixedQuotes(out, shortable=frozenset(out))


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
    # Real public SEC data for one issuer, from the recorded fixture, for the Earnings screen.
    from .sources import sec

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sec"
    if fixtures.exists():
        sec.ingest_issuer(sec.SecClient(sec.FixtureSecTransport(fixtures), cfg.sources.sec), "320193", "AAPL",
                          store, master, rec2, cfg)
    # Phase 3: published factors through the evidence pipeline, then Composite v0.
    from .composite.v0 import build as build_v0
    from .research.academic import load_osap
    from .research.published import run_published_factor
    from .research.registry import ResearchRegistry

    osap = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "osap"
    research = ResearchRegistry(workdir / "research.sqlite", audit)
    if osap.exists():
        ls, claims = load_osap(osap / "PredictorLSretWide_subset.parquet", osap / "SignalDoc_subset.csv")
        for name, sid, note in (("Mom12m", "xs_momentum_12_1", ""), ("STreversal", "st_reversal_5", ""),
                                ("BetaFP", "betting_against_beta",
                                 "Chosen as the expected failure because the dataset rates its reconstruction 3_distant. "
                                 "The reproduction table was viewed before choosing, so this is not a blind pre-registration.")):
            run_published_factor(claims[name], ls[name], sid, research, cfg, rec2, f"osap {cfg.research.osap_release}", note)
    # Phase 5: one Hypothesis Factory day, a model comparison and a pending promotion request.
    from .research import factory
    from .research.champion import compare
    from .models import supervised
    from .composite.v0 import _matrix
    import numpy as np

    lib = factory.Library({"xs_momentum_12_1": "cross sectional momentum past twelve month return skipping the most recent month",
                           "st_reversal_5": "short term reversal previous week return"},
                          {c["signal_id"]: c["claim_id"] for c in research.claims() if c.get("signal_id")})
    factory.run_daily([
        {"title": "Momentum crashes after market rebounds", "stance": "contradicts", "about_signal": "xs_momentum_12_1",
         "definition": "momentum suffers large losses after market rebounds"},
        {"title": "Analyst forecast dispersion predicts returns", "data_required": ["analyst estimates"]},
        {"title": "Seasonal returns in industry portfolios", "study_type": "reproduction"},
    ], research, lib, {"osap"}, cfg, rec2)
    ids, days, prices, volume, vendors = _matrix(store, master, rec2, d2)
    X, y, _ = supervised.panel(prices)
    preds = {k: supervised.walk_forward(X, y, make, feats, 300, 21, 21) for k, (make, feats) in supervised.MODELS.items()}
    mask = np.isfinite(y) & np.all([np.isfinite(p) for p in preds.values()], axis=0)
    def platform_claim(title):
        return research.add_claim({"source_type": "platform", "title": title, "market": "US equities",
                                   "target": "21-day residual return", "definition": "walk-forward model comparison"}, rec2)

    compare(research, platform_claim("Level B ridge challenges the Level A momentum regression"), supervised.LEVEL_A, supervised.LEVEL_B, y[mask], preds[supervised.LEVEL_A][mask],
            preds[supervised.LEVEL_B][mask], True, 21, cfg, rec2, ("SYNTHETIC",))
    compare(research, platform_claim("Level C boosted trees challenge Level B ridge"), supervised.LEVEL_B, supervised.LEVEL_C, y[mask], preds[supervised.LEVEL_B][mask],
            preds[supervised.LEVEL_C][mask], False, 21, cfg, rec2, ("SYNTHETIC",))
    research.propose_promotion("st_reversal_5", 5, {"note": "demo request, synthetic shadow record"}, rec2)
    build_v0(store, master, research, cfg, d2, rec2)
    # Phase 4: real government RSS items from the recorded fixtures.
    from .sources.rss import NewsStore, ingest

    rss_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "rss"
    news = NewsStore(workdir / "news.sqlite")
    for feed, fname in (("sec_press", "sec_press"), ("sec_litigation", "sec_lit"), ("fed_press", "fed_press")):
        if (rss_dir / f"{fname}.xml").exists():
            ingest(next(f for f in cfg.news.feeds if f.name == feed), (rss_dir / f"{fname}.xml").read_bytes(), news,
                   datetime(2026, 11, 24, 6, 0, tzinfo=UTC), cfg)
    news.close()
    research.close()
    store.close()  # the scheduled jobs open the price database themselves
    # Phase 6: one round of the follow-the-sun research jobs (FX, macro and global factors).
    from .scheduler import run_slot

    for slot, when in (("asia_pacific", datetime(2026, 11, 20, 8, 0, tzinfo=UTC)), ("europe", datetime(2026, 11, 20, 17, 0, tzinfo=UTC))):
        run_slot(slot, when, workdir, cfg, True)
    write_heartbeat(workdir, "record", "ok", rec2, {"sessions": [d2.isoformat()], "synthetic": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="var/demo")
    build(Path(parser.parse_args().workdir))
    print("demo built (synthetic data)")
