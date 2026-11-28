"""Recording jobs for the asset classes beyond stocks. Read only. Each returns a plain summary.

Run from the command line:
  .venv/bin/python -m candleisgreen.markets.service crypto --workdir var/live
  .venv/bin/python -m candleisgreen.markets.service cot --workdir var/live
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.config import AppConfig, load_config
from ..core.timeutil import utc_now
from .futures import parse_code, parse_settlements, products
from .store import Bar, MarketStore

STORE_FILE = "markets.sqlite"


def record_crypto(store: MarketStore, api, cfg: AppConfig, now: datetime) -> dict:
    """Daily bars for every listed pair, from the day after the last stored bar."""
    from ..sources.alpaca_crypto import to_bars
    out = {}
    for sym in cfg.assets.crypto.symbols:
        have = [s for s in store.symbols("crypto") if s[1] == sym and s[0] == "alpaca_us"]
        start = (have[0][3].date() + timedelta(days=1)) if have and have[0][3] else cfg.assets.crypto.history_start
        rows = api.daily_bars([sym], start).get(sym, [])
        out[sym] = store.add_bars(to_bars(sym, rows, now), now)
    return {"job": "crypto", "stored": out, "at": now.isoformat()}


def record_cot(store: MarketStore, transport, cfg: AppConfig, now: datetime, since: Optional[date] = None) -> dict:
    """Commitments of Traders for each futures product in its matching report, about three years back."""
    from ..sources.cftc import LICENSE, VENDOR, fetch, first_usable_at, report_date
    since = since or (now.date() - timedelta(weeks=cfg.assets.futures.cot_percentile_window_weeks + 4))
    out = {}
    for code, p in products().items():
        rows = fetch(transport, p.cot_dataset, p.cftc_code, since=since)
        n = 0
        for r in rows:
            rep = report_date(r)
            n += store.add_report(p.cot_dataset, p.cftc_code, rep, r, VENDOR, LICENSE, now, first_usable_at(rep, now, cfg.assets.futures))
        out[code] = n
    return {"job": "cot", "stored": out, "at": now.isoformat()}


def load_settlements(store: MarketStore, text: str, now: datetime) -> dict:
    """Your own settlement file. Stored as research-only uploaded data."""
    series = parse_settlements(text)
    n = 0
    for code, rows in series.items():
        # A settlement is published the evening of its trading day, so it counts from the end of that day.
        bars = [Bar("future", "user_upload", code, "1Day", datetime(d.year, d.month, d.day, tzinfo=now.tzinfo), s, s, s, s, None,
                    True, "user_upload", "user_upload", datetime(d.year, d.month, d.day, tzinfo=now.tzinfo) + timedelta(days=1))
                for d, s in rows]
        n += store.add_bars(bars, now)
        parse_code(code)
    return {"contracts": sorted(series), "stored": n}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Record data for crypto and futures positioning. Read only.")
    parser.add_argument("job", choices=["crypto", "cot"])
    parser.add_argument("--workdir", default="var/live")
    args = parser.parse_args(argv)
    cfg = load_config()
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    store = MarketStore(wd / STORE_FILE, shared=False)
    now = utc_now()
    if args.job == "crypto":
        from ..sources.alpaca_crypto import AlpacaCrypto, transport_from_env
        out = record_crypto(store, AlpacaCrypto(transport_from_env(cfg.sources.alpaca), cfg.sources.alpaca, cfg.assets.crypto), cfg, now)
    else:
        from ..sources.public_http import PublicTransport
        out = record_cot(store, PublicTransport(), cfg, now)
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
